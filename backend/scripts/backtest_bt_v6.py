#!/usr/bin/env python3
"""
Backtrader标准回测 v6
统一资金池 + 信号评分排序 + 交易成本 + 大盘过滤 + 冷却期 + 基准对比
"""

import backtrader as bt
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os


# ============================================================
# 策略配置
# ============================================================

CONFIG = {
    'initial_cash': 1_000_000,      # 初始资金100万
    'max_positions': 5,             # 最多持仓5只
    'position_pct': 0.18,           # 单只仓位18%
    'commission': 0.00025,          # 佣金万2.5
    'stamp_tax': 0.001,             # 印花税千1(卖出)
    'slippage_pct': 0.001,          # 滑点0.1%
    'cooldown_days': 5,             # 卖出后冷却5天
    'market_filter': True,          # 大盘过滤
    'ma_period': 20,                # MA周期
    'atr_period': 14,               # ATR周期
    'volume_ratio': 1.2,            # 放量阈值(放宽到1.2)
    'atr_threshold': 0.02,          # ATR波动率阈值
    'max_deviation': 0.10,          # 最大偏离度
    'take_profit_pct': 0.15,        # 止盈启动点
    'trailing_stop_pct': 0.05,      # 移动止演回撤
    'atr_stop_multiplier': 2,       # ATR止损倍数
}


# ============================================================
# 自定义数据源 (akshare)
# ============================================================

class AkshareData(bt.feeds.PandasData):
    lines = ('volume',)
    params = (
        ('datetime', None),
        ('open', '开盘'),
        ('high', '最高'),
        ('low', '最低'),
        ('close', '收盘'),
        ('volume', '成交量'),
        ('openinterest', -1),
    )


def fetch_stock_data(code, start_date, end_date):
    """从akshare获取股票数据"""
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start_date, end_date=end_date,
            adjust="qfq"
        )
        if df.empty:
            return None
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.set_index('日期')
        df = df.sort_index()
        return df
    except Exception as e:
        print(f"  ❌ {code} 数据获取失败: {e}")
        return None


def fetch_index_data(start_date, end_date):
    """获取上证指数数据"""
    try:
        df = ak.stock_zh_index_daily_em(symbol="sh000001")
        df['date'] = pd.to_datetime(df['date'])
        df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
        df = df.set_index('date').sort_index()
        return df
    except Exception as e:
        print(f"  ❌ 上证指数获取失败: {e}")
        return None


# ============================================================
# 自定义佣金方案
# ============================================================

class CNCommission(bt.CommInfoBase):
    params = (
        ('commission', 0.00025),
        ('stamp_tax', 0.001),
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC),
    )

    def _getcommission(self, size, price, pseudoexec):
        turnover = abs(size) * price
        comm = turnover * self.p.commission
        # 卖出加印花税
        if size < 0:
            comm += turnover * self.p.stamp_tax
        return max(comm, 5)  # 最低5元


# ============================================================
# 策略类
# ============================================================

class MA20Strategy(bt.Strategy):
    """MA20突破策略 - 信号评分 + 大盘过滤 + 冷却期"""

    params = (
        ('ma_period', 20),
        ('atr_period', 14),
        ('volume_ratio', 1.2),
        ('atr_threshold', 0.02),
        ('max_deviation', 0.10),
        ('take_profit_pct', 0.15),
        ('trailing_stop_pct', 0.05),
        ('atr_stop_multiplier', 2),
        ('max_positions', 5),
        ('position_pct', 0.18),
        ('cooldown_days', 5),
        ('market_filter', True),
    )

    def __init__(self):
        self.order_dict = {}
        self.buy_prices = {}
        self.max_profits = {}
        self.cooldown_until = {}  # stock -> datetime
        self.signal_scores = {}
        self.trade_log = []
        self.daily_values = []

        # 指标
        for d in self.datas:
            d.ma = bt.indicators.SMA(d.close, period=self.p.ma_period)
            d.atr = bt.indicators.ATR(d, period=self.p.atr_period)
            d.vol_ma = bt.indicators.SMA(d.volume, period=5)
            d.slope = (d.ma - d.ma(-5)) / d.ma(-5) * 100

    def log(self, msg, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        # print(f'{dt}: {msg}')

    def notify_order(self, order):
        if order.status in [order.Completed]:
            d = order.data
            name = d._name
            if order.isbuy():
                self.buy_prices[name] = order.executed.price
                self.max_profits[name] = 0
                self.log(f'🟢 买入 {name} @ {order.executed.price:.2f} × {order.executed.size}')
            elif order.issell():
                if name in self.buy_prices:
                    profit = (order.executed.price - self.buy_prices[name]) / self.buy_prices[name]
                    self.log(f'🔴 卖出 {name} @ {order.executed.price:.2f} 盈亏{profit:.1%}')
                    # 设置冷却期
                    self.cooldown_until[name] = self.datas[0].datetime.date(0) + timedelta(days=self.p.cooldown_days)
                    del self.buy_prices[name]
                    if name in self.max_profits:
                        del self.max_profits[name]

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trade_log.append({
                'stock': trade.data._name,
                'pnl': trade.pnl,
                'pnlcomm': trade.pnlcomm,
                'date': self.datas[0].datetime.date(0).isoformat(),
            })

    def get_position_count(self):
        return len([d for d in self.datas if self.getposition(d).size > 0])

    def calc_signal_score(self, d):
        """计算买入信号评分"""
        score = 0
        price = d.close[0]
        ma = d.ma[0]
        atr = d.atr[0]
        vol = d.volume[0]
        vol_ma = d.vol_ma[0]
        slope = d.slope[0]

        if pd.isna(ma) or pd.isna(atr) or pd.isna(vol_ma) or pd.isna(slope):
            return 0

        # 1. 偏离度
        deviation = abs(price - ma) / ma
        if deviation > self.p.max_deviation:
            return 0
        score += 30

        # 2. 站上MA20
        if price >= ma:
            score += 20
        else:
            return 0

        # 3. 放量
        if vol_ma > 0 and vol > vol_ma * self.p.volume_ratio:
            score += 20

        # 4. ATR波动率
        if price > 0 and atr / price > self.p.atr_threshold:
            score += 15

        # 5. MA20斜率
        if slope > 1:
            score += 15
        elif slope > 0:
            score += 10
        else:
            return 0  # MA20下降不买

        return score

    def next(self):
        # 记录每日净值
        self.daily_values.append({
            'date': self.datas[0].datetime.date(0).isoformat(),
            'value': self.broker.getvalue(),
        })

        current_date = self.datas[0].datetime.date(0)

        # 大盘过滤
        market_ok = True
        if self.p.market_filter:
            index_data = self.datas[0]  # 第一个data是上证指数
            if hasattr(index_data, 'ma') and not pd.isna(index_data.ma[0]):
                market_ok = index_data.close[0] > index_data.ma[0]

        # 遍历所有股票(跳过指数)
        signals = []
        for i, d in enumerate(self.datas):
            if i == 0:  # 跳过上证指数
                continue
            name = d._name
            pos = self.getposition(d)

            # 已持仓 → 检查卖出
            if pos.size > 0:
                self._check_sell(d, name, pos)
                continue

            # 未持仓 → 检查买入信号
            if self.get_position_count() >= self.p.max_positions:
                continue

            # 冷却期检查
            if name in self.cooldown_until and current_date < self.cooldown_until[name]:
                continue

            # 计算信号评分
            score = self.calc_signal_score(d)
            if score >= 70:
                signals.append((d, name, score))

        # 按评分排序，优先买入最强信号
        signals.sort(key=lambda x: x[2], reverse=True)
        for d, name, score in signals:
            if self.get_position_count() >= self.p.max_positions:
                break
            self._execute_buy(d, name, score)

    def _execute_buy(self, d, name, score):
        """执行买入"""
        cash = self.broker.getcash()
        price = d.close[0]
        total_value = self.broker.getvalue()
        max_amount = total_value * self.p.position_pct
        shares = int(max_amount / price / 100) * 100

        if shares <= 0 or shares * price > cash * 0.95:
            return

        self.log(f'📈 信号买入 {name} 评分{score} @ {price:.2f} × {shares}')
        self.buy(data=d, size=shares)

    def _check_sell(self, d, name, pos):
        """检查卖出条件"""
        price = d.close[0]
        buy_price = self.buy_prices.get(name, 0)
        if buy_price <= 0:
            return

        profit_pct = (price - buy_price) / buy_price
        ma = d.ma[0]
        atr = d.atr[0]

        # 更新最高盈利
        if name not in self.max_profits:
            self.max_profits[name] = profit_pct
        else:
            self.max_profits[name] = max(self.max_profits[name], profit_pct)

        max_profit = self.max_profits[name]
        sell_reason = None

        # 1. ATR止损
        if not pd.isna(atr):
            stop_price = buy_price - self.p.atr_stop_multiplier * atr
            if price <= stop_price:
                sell_reason = f'ATR止损({profit_pct:.1%})'

        # 2. 移动止盈
        if sell_reason is None and max_profit >= self.p.take_profit_pct:
            trailing_line = max_profit - self.p.trailing_stop_pct
            if profit_pct <= trailing_line:
                sell_reason = f'移动止盈(最高{max_profit:.1%})'

        # 3. 跌破MA20
        if sell_reason is None and not pd.isna(ma):
            if price < ma * 0.98:
                sell_reason = f'跌破MA20({profit_pct:.1%})'

        if sell_reason:
            self.log(f'📉 卖出 {name} {sell_reason}')
            self.sell(data=d, size=pos.size)


# ============================================================
# 运行回测
# ============================================================

def run_backtest():
    start_date = '20250101'
    end_date = '20260609'
    display_start = '2025-01-01'
    display_end = '2026-06-09'

    stocks = [
        # 半导体/电子
        {'code': '600584', 'name': '长电科技'},
        {'code': '601138', 'name': '工业富联'},
        {'code': '002185', 'name': '华天科技'},
        {'code': '002049', 'name': '紫光国微'},
        {'code': '600487', 'name': '亨通光电'},
        {'code': '002916', 'name': '深南电路'},
        # 新能源/汽车
        {'code': '002594', 'name': '比亚迪'},
        {'code': '000333', 'name': '美的集团'},
        # 有色/矿业
        {'code': '601899', 'name': '紫金矿业'},
        {'code': '603993', 'name': '洛阳钼业'},
        # 通信/科技
        {'code': '002475', 'name': '立讯精密'},
        {'code': '002371', 'name': '北方华创'},
        # 军工
        {'code': '600760', 'name': '中航沈飞'},
        {'code': '600893', 'name': '航发动力'},
        # 化工
        {'code': '600309', 'name': '万华化学'},
        {'code': '600176', 'name': '中国巨石'},
        # 电力
        {'code': '600900', 'name': '长江电力'},
        {'code': '600025', 'name': '华能水电'},
        # 机械
        {'code': '600031', 'name': '三一重工'},
        {'code': '000425', 'name': '徐工机械'},
    ]

    print("="*70)
    print("📊 Backtrader标准回测 v6")
    print("="*70)
    print(f"回测期间: {display_start} ~ {display_end}")
    print(f"初始资金: {CONFIG['initial_cash']/10000:.0f}万")
    print(f"股票池: {len(stocks)}只")
    print(f"最大持仓: {CONFIG['max_positions']}只")
    print(f"单只仓位: {CONFIG['position_pct']*100:.0f}%")
    print(f"大盘过滤: {'开' if CONFIG['market_filter'] else '关'}")
    print(f"冷却期: {CONFIG['cooldown_days']}天")
    print(f"放量阈值: {CONFIG['volume_ratio']}倍")
    print("="*70)

    # 获取数据
    print("\n获取数据...")
    cerebro = bt.Cerebro()

    # 上证指数(第一个data，用于大盘过滤)
    print("  上证指数...")
    index_df = fetch_index_data(start_date, end_date)
    if index_df is not None and not index_df.empty:
        # 适配backtrader格式
        idx = index_df.rename(columns={'open': '开盘', 'high': '最高', 'low': '最低', 'close': '收盘', 'volume': '成交量'})
        idx_data = AkshareData(dataname=idx, name='上证指数')
        cerebro.adddata(idx_data)
        print(f"  ✅ 上证指数: {len(idx)}条")

    # 个股数据
    for s in stocks:
        print(f"  {s['name']}...")
        df = fetch_stock_data(s['code'], start_date, end_date)
        if df is not None and not df.empty:
            data = AkshareData(dataname=df, name=s['name'])
            cerebro.adddata(data)
            print(f"  ✅ {s['name']}: {len(df)}条")

    # 设置
    cerebro.addstrategy(MA20Strategy)
    cerebro.broker.setcash(CONFIG['initial_cash'])
    cerebro.broker.addcommissioninfo(CNCommission(commission=CONFIG['commission'], stamp_tax=CONFIG['stamp_tax']))
    cerebro.broker.set_slippage_perc(CONFIG['slippage_pct'])

    # 分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.02, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    # 运行
    print("\n运行回测...")
    results = cerebro.run()
    strat = results[0]

    # 输出结果
    final_value = cerebro.broker.getvalue()
    total_return = (final_value - CONFIG['initial_cash']) / CONFIG['initial_cash']

    print("\n" + "="*70)
    print("📊 回测结果")
    print("="*70)

    # 核心指标
    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    returns = strat.analyzers.returns.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    print(f"\n{'指标':<20} {'数值':>15}")
    print("-"*40)
    print(f"{'初始资金':<20} {'¥{:,.0f}'.format(CONFIG['initial_cash']):>15}")
    print(f"{'最终权益':<20} {'¥{:,.0f}'.format(final_value):>15}")
    print(f"{'总收益率':<20} {total_return:>14.2%}")
    print(f"{'年化收益率':<20} {returns.get('rnorm100', 0):>14.2f}%")
    print(f"{'最大回撤':<20} {drawdown.max.drawdown:>14.2f}%")
    print(f"{'夏普比率':<20} {sharpe.get('sharperatio', 0) or 0:>14.2f}")

    # 交易统计
    total_trades = trades.get('total', {}).get('total', 0)
    won = trades.get('won', {}).get('total', 0)
    lost = trades.get('lost', {}).get('total', 0)
    win_rate = won / max(total_trades, 1)

    print(f"{'总交易次数':<20} {total_trades:>15}")
    print(f"{'盈利次数':<20} {won:>15}")
    print(f"{'亏损次数':<20} {lost:>15}")
    print(f"{'胜率':<20} {win_rate:>14.1%}")

    # 盈亏比
    avg_won = trades.get('won', {}).get('pnl', {}).get('average', 0)
    avg_lost = abs(trades.get('lost', {}).get('pnl', {}).get('average', 1))
    profit_ratio = avg_won / max(avg_lost, 1)
    print(f"{'盈亏比':<20} {profit_ratio:>14.2f}")

    # 交易明细
    if strat.trade_log:
        print(f"\n{'='*70}")
        print("📝 交易明细")
        print(f"{'='*70}")
        print(f"{'日期':<12} {'股票':<10} {'盈亏':>12} {'盈亏(含费)':>12}")
        print("-"*50)
        for t in strat.trade_log:
            emoji = '🟢' if t['pnlcomm'] > 0 else '🔴'
            print(f"{t['date']:<12} {t['stock']:<10} {emoji}{t['pnl']:>+10,.0f} {t['pnlcomm']:>+10,.0f}")

    # 生成HTML报告
    generate_html_report(strat, final_value, CONFIG, sharpe, drawdown, returns, trades, stocks)

    return strat


def generate_html_report(strat, final_value, config, sharpe, drawdown, returns, trades, stocks):
    """生成HTML回测报告"""

    daily = strat.daily_values
    dates = [d['date'] for d in daily]
    values = [d['value'] for d in daily]

    # 计算每日收益率
    daily_returns = []
    for i in range(1, len(values)):
        daily_returns.append((values[i] - values[i-1]) / values[i-1])

    # 统计
    total_return = (final_value - config['initial_cash']) / config['initial_cash']
    max_dd = drawdown.max.drawdown
    sharpe_val = sharpe.get('sharperatio', 0) or 0
    annual_return = returns.get('rnorm100', 0)
    total_trades = trades.get('total', {}).get('total', 0)
    won = trades.get('won', {}).get('total', 0)
    lost = trades.get('lost', {}).get('total', 0)
    win_rate = won / max(total_trades, 1)
    avg_won = trades.get('won', {}).get('pnl', {}).get('average', 0)
    avg_lost = abs(trades.get('lost', {}).get('pnl', {}).get('average', 1))
    profit_ratio = avg_won / max(avg_lost, 1)

    # 交易明细
    trade_rows = ""
    for t in strat.trade_log:
        emoji = "🟢" if t['pnlcomm'] > 0 else "🔴"
        color = "#00e676" if t['pnlcomm'] > 0 else "#ff5252"
        trade_rows += f"""
        <tr>
            <td>{t['date']}</td>
            <td>{t['stock']}</td>
            <td style="color:{color};text-align:right;">{emoji} {t['pnlcomm']:>+,.0f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Backtrader回测报告</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
body {{ font-family: -apple-system, 'PingFang SC', sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 20px; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; margin-bottom: 20px; }}
h1 {{ text-align: center; color: #58a6ff; margin-bottom: 8px; font-size: 28px; }}
.subtitle {{ text-align: center; color: #8b949e; margin-bottom: 24px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
.metric {{ background: #21262d; border-radius: 8px; padding: 16px; text-align: center; }}
.metric .label {{ color: #8b949e; font-size: 12px; margin-bottom: 4px; }}
.metric .value {{ font-size: 24px; font-weight: bold; }}
.metric .value.positive {{ color: #3fb950; }}
.metric .value.negative {{ color: #f85149; }}
.metric .value.neutral {{ color: #58a6ff; }}
h2 {{ color: #58a6ff; margin-top: 0; font-size: 18px; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #21262d; padding: 10px 12px; text-align: left; color: #8b949e; font-size: 13px; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #21262d; font-size: 13px; }}
.config {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; }}
.config-item {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #21262d; }}
.config-item .key {{ color: #8b949e; }}
</style></head><body>

<h1>📊 Backtrader 策略回测报告</h1>
<p class="subtitle">MA20突破 + 移动止盈 + ATR止损 + 大盘过滤 + 冷却期 | {dates[0]} ~ {dates[-1]}</p>

<div class="grid">
    <div class="metric">
        <div class="label">最终权益</div>
        <div class="value {'positive' if total_return > 0 else 'negative'}">¥{final_value:,.0f}</div>
    </div>
    <div class="metric">
        <div class="label">总收益率</div>
        <div class="value {'positive' if total_return > 0 else 'negative'}">{total_return:+.2%}</div>
    </div>
    <div class="metric">
        <div class="label">年化收益率</div>
        <div class="value {'positive' if annual_return > 0 else 'negative'}">{annual_return:+.1f}%</div>
    </div>
    <div class="metric">
        <div class="label">最大回撤</div>
        <div class="value negative">-{max_dd:.2f}%</div>
    </div>
    <div class="metric">
        <div class="label">夏普比率</div>
        <div class="value neutral">{sharpe_val:.2f}</div>
    </div>
    <div class="metric">
        <div class="label">胜率</div>
        <div class="value neutral">{win_rate:.1%}</div>
    </div>
    <div class="metric">
        <div class="label">盈亏比</div>
        <div class="value neutral">{profit_ratio:.2f}</div>
    </div>
    <div class="metric">
        <div class="label">交易次数</div>
        <div class="value neutral">{total_trades}</div>
    </div>
</div>

<div class="card">
    <h2>📈 权益曲线</h2>
    <div id="equityChart" style="height:400px;"></div>
</div>

<div class="card">
    <h2>📉 每日收益率分布</h2>
    <div id="returnChart" style="height:300px;"></div>
</div>

<div class="card">
    <h2>⚙️ 策略配置</h2>
    <div class="config">
        <div class="config-item"><span class="key">初始资金</span><span>¥{config['initial_cash']/10000:.0f}万</span></div>
        <div class="config-item"><span class="key">最大持仓</span><span>{config['max_positions']}只</span></div>
        <div class="config-item"><span class="key">单只仓位</span><span>{config['position_pct']*100:.0f}%</span></div>
        <div class="config-item"><span class="key">佣金</span><span>万{config['commission']*10000:.1f}</span></div>
        <div class="config-item"><span class="key">印花税</span><span>千{config['stamp_tax']*1000:.0f}</span></div>
        <div class="config-item"><span class="key">滑点</span><span>{config['slippage_pct']*100:.1f}%</span></div>
        <div class="config-item"><span class="key">冷却期</span><span>{config['cooldown_days']}天</span></div>
        <div class="config-item"><span class="key">大盘过滤</span><span>{'开' if config['market_filter'] else '关'}</span></div>
        <div class="config-item"><span class="key">放量阈值</span><span>{config['volume_ratio']}倍</span></div>
        <div class="config-item"><span class="key">止盈</span><span>{config['take_profit_pct']*100:.0f}%启动/{config['trailing_stop_pct']*100:.0f}%回撤</span></div>
        <div class="config-item"><span class="key">止损</span><span>ATR×{config['atr_stop_multiplier']}</span></div>
    </div>
</div>

<div class="card">
    <h2>📝 交易明细</h2>
    <table>
        <tr><th>日期</th><th>股票</th><th>盈亏(含费)</th></tr>
        {trade_rows}
    </table>
</div>

<script>
// 权益曲线
var chart1 = echarts.init(document.getElementById('equityChart'));
chart1.setOption({{
    backgroundColor: 'transparent',
    tooltip: {{ trigger: 'axis', formatter: function(p) {{ return p[0].axisValue + '<br/>¥' + p[0].data.toLocaleString(); }} }},
    grid: {{ left: 80, right: 30, top: 30, bottom: 40 }},
    xAxis: {{ type: 'category', data: {json.dumps(dates)}, axisLabel: {{ color: '#8b949e', fontSize: 10 }} }},
    yAxis: {{ type: 'value', axisLabel: {{ color: '#8b949e', formatter: '¥{{value}}' }}, name: '权益', nameTextStyle: {{ color: '#8b949e' }} }},
    series: [{{
        type: 'line', data: {json.dumps(values)},
        lineStyle: {{ color: '#58a6ff', width: 2 }},
        itemStyle: {{ color: '#58a6ff' }},
        areaStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            {{ offset: 0, color: 'rgba(88,166,255,0.25)' }},
            {{ offset: 1, color: 'rgba(88,166,255,0.02)' }}
        ]) }},
        showSymbol: false,
        markLine: {{
            data: [{{ yAxis: {config['initial_cash']}, label: {{ formatter: '初始资金', color: '#8b949e' }} }}],
            lineStyle: {{ color: '#f85149', type: 'dashed' }},
            silent: true,
        }}
    }}]
}});

// 收益率分布
var chart2 = echarts.init(document.getElementById('returnChart'));
var returns = {json.dumps([round(r*100, 2) for r in daily_returns])};
var bins = [];
for (var i = -5; i <= 5; i += 0.5) bins.push(i);
var hist = new Array(bins.length - 1).fill(0);
returns.forEach(r => {{
    for (var i = 0; i < bins.length - 1; i++) {{
        if (r >= bins[i] && r < bins[i+1]) {{ hist[i]++; break; }}
    }}
}});
chart2.setOption({{
    backgroundColor: 'transparent',
    tooltip: {{ trigger: 'axis' }},
    grid: {{ left: 50, right: 30, top: 20, bottom: 40 }},
    xAxis: {{ type: 'category', data: bins.slice(0, -1).map((b,i) => b.toFixed(1)+'~'+bins[i+1].toFixed(1)+'%'), axisLabel: {{ color: '#8b949e', fontSize: 9, rotate: 45 }} }},
    yAxis: {{ type: 'value', axisLabel: {{ color: '#8b949e' }} }},
    series: [{{ type: 'bar', data: hist, itemStyle: {{ color: function(p) {{ return p.data >= 0 ? '#3fb950' : '#f85149'; }} }} }}]
}});

window.addEventListener('resize', () => {{ chart1.resize(); chart2.resize(); }});
</script>
</body></html>"""

    out_path = "/usr/share/nginx/html/public/backtest_bt_report.html"
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ 报告已生成: {out_path}")
    return out_path


if __name__ == "__main__":
    run_backtest()
