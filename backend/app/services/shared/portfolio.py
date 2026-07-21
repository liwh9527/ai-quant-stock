"""共享投资组合模型 — 回测与实盘共用"""
from typing import Dict, Optional
from .position import Position


class Portfolio:
    """投资组合

    回测和实盘共用。买入时自动处理 T+0 冻结。
    """

    def __init__(self, initial_cash: float = 1000000):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.history: list = []

    # ---- 查询 ----

    def total_value(self, prices: Dict[str, float]) -> float:
        """总市值 = 现金 + 所有持仓市值"""
        pos_value = sum(
            pos.market_value(prices.get(pos.ts_code, pos.buy_price))
            for pos in self.positions.values()
        )
        return self.cash + pos_value

    def position_count(self) -> int:
        return len(self.positions)

    def has_position(self, ts_code: str) -> bool:
        return ts_code in self.positions

    def get_position(self, ts_code: str) -> Optional[Position]:
        return self.positions.get(ts_code)

    def can_buy(self, price: float, shares: int, commission: float = 0.0003) -> bool:
        """是否有足够资金买入"""
        cost = price * shares * (1 + commission)
        return cost <= self.cash

    def can_sell(self, ts_code: str, shares: int) -> bool:
        """是否有足够可卖持仓（T+1 检查）"""
        if ts_code not in self.positions:
            return False
        pos = self.positions[ts_code]
        if pos.available_shares < 0:
            return shares <= pos.shares  # 回测模式
        return shares <= pos.available_shares

    # ---- 交易 ----

    def buy(self, ts_code: str, price: float, shares: int, date: str,
            commission: float = 0.0003) -> bool:
        """买入股票，成功返回 True"""
        cost = price * shares * (1 + commission)
        if cost > self.cash:
            return False
        self.cash -= cost
        if ts_code in self.positions:
            # 加仓：合并持仓
            old = self.positions[ts_code]
            total_shares = old.shares + shares
            avg_price = (old.buy_price * old.shares + price * shares) / total_shares
            old.buy_price = avg_price
            old.shares = total_shares
            # T+0：新买入的部分不可卖
            if old.available_shares >= 0:
                pass  # available_shares 不变，新增部分冻结
        else:
            # 新建持仓，T+0：买入当日不可卖
            self.positions[ts_code] = Position(
                ts_code=ts_code,
                buy_price=price,
                buy_date=date,
                shares=shares,
                available_shares=0,  # T+0 冻结
            )
        return True

    def sell(self, ts_code: str, price: float, shares: int, date: str,
             commission: float = 0.0003, stamp_tax: float = 0.001) -> float:
        """卖出股票，返回实际收到的金额"""
        if ts_code not in self.positions:
            return 0
        pos = self.positions[ts_code]
        actual_shares = min(shares, pos.shares)
        revenue = price * actual_shares * (1 - commission - stamp_tax)
        self.cash += revenue
        pos.shares -= actual_shares
        if pos.available_shares >= 0:
            pos.available_shares = max(0, pos.available_shares - actual_shares)
        if pos.shares <= 0:
            del self.positions[ts_code]
        return revenue

    # ---- 每日更新 ----

    def daily_update(self, date: str, prices: Dict[str, float]):
        """每日更新：持仓天数+1，T+0 解冻，记录净值"""
        for pos in self.positions.values():
            pos.update_hold_days()
        self.history.append({
            'date': date,
            'value': self.total_value(prices),
            'cash': self.cash,
            'positions': {k: v.to_dict() for k, v in self.positions.items()}
        })

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        return {
            'initial_cash': self.initial_cash,
            'cash': self.cash,
            'positions': {k: v.to_dict() for k, v in self.positions.items()},
            'history': self.history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Portfolio':
        p = cls(initial_cash=data.get('initial_cash', 1000000))
        p.cash = data.get('cash', p.initial_cash)
        p.positions = {
            k: Position.from_dict(v) for k, v in data.get('positions', {}).items()
        }
        p.history = data.get('history', [])
        return p
