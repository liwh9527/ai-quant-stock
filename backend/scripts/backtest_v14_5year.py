#!/usr/bin/env python3
"""v14策略5年回测（使用数据库数据）

时间范围：2021-01-01 ~ 2026-06-14
数据源：本地SQLite数据库
"""

import sys
import os
import json
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# 添加backend路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# v14策略配置
CONFIG = {
    'initial_cash': 1_000_000,
    'max_positions': 4,
    'position_pct_high': 0.25,
    'position_pct_low': 0.18,
    'target_volatility': 0.15,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'cooldown_days': 3,
    'ma_period': 20,
    'atr_period': 14,
    'volume_ratio': 1.2,
    'atr_threshold': 0.02,
    'max_deviation': 0.10,
    'take_profit_pct': 0.40,
    'trailing_stop_pct': 0.08,
    'atr_stop_multiplier': 1.5,
    'chandelier_atr_mult': 3,
    'top_n_sectors': 3,
    'sector_lookback': 20,
    'portfolio_drawdown_stop': 0.07,
    'adx_threshold': 15,
    'max_per_sector': 1,
    'circuit_breaker_days': 3,
    'blacklist_days': 30,
}

# 股票池
STOCK_POOL = [
    {'code': '600584', 'name': '长电科技', 'sector': '半导体'},
    {'code': '601138', 'name': '工业富联', 'sector': '半导体'},
    {'code': '002185', 'name': '华天科技', 'sector': '半导体'},
    {'code': '002049', 'name': '紫光国微', 'sector': '半导体'},
    {'code': '600487', 'name': '亨通光电', 'sector': '半导体'},
    {'code': '002916', 'name': '深南电路', 'sector': '半导体'},
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源'},
    {'code': '000333', 'name': '美的集团', 'sector': '家电'},
    {'code': '601899', 'name': '紫金矿业', 'sector': '有色'},
    {'code': '603993', 'name': '洛阳钼业', 'sector': '有色'},
    {'code': '002475', 'name': '立讯精密', 'sector': '科技'},
    {'code': '002371', 'name': '北方华创', 'sector': '半导体'},
    {'code': '600760', 'name': '中航沈飞', 'sector': '军工'},
    {'code': '600893', 'name': '航发动力', 'sector': '军工'},
    {'code': '600309', 'name': '万华化学', 'sector': '化工'},
    {'code': '600176', 'name': '中国巨石', 'sector': '化工'},
    {'code': '600900', 'name': '长江电力', 'sector': '电力'},
    {'code': '600025', 'name': '华能水电', 'sector': '电力'},
    {'code': '600031', 'name': '三一重工', 'sector': '机械'},
    {'code': '000425', 'name': '徐工机械', 'sector': '机械'},
]

SECTORS = list(set(s['sector'] for s in STOCK_POOL))


def load_stock_data(ts_code, start_date, end_date):
    """从数据库加载股票数据"""
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT trade_date, open, high, low, close, vol, amount
    FROM daily_quotes
    WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
    ORDER BY trade_date
    """
    df = pd.read_sql_query(query, conn, params=(ts_code, start_date, end_date))
    conn.close()
    
    if df.empty:
        return None
    
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    df = df.rename(columns={'vol': 'volume'})
    
    # 计算技术指标
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma5'] = df['close'].rolling(5).mean()
    df['atr'] = calculate_atr(df, 14)
    df['vol_ma5'] = df['volume'].rolling(5).mean()
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['macd'], df['signal'] = calculate_macd(df['close'])
    df['adx'] = calculate_adx(df, 14)
    df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
    
    return df


def calculate_atr(df, period):
    """计算ATR"""
    high = df['high']
    low = df['low']
    close = df['close'].shift(1)
    tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calculate_rsi(prices, period=14):
    """计算RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """计算MACD"""
    ema_fast = prices.ewm(span=fast).mean()
    ema_slow = prices.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    return macd, signal_line


def calculate_adx(df, period=14):
    """计算ADX"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(period).mean()
    return adx


class V14Backtest:
    """v14策略回测引擎"""
    
    def __init__(self, config):
        self.config = config
        self.cash = config['initial_cash']
        self.positions = {}  # {name: {'shares': 0, 'buy_price': 0, 'buy_date': None}}
        self.trade_log = []
        self.daily_values = []
        self.buy_prices = {}
        self.max_profits = {}
        self.highest_prices = {}
        self.cooldown_until = {}
        self.blacklist_until = {}
        self.consecutive_losses = {}
        self.total_pnl_by_stock = {}
        self.sector_counts = {}
        self.peak_value = config['initial_cash']
        self.circuit_breaker = False
        self.circuit_breaker_until = None
        self.stock_sector = {s['name']: s['sector'] for s in STOCK_POOL}
    
    def get_portfolio_value(self, prices):
        """计算组合总价值"""
        value = self.cash
        for name, pos in self.positions.items():
            if pos['shares'] > 0 and name in prices:
                value += pos['shares'] * prices[name]
        return value
    
    def get_position_count(self):
        """获取持仓数量"""
        return len([p for p in self.positions.values() if p['shares'] > 0])
    
    def calc_signal_score(self, row):
        """计算信号分数"""
        score = 0
        
        ma20 = row.get('ma20')
        atr = row.get('atr')
        vol = row.get('volume')
        vol_ma5 = row.get('vol_ma5')
        rsi = row.get('rsi')
        macd = row.get('macd')
        signal = row.get('signal')
        close = row.get('close')
        
        if any(pd.isna(x) for x in [ma20, atr, vol_ma5, rsi, macd, signal, close]):
            return 0
        
        # 偏离度检查
        deviation = abs(close - ma20) / ma20
        if deviation > self.config['max_deviation']:
            return 0
        
        # 价格在MA20上方
        if close >= ma20:
            score += 20
        else:
            return 0
        
        # MA20基础分
        score += 30
        
        # 放量检查
        if vol_ma5 > 0 and vol > vol_ma5 * self.config['volume_ratio']:
            score += 15
        
        # ATR阈值
        if close > 0 and atr / close > self.config['atr_threshold']:
            score += 10
        
        # MA斜率
        score += 10  # 简化处理
        
        # RSI区间
        if 40 <= rsi <= 70:
            score += 10
        elif rsi > 70:
            return 0
        
        # MACD金叉
        if macd > signal:
            score += 5
        
        return score
    
    def execute_buy(self, name, price, date, row):
        """执行买入"""
        if self.get_position_count() >= self.config['max_positions']:
            return False
        
        # 冷却期检查
        if name in self.cooldown_until and date < self.cooldown_until[name]:
            return False
        
        # 黑名单检查
        if name in self.blacklist_until and date < self.blacklist_until[name]:
            return False
        
        # 板块限制
        sector = self.stock_sector.get(name, '未知')
        if self.sector_counts.get(sector, 0) >= self.config['max_per_sector']:
            return False
        
        # 计算仓位
        total_value = self.get_portfolio_value({n: self.positions[n].get('current_price', 0) for n in self.positions})
        score = self.calc_signal_score(row)
        pct = self.config['position_pct_high'] if score >= 90 else self.config['position_pct_low']
        max_amount = total_value * pct
        
        shares = int(max_amount / price / 100) * 100
        if shares <= 0 or shares * price > self.cash * 0.95:
            return False
        
        # 执行买入
        cost = shares * price * (1 + self.config['commission'] + self.config['slippage_pct'])
        if cost > self.cash:
            return False
        
        self.cash -= cost
        self.positions[name] = {
            'shares': shares,
            'buy_price': price,
            'buy_date': date,
            'current_price': price
        }
        self.buy_prices[name] = price
        self.max_profits[name] = 0
        self.highest_prices[name] = price
        self.sector_counts[sector] = self.sector_counts.get(sector, 0) + 1
        
        return True
    
    def execute_sell(self, name, price, date, reason=''):
        """执行卖出"""
        if name not in self.positions or self.positions[name]['shares'] <= 0:
            return False
        
        pos = self.positions[name]
        shares = pos['shares']
        buy_price = pos['buy_price']
        
        # 执行卖出
        revenue = shares * price * (1 - self.config['commission'] - self.config['stamp_tax'] - self.config['slippage_pct'])
        self.cash += revenue
        
        # 计算盈亏
        pnl = revenue - shares * buy_price
        pnl_pct = (price - buy_price) / buy_price
        
        # 记录交易
        self.trade_log.append({
            'date': date.isoformat(),
            'stock': name,
            'buy_price': buy_price,
            'sell_price': price,
            'shares': shares,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'reason': reason
        })
        
        # 更新统计
        self.total_pnl_by_stock[name] = self.total_pnl_by_stock.get(name, 0) + pnl
        if pnl < 0:
            self.consecutive_losses[name] = self.consecutive_losses.get(name, 0) + 1
        else:
            self.consecutive_losses[name] = 0
        
        # 动态黑名单
        if (self.consecutive_losses.get(name, 0) >= 2 and
            self.total_pnl_by_stock.get(name, 0) < 0):
            self.blacklist_until[name] = date + timedelta(days=self.config['blacklist_days'])
        
        # 冷却期
        self.cooldown_until[name] = date + timedelta(days=self.config['cooldown_days'])
        
        # 更新板块计数
        sector = self.stock_sector.get(name, '未知')
        self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
        
        # 清除持仓
        self.positions[name] = {'shares': 0, 'buy_price': 0, 'buy_date': None}
        
        return True
    
    def check_sell_conditions(self, name, row, date):
        """检查卖出条件"""
        if name not in self.positions or self.positions[name]['shares'] <= 0:
            return
        
        price = row['close']
        buy_price = self.buy_prices.get(name, 0)
        if buy_price <= 0:
            return
        
        profit_pct = (price - buy_price) / buy_price
        ma20 = row.get('ma20')
        atr = row.get('atr')
        highest = self.highest_prices.get(name, buy_price)
        
        # 更新最高价
        self.highest_prices[name] = max(highest, price)
        
        # 更新最大盈利
        if name not in self.max_profits:
            self.max_profits[name] = profit_pct
        else:
            self.max_profits[name] = max(self.max_profits[name], profit_pct)
        
        max_profit = self.max_profits[name]
        
        # 1. Chandelier Exit
        if not pd.isna(atr):
            chandelier_stop = highest - self.config['chandelier_atr_mult'] * atr
            if price <= chandelier_stop and profit_pct > 0:
                self.execute_sell(name, price, date, f'Chandelier({profit_pct:.1%})')
                return
        
        # 2. ATR止损
        if not pd.isna(atr):
            stop_price = buy_price - self.config['atr_stop_multiplier'] * atr
            if price <= stop_price:
                self.execute_sell(name, price, date, f'ATR止损({profit_pct:.1%})')
                return
        
        # 3. 移动止盈
        if max_profit >= self.config['take_profit_pct']:
            trailing_pct = self.config['trailing_stop_pct']
            if not pd.isna(atr) and price > 0:
                atr_ratio = atr / price
                if atr_ratio > 0.04:
                    trailing_pct = 0.10
            if profit_pct <= max_profit - trailing_pct:
                self.execute_sell(name, price, date, f'移动止盈({max_profit:.1%}→{profit_pct:.1%})')
                return
        
        # 4. 跌破MA20
        if not pd.isna(ma20):
            if price < ma20 * 0.98:
                self.execute_sell(name, price, date, f'跌破MA20({profit_pct:.1%})')
                return
    
    def run(self, stock_data, dates):
        """运行回测"""
        print("开始回测...")
        
        for i, date in enumerate(dates):
            # 获取当日价格
            prices = {}
            for name, df in stock_data.items():
                if date in df.index:
                    row = df.loc[date]
                    prices[name] = row['close']
                    if name in self.positions:
                        self.positions[name]['current_price'] = row['close']
            
            # 计算组合价值
            portfolio_value = self.get_portfolio_value(prices)
            self.daily_values.append({
                'date': date.isoformat(),
                'value': portfolio_value
            })
            
            # 更新峰值
            if portfolio_value > self.peak_value:
                self.peak_value = portfolio_value
            
            # 组合回撤熔断
            drawdown = (self.peak_value - portfolio_value) / self.peak_value
            if drawdown >= self.config['portfolio_drawdown_stop']:
                if not self.circuit_breaker:
                    self.circuit_breaker = True
                    self.circuit_breaker_until = date + timedelta(days=self.config['circuit_breaker_days'])
                    # 清仓盈利股票
                    for name in list(self.positions.keys()):
                        if self.positions[name]['shares'] > 0 and name in prices:
                            buy_price = self.buy_prices.get(name, 0)
                            if buy_price > 0 and prices[name] > buy_price:
                                self.execute_sell(name, prices[name], date, '熔断清仓')
                    continue
            else:
                if self.circuit_breaker and date >= self.circuit_breaker_until:
                    self.circuit_breaker = False
                    self.peak_value = portfolio_value
            
            if self.circuit_breaker:
                continue
            
            # 检查卖出条件
            for name in list(self.positions.keys()):
                if self.positions[name]['shares'] > 0 and name in stock_data and date in stock_data[name].index:
                    row = stock_data[name].loc[date]
                    self.check_sell_conditions(name, row, date)
            
            # 检查买入信号
            if self.get_position_count() < self.config['max_positions']:
                signals = []
                for s in STOCK_POOL:
                    name = s['name']
                    if name in self.positions and self.positions[name]['shares'] > 0:
                        continue
                    if name not in stock_data or date not in stock_data[name].index:
                        continue
                    
                    row = stock_data[name].loc[date]
                    score = self.calc_signal_score(row)
                    if score >= 70:
                        signals.append((name, row['close'], score, row))
                
                # 按分数排序
                signals.sort(key=lambda x: x[2], reverse=True)
                
                for name, price, score, row in signals:
                    if self.get_position_count() >= self.config['max_positions']:
                        break
                    self.execute_buy(name, price, date, row)
            
            # 进度显示
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(dates)}] 权益: ¥{portfolio_value:,.0f}")
        
        return portfolio_value


def generate_report(backtest, final_value, config):
    """生成回测报告"""
    initial_cash = config['initial_cash']
    total_return = (final_value - initial_cash) / initial_cash
    
    # 计算年化收益
    days = len(backtest.daily_values)
    years = days / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    
    # 计算最大回撤
    values = [d['value'] for d in backtest.daily_values]
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    
    # 交易统计
    trades = backtest.trade_log
    total_trades = len(trades)
    winning_trades = [t for t in trades if t['pnl'] > 0]
    losing_trades = [t for t in trades if t['pnl'] <= 0]
    win_rate = len(winning_trades) / max(total_trades, 1)
    avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
    avg_loss = abs(np.mean([t['pnl'] for t in losing_trades])) if losing_trades else 1
    profit_ratio = avg_win / max(avg_loss, 1)
    
    # 夏普比率
    daily_returns = pd.Series(values).pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0
    
    # 生成HTML报告
    dates = [d['date'] for d in backtest.daily_values]
    
    trade_rows = ""
    for t in trades[-100:]:  # 最近100笔
        color = "#3fb950" if t['pnl'] > 0 else "#f85149"
        emoji = "🟢" if t['pnl'] > 0 else "🔴"
        trade_rows += f"""<tr>
            <td>{t['date']}</td>
            <td>{t['stock']}</td>
            <td>{t['buy_price']:.2f}</td>
            <td>{t['sell_price']:.2f}</td>
            <td>{t['pnl_pct']:.1%}</td>
            <td style="color:{color}">{emoji} {t['pnl']:>+,.0f}</td>
            <td>{t['reason']}</td>
        </tr>"""
    
    # 年度收益统计
    yearly_stats = {}
    for d in backtest.daily_values:
        year = d['date'][:4]
        if year not in yearly_stats:
            yearly_stats[year] = {'start': d['value'], 'end': d['value']}
        yearly_stats[year]['end'] = d['value']
    
    yearly_rows = ""
    for year, stats in sorted(yearly_stats.items()):
        ret = (stats['end'] - stats['start']) / stats['start']
        color = "#3fb950" if ret > 0 else "#f85149"
        yearly_rows += f'<tr><td>{year}</td><td style="color:{color}">{ret:+.1%}</td></tr>'
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>v14策略5年回测报告</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;margin-bottom:20px}}
h1{{text-align:center;color:#58a6ff;margin-bottom:8px;font-size:28px}}
.subtitle{{text-align:center;color:#8b949e;margin-bottom:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
.metric{{background:#21262d;border-radius:8px;padding:16px;text-align:center}}
.metric .label{{color:#8b949e;font-size:12px;margin-bottom:4px}}
.metric .value{{font-size:22px;font-weight:bold}}
.positive{{color:#3fb950}}.negative{{color:#f85149}}.neutral{{color:#58a6ff}}
h2{{color:#58a6ff;margin-top:0;font-size:18px}}
table{{width:100%;border-collapse:collapse}}
th{{background:#21262d;padding:10px;text-align:left;color:#8b949e;font-size:12px}}
td{{padding:8px 10px;border-bottom:1px solid #21262d;font-size:12px}}
.target{{background:#1c2128;border:2px solid #ff9800;border-radius:12px;padding:20px;margin:20px 0;text-align:center}}
.target .title{{color:#ff9800;font-size:18px;font-weight:bold;margin-bottom:10px}}
.target .status{{font-size:20px}}
</style></head><body>
<h1>📊 v14策略5年回测报告</h1>
<p class="subtitle">2021-01-01 ~ 2026-06-14 | 初始资金 ¥1,000,000</p>

<div class="target">
<div class="title">🎯 目标达成</div>
<div class="status">
年化>50%: {'✅' if annual_return > 0.5 else '❌'} ({annual_return:.1%}) &nbsp;|&nbsp;
回撤<10%: {'✅' if max_dd < 0.1 else '❌'} ({max_dd:.1%})
</div>
</div>

<div class="grid">
    <div class="metric"><div class="label">最终权益</div><div class="value {'positive' if total_return>0 else 'negative'}">¥{final_value:,.0f}</div></div>
    <div class="metric"><div class="label">总收益率</div><div class="value {'positive' if total_return>0 else 'negative'}">{total_return:+.1%}</div></div>
    <div class="metric"><div class="label">年化收益率</div><div class="value {'positive' if annual_return>0.5 else 'negative'}">{annual_return:+.1%}</div></div>
    <div class="metric"><div class="label">最大回撤</div><div class="value {'positive' if max_dd<0.1 else 'negative'}">{max_dd:.1%}</div></div>
    <div class="metric"><div class="label">夏普比率</div><div class="value neutral">{sharpe:.2f}</div></div>
    <div class="metric"><div class="label">胜率</div><div class="value neutral">{win_rate:.1%}</div></div>
    <div class="metric"><div class="label">盈亏比</div><div class="value neutral">{profit_ratio:.2f}</div></div>
    <div class="metric"><div class="label">交易次数</div><div class="value neutral">{total_trades}</div></div>
</div>

<div class="card"><h2>📈 权益曲线</h2><div id="equity" style="height:400px"></div></div>

<div class="card"><h2>📅 年度收益</h2>
<table><tr><th>年份</th><th>收益率</th></tr>{yearly_rows}</table>
</div>

<div class="card"><h2>📝 交易明细（最近100笔）</h2>
<div style="max-height:600px;overflow-y:auto">
<table>
<tr><th>日期</th><th>股票</th><th>买入价</th><th>卖出价</th><th>收益率</th><th>盈亏</th><th>原因</th></tr>
{trade_rows}
</table>
</div>
</div>

<script>
var c = echarts.init(document.getElementById('equity'));
c.setOption({{
    backgroundColor: 'transparent',
    tooltip: {{trigger: 'axis'}},
    grid: {{left: 80, right: 30, top: 30, bottom: 40}},
    xAxis: {{
        type: 'category',
        data: {json.dumps(dates)},
        axisLabel: {{color: '#8b949e', fontSize: 10}}
    }},
    yAxis: {{
        type: 'value',
        axisLabel: {{color: '#8b949e', formatter: '¥{{value}}'}}
    }},
    series: [{{
        type: 'line',
        data: {json.dumps(values)},
        lineStyle: {{color: '#00e676', width: 2}},
        itemStyle: {{color: '#00e676'}},
        areaStyle: {{
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                {{offset: 0, color: 'rgba(0,230,118,0.25)'}},
                {{offset: 1, color: 'rgba(0,230,118,0.02)'}}
            ])
        }},
        showSymbol: false,
        markLine: {{
            data: [{{yAxis: {config['initial_cash']}, label: {{formatter: '初始资金', color: '#8b949e'}}}}],
            lineStyle: {{color: '#f85149', type: 'dashed'}},
            silent: true
        }}
    }}]
}});
window.addEventListener('resize', () => c.resize());
</script>
</body></html>"""
    
    # 保存HTML报告
    report_path = '/usr/share/nginx/html/public/backtest_v14_5year.html'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # 打印统计
    print("\n" + "=" * 70)
    print("📊 v14策略5年回测结果")
    print("=" * 70)
    print(f"{'初始资金':<20} {'¥{:,.0f}'.format(initial_cash):>15}")
    print(f"{'最终权益':<20} {'¥{:,.0f}'.format(final_value):>15}")
    print(f"{'总收益率':<20} {total_return:>14.1%}")
    print(f"{'年化收益率':<20} {annual_return:>14.1%}")
    print(f"{'最大回撤':<20} {max_dd:>14.1%}")
    print(f"{'夏普比率':<20} {sharpe:>14.2f}")
    print(f"{'总交易次数':<20} {total_trades:>15}")
    print(f"{'胜率':<20} {win_rate:>14.1%}")
    print(f"{'盈亏比':<20} {profit_ratio:>14.2f}")
    print(f"\n✅ 报告已保存: {report_path}")
    
    return report_path


def main():
    print("=" * 70)
    print("📊 v14策略5年回测")
    print("=" * 70)
    print(f"时间范围: 2021-01-01 ~ 2026-06-14")
    print(f"股票池: {len(STOCK_POOL)} 只")
    print()
    
    # 加载数据
    print("加载股票数据...")
    start_date = '2021-01-01'
    end_date = '2026-06-14'
    
    stock_data = {}
    all_dates = set()
    
    for s in STOCK_POOL:
        ts_code = f"{s['code']}.{'SH' if s['code'].startswith('6') else 'SZ'}"
        df = load_stock_data(ts_code, start_date, end_date)
        if df is not None and len(df) > 100:
            stock_data[s['name']] = df
            all_dates.update(df.index)
            print(f"  ✅ {s['name']}: {len(df)} 条")
        else:
            print(f"  ❌ {s['name']}: 数据不足")
    
    if not stock_data:
        print("没有可用数据！")
        return
    
    # 获取交易日期
    dates = sorted(all_dates)
    print(f"\n交易日数: {len(dates)}")
    
    # 运行回测
    backtest = V14Backtest(CONFIG)
    final_value = backtest.run(stock_data, dates)
    
    # 生成报告
    generate_report(backtest, final_value, CONFIG)


if __name__ == '__main__':
    main()
