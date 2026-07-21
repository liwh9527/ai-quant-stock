"""执行引擎 — 信号 → 风控 → 订单 → Broker → 持仓

核心流程：
  1. 接收信号（来自 SignalGenerator / Monitor / 手动）
  2. 风控检查（RiskManager.check_buy / check_sell）
  3. 生成 Order
  4. 提交到 Broker
  5. 更新 Portfolio 持仓
  6. 记录交易日志

支持两种模式：
  - 自动模式：信号自动转订单并提交
  - 手动确认模式：信号展示，等用户确认后下单
"""
import logging
from typing import List, Dict, Optional, Callable
from datetime import datetime

from ..shared.order import Order, OrderStatus
from ..shared.position import Position
from ..shared.portfolio import Portfolio
from ..broker.base import BrokerBase, BrokerError, AccountInfo
from .risk_manager import RiskManager, RiskConfig, RiskCheckResult

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """交易执行引擎

    用法：
        engine = ExecutionEngine(broker, portfolio, risk_manager)
        await engine.start()

        # 接收信号
        orders = await engine.on_signal(signal)

        # 或手动下单
        order = await engine.buy('600519.SH', 1800.0, 100, reason='手动买入')

        await engine.stop()
    """

    def __init__(
        self,
        broker: BrokerBase,
        portfolio: Portfolio,
        risk_manager: Optional[RiskManager] = None,
        auto_execute: bool = True,
        on_order_update: Optional[Callable[[Order], None]] = None,
    ):
        self.broker = broker
        self.portfolio = portfolio
        self.risk_manager = risk_manager or RiskManager()
        self.auto_execute = auto_execute
        self.on_order_update = on_order_update  # 订单状态变更回调

        self._running = False
        self._orders: List[Order] = []           # 所有订单历史
        self._pending_signals: List[Dict] = []   # 待确认信号（手动模式）
        self._highest_prices: Dict[str, float] = {}  # 持仓期间最高价

    # ---- 生命周期 ----

    async def start(self):
        """启动引擎，连接 Broker"""
        if self._running:
            return
        connected = await self.broker.connect()
        if not connected:
            raise BrokerError("无法连接到 Broker")
        self._running = True

        # 同步初始持仓
        await self.sync_positions()
        logger.info("执行引擎已启动")

    async def stop(self):
        """停止引擎"""
        self._running = False
        await self.broker.disconnect()
        logger.info("执行引擎已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    # ---- 持仓同步 ----

    async def sync_positions(self):
        """从 Broker 同步持仓和账户信息到本地 Portfolio"""
        try:
            account = await self.broker.query_account()
            positions = await self.broker.query_positions()

            # 更新 Portfolio
            self.portfolio.positions.clear()
            for pos in positions:
                self.portfolio.positions[pos.ts_code] = pos
                # 初始化最高价
                if pos.ts_code not in self._highest_prices:
                    self._highest_prices[pos.ts_code] = pos.buy_price

            logger.info(f"同步持仓: {len(positions)} 只, 可用资金: {account.available_cash:.2f}")
        except BrokerError as e:
            logger.error(f"同步持仓失败: {e}")

    # ---- 信号处理 ----

    async def on_signal(self, signal: Dict) -> List[Order]:
        """处理交易信号

        Args:
            signal: {
                'ts_code': '600519.SH',
                'type': 'BUY' | 'SELL',
                'price': 1800.0,
                'strength': 0.65,  # 可选
                'reason': 'MACD golden cross',
                'source': 'macd',  # 信号来源
            }

        Returns:
            生成的订单列表（可能为空）
        """
        if not self._running:
            logger.warning("引擎未运行，忽略信号")
            return []

        ts_code = signal.get('ts_code', '')
        signal_type = signal.get('type', '').upper()
        price = signal.get('price', 0)
        reason = signal.get('reason', '')
        source = signal.get('source', 'signal')

        if signal_type == 'BUY':
            return await self._handle_buy_signal(ts_code, price, reason, source)
        elif signal_type == 'SELL':
            return await self._handle_sell_signal(ts_code, price, reason, source)
        else:
            logger.warning(f"未知信号类型: {signal_type}")
            return []

    async def _handle_buy_signal(
        self, ts_code: str, price: float, reason: str, source: str
    ) -> List[Order]:
        """处理买入信号"""
        # 计算买入数量（等权分配）
        account = await self.broker.query_account()
        max_amount = account.total_assets * self.risk_manager.config.max_single_position_pct
        shares = int(max_amount / price / 100) * 100  # 取整到 100 股
        if shares <= 0:
            logger.info(f"计算买入数量为 0，跳过: {ts_code}")
            return []

        order = Order(
            ts_code=ts_code,
            action='BUY',
            price=price,
            shares=shares,
            reason=reason,
            signal_source=source,
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )

        # 风控检查
        check = self.risk_manager.check_buy(
            order=order,
            portfolio=self.portfolio,
            current_price=price,
            account_total=account.total_assets,
        )

        if not check:
            logger.info(f"风控拒绝买入 {ts_code}: {check}")
            order.mark_rejected(str(check))
            self._orders.append(order)
            self._notify_order(order)
            return []

        if self.auto_execute:
            return await self._execute_order(order)
        else:
            # 手动模式：放入待确认列表
            order.status = OrderStatus.PENDING
            self._pending_signals.append({'signal': {'ts_code': ts_code, 'type': 'BUY', 'price': price}, 'order': order})
            logger.info(f"买入信号待确认: {ts_code} {shares}股@{price}")
            return [order]

    async def _handle_sell_signal(
        self, ts_code: str, price: float, reason: str, source: str
    ) -> List[Order]:
        """处理卖出信号"""
        if not self.portfolio.has_position(ts_code):
            logger.info(f"无持仓，忽略卖出信号: {ts_code}")
            return []

        pos = self.portfolio.get_position(ts_code)
        shares = pos.available_shares if pos.available_shares > 0 else pos.shares
        if shares <= 0:
            logger.info(f"可卖数量为 0（T+1冻结），跳过: {ts_code}")
            return []

        order = Order(
            ts_code=ts_code,
            action='SELL',
            price=price,
            shares=shares,
            reason=reason,
            signal_source=source,
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )

        # 风控检查
        check = self.risk_manager.check_sell(order=order, portfolio=self.portfolio)
        if not check:
            logger.info(f"风控拒绝卖出 {ts_code}: {check}")
            order.mark_rejected(str(check))
            self._orders.append(order)
            self._notify_order(order)
            return []

        if self.auto_execute:
            return await self._execute_order(order)
        else:
            order.status = OrderStatus.PENDING
            self._pending_signals.append({'signal': {'ts_code': ts_code, 'type': 'SELL', 'price': price}, 'order': order})
            return [order]

    # ---- 手动下单 ----

    async def buy(self, ts_code: str, price: float, shares: int, reason: str = '手动买入') -> Optional[Order]:
        """手动买入"""
        order = Order(
            ts_code=ts_code, action='BUY', price=price, shares=shares,
            reason=reason, signal_source='manual',
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        account = await self.broker.query_account()
        check = self.risk_manager.check_buy(order, self.portfolio, price, account.total_assets)
        if not check:
            logger.warning(f"风控拒绝: {check}")
            order.mark_rejected(str(check))
            self._orders.append(order)
            return order
        return (await self._execute_order(order))[0] if self._execute_order else order

    async def sell(self, ts_code: str, price: float, shares: int, reason: str = '手动卖出') -> Optional[Order]:
        """手动卖出"""
        order = Order(
            ts_code=ts_code, action='SELL', price=price, shares=shares,
            reason=reason, signal_source='manual',
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        check = self.risk_manager.check_sell(order, self.portfolio)
        if not check:
            logger.warning(f"风控拒绝: {check}")
            order.mark_rejected(str(check))
            self._orders.append(order)
            return order
        return (await self._execute_order(order))[0] if self._execute_order else order

    # ---- 确认待执行信号（手动模式） ----

    async def confirm_order(self, order_index: int) -> Optional[Order]:
        """确认待执行的订单

        Args:
            order_index: 待确认信号的索引

        Returns:
            执行后的订单，或 None
        """
        if order_index < 0 or order_index >= len(self._pending_signals):
            return None
        item = self._pending_signals.pop(order_index)
        order = item['order']
        return (await self._execute_order(order))[0]

    def get_pending_signals(self) -> List[Dict]:
        """获取待确认信号"""
        return [
            {'index': i, 'ts_code': item['order'].ts_code, 'action': item['order'].action,
             'price': item['order'].price, 'shares': item['order'].shares,
             'reason': item['order'].reason}
            for i, item in enumerate(self._pending_signals)
        ]

    # ---- 订单执行 ----

    async def _execute_order(self, order: Order) -> List[Order]:
        """执行订单：提交到 Broker，更新 Portfolio"""
        try:
            # 提交到 Broker
            broker_id = await self.broker.submit_order(order)
            logger.info(f"订单已提交: {order.action} {order.ts_code} {order.shares}股@{order.price} [{broker_id}]")

            # 模拟成交（妙想模拟盘提交即成交）
            # 实盘需要监听回报回调
            order.mark_filled(order.price, order.shares, commission=order.price * order.shares * 0.0003)

            # 更新 Portfolio
            if order.is_buy:
                self.portfolio.buy(order.ts_code, order.filled_price, order.filled_shares,
                                   order.created_at[:10])
                self._highest_prices[order.ts_code] = order.filled_price
            elif order.is_sell:
                revenue = self.portfolio.sell(order.ts_code, order.filled_price, order.filled_shares,
                                              order.created_at[:10])
                # 记录盈亏
                pos = self.portfolio.get_position(order.ts_code)
                if not pos and order.ts_code in self._highest_prices:
                    del self._highest_prices[order.ts_code]

            self._orders.append(order)
            self._notify_order(order)
            return [order]

        except BrokerError as e:
            logger.error(f"订单执行失败: {e}")
            order.mark_rejected(str(e))
            self._orders.append(order)
            self._notify_order(order)
            return [order]

    # ---- 持仓风控扫描 ----

    async def scan_risk(self) -> List[Order]:
        """扫描所有持仓的止损/止盈，返回需要卖出的订单"""
        # 获取当前价格
        current_prices = {}
        for ts_code in self.portfolio.positions:
            quote = await self.broker.get_quote(ts_code)
            if quote:
                current_prices[ts_code] = quote.price
                # 更新最高价
                if ts_code in self._highest_prices:
                    self._highest_prices[ts_code] = max(self._highest_prices[ts_code], quote.price)
                else:
                    self._highest_prices[ts_code] = quote.price

        # 风控检查
        sell_orders = self.risk_manager.check_positions(
            self.portfolio, current_prices, self._highest_prices
        )

        # 执行卖出
        executed = []
        for order in sell_orders:
            result = await self._execute_order(order)
            executed.extend(result)

        return executed

    # ---- 状态查询 ----

    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """获取订单列表"""
        if status:
            return [o for o in self._orders if o.status == status]
        return self._orders

    def get_today_orders(self) -> List[Order]:
        """获取今日订单"""
        today = datetime.now().strftime('%Y-%m-%d')
        return [o for o in self._orders if o.created_at.startswith(today)]

    def get_status(self) -> Dict:
        """获取引擎状态"""
        return {
            'running': self._running,
            'auto_execute': self.auto_execute,
            'total_orders': len(self._orders),
            'pending_signals': len(self._pending_signals),
            'positions': self.portfolio.position_count(),
            'risk': self.risk_manager.to_dict(),
        }

    # ---- 内部工具 ----

    def _notify_order(self, order: Order):
        """通知订单状态变更"""
        if self.on_order_update:
            try:
                self.on_order_update(order)
            except Exception as e:
                logger.error(f"订单回调异常: {e}")
