#!/usr/bin/env python3
"""
Backtrader回测 v14 - 综合优化
v13 → v14 改进：
1. 提高资金利用率：3只→4只，仓位22%/14%→25%/18%
2. 市场状态识别：波动率聚类判断牛/熊/震荡，熊市不开仓
3. 动态排除问题股：连续亏2次+总亏损>0→暂停30天
4. 缩短冷却期：7天→3天
5. 放宽止盈：35%→40%
6. 个股ATR自适应止盈：高波动股止盈更宽松
"""

import backtrader as bt
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json


CONFIG = {
    'initial_cash': 1_000_000,
    'max_positions': 4,             # 3→4
    'position_pct_high': 0.25,      # 22%→25%
    'position_pct_low': 0.18,       # 14%→18%
    'target_volatility': 0.15,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'cooldown_days': 3,             # 7→3
    'market_filter': True,
    'ma_period': 20,
    'atr_period': 14,
    'volume_ratio': 1.2,
    'atr_threshold': 0.02,
    'max_deviation': 0.10,
    'take_profit_pct': 0.40,        # 35%→40%
    'trailing_stop_pct': 0.08,
    'atr_stop_multiplier': 1.5,
    'chandelier_atr_mult': 3,
    'top_n_sectors': 3,
    'sector_lookback': 20,
    'portfolio_drawdown_stop': 0.07,
    'adx_threshold': 15,
    'max_per_sector': 1,
    'circuit_breaker_days': 3,
    'blacklist_days': 30,           # 问题股暂停30天
}


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


class MA20StrategyV14(bt.Strategy):
    params = (
        ('ma_period', 15),
        ('atr_period', 14),
        ('volume_ratio', 1.2),
        ('atr_threshold', 0.02),
        ('max_deviation', 0.10),
        ('take_profit_pct', 0.40),
        ('trailing_stop_pct', 0.08),
        ('atr_stop_multiplier', 1.5),
        ('chandelier_atr_mult', 3),
        ('max_positions', 4),
        ('position_pct_high', 0.25),
        ('position_pct_low', 0.18),
        ('target_volatility', 0.15),
        ('cooldown_days', 3),
        ('market_filter', True),
        ('top_n_sectors', 3),
        ('sector_lookback', 20),
        ('portfolio_drawdown_stop', 0.07),
        ('adx_threshold', 15),
        ('max_per_sector', 1),
        ('circuit_breaker_days', 3),
        ('blacklist_days', 30),
    )

    def __init__(self):
        self.buy_prices = {}
        self.max_profits = {}
        self.highest_prices = {}
        self.cooldown_until = {}
        self.trade_log = []
        self.daily_values = []
        self.stock_sector = {s['name']: s['sector'] for s in STOCK_POOL}
        self.sector_counts = {}
        self.peak_value = CONFIG['initial_cash']
        self.circuit_breaker = False
        self.circuit_breaker_until = None
        # 问题股追踪
        self.consecutive_losses = {}
        self.total_pnl_by_stock = {}
        self.blacklist_until = {}

        for d in self.datas:
            d.ma = bt.indicators.SMA(d.close, period=self.p.ma_period)
            d.ma5 = bt.indicators.SMA(d.close, period=5)
            d.atr = bt.indicators.ATR(d, period=self.p.atr_period)
            d.vol_ma = bt.indicators.SMA(d.volume, period=5)
            d.rsi = bt.indicators.RSI(d.close, period=14)
            d.macd = bt.indicators.MACD(d.close)
            d.macd_line = d.macd.macd
            d.signal_line = d.macd.signal
            d.adx = bt.indicators.ADX(d, period=14)
            d.atr_ma = bt.indicators.SMA(d.atr, period=20)
            d.volatility = bt.indicators.StdDev(d.close, period=20) / d.close * (252 ** 0.5)

    def log(self, msg, dt=None):
        pass

    def notify_order(self, order):
        if order.status in [order.Completed]:
            d = order.data
            name = d._name
            if order.isbuy():
                self.buy_prices[name] = order.executed.price
                self.max_profits[name] = 0
                self.highest_prices[name] = order.executed.price
                sector = self.stock_sector.get(name, '未知')
                self.sector_counts[sector] = self.sector_counts.get(sector, 0) + 1
            elif order.issell():
                if name in self.buy_prices:
                    del self.buy_prices[name]
                    if name in self.max_profits:
                        del self.max_profits[name]
                    if name in self.highest_prices:
                        del self.highest_prices[name]
                    sector = self.stock_sector.get(name, '未知')
                    self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
                    self.cooldown_until[name] = self.datas[0].datetime.date(0) + timedelta(days=self.p.cooldown_days)

    def notify_trade(self, trade):
        if trade.isclosed:
            name = trade.data._name
            self.trade_log.append({
                'stock': name,
                'pnl': trade.pnl,
                'pnlcomm': trade.pnlcomm,
                'date': self.datas[0].datetime.date(0).isoformat(),
            })
            # 问题股追踪
            self.total_pnl_by_stock[name] = self.total_pnl_by_stock.get(name, 0) + trade.pnlcomm
            if trade.pnlcomm < 0:
                self.consecutive_losses[name] = self.consecutive_losses.get(name, 0) + 1
            else:
                self.consecutive_losses[name] = 0

            # 动态黑名单：连续亏2次 + 总亏损>0 → 暂停30天
            if (self.consecutive_losses.get(name, 0) >= 2 and
                self.total_pnl_by_stock.get(name, 0) < 0):
                self.blacklist_until[name] = self.datas[0].datetime.date(0) + timedelta(days=self.p.blacklist_days)

    def get_position_count(self):
        return len([d for d in self.datas if self.getposition(d).size > 0])

    def get_market_state(self):
        """市场状态识别：用波动率和趋势判断"""
        idx = self.datas[0]
        try:
            cur_vol = idx.volatility[0]
            ma5 = idx.ma5[0]
            ma = idx.ma[0]
            if pd.isna(cur_vol) or pd.isna(ma5) or pd.isna(ma):
                return 'unknown'

            # 波动率水平
            atr_cur = idx.atr[0]
            atr_avg = idx.atr_ma[0]
            vol_high = not pd.isna(atr_cur) and not pd.isna(atr_avg) and atr_avg > 0 and atr_cur > atr_avg * 1.3

            # 趋势方向
            trend_up = ma5 > ma

            if trend_up and not vol_high:
                return 'bull'       # 牛市：趋势上+低波动
            elif trend_up and vol_high:
                return 'volatile_up'  # 震荡上：趋势上+高波动
            elif not trend_up and vol_high:
                return 'bear'       # 熊市：趋势下+高波动
            else:
                return 'sideways'   # 震荡：趋势下+低波动
        except:
            return 'unknown'

    def get_position_pct(self, d, score):
        """不对称波动率 + 动量加权"""
        if score >= 90:
            base_pct = self.p.position_pct_high
        else:
            base_pct = self.p.position_pct_low

        try:
            cur_vol = d.volatility[0]
            if pd.isna(cur_vol) or cur_vol <= 0:
                return base_pct

            idx = self.datas[0]
            trend_up = True
            if hasattr(idx, 'ma5') and hasattr(idx, 'ma'):
                if not pd.isna(idx.ma5[0]) and not pd.isna(idx.ma[0]):
                    trend_up = idx.ma5[0] > idx.ma[0]

            vol_ratio = self.p.target_volatility / cur_vol
            if trend_up:
                ratio = max(0.8, min(1.2, vol_ratio))
            else:
                ratio = max(0.4, min(1.0, vol_ratio))

            return base_pct * ratio
        except:
            return base_pct

    def check_weekly_trend(self):
        idx = self.datas[0]
        try:
            ma_cur = idx.ma[0]
            ma_20ago = idx.ma[-20]
            if pd.isna(ma_cur) or pd.isna(ma_20ago) or ma_20ago == 0:
                return True
            return (ma_cur - ma_20ago) / ma_20ago > 0
        except:
            return True

    def get_sector_momentum(self):
        sector_returns = {}
        for sector in SECTORS:
            returns = []
            for i, d in enumerate(self.datas):
                if i == 0:
                    continue
                name = d._name
                if self.stock_sector.get(name) != sector:
                    continue
                try:
                    cur = d.close[0]
                    prev = d.close[-self.p.sector_lookback]
                    if not pd.isna(prev) and prev > 0:
                        returns.append((cur - prev) / prev)
                except:
                    pass
            if returns:
                sector_returns[sector] = np.mean(returns)
        return sector_returns

    def is_top_sector(self, stock_name):
        sector = self.stock_sector.get(stock_name)
        if not sector:
            return False
        sector_momentum = self.get_sector_momentum()
        if not sector_momentum:
            return True
        sorted_sectors = sorted(sector_momentum.items(), key=lambda x: x[1], reverse=True)
        top_sectors = [s[0] for s in sorted_sectors[:self.p.top_n_sectors]]
        return sector in top_sectors

    def calc_signal_score(self, d):
        score = 0
        price = d.close[0]
        ma = d.ma[0]
        atr = d.atr[0]
        vol = d.volume[0]
        vol_ma = d.vol_ma[0]
        rsi = d.rsi[0]
        macd_line = d.macd_line[0]
        signal_line = d.signal_line[0]

        if any(pd.isna(x) for x in [ma, atr, vol_ma, rsi, macd_line, signal_line]):
            return 0

        deviation = abs(price - ma) / ma
        if deviation > self.p.max_deviation:
            return 0
        score += 30

        if price >= ma:
            score += 20
        else:
            return 0

        if vol_ma > 0 and vol > vol_ma * self.p.volume_ratio:
            score += 15

        if price > 0 and atr / price > self.p.atr_threshold:
            score += 10

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

        if 40 <= rsi <= 70:
            score += 10
        elif rsi > 70:
            return 0

        macd_hist = macd_line - signal_line
        if macd_hist > 0:
            score += 5

        return score

    def next(self):
        current_value = self.broker.getvalue()
        current_date = self.datas[0].datetime.date(0)

        self.daily_values.append({
            'date': current_date.isoformat(),
            'value': current_value,
        })

        if current_value > self.peak_value:
            self.peak_value = current_value

        # 组合回撤熔断
        drawdown_from_peak = (self.peak_value - current_value) / self.peak_value
        if drawdown_from_peak >= self.p.portfolio_drawdown_stop:
            if not self.circuit_breaker:
                self.circuit_breaker = True
                self.circuit_breaker_until = current_date + timedelta(days=self.p.circuit_breaker_days)
                for i, d in enumerate(self.datas):
                    if i == 0:
                        continue
                    pos = self.getposition(d)
                    if pos.size > 0:
                        name = d._name
                        buy_price = self.buy_prices.get(name, 0)
                        if buy_price > 0 and d.close[0] > buy_price:
                            self.sell(data=d, size=pos.size)
                return
        else:
            if self.circuit_breaker and current_date >= self.circuit_breaker_until:
                self.circuit_breaker = False
                self.peak_value = current_value

        if self.circuit_breaker:
            return

        # 市场状态识别（v14新增）
        market_state = self.get_market_state()
        if market_state == 'bear':
            # 熊市不开新仓，但不强制清仓
            pass

        # 大盘过滤
        market_ok = True
        if self.p.market_filter:
            idx = self.datas[0]
            if hasattr(idx, 'ma5') and hasattr(idx, 'ma'):
                if not pd.isna(idx.ma5[0]) and not pd.isna(idx.ma[0]):
                    try:
                        idx_ma5ago = idx.ma[-5]
                        idx_slope = (idx.ma[0] - idx_ma5ago) / idx_ma5ago * 100 if not pd.isna(idx_ma5ago) else 0
                    except:
                        idx_slope = 0
                    market_ok = idx.close[0] > idx.ma[0] and idx.ma5[0] > idx.ma[0] and idx_slope > 0

        adx_ok = True
        idx = self.datas[0]
        if hasattr(idx, 'adx'):
            try:
                adx_val = idx.adx[0]
                if not pd.isna(adx_val):
                    adx_ok = adx_val >= self.p.adx_threshold
            except:
                pass

        weekly_ok = self.check_weekly_trend()

        # Chandelier Exit检查
        for i, d in enumerate(self.datas):
            if i == 0:
                continue
            name = d._name
            pos = self.getposition(d)
            if pos.size > 0:
                if name in self.highest_prices:
                    self.highest_prices[name] = max(self.highest_prices[name], d.close[0])
                self._check_sell(d, name, pos)

        # 买入信号
        signals = []
        for i, d in enumerate(self.datas):
            if i == 0:
                continue
            name = d._name
            pos = self.getposition(d)

            if pos.size > 0:
                continue
            if self.get_position_count() >= self.p.max_positions:
                continue
            if name in self.cooldown_until and current_date < self.cooldown_until[name]:
                continue
            # 黑名单检查（v14新增）
            if name in self.blacklist_until and current_date < self.blacklist_until[name]:
                continue
            if not market_ok or not adx_ok or not weekly_ok:
                continue
            # 熊市不开新仓
            if market_state == 'bear':
                continue
            sector = self.stock_sector.get(name, '未知')
            if self.sector_counts.get(sector, 0) >= self.p.max_per_sector:
                continue
            if not self.is_top_sector(name):
                continue

            score = self.calc_signal_score(d)
            if score >= 70:
                signals.append((d, name, score))

        signals.sort(key=lambda x: x[2], reverse=True)
        for d, name, score in signals:
            if self.get_position_count() >= self.p.max_positions:
                break
            self._execute_buy(d, name, score)

    def _execute_buy(self, d, name, score):
        cash = self.broker.getcash()
        price = d.close[0]
        total_value = self.broker.getvalue()
        pct = self.get_position_pct(d, score)
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
        highest = self.highest_prices.get(name, buy_price)

        if name not in self.max_profits:
            self.max_profits[name] = profit_pct
        else:
            self.max_profits[name] = max(self.max_profits[name], profit_pct)

        max_profit = self.max_profits[name]
        sell_reason = None

        # 1. Chandelier Exit
        if not pd.isna(atr):
            chandelier_stop = highest - self.p.chandelier_atr_mult * atr
            if price <= chandelier_stop and profit_pct > 0:
                sell_reason = f'Chandelier({profit_pct:.1%})'

        # 2. ATR止损
        if sell_reason is None and not pd.isna(atr):
            stop_price = buy_price - self.p.atr_stop_multiplier * atr
            if price <= stop_price:
                sell_reason = f'ATR止损({profit_pct:.1%})'

        # 3. 移动止盈（40%启动，8%回撤）- v14：ATR自适应
        if sell_reason is None and max_profit >= self.p.take_profit_pct:
            # 高波动股给更多空间
            trailing_pct = self.p.trailing_stop_pct
            try:
                if not pd.isna(atr) and price > 0:
                    atr_ratio = atr / price
                    if atr_ratio > 0.04:  # 高波动
                        trailing_pct = 0.10  # 给10%回撤空间
            except:
                pass
            if profit_pct <= max_profit - trailing_pct:
                sell_reason = f'移动止盈({max_profit:.1%}→{profit_pct:.1%})'

        # 4. 跌破MA20
        if sell_reason is None and not pd.isna(ma):
            if price < ma * 0.98:
                sell_reason = f'跌破MA20({profit_pct:.1%})'

        if sell_reason:
            self.sell(data=d, size=pos.size)


def run():
    start_date = '20250101'
    end_date = '20260609'

    print("="*70)
    print("📊 Backtrader回测 v14 - 综合优化")
    print("="*70)

    cerebro = bt.Cerebro()

    print("获取数据...")
    idx_df = fetch_index_data(start_date, end_date)
    if idx_df is not None and not idx_df.empty:
        idx = idx_df.rename(columns={'open':'开盘','high':'最高','low':'最低','close':'收盘','volume':'成交量'})
        cerebro.adddata(AkshareData(dataname=idx, name='上证指数'))
        print(f"  ✅ 上证指数: {len(idx)}条")

    for s in STOCK_POOL:
        df = fetch_stock_data(s['code'], start_date, end_date)
        if df is not None and not df.empty:
            cerebro.adddata(AkshareData(dataname=df, name=s['name']))
            print(f"  ✅ {s['name']}: {len(df)}条")

    cerebro.addstrategy(MA20StrategyV14)
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

    values = [d['value'] for d in strat.daily_values]
    peak = values[0]
    max_dd_calc = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd_calc:
            max_dd_calc = dd

    print("\n" + "="*70)
    print("📊 v14回测结果")
    print("="*70)
    print(f"{'初始资金':<20} {'¥{:,.0f}'.format(CONFIG['initial_cash']):>15}")
    print(f"{'最终权益':<20} {'¥{:,.0f}'.format(final_value):>15}")
    print(f"{'总收益率':<20} {total_return:>14.2%}")
    print(f"{'年化收益率':<20} {returns.get('rnorm100', 0):>14.2f}%")
    print(f"{'最大回撤':<20} {max_dd_calc*100:>14.2f}%")
    print(f"{'夏普比率':<20} {sharpe.get('sharperatio', 0) or 0:>14.2f}")
    print(f"{'总交易次数':<20} {total_trades:>15}")
    print(f"{'胜率':<20} {win_rate:>14.1%}")
    print(f"{'盈亏比':<20} {profit_ratio:>14.2f}")

    if strat.trade_log:
        print(f"\n📝 交易明细:")
        for t in strat.trade_log:
            emoji = '🟢' if t['pnlcomm'] > 0 else '🔴'
            print(f"  {t['date']:<12} {t['stock']:<10} {emoji}{t['pnlcomm']:>+10,.0f}")

    generate_html(strat, final_value, CONFIG, sharpe, drawdown, returns, trades, max_dd_calc)


def generate_html(strat, final_value, config, sharpe, drawdown, returns, trades, max_dd_calc):
    daily = strat.daily_values
    dates = [d['date'] for d in daily]
    values = [d['value'] for d in daily]

    total_return = (final_value - config['initial_cash']) / config['initial_cash']
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

    annual_ok = annual_return >= 50
    dd_ok = max_dd_calc * 100 <= 10

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>策略回测 v14</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;margin-bottom:20px}}
h1{{text-align:center;color:#58a6ff;margin-bottom:8px;font-size:28px}}
.subtitle{{text-align:center;color:#8b949e;margin-bottom:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}}
.metric{{background:#21262d;border-radius:8px;padding:14px;text-align:center}}
.metric .label{{color:#8b949e;font-size:11px;margin-bottom:4px}}
.metric .value{{font-size:20px;font-weight:bold}}
.positive{{color:#3fb950}}.negative{{color:#f85149}}.neutral{{color:#58a6ff}}
h2{{color:#58a6ff;margin-top:0;font-size:18px}}
table{{width:100%;border-collapse:collapse}}
th{{background:#21262d;padding:8px 10px;text-align:left;color:#8b949e;font-size:12px}}
td{{padding:6px 10px;border-bottom:1px solid #21262d;font-size:12px}}
.changes{{background:#1c2128;border-left:3px solid #00e676;padding:12px 16px;border-radius:4px;margin:12px 0}}
.changes li{{margin:4px 0;font-size:13px}}
.compare{{display:grid;grid-template-columns:repeat(9,1fr);gap:4px;margin:16px 0}}
.compare-item{{background:#21262d;border-radius:6px;padding:6px;text-align:center}}
.compare-item .ver{{color:#8b949e;font-size:8px;margin-bottom:3px}}
.compare-item .val{{font-size:12px;font-weight:bold}}
.best{{border:2px solid #3fb950}}
.target{{background:#1c2128;border:2px solid #ff9800;border-radius:12px;padding:16px;margin:16px 0;text-align:center}}
.target .title{{color:#ff9800;font-size:16px;font-weight:bold;margin-bottom:8px}}
.target .status{{font-size:18px}}
</style></head><body>
<h1>📊 策略回测报告 v14 - 综合优化</h1>
<p class="subtitle">资金利用率↑ | 市场状态识别 | 问题股排除 | 冷却3天 | 止盈40%</p>

<div class="target">
<div class="title">🎯 目标达成</div>
<div class="status">
年化>50%: {'✅' if annual_ok else '❌'} ({annual_return:.1f}%) &nbsp;|&nbsp;
回撤<10%: {'✅' if dd_ok else '❌'} ({max_dd_calc*100:.1f}%)
</div>
</div>

<div class="compare">
<div class="compare-item"><div class="ver">v6</div><div class="val positive">+77%</div></div>
<div class="compare-item"><div class="ver">v8</div><div class="val positive">+67%</div></div>
<div class="compare-item"><div class="ver">v10</div><div class="val positive">+75%</div></div>
<div class="compare-item"><div class="ver">v11</div><div class="val positive">+63%</div></div>
<div class="compare-item"><div class="ver">v12</div><div class="val positive">+39%</div></div>
<div class="compare-item"><div class="ver">v13</div><div class="val positive">+51%</div></div>
<div class="compare-item best"><div class="ver">v14</div><div class="val {'positive' if total_return>0 else 'negative'}">{total_return:+.0%}</div></div>
<div class="compare-item"><div class="ver">目标年化</div><div class="val neutral">>50%</div></div>
<div class="compare-item"><div class="ver">目标回撤</div><div class="val neutral"><10%</div></div>
</div>

<div class="changes">
<strong>v13 → v14 改进：</strong>
<ul>
<li>🔥 资金利用率：3只→4只，仓位22%/14%→25%/18%</li>
<li>🔥 市场状态识别：波动率+趋势判断牛/熊/震荡，熊市不开仓</li>
<li>🔥 动态问题股排除：连续亏2次+总亏损→暂停30天</li>
<li>🔥 冷却期缩短：7天→3天</li>
<li>🔥 止盈放宽：35%→40%，高波动股给10%回撤空间</li>
</ul>
</div>

<div class="grid">
    <div class="metric"><div class="label">最终权益</div><div class="value {'positive' if total_return>0 else 'negative'}">¥{final_value:,.0f}</div></div>
    <div class="metric"><div class="label">总收益率</div><div class="value {'positive' if total_return>0 else 'negative'}">{total_return:+.2%}</div></div>
    <div class="metric"><div class="label">年化收益率</div><div class="value {'positive' if annual_ok else 'negative'}">{annual_return:+.1f}%</div></div>
    <div class="metric"><div class="label">最大回撤</div><div class="value {'positive' if dd_ok else 'negative'}">{max_dd_calc*100:.2f}%</div></div>
    <div class="metric"><div class="label">夏普比率</div><div class="value neutral">{sharpe_val:.2f}</div></div>
    <div class="metric"><div class="label">胜率</div><div class="value neutral">{win_rate:.1%}</div></div>
    <div class="metric"><div class="label">盈亏比</div><div class="value neutral">{profit_ratio:.2f}</div></div>
    <div class="metric"><div class="label">交易次数</div><div class="value neutral">{total_trades}</div></div>
</div>

<div class="card"><h2>📈 权益曲线</h2><div id="eq" style="height:400px"></div></div>

<div class="card"><h2>📝 交易明细</h2><table>
<tr><th>日期</th><th>股票</th><th>盈亏(含费)</th></tr>{trade_rows}
</table></div>

<script>
var c=echarts.init(document.getElementById('eq'));
c.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis'}},
grid:{{left:80,right:30,top:30,bottom:40}},
xAxis:{{type:'category',data:{json.dumps(dates)},axisLabel:{{color:'#8b949e',fontSize:10}}}},
yAxis:{{type:'value',axisLabel:{{color:'#8b949e',formatter:'¥{{value}}'}}}},
series:[{{type:'line',data:{json.dumps(values)},lineStyle:{{color:'#00e676',width:2}},itemStyle:{{color:'#00e676'}},
areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(0,230,118,0.25)'}},{{offset:1,color:'rgba(0,230,118,0.02)'}}])}},
showSymbol:false,
markLine:{{data:[{{yAxis:{config['initial_cash']},label:{{formatter:'初始',color:'#8b949e'}}}}],lineStyle:{{color:'#f85149',type:'dashed'}},silent:true}}}}]
}});
window.addEventListener('resize',()=>c.resize());
</script></body></html>"""

    path = "/usr/share/nginx/html/public/backtest_v14_report.html"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ 报告: {path}")


if __name__ == "__main__":
    run()
