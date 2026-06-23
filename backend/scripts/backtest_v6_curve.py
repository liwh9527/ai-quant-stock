#!/usr/bin/env python3
"""
策略回测 v6 - 含曲线图生成
MA20突破 + 移动止盈 + ATR止损 + MA20斜率过滤
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime

TUSHARE_TOKEN = "29479ac41a3b85cd62b519f1d32a14e343ea99b6def6ce61a646395d"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

def get_stock_data(code, start_date, end_date):
    ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df.empty:
        return pd.DataFrame()
    return df.sort_values('trade_date').reset_index(drop=True)

def calculate_ma(prices, period=20):
    return prices.rolling(window=period).mean()

def calculate_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def backtest_v6(stock_df, initial_capital=100000):
    """v6策略回测：MA20突破 + 移动止盈 + ATR止损 + MA20斜率过滤"""
    if stock_df.empty:
        return {}

    df = stock_df.copy()
    df['ma20'] = calculate_ma(df['close'], 20)
    df['atr'] = calculate_atr(df['high'], df['low'], df['close'], 14)
    df['avg_vol'] = df['vol'].rolling(window=5).mean()

    # 计算MA20斜率 (5日前到当前的MA20变化率)
    df['ma20_5ago'] = df['ma20'].shift(5)
    df['ma20_slope'] = (df['ma20'] - df['ma20_5ago']) / df['ma20_5ago'] * 100

    trades = []
    equity_curve = []
    position = None
    capital = initial_capital
    max_profit = 0
    shares = 0

    for i in range(25, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]

        if pd.isna(row['ma20']) or pd.isna(row['atr']) or pd.isna(row['ma20_slope']):
            equity_curve.append({'date': row['trade_date'], 'equity': capital})
            continue

        current_value = capital
        if position:
            current_value = capital + shares * row['close']

        equity_curve.append({'date': row['trade_date'], 'equity': round(current_value, 2)})

        # 买入逻辑
        if position is None:
            deviation = abs(row['close'] - row['ma20']) / row['ma20']
            volume_ok = row['vol'] > row['avg_vol'] * 1.5 if not pd.isna(row['avg_vol']) else False
            atr_ok = row['atr'] / row['close'] > 0.02
            above_ma20 = row['close'] >= row['ma20']  # 站上MA20即可
            slope_ok = row['ma20_slope'] > 0  # MA20斜率过滤

            if deviation < 0.10 and volume_ok and atr_ok and above_ma20 and slope_ok:
                shares = int(capital * 0.25 / row['close'] / 100) * 100
                if shares > 0:
                    buy_amount = shares * row['close']
                    capital -= buy_amount
                    position = {
                        'buy_price': row['close'],
                        'buy_date': row['trade_date'],
                        'stop_loss': row['close'] - 2 * row['atr'],
                        'atr_at_buy': row['atr'],
                    }
                    trades.append({
                        'type': 'buy', 'date': row['trade_date'],
                        'price': row['close'], 'shares': shares,
                        'reason': f'MA20突破 (斜率{row["ma20_slope"]:+.1f}%)'
                    })
                    max_profit = 0

        # 卖出逻辑
        else:
            profit_pct = (row['close'] - position['buy_price']) / position['buy_price']
            max_profit = max(max_profit, profit_pct)
            sell_reason = None

            # ATR止损
            if row['close'] <= position['stop_loss']:
                sell_reason = f'ATR止损 ({profit_pct:.1%})'
            # 移动止盈
            elif max_profit >= 0.15:
                if profit_pct <= max_profit - 0.05:
                    sell_reason = f'移动止盈 (最高{max_profit:.1%})'
            # 跌破MA20
            elif row['close'] < row['ma20'] * 0.98:
                sell_reason = f'跌破MA20 ({profit_pct:.1%})'

            if sell_reason:
                sell_amount = shares * row['close']
                capital += sell_amount
                trades.append({
                    'type': 'sell', 'date': row['trade_date'],
                    'price': row['close'], 'shares': shares,
                    'profit_pct': profit_pct,
                    'profit_amount': sell_amount - shares * position['buy_price'],
                    'reason': sell_reason
                })
                position = None
                shares = 0

    # 最终权益
    if position and len(df) > 0:
        last = df.iloc[-1]
        capital += shares * last['close']

    sell_trades = [t for t in trades if t['type'] == 'sell']
    win_trades = [t for t in sell_trades if t.get('profit_amount', 0) > 0]
    lose_trades = [t for t in sell_trades if t.get('profit_amount', 0) <= 0]

    return {
        'trades': trades,
        'equity_curve': equity_curve,
        'total_trades': len(sell_trades),
        'win_trades': len(win_trades),
        'lose_trades': len(lose_trades),
        'win_rate': len(win_trades) / max(len(sell_trades), 1),
        'total_profit': sum(t.get('profit_amount', 0) for t in sell_trades),
        'final_equity': capital,
    }


def generate_html(all_results, index_curve, stock_data):
    """生成回测报告HTML"""

    # 合并所有股票的权益曲线为组合权益
    # 找到共同日期范围
    all_dates = set()
    for name, r in all_results.items():
        for p in r.get('equity_curve', []):
            all_dates.add(p['date'])
    all_dates = sorted(all_dates)

    # 组合权益 = 各股票等权分配
    portfolio_equity = []
    for date in all_dates:
        total = 0
        count = 0
        for name, r in all_results.items():
            ec = {p['date']: p['equity'] for p in r.get('equity_curve', [])}
            if date in ec:
                # 每只股票初始10万，组合按比例
                total += ec[date]
                count += 1
        if count > 0:
            # 等权：每只分配1/6的资金
            portfolio_equity.append({'date': date, 'equity': round(total / len(all_results), 2)})

    # 上证指数归一化
    index_norm = []
    if not index_curve.empty:
        base = index_curve.iloc[0]['close']
        for _, row in index_curve.iterrows():
            index_norm.append({'date': row['trade_date'], 'value': round(row['close'] / base * 100000, 2)})

    dates = [p['date'] for p in portfolio_equity]
    portfolio_vals = [p['equity'] for p in portfolio_equity]
    index_vals = [p['value'] for p in index_norm] if index_norm else []

    # 各股票权益
    stock_series = []
    for name, r in all_results.items():
        ec = {p['date']: p['equity'] for p in r.get('equity_curve', [])}
        vals = [ec.get(d, None) for d in dates]
        stock_series.append({'name': name, 'data': vals})

    # 交易统计
    stats_html = ""
    total_profit = 0
    total_trades = 0
    total_win = 0
    for name, r in all_results.items():
        total_profit += r.get('total_profit', 0)
        total_trades += r.get('total_trades', 0)
        total_win += r.get('win_trades', 0)
        wr = r.get('win_rate', 0) * 100
        tp = r.get('total_profit', 0)
        emoji = "🟢" if tp > 0 else "🔴"
        stats_html += f"""
        <tr>
            <td style="padding:8px 12px;">{name}</td>
            <td style="padding:8px 12px;text-align:center;">{r.get('total_trades', 0)}</td>
            <td style="padding:8px 12px;text-align:center;">{r.get('win_trades', 0)}</td>
            <td style="padding:8px 12px;text-align:center;">{r.get('lose_trades', 0)}</td>
            <td style="padding:8px 12px;text-align:center;">{wr:.1f}%</td>
            <td style="padding:8px 12px;text-align:right;">{emoji} {tp:+,.0f}</td>
        </tr>"""

    overall_wr = total_win / max(total_trades, 1) * 100
    overall_emoji = "🟢" if total_profit > 0 else "🔴"

    # 交易明细
    trade_details = ""
    for name, r in all_results.items():
        for t in r.get('trades', []):
            emoji = ""
            detail = ""
            if t['type'] == 'buy':
                emoji = "🟢"
                detail = f"买入 {t['price']:.2f} × {t['shares']}股"
            else:
                pe = t.get('profit_pct', 0)
                emoji = "🟢" if pe > 0 else "🔴"
                detail = f"卖出 {t['price']:.2f} {emoji}{pe:+.1%}"
            trade_details += f"""
            <tr>
                <td style="padding:4px 8px;">{t['date']}</td>
                <td style="padding:4px 8px;">{name}</td>
                <td style="padding:4px 8px;">{emoji} {'买入' if t['type']=='buy' else '卖出'}</td>
                <td style="padding:4px 8px;text-align:right;">{t['price']:.2f}</td>
                <td style="padding:4px 8px;">{t.get('reason', '')}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>策略回测报告 v6</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
body {{ font-family: -apple-system, 'PingFang SC', sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }}
.card {{ background: #16213e; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
h1 {{ text-align: center; color: #00d4ff; margin-bottom: 8px; }}
h2 {{ color: #00d4ff; margin-top: 0; }}
.subtitle {{ text-align: center; color: #888; margin-bottom: 24px; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #0f3460; padding: 10px 12px; text-align: left; color: #00d4ff; }}
td {{ border-bottom: 1px solid #1a1a3e; }}
.summary {{ display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; margin: 20px 0; }}
.summary-item {{ background: #0f3460; border-radius: 10px; padding: 16px 28px; text-align: center; }}
.summary-item .label {{ color: #888; font-size: 13px; }}
.summary-item .value {{ font-size: 28px; font-weight: bold; color: #00d4ff; }}
.summary-item .value.positive {{ color: #00e676; }}
.summary-item .value.negative {{ color: #ff5252; }}
</style></head><body>
<h1>📊 智能量化策略回测报告 v6</h1>
<p class="subtitle">MA20突破 + 移动止盈 + ATR止损 + MA20斜率过滤 | 回测期间: 2025-01-01 ~ 2026-06-09</p>

<div class="summary">
    <div class="summary-item">
        <div class="label">总交易次数</div>
        <div class="value">{total_trades}</div>
    </div>
    <div class="summary-item">
        <div class="label">整体胜率</div>
        <div class="value">{overall_wr:.1f}%</div>
    </div>
    <div class="summary-item">
        <div class="label">总盈亏</div>
        <div class="value {'positive' if total_profit > 0 else 'negative'}">{overall_emoji} {total_profit:+,.0f}</div>
    </div>
    <div class="summary-item">
        <div class="label">组合终值(10万起)</div>
        <div class="value {'positive' if portfolio_vals[-1] > 100000 else 'negative'}">{portfolio_vals[-1]:,.0f}</div>
    </div>
</div>

<div class="card">
    <h2>📈 组合权益曲线 vs 上证指数</h2>
    <div id="mainChart" style="height:420px;"></div>
</div>

<div class="card">
    <h2>📊 各股票权益曲线</h2>
    <div id="stockChart" style="height:380px;"></div>
</div>

<div class="card">
    <h2>📋 各股票回测统计</h2>
    <table>
        <tr><th>股票</th><th>交易次数</th><th>盈利次数</th><th>亏损次数</th><th>胜率</th><th>总盈亏</th></tr>
        {stats_html}
    </table>
</div>

<div class="card">
    <h2>📝 交易明细</h2>
    <table>
        <tr><th>日期</th><th>股票</th><th>方向</th><th>价格</th><th>原因</th></tr>
        {trade_details}
    </table>
</div>

<script>
// 主图：组合 vs 指数
var chart1 = echarts.init(document.getElementById('mainChart'));
chart1.setOption({{
    backgroundColor: 'transparent',
    tooltip: {{ trigger: 'axis' }},
    legend: {{ data: ['组合权益', '上证指数(归一化)'], textStyle: {{ color: '#aaa' }} }},
    grid: {{ left: 60, right: 30, top: 40, bottom: 40 }},
    xAxis: {{ type: 'category', data: {json.dumps(dates)}, axisLabel: {{ color: '#888', rotate: 45, fontSize: 10 }} }},
    yAxis: [
        {{ type: 'value', name: '组合权益', axisLabel: {{ color: '#888' }}, nameTextStyle: {{ color: '#888' }} }},
        {{ type: 'value', name: '指数(归一化)', axisLabel: {{ color: '#888' }}, nameTextStyle: {{ color: '#888' }} }}
    ],
    series: [
        {{
            name: '组合权益', type: 'line', data: {json.dumps(portfolio_vals)},
            lineStyle: {{ color: '#00d4ff', width: 2 }},
            itemStyle: {{ color: '#00d4ff' }},
            areaStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                {{ offset: 0, color: 'rgba(0,212,255,0.3)' }},
                {{ offset: 1, color: 'rgba(0,212,255,0.02)' }}
            ]) }},
            showSymbol: false,
        }},
        {{
            name: '上证指数(归一化)', type: 'line', yAxisIndex: 1, data: {json.dumps(index_vals)},
            lineStyle: {{ color: '#ff9800', width: 1.5, type: 'dashed' }},
            itemStyle: {{ color: '#ff9800' }},
            showSymbol: false,
        }}
    ]
}});

// 各股票图
var chart2 = echarts.init(document.getElementById('stockChart'));
var colors = ['#00d4ff', '#00e676', '#ff5252', '#ffeb3b', '#e040fb', '#ff6d00'];
var stockSeries = {json.dumps(stock_series)};
chart2.setOption({{
    backgroundColor: 'transparent',
    tooltip: {{ trigger: 'axis' }},
    legend: {{ data: stockSeries.map(s => s.name), textStyle: {{ color: '#aaa' }} }},
    grid: {{ left: 60, right: 30, top: 40, bottom: 40 }},
    xAxis: {{ type: 'category', data: {json.dumps(dates)}, axisLabel: {{ color: '#888', rotate: 45, fontSize: 10 }} }},
    yAxis: {{ type: 'value', axisLabel: {{ color: '#888' }} }},
    series: stockSeries.map((s, i) => ({{
        name: s.name, type: 'line', data: s.data,
        lineStyle: {{ color: colors[i % colors.length], width: 1.5 }},
        itemStyle: {{ color: colors[i % colors.length] }},
        showSymbol: false,
    }}))
}});

window.addEventListener('resize', () => {{ chart1.resize(); chart2.resize(); }});
</script>
</body></html>"""

    out_path = "/usr/share/nginx/html/public/backtest_v6_report.html"
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ 报告已生成: {out_path}")
    return out_path


def run():
    start_date = '20250101'
    end_date = '20260609'

    stocks = [
        {'code': '600584', 'name': '长电科技'},
        {'code': '601138', 'name': '工业富联'},
        {'code': '002185', 'name': '华天科技'},
        {'code': '002049', 'name': '紫光国微'},
        {'code': '600487', 'name': '亨通光电'},
        {'code': '002916', 'name': '深南电路'},
    ]

    print("获取数据中...")
    stock_data = {}
    for s in stocks:
        df = get_stock_data(s['code'], start_date, end_date)
        if not df.empty:
            stock_data[s['name']] = df
            print(f"  ✅ {s['name']}: {len(df)} 条")

    # 上证指数
    print("获取上证指数...")
    index_df = pro.index_daily(ts_code='000001.SH', start_date=start_date, end_date=end_date)
    index_df = index_df.sort_values('trade_date').reset_index(drop=True) if not index_df.empty else pd.DataFrame()
    print(f"  ✅ 上证指数: {len(index_df)} 条")

    print("\n回测中...")
    all_results = {}
    for name, df in stock_data.items():
        result = backtest_v6(df)
        all_results[name] = result
        wr = result.get('win_rate', 0) * 100
        tp = result.get('total_profit', 0)
        emoji = "🟢" if tp > 0 else "🔴"
        print(f"  {name}: {result.get('total_trades',0)}笔 胜率{wr:.1f}% {emoji}{tp:+,.0f}")

    generate_html(all_results, index_df, stock_data)


if __name__ == "__main__":
    run()
