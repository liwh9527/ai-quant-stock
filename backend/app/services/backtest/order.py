"""订单管理 — T+1 规则"""
from typing import List, Dict
from dataclasses import dataclass, field


@dataclass
class Order:
    """交易订单"""
    BUY = 'BUY'
    SELL = 'SELL'

    ts_code: str
    action: str  # BUY or SELL
    price: float
    shares: int
    reason: str = ''
    date: str = ''  # 订单生成日期
    execute_date: str = ''  # 实际执行日期
    executed: bool = False
    execute_price: float = 0

    def to_dict(self) -> dict:
        return {
            'ts_code': self.ts_code, 'action': self.action,
            'price': self.price, 'shares': self.shares,
            'reason': self.reason, 'date': self.date,
            'execute_date': self.execute_date, 'executed': self.executed,
            'execute_price': self.execute_price
        }


class OrderManager:
    """订单管理器，处理 T+1 规则"""

    def __init__(self):
        self.pending_orders: List[Order] = []
        self.executed_orders: List[Order] = []

    def add_order(self, order: Order):
        self.pending_orders.append(order)

    def execute_pending(self, date: str, open_prices: Dict[str, float],
                        close_prices: Dict[str, float]) -> List[Order]:
        """执行待处理订单
        买入：当日执行，用开盘价（竞价买入）
        卖出：当日执行，用收盘价（T+1 规则：买入当天不能卖出）
        """
        executed = []
        remaining = []

        for order in self.pending_orders:
            if order.action == Order.BUY:
                # 买入当日执行（竞价买入）
                price = open_prices.get(order.ts_code, order.price)
                order.execute_price = price
                order.execute_date = date
                order.executed = True
                executed.append(order)
            elif order.action == Order.SELL:
                # T+1：卖出订单的日期必须早于执行日期
                if date > order.date:
                    price = close_prices.get(order.ts_code, order.price)
                    order.execute_price = price
                    order.execute_date = date
                    order.executed = True
                    executed.append(order)
                else:
                    remaining.append(order)

        self.pending_orders = remaining
        self.executed_orders.extend(executed)
        return executed

    def get_pending_count(self) -> int:
        return len(self.pending_orders)

    def to_dict(self) -> dict:
        return {
            'pending': [o.to_dict() for o in self.pending_orders],
            'executed': [o.to_dict() for o in self.executed_orders]
        }
