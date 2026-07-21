"""共享订单模型 — 回测与实盘共用

状态机：
  PENDING → SUBMITTED → PARTIAL_FILLED → FILLED
                ↓              ↓
           CANCELLED       CANCELLED
                ↓
            REJECTED
"""
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime


class OrderStatus(Enum):
    """订单状态"""
    PENDING = 'PENDING'              # 待提交（本地生成）
    SUBMITTED = 'SUBMITTED'          # 已提交到券商
    PARTIAL_FILLED = 'PARTIAL_FILLED'  # 部分成交
    FILLED = 'FILLED'                # 全部成交
    CANCELLED = 'CANCELLED'          # 已撤单
    REJECTED = 'REJECTED'            # 被拒绝


class OrderType(Enum):
    """订单类型"""
    LIMIT = 'LIMIT'      # 限价单
    MARKET = 'MARKET'    # 市价单


@dataclass
class Order:
    """交易订单 — 回测与实盘共用

    回测模式下：broker_order_id 为空，status 直接从 PENDING 变为 FILLED
    实盘模式下：走完整状态机，券商返回 broker_order_id
    """
    # 基本信息
    ts_code: str                     # 股票代码，如 600519.SH
    action: str                      # BUY / SELL
    price: float                     # 委托价格
    shares: int                      # 委托数量

    # 类型与状态
    order_type: OrderType = OrderType.LIMIT
    status: OrderStatus = OrderStatus.PENDING

    # 时间
    created_at: str = ''             # 创建时间 (YYYY-MM-DD HH:MM:SS)
    submitted_at: str = ''           # 提交时间
    filled_at: str = ''              # 成交时间

    # 券商信息
    broker_order_id: str = ''        # 券商返回的订单号

    # 成交信息
    filled_price: float = 0.0        # 实际成交价
    filled_shares: int = 0           # 实际成交数量
    commission: float = 0.0          # 佣金
    slippage: float = 0.0            # 滑点

    # 元信息
    reason: str = ''                 # 下单原因
    signal_source: str = ''          # 信号来源 (macd/kdj/monitor/manual)
    execute_price: float = 0.0       # 预设执行价（止损单用），0 = 使用市场价

    # ---- 便捷属性 ----

    @property
    def is_buy(self) -> bool:
        return self.action == 'BUY'

    @property
    def is_sell(self) -> bool:
        return self.action == 'SELL'

    @property
    def is_terminal(self) -> bool:
        """是否已终结（不再变化）"""
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)

    @property
    def pending_shares(self) -> int:
        """待成交数量"""
        return self.shares - self.filled_shares

    # ---- 状态变更 ----

    def mark_submitted(self, broker_order_id: str = ''):
        """标记为已提交"""
        self.status = OrderStatus.SUBMITTED
        self.broker_order_id = broker_order_id
        self.submitted_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def mark_filled(self, price: float, shares: int, commission: float = 0.0):
        """标记为成交（全部或部分）"""
        self.filled_price = price
        self.filled_shares = shares
        self.commission = commission
        if shares >= self.shares:
            self.status = OrderStatus.FILLED
            self.filled_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            self.status = OrderStatus.PARTIAL_FILLED

    def mark_cancelled(self):
        self.status = OrderStatus.CANCELLED

    def mark_rejected(self, reason: str = ''):
        self.status = OrderStatus.REJECTED
        if reason:
            self.reason = reason

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        return {
            'ts_code': self.ts_code,
            'action': self.action,
            'order_type': self.order_type.value,
            'price': self.price,
            'shares': self.shares,
            'status': self.status.value,
            'created_at': self.created_at,
            'submitted_at': self.submitted_at,
            'filled_at': self.filled_at,
            'broker_order_id': self.broker_order_id,
            'filled_price': self.filled_price,
            'filled_shares': self.filled_shares,
            'commission': self.commission,
            'slippage': self.slippage,
            'reason': self.reason,
            'signal_source': self.signal_source,
            'execute_price': self.execute_price,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Order':
        data = data.copy()
        data['order_type'] = OrderType(data.get('order_type', 'LIMIT'))
        data['status'] = OrderStatus(data.get('status', 'PENDING'))
        return cls(**data)

    # ---- 兼容旧接口 ----

    @property
    def executed(self) -> bool:
        """兼容旧 Order.executed 属性"""
        return self.status == OrderStatus.FILLED

    @property
    def date(self) -> str:
        """兼容旧 Order.date 属性，返回创建日期"""
        return self.created_at[:10] if self.created_at else ''

    @date.setter
    def date(self, value: str):
        """兼容旧代码设置 date"""
        if value and not self.created_at:
            self.created_at = value

    @property
    def execute_date(self) -> str:
        """兼容旧 Order.execute_date 属性"""
        return self.filled_at[:10] if self.filled_at else ''

    @execute_date.setter
    def execute_date(self, value: str):
        """兼容旧代码设置 execute_date"""
        pass  # 新模型用 filled_at
