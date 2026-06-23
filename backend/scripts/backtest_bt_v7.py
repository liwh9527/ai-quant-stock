#!/usr/bin/env python3
"""
Backtrader回测 v7 - 全面优化版
v6 → v7 改进：
1. MACD+RSI趋势确认
2. 动态仓位（按评分）
3. 行业分散（每行业最多2只）
4. 冷却期 5→10天
5. 止损 ATR×2→ATR×1.5
6. 大盘过滤强化：MA5>MA20
"""

import backtrader as bt
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json


# ============================================================
# 配置
# ============================================================

CONFIG = {
    'initial_cash': 1_000_000,
    'max_positions': 5,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'cooldown_days': 10,            # 5→10
    'market_filter': True,
    'ma_period': 20,
    'atr_period': 14,
    'volume_ratio': 1.2,
    'atr_threshold': 0.02,
    'max_deviation': 0.10,
    'take_profit_pct': 0.15,
    'trailing_stop_pct': 0.05,
    'atr_stop_multiplier': 1.5,     # 2→1.5
    # 动态仓位
    'pos_tier1': {'min_score': 90, 'pct': 0.18},
    'pos_tier2': {'min_score': 80, 'pct': 0.14},
    'pos_tier3': {'min_score': 70, 'pct': 0.10},
    # 行业限制
    'max_per_sector': 2,
}


# ============================================================
# 股票池 + 行业分类
# ============================================================

STOCK_POOL = [
    # 半导体/电子 (最多买2只)
    {'code': '600584', 'name': '长电科技', 'sector': '半导体'},
    {'code': '601138', 'name': '工业富联', 'sector': '半导体'},
    {'code': '002185', 'name': '华天科技', 'sector': '半导体'},
    {'code': '002049', 'name': '紫光国微', 'sector': '半导体'},
    {'code': '600487', 'name': '亨通光电', 'sector': '半导体'},
    {'code': '002916', 'name': '深南电路', 'sector': '半导体'},
    # 新能源/汽车
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源'},
    {'code': '000333', 'name': '美的集团', 'sector': '家电'},
    # 有色/矿业
    {'code': '601899', 'name': '紫金矿业', 'sector': '有色'},
    {'code': '603993', 'name': '洛阳钼业', 'sector': '有色'},
    # 科技
    {'code': '002475', 'name': '立讯精密', 'sector': '科技'},
    {'code': '002371', 'name': '北方华创', 'sector': '半导体'},
    # 军工
    {'code': '600760', 'name': '中航沈飞', 'sector': '军工'},
    {'code': '600893', 'name': '航发动力', 'sector': '军工'},
    # 化工
    {'code': '600309', 'name': '万华化学', 'sector': '化工'},
    {'code': '600176', 'name': '中国巨石', 'sector': '化工'},
    # 电力
    {'code': '600900', 'name': '长江电力', 'sector': '电力'},
    {'code': '600025', 'name': '华能水电', 'sector': '电力'},
    # 机械
    {'code': '600031', 'name': '三一重工', 'sector': '机械'},
    {'code': '000425', 'name': '徐工机械', 'sector': '机械'},
]


# ============================================================
# 数据源
# ============================================================

class AkshareData(bt.feeds.PandasData):
    lines = ('volume',)
    params = (
        ('datetime', None),
        ('open', '开盘'), ('high', '最高'), ('low', '最低'),
        ('close', '收盘'), ('volume', '成交量'),
        ('openinterest', -1),
    )


def fetch_stock_data(code, start_date, end_date):
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=start_date, end_date=end_date, adjust="qfq")
        if df.empty:
            return None
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.set_index('日期').sort_index()
        return df
    except Exception as e:
        print(f"  ❌ {code}: {e}")
        return None


def fetch_index_data(start_date, end_date):
    try:
        df = ak.stock_zh_index_daily_em(symbol="sh000001")
        df['date'] = pd.to_datetime(df['date'])
        df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
        df = df.set_index('date').sort_index()
        return df
    except Exception as e:
        print(f"  ❌ 上证指数: {e}")
        return None


# ============================================================
# 佣金
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
        if size < 0:
            comm += turnover * self.p.stamp_tax
        return max(comm, 5)


# ============================================================
# RSI指标 (Backtrader内置，但自定义周期)
# ============================================================

class RSI(bt.indicators.RSI):
    params = (('period', 14),)


# ============================================================
# 策略 v7
# ============================================================

class MA20StrategyV7(bt.Strategy):
    params = (
        ('ma_period', 20),
        ('atr_period', 14),
        ('volume_ratio', 1.2),
        ('atr_threshold', 0.02),
        ('max_deviation', 0.10),
        ('take_profit_pct', 0.15),
        ('trailing_stop_pct', 0.05),
        ('atr_stop_multiplier', 1.5),
        ('max_positions', 5),
        ('cooldown_days', 10),
        ('market_filter', True),
        ('max_per_sector', 2),
    )

    def __init__(self):
        self.buy_prices = {}
        self.max_profits = {}
        self.cooldown_until = {}
        self.trade_log = []
        self.daily_values = []
        self.sector_counts = {}  # 当前持仓的行业计数

        # 股票代码到行业的映射
        self.stock_sector = {}
        for s in STOCK_POOL:
            self.stock_sector[s['name']] = s['sector']

        # 指标
        for d in self.datas:
            d.ma = bt.indicators.SMA(d.close, period=self.p.ma_period)
            d.ma5 = bt.indicators.SMA(d.close, period=5)
            d.atr = bt.indicators.ATR(d, period=self.p.atr_period)
            d.vol_ma = bt.indicators.SMA(d.volume, period=5)
            d.rsi = bt.indicators.RSI(d.close, period=14)
            d.macd = bt.indicators.MACD(d.close)
            d.macd_line = d.macd.macd
            d.signal_line = d.macd.signal
            d.macd_hist = d.macd.macd - d.macd.signal  # 柱状图

    def log(self, msg, dt=None):
        pass  # 静默

    def notify_order(self, order):
        if order.status in [order.Completed]:
            d = order.data
            name = d._name
            if order.isbuy():
                self.buy_prices[name] = order.executed.price
                self.max_profits[name] = 0
                # 更新行业计数
                sector = self.stock_sector.get(name, '未知')
                self.sector_counts[sector] = self.sector_counts.get(sector, 0) + 1
            elif order.issell():
                if name in self.buy_prices:
                    del self.buy_prices[name]
                    if name in self.max_profits:
                        del self.max_profits[name]
                    # 减少行业计数
                    sector = self.stock_sector.get(name, '未知')
                    self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
                    # 冷却期
                    self.cooldown_until[name] = self.datas[0].datetime.date(0) + timedelta(days=self.p.cooldown_days)

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

    def get_position_size_by_score(self, score, total_value):
        """动态仓位：按评分决定仓位"""
        if score >= 90:
            pct = 0.18
        elif score >= 80:
            pct = 0.14
        else:
            pct = 0.10
        return pct

    def calc_signal_score(self, d):
        """v7评分：增加MACD+RSI确认"""
        score = 0
        price = d.close[0]
        ma = d.ma[0]
        atr = d.atr[0]
        vol = d.volume[0]
        vol_ma = d.vol_ma[0]
        rsi = d.rsi[0]
        macd_hist = d.macd_hist[0]
        macd_line = d.macd_line[0]

        if any(pd.isna(x) for x in [ma, atr, vol_ma, rsi, macd_hist, macd_line]):
            return 0

        # 1. 偏离度 (30分)
        deviation = abs(price - ma) / ma
        if deviation > self.p.max_deviation:
            return 0
        score += 30

        # 2. 站上MA20 (20分)
        if price >= ma:
            score += 20
        else:
            return 0

        # 3. 放量 (15分)
        if vol_ma > 0 and vol > vol_ma * self.p.volume_ratio:
            score += 15

        # 4. ATR波动率 (10分)
        if price > 0 and atr / price > self.p.atr_threshold:
            score += 10

        # 5. MA20斜率 (10分) - 必须>0
        try:
            ma_5ago = d.ma[-5]
            if pd.isna(ma_5ago) or ma_5ago == 0:
                return 0
            ma_slope = (ma - ma_5ago) / ma_5ago * 100
        except:
            return 0
        if ma_slope <= 0:
            return 0
        if ma_slope > 1:
            score += 10
        elif ma_slope > 0:
            score += 5

        # 6. RSI确认 (10分) - 不超买不超卖
        if 40 <= rsi <= 70:
            score += 10
        elif rsi > 70:
            return 0  # 超买不买

        # 7. MACD确认 (5分) - 柱状图为正
        if macd_hist > 0:
            score += 5

        return score

    def next(self):
        self.daily_values.append({
            'date': self.datas[0].datetime.date(0).isoformat(),
            'value': self.broker.getvalue(),
        })

        current_date = self.datas[0].datetime.date(0)

        # 大盘过滤（v7: MA5 > MA20）
        market_ok = True
        if self.p.market_filter:
            idx = self.datas[0]
            if hasattr(idx, 'ma5') and hasattr(idx, 'ma'):
                if not pd.isna(idx.ma5[0]) and not pd.isna(idx.ma[0]):
                    market_ok = idx.close[0] > idx.ma[0] and idx.ma5[0] > idx.ma[0]

        # 收集信号
        signals = []
        for i, d in enumerate(self.datas):
            if i == 0:
                continue
            name = d._name
            pos = self.getposition(d)

            # 已持仓 → 检查卖出
            if pos.size > 0:
                self._check_sell(d, name, pos)
                continue

            # 未持仓 → 检查买入
            if self.get_position_count() >= self.p.max_positions:
                continue

            # 冷却期
            if name in self.cooldown_until and current_date < self.cooldown_until[name]:
                continue

            # 行业限制
            sector = self.stock_sector.get(name, '未知')
            if self.sector_counts.get(sector, 0) >= self.p.max_per_sector:
                continue

            # 大盘过滤
            if not market_ok:
                continue

            # 评分
            score = self.calc_signal_score(d)
            if score >= 70:
                signals.append((d, name, score))

        # 按评分排序
        signals.sort(key=lambda x: x[2], reverse=True)
        for d, name, score in signals:
            if self.get_position_count() >= self.p.max_positions:
                break
            self._execute_buy(d, name, score)

    def _execute_buy(self, d, name, score):
        cash = self.broker.getcash()
        price = d.close[0]
        total_value = self.broker.getvalue()
        pct = self.get_position_size_by_score(score, total_value)
        max_amount = total_value * pct
        shares = int(max_amount / price / 100) * 100

        if shares <= 0 or shares * price > cash * 0.95:
            return

        self.buy(data=d, size=shares)

    def _check_sell(self, d, name, pos):
        price = d.close[0]
        buy_price = self.buy_prices.get(name, 0)
        if buy_price <= 0:
            return

        profit_pct = (price - buy_price) / buy_price
        ma = d.ma[0]
        atr = d.atr[0]

        if name not in self.max_profits:
            self.max_profits[name] = profit_pct
        else:
            self.max_profits[name] = max(self.max_profits[name], profit_pct)

        max_profit = self.max_profits[name]
        sell_reason = None

        # 1. ATR止损 (收紧到1.5倍)
        if not pd.isna(atr):
            stop_price = buy_price - self.p.atr_stop_multiplier * atr
            if price <= stop_price:
                sell_reason = f'ATR止损({profit_pct:.1%})'

        # 2. 移动止盈
        if sell_reason is None and max_profit >= self.p.take_profit_pct:
            if profit_pct <= max_profit - self.p.trailing_stop_pct:
                sell_reason = f'移动止盈(最高{max_profit:.1%})'

        # 3. 跌破MA20
        if sell_reason is None and not pd.isna(ma):
            if price < ma * 0.98:
                sell_reason = f'跌破MA20({profit_pct:.1%})'

        if sell_reason:
            self.sell(data=d, size=pos.size)


# ============================================================
# 运行
# ============================================================

def run():
    start_date = '20250101'
    end_date = '20260609'

    print("="*70)
    print("📊 Backtrader回测 v7 - 全面优化版")
    print("="*70)
    print(f"改进: MACD+RSI确认 | 动态仓位 | 行业分散 | 冷却10天 | 止损1.5×ATR")
    print("="*70)

    cerebro = bt.Cerebro()

    # 上证指数
    print("获取数据...")
    idx_df = fetch_index_data(start_date, end_date)
    if idx_df is not None and not idx_df.empty:
        idx = idx_df.rename(columns={'open':'开盘','high':'最高','low':'最低','close':'收盘','volume':'成交量'})
        cerebro.adddata(AkshareData(dataname=idx, name='上证指数'))
        print(f"  ✅ 上证指数: {len(idx)}条")

    # 个股
    for s in STOCK_POOL:
        df = fetch_stock_data(s['code'], start_date, end_date)
        if df is not None and not df.empty:
            cerebro.adddata(AkshareData(dataname=df, name=s['name']))
            print(f"  ✅ {s['name']}: {len(df)}条")

    cerebro.addstrategy(MA20StrategyV7)
    cerebro.broker.setcash(CONFIG['initial_cash'])
    cerebro.broker.addcommissioninfo(CNCommission(commission=CONFIG['commission'], stamp_tax=CONFIG['stamp_tax']))
    cerebro.broker.set_slippage_perc(CONFIG['slippage_pct'])

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.02, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    print("\n运行回测...")
    results = cerebro.run()
    strat = results[0]

    final_value = cerebro.broker.getvalue()
    total_return = (final_value - CONFIG['initial_cash']) / CONFIG['initial_cash']

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    returns = strat.analyzers.returns.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    total_trades = trades.get('total', {}).get('total', 0)
    won = trades.get('won', {}).get('total', 0)
    lost = trades.get('lost', {}).get('total', 0)
    win_rate = won / max(total_trades, 1)
    avg_won = trades.get('won', {}).get('pnl', {}).get('average', 0)
    avg_lost = abs(trades.get('lost', {}).get('pnl', {}).get('average', 1))
    profit_ratio = avg_won / max(avg_lost, 1)

    print("\n" + "="*70)
    print("📊 v7回测结果")
    print("="*70)
    print(f"{'初始资金':<20} {'¥{:,.0f}'.format(CONFIG['initial_cash']):>15}")
    print(f"{'最终权益':<20} {'¥{:,.0f}'.format(final_value):>15}")
    print(f"{'总收益率':<20} {total_return:>14.2%}")
    print(f"{'年化收益率':<20} {returns.get('rnorm100', 0):>14.2f}%")
    print(f"{'最大回撤':<20} {drawdown.max.drawdown:>14.2f}%")
    print(f"{'夏普比率':<20} {sharpe.get('sharperatio', 0) or 0:>14.2f}")
    print(f"{'总交易次数':<20} {total_trades:>15}")
    print(f"{'胜率':<20} {win_rate:>14.1%}")
    print(f"{'盈亏比':<20} {profit_ratio:>14.2f}")

    # 交易明细
    if strat.trade_log:
        print(f"\n📝 交易明细:")
        print(f"{'日期':<12} {'股票':<10} {'盈亏(含费)':>12}")
        print("-"*38)
        for t in strat.trade_log:
            emoji = '🟢' if t['pnlcomm'] > 0 else '🔴'
            print(f"{t['date']:<12} {t['stock']:<10} {emoji}{t['pnlcomm']:>+10,.0f}")

    # 生成报告
    generate_html(strat, final_value, CONFIG, sharpe, drawdown, returns, trades)

    return strat, final_value, sharpe, drawdown, returns, trades


def generate_html(strat, final_value, config, sharpe, drawdown, returns, trades):
    daily = strat.daily_values
    dates = [d['date'] for d in daily]
    values = [d['value'] for d in daily]

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

    trade_rows = ""
    for t in strat.trade_log:
        color = "#3fb950" if t['pnlcomm'] > 0 else "#f85149"
        emoji = "🟢" if t['pnlcomm'] > 0 else "🔴"
        trade_rows += f'<tr><td>{t["date"]}</td><td>{t["stock"]}</td><td style="color:{color};text-align:right;">{emoji} {t["pnlcomm"]:>+,.0f}</td></tr>'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>策略回测 v7</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;margin-bottom:20px}}
h1{{text-align:center;color:#58a6ff;margin-bottom:8px;font-size:28px}}
.subtitle{{text-align:center;color:#8b949e;margin-bottom:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
.metric{{background:#21262d;border-radius:8px;padding:14px;text-align:center}}
.metric .label{{color:#8b949e;font-size:11px;margin-bottom:4px}}
.metric .value{{font-size:22px;font-weight:bold}}
.positive{{color:#3fb950}}.negative{{color:#f85149}}.neutral{{color:#58a6ff}}
h2{{color:#58a6ff;margin-top:0;font-size:18px}}
table{{width:100%;border-collapse:collapse}}
th{{background:#21262d;padding:8px 10px;text-align:left;color:#8b949e;font-size:12px}}
td{{padding:6px 10px;border-bottom:1px solid #21262d;font-size:12px}}
.config{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:6px}}
.config-item{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #21262d}}
.config-item .key{{color:#8b949e}}
.changes{{background:#1c2128;border-left:3px solid #58a6ff;padding:12px 16px;border-radius:4px;margin:12px 0}}
.changes li{{margin:4px 0;font-size:13px}}
</style></head><body>
<h1>📊 策略回测报告 v7 - 全面优化版</h1>
<p class="subtitle">MA20+MACD+RSI | 动态仓位 | 行业分散 | 冷却10天 | 止损1.5×ATR</p>

<div class="changes">
<strong>v6→v7 改进：</strong>
<ul>
<li>✅ 增加MACD柱状图+RSI趋势确认，减少假突破</li>
<li>✅ 动态仓位：评分90+→18%，80-89→14%，70-79→10%</li>
<li>✅ 行业分散：每行业最多2只</li>
<li>✅ 冷却期5→10天，防震荡收割</li>
<li>✅ 止损收紧：ATR×2→ATR×1.5</li>
<li>✅ 大盘过滤强化：MA5>MA20</li>
</ul>
</div>

<div class="grid">
    <div class="metric"><div class="label">最终权益</div><div class="value {'positive' if total_return>0 else 'negative'}">¥{final_value:,.0f}</div></div>
    <div class="metric"><div class="label">总收益率</div><div class="value {'positive' if total_return>0 else 'negative'}">{total_return:+.2%}</div></div>
    <div class="metric"><div class="label">年化收益率</div><div class="value {'positive' if annual_return>0 else 'negative'}">{annual_return:+.1f}%</div></div>
    <div class="metric"><div class="label">最大回撤</div><div class="value negative">-{max_dd:.2f}%</div></div>
    <div class="metric"><div class="label">夏普比率</div><div class="value neutral">{sharpe_val:.2f}</div></div>
    <div class="metric"><div class="label">胜率</div><div class="value neutral">{win_rate:.1%}</div></div>
    <div class="metric"><div class="label">盈亏比</div><div class="value neutral">{profit_ratio:.2f}</div></div>
    <div class="metric"><div class="label">交易次数</div><div class="value neutral">{total_trades}</div></div>
</div>

<div class="card"><h2>📈 权益曲线</h2><div id="eq" style="height:400px"></div></div>
<div class="card"><h2>⚙️ 策略配置</h2>
<div class="config">
<div class="config-item"><span class="key">初始资金</span><span>¥{config['initial_cash']/10000:.0f}万</span></div>
<div class="config-item"><span class="key">最大持仓</span><span>{config['max_positions']}只</span></div>
<div class="config-item"><span class="key">动态仓位</span><span>90+→18%/80→14%/70→10%</span></div>
<div class="config-item"><span class="key">冷却期</span><span>{config['cooldown_days']}天</span></div>
<div class="config-item"><span class="key">止损</span><span>ATR×{config['atr_stop_multiplier']}</span></div>
<div class="config-item"><span class="key">放量阈值</span><span>{config['volume_ratio']}倍</span></div>
<div class="config-item"><span class="key">行业限制</span><span>每行业≤{config['max_per_sector']}只</span></div>
<div class="config-item"><span class="key">大盘过滤</span><span>MA5>MA20</span></div>
</div></div>

<div class="card"><h2>📝 交易明细</h2><table>
<tr><th>日期</th><th>股票</th><th>盈亏(含费)</th></tr>{trade_rows}
</table></div>

<script>
var c=echarts.init(document.getElementById('eq'));
c.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis'}},
grid:{{left:80,right:30,top:30,bottom:40}},
xAxis:{{type:'category',data:{json.dumps(dates)},axisLabel:{{color:'#8b949e',fontSize:10}}}},
yAxis:{{type:'value',axisLabel:{{color:'#8b949e',formatter:'¥{{value}}'}}}},
series:[{{type:'line',data:{json.dumps(values)},lineStyle:{{color:'#58a6ff',width:2}},itemStyle:{{color:'#58a6ff'}},
areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(88,166,255,0.25)'}},{{offset:1,color:'rgba(88,166,255,0.02)'}}])}},
showSymbol:false,
markLine:{{data:[{{yAxis:{config['initial_cash']},label:{{formatter:'初始',color:'#8b949e'}}}}],lineStyle:{{color:'#f85149',type:'dashed'}},silent:true}}}}]
}});
window.addEventListener('resize',()=>c.resize());
</script></body></html>"""

    path = "/usr/share/nginx/html/public/backtest_v7_report.html"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ 报告: {path}")


if __name__ == "__main__":
    run()
