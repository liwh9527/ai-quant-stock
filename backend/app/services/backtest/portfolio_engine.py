"""多股票组合回测引擎"""
from typing import Dict, List
from datetime import datetime, timedelta
from app.services.backtest.portfolio import Portfolio
from app.services.backtest.order import Order, OrderManager
from app.services.backtest.screening_engine import DailyScreeningEngine
from app.services.data.data_manager import DataManager


class BacktestResult:
    """回测结果"""
    def __init__(self):
        self.metrics: Dict = {}
        self.equity_curve: List[Dict] = []
        self.trades: List[Dict] = []
        self.screening_log: List[Dict] = []

    def to_dict(self) -> dict:
        return {
            'metrics': self.metrics,
            'equity_curve': self.equity_curve,
            'trades': self.trades,
            'screening_log': self.screening_log
        }


class PortfolioBacktestEngine:
    """多股票组合回测引擎"""

    def __init__(self, data_manager: DataManager):
        self.dm = data_manager
        self.screening = DailyScreeningEngine()
        self.portfolio: Portfolio = None
        self.order_mgr: OrderManager = None
        self.result: BacktestResult = None
        self.consecutive_losses = 0

    def run(self, config: Dict, start_date: str, end_date: str) -> BacktestResult:
        """执行回测"""
        self.result = BacktestResult()
        initial_cash = config.get('initial_cash', 1000000)
        self.portfolio = Portfolio(initial_cash)
        self.order_mgr = OrderManager()
        self.consecutive_losses = 0

        cost_cfg = config.get('cost', {})
        commission = cost_cfg.get('commission', 0.0003)
        stamp_tax = cost_cfg.get('stamp_tax', 0.001)

        trade_dates = self.dm.get_trade_dates(start_date, end_date)

        for date in trade_dates:
            # 1. 大盘择时
            if not self._check_market_timing(config, date):
                self.portfolio.daily_update(date, self._get_current_prices(date))
                continue

            # 2. 风控检查
            if not self._check_risk_control(config, date):
                self.portfolio.daily_update(date, self._get_current_prices(date))
                continue

            # 3. 获取当日价格
            open_prices, close_prices = self._get_prices(date)

            # 4. 执行待处理订单
            executed = self.order_mgr.execute_pending(date, open_prices, close_prices)
            for order in executed:
                if order.action == Order.BUY:
                    shares = order.shares
                    price = order.execute_price
                    self.portfolio.buy(order.ts_code, price, shares, date, commission)
                    self.result.trades.append({
                        'date': date, 'ts_code': order.ts_code,
                        'action': 'BUY', 'price': price, 'shares': shares,
                        'reason': order.reason
                    })
                elif order.action == Order.SELL:
                    price = order.execute_price
                    self.portfolio.sell(order.ts_code, price, order.shares, date, commission, stamp_tax)
                    self.result.trades.append({
                        'date': date, 'ts_code': order.ts_code,
                        'action': 'SELL', 'price': price, 'shares': order.shares,
                        'reason': order.reason
                    })

            # 5. 持仓检查（止损/断板）
            self._check_positions(config, date, close_prices, commission, stamp_tax)

            # 6. 每日选股 + 生成买入订单
            risk_cfg = config.get('risk_control', {})
            max_pos = risk_cfg.get('max_positions', 3)
            available_slots = max_pos - self.portfolio.position_count()

            if available_slots > 0:
                screening_cfg = config.get('screening', {})
                candidates = self.screening.screen(date, screening_cfg, self.dm)
                self.result.screening_log.append({
                    'date': date,
                    'candidates': [{'ts_code': c.get('ts_code'), 'name': c.get('name')} for c in candidates[:5]]
                })

                entry_cfg = config.get('entry', {})
                sizing = entry_cfg.get('position_sizing', {'method': 'equal'})

                for stock in candidates[:available_slots]:
                    ts_code = stock.get('ts_code')
                    if ts_code and not self.portfolio.has_position(ts_code):
                        price = close_prices.get(ts_code, 0)
                        if price > 0:
                            shares = self._calc_shares(price, sizing, stock, initial_cash, max_pos)
                            if shares > 0 and self.portfolio.can_buy(price, shares, commission):
                                self.order_mgr.add_order(Order(
                                    ts_code=ts_code, action=Order.BUY,
                                    price=price, shares=shares,
                                    reason='选股买入', date=date
                                ))

            # 7. 更新净值
            self.portfolio.daily_update(date, close_prices)

        # 计算指标
        self.result.metrics = self._calculate_metrics()
        self.result.equity_curve = self.portfolio.history

        return self.result

    def _check_market_timing(self, config: Dict, date: str) -> bool:
        """大盘择时"""
        timing_cfg = config.get('risk_control', {}).get('market_timing', {})
        if not timing_cfg.get('enabled', False):
            return True

        index_code = timing_cfg.get('index', '000001.SH')
        condition = timing_cfg.get('condition', 'close > ma5')

        # 获取指数数据
        end_date = date
        start_date = (datetime.strptime(date, '%Y%m%d') - timedelta(days=30)).strftime('%Y%m%d')
        index_data = self.dm.get_index_daily(index_code, start_date, end_date)

        if not index_data or len(index_data) < 5:
            return True  # 数据不足时默认通过

        # 计算 MA5
        closes = [d['close'] for d in index_data[-5:]]
        ma5 = sum(closes) / len(closes)
        current_close = index_data[-1]['close']

        if 'close > ma5' in condition:
            return current_close > ma5
        return True

    def _check_risk_control(self, config: Dict, date: str) -> bool:
        """风控检查"""
        risk_cfg = config.get('risk_control', {})
        pause_cfg = risk_cfg.get('consecutive_loss_pause', {})
        if not pause_cfg.get('enabled', False):
            return True

        threshold = pause_cfg.get('threshold', 3)
        if self.consecutive_losses >= threshold:
            return False
        return True

    def _check_positions(self, config: Dict, date: str, prices: Dict,
                         commission: float, stamp_tax: float):
        """持仓检查：止损/断板卖出"""
        exit_cfg = config.get('exit', {})
        rules = exit_cfg.get('rules', [])

        for ts_code, pos in list(self.portfolio.positions.items()):
            current_price = prices.get(ts_code, pos.buy_price)

            for rule in rules:
                if rule.get('type') == 'stop_loss':
                    pct = rule.get('pct', -0.05)
                    if pos.profit_pct(current_price) <= pct:
                        self.order_mgr.add_order(Order(
                            ts_code=ts_code, action=Order.SELL,
                            price=current_price, shares=pos.shares,
                            reason=f'止损 {pos.profit_pct(current_price):.1%}',
                            date=date
                        ))
                        break

                elif rule.get('type') == 'break_limit_up':
                    # 断板：前一日涨停但今日不涨停
                    if pos.hold_days >= 1:
                        is_limit = self.dm.check_limit_up(ts_code, date)
                        if not is_limit:
                            self.order_mgr.add_order(Order(
                                ts_code=ts_code, action=Order.SELL,
                                price=current_price, shares=pos.shares,
                                reason='断板卖出', date=date
                            ))
                            break

    def _calc_shares(self, price: float, sizing: Dict, stock: Dict,
                     initial_cash: float, max_pos: int) -> int:
        """计算买入股数"""
        method = sizing.get('method', 'equal')

        if method == 'equal':
            amount = initial_cash / max_pos
        elif method == 'tiered':
            tiers = sizing.get('tiers', [])
            ratio = 1.0 / max_pos
            for tier in tiers:
                # 简化处理：默认用等权
                pass
            amount = initial_cash * ratio / max_pos
        else:
            amount = initial_cash / max_pos

        shares = int(amount / price / 100) * 100  # 取整到100股
        return shares

    def _get_prices(self, date: str):
        """获取当日开收盘价"""
        stocks = self.dm.get_all_stocks()
        codes = [s['ts_code'] for s in stocks]
        daily = self.dm.get_daily_for_date(codes, date)
        open_prices = {k: v.get('open', 0) for k, v in daily.items()}
        close_prices = {k: v.get('close', 0) for k, v in daily.items()}
        return open_prices, close_prices

    def _get_current_prices(self, date: str) -> Dict[str, float]:
        """获取当前持仓股票的价格"""
        prices = {}
        for ts_code in self.portfolio.positions:
            p = self.dm.get_stock_price_on_date(ts_code, date)
            if p:
                prices[ts_code] = p['close']
        return prices

    def _calculate_metrics(self) -> Dict:
        """计算回测指标"""
        if not self.portfolio.history:
            return {}

        values = [h['value'] for h in self.portfolio.history]
        initial = self.portfolio.initial_cash
        final = values[-1]

        total_return = (final - initial) / initial
        days = len(values)
        annual_return = (1 + total_return) ** (252 / max(days, 1)) - 1

        # 最大回撤
        peak = values[0]
        max_dd = 0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd

        # 夏普比率（简化）
        if len(values) > 1:
            daily_returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
            avg_ret = sum(daily_returns) / len(daily_returns)
            std_ret = (sum((r - avg_ret) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
            sharpe = (avg_ret * 252) / (std_ret * (252 ** 0.5)) if std_ret > 0 else 0
        else:
            sharpe = 0

        # 胜率
        trades = self.result.trades
        sell_trades = [t for t in trades if t['action'] == 'SELL']
        buy_map = {}
        for t in trades:
            if t['action'] == 'BUY':
                buy_map[t['ts_code']] = t['price']
        wins = sum(1 for t in sell_trades if t['price'] > buy_map.get(t['ts_code'], t['price']))
        win_rate = wins / len(sell_trades) if sell_trades else 0

        return {
            'total_return': round(total_return, 4),
            'annual_return': round(annual_return, 4),
            'max_drawdown': round(max_dd, 4),
            'sharpe_ratio': round(sharpe, 2),
            'win_rate': round(win_rate, 4),
            'trade_count': len(trades),
            'final_value': round(final, 2)
        }
