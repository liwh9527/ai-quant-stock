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
        self.pause_remaining = 0  # 剩余暂停天数

    def run(self, config: Dict, start_date: str, end_date: str) -> BacktestResult:
        """执行回测"""
        self.result = BacktestResult()
        initial_cash = config.get('initial_cash', 1000000)
        self.portfolio = Portfolio(initial_cash)
        self.order_mgr = OrderManager()
        self.consecutive_losses = 0
        self.pause_remaining = 0

        cost_cfg = config.get('cost', {})
        commission = cost_cfg.get('commission', 0.0003)
        stamp_tax = cost_cfg.get('stamp_tax', 0.001)

        trade_dates = self.dm.get_trade_dates(start_date, end_date)

        for date in trade_dates:
            # 1. 大盘择时
            if not self._check_market_timing(config, date):
                prices = self._get_position_prices(date)
                self.portfolio.daily_update(date, prices)
                continue

            # 2. 风控检查（连亏暂停）
            if not self._check_risk_control(config, date):
                prices = self._get_position_prices(date)
                self.portfolio.daily_update(date, prices)
                continue

            # 3. 每日选股（只调用一次）
            risk_cfg = config.get('risk_control', {})
            max_pos = risk_cfg.get('max_positions', 3)
            screening_cfg = config.get('screening', {})
            candidates = self.screening.screen(date, screening_cfg, self.dm)
            candidate_codes = [c.get('ts_code') for c in candidates[:20]]

            self.result.screening_log.append({
                'date': date,
                'candidates': [{'ts_code': c.get('ts_code'), 'name': c.get('name')} for c in candidates[:5]]
            })

            # 4. 获取相关股票价格（持仓+候选）
            position_codes = list(self.portfolio.positions.keys())
            all_codes = list(set(position_codes + candidate_codes))
            open_prices, close_prices = self._get_prices(all_codes, date)

            # 5. 执行待处理订单（昨日生成的卖出单）
            executed = self.order_mgr.execute_pending(date, open_prices, close_prices)
            self._process_executed_orders(executed, date, commission, stamp_tax)

            # 6. 持仓检查（止损/断板）
            self._check_positions(config, date, close_prices, commission, stamp_tax)

            # 7. 生成买入订单
            available_slots = max_pos - self.portfolio.position_count()
            if available_slots > 0:
                entry_cfg = config.get('entry', {})
                sizing = entry_cfg.get('position_sizing', {'method': 'equal'})
                total_value = self.portfolio.total_value(close_prices)

                for stock in candidates[:available_slots]:
                    ts_code = stock.get('ts_code')
                    if ts_code and not self.portfolio.has_position(ts_code):
                        price = open_prices.get(ts_code, 0)
                        if price > 0:
                            shares = self._calc_shares(price, sizing, stock, total_value, max_pos)
                            if shares > 0 and self.portfolio.can_buy(price, shares, commission):
                                self.order_mgr.add_order(Order(
                                    ts_code=ts_code, action=Order.BUY,
                                    price=price, shares=shares,
                                    reason=stock.get('name', ts_code), date=date
                                ))

            # 8. 更新净值
            self.portfolio.daily_update(date, close_prices)

        # 计算指标
        self.result.metrics = self._calculate_metrics()
        self.result.equity_curve = self.portfolio.history

        return self.result

    def _process_executed_orders(self, executed: List[Order], date: str,
                                 commission: float, stamp_tax: float):
        """处理已执行的订单"""
        for order in executed:
            if order.action == Order.BUY:
                self.portfolio.buy(order.ts_code, order.execute_price, order.shares, date, commission)
                self.result.trades.append({
                    'date': date, 'ts_code': order.ts_code, 'name': order.reason,
                    'action': 'BUY', 'price': round(order.execute_price, 2), 'shares': order.shares,
                    'reason': '选股买入'
                })
            elif order.action == Order.SELL:
                old_pos = self.portfolio.get_position(order.ts_code)
                buy_price = old_pos.buy_price if old_pos else order.execute_price
                self.portfolio.sell(order.ts_code, order.execute_price, order.shares, date, commission, stamp_tax)
                pnl_pct = (order.execute_price - buy_price) / buy_price if buy_price > 0 else 0
                if pnl_pct < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0
                self.result.trades.append({
                    'date': date, 'ts_code': order.ts_code,
                    'action': 'SELL', 'price': round(order.execute_price, 2), 'shares': order.shares,
                    'reason': order.reason, 'pnl_pct': round(pnl_pct, 4)
                })

    def _check_market_timing(self, config: Dict, date: str) -> bool:
        """大盘择时"""
        timing_cfg = config.get('risk_control', {}).get('market_timing', {})
        if not timing_cfg.get('enabled', False):
            return True

        index_code = timing_cfg.get('index', '000001.SH')
        condition = timing_cfg.get('condition', 'close > ma5')

        end_date = date
        start_date = (datetime.strptime(date, '%Y%m%d') - timedelta(days=30)).strftime('%Y%m%d')
        index_data = self.dm.get_index_daily(index_code, start_date, end_date)

        if not index_data or len(index_data) < 5:
            return True

        closes = [d['close'] for d in index_data[-5:]]
        ma5 = sum(closes) / len(closes)
        current_close = index_data[-1]['close']

        if 'close > ma5' in condition:
            return current_close > ma5
        return True

    def _check_risk_control(self, config: Dict, date: str) -> bool:
        """风控检查：连亏暂停"""
        risk_cfg = config.get('risk_control', {})
        pause_cfg = risk_cfg.get('consecutive_loss_pause', {})
        if not pause_cfg.get('enabled', False):
            return True

        # 正在暂停中
        if self.pause_remaining > 0:
            self.pause_remaining -= 1
            return False

        threshold = pause_cfg.get('threshold', 3)
        pause_days = pause_cfg.get('pause_days', 1)
        if self.consecutive_losses >= threshold:
            self.pause_remaining = pause_days - 1  # 当天已跳过
            self.consecutive_losses = 0
            return False
        return True

    def _check_positions(self, config: Dict, date: str, prices: Dict,
                         commission: float, stamp_tax: float):
        """持仓检查：止损/断板卖出"""
        exit_cfg = config.get('exit', {})
        rules = exit_cfg.get('rules', [])

        for ts_code, pos in list(self.portfolio.positions.items()):
            # T+1：买入当天不能卖出
            if pos.hold_days < 1:
                continue

            current_price = prices.get(ts_code, pos.buy_price)

            for rule in rules:
                if rule.get('type') == 'stop_loss':
                    pct = rule.get('pct', -0.05)
                    stop_price = pos.buy_price * (1 + pct)
                    # 用当日最低价判断是否触发止损
                    day_data = self.dm.get_stock_price_on_date(ts_code, date)
                    low_price = day_data.get('low', current_price) if day_data else current_price
                    if low_price <= stop_price:
                        self.order_mgr.add_order(Order(
                            ts_code=ts_code, action=Order.SELL,
                            price=stop_price, shares=pos.shares,
                            execute_price=stop_price,  # 预设止损价
                            reason=f'止损 {pct:.0%}',
                            date=date
                        ))
                        break

                elif rule.get('type') == 'break_limit_up':
                    is_limit = self.dm.check_limit_up(ts_code, date)
                    if not is_limit:
                        self.order_mgr.add_order(Order(
                            ts_code=ts_code, action=Order.SELL,
                            price=current_price, shares=pos.shares,
                            reason='断板卖出', date=date
                        ))
                        break

    def _calc_shares(self, price: float, sizing: Dict, stock: Dict,
                     total_value: float, max_pos: int) -> int:
        """计算买入股数"""
        method = sizing.get('method', 'equal')

        if method == 'equal':
            amount = total_value / max_pos
        elif method == 'tiered':
            tiers = sizing.get('tiers', [])
            auction_pct = stock.get('auction_pct', 0)
            ratio = 1.0 / max_pos
            for tier in tiers:
                min_pct = tier.get('min_auction_pct', 0)
                if auction_pct >= min_pct:
                    ratio = tier.get('ratio', ratio)
                    break
            amount = total_value * ratio
        else:
            amount = total_value / max_pos

        shares = int(amount / price / 100) * 100
        return shares

    def _get_prices(self, codes: List[str], date: str):
        """获取指定股票的开收盘价"""
        if not codes:
            return {}, {}
        try:
            daily = self.dm.get_daily_for_date(codes, date)
            if not daily:
                return {}, {}
            open_prices = {k: v.get('open', 0) for k, v in daily.items()}
            close_prices = {k: v.get('close', 0) for k, v in daily.items()}
            return open_prices, close_prices
        except Exception:
            return {}, {}

    def _get_position_prices(self, date: str) -> Dict[str, float]:
        """获取当前持仓股票的价格"""
        prices = {}
        for ts_code in self.portfolio.positions:
            try:
                p = self.dm.get_stock_price_on_date(ts_code, date)
                if p:
                    prices[ts_code] = p['close']
            except Exception:
                pass
        return prices

    def _calculate_metrics(self) -> Dict:
        """计算回测指标"""
        if not self.portfolio.history:
            return {}

        values = [h['value'] for h in self.portfolio.history]
        initial = self.portfolio.initial_cash
        final = values[-1]

        total_return = (final - initial) / initial if initial > 0 else 0
        days = len(values)
        annual_return = (1 + total_return) ** (252 / max(days, 1)) - 1

        # 最大回撤
        peak = values[0]
        max_dd = 0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # 夏普比率
        sharpe = 0
        if len(values) > 1:
            daily_returns = []
            for i in range(1, len(values)):
                if values[i-1] > 0:
                    daily_returns.append((values[i] - values[i-1]) / values[i-1])
            if daily_returns:
                avg_ret = sum(daily_returns) / len(daily_returns)
                variance = sum((r - avg_ret) ** 2 for r in daily_returns) / len(daily_returns)
                std_ret = variance ** 0.5
                sharpe = (avg_ret * 252) / (std_ret * (252 ** 0.5)) if std_ret > 0 else 0

        # 胜率（用 pnl_pct 字段，非 buy_map）
        sell_trades = [t for t in self.result.trades if t['action'] == 'SELL']
        wins = sum(1 for t in sell_trades if t.get('pnl_pct', 0) > 0)
        win_rate = wins / len(sell_trades) if sell_trades else 0

        return {
            'total_return': round(total_return, 4),
            'annual_return': round(annual_return, 4),
            'max_drawdown': round(max_dd, 4),
            'sharpe_ratio': round(sharpe, 2),
            'win_rate': round(win_rate, 4),
            'trade_count': len(self.result.trades),
            'final_value': round(final, 2)
        }
