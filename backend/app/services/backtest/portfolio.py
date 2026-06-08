"""投资组合管理"""
from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class Position:
    """单只股票持仓"""
    ts_code: str
    buy_price: float
    buy_date: str  # YYYYMMDD
    shares: int
    hold_days: int = 0

    def market_value(self, current_price: float) -> float:
        return current_price * self.shares

    def profit_pct(self, current_price: float) -> float:
        return (current_price - self.buy_price) / self.buy_price if self.buy_price else 0

    def update_hold_days(self):
        self.hold_days += 1

    def to_dict(self) -> dict:
        return {
            'ts_code': self.ts_code, 'buy_price': self.buy_price,
            'buy_date': self.buy_date, 'shares': self.shares,
            'hold_days': self.hold_days
        }


class Portfolio:
    """投资组合"""

    def __init__(self, initial_cash: float = 1000000):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.history: list = []  # [{'date': ..., 'value': ..., 'positions': ...}]

    def total_value(self, prices: Dict[str, float]) -> float:
        """总市值 = 现金 + 所有持仓市值"""
        pos_value = sum(
            pos.market_value(prices.get(pos.ts_code, pos.buy_price))
            for pos in self.positions.values()
        )
        return self.cash + pos_value

    def buy(self, ts_code: str, price: float, shares: int, date: str,
            commission: float = 0.0003) -> bool:
        """买入股票"""
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
        else:
            self.positions[ts_code] = Position(
                ts_code=ts_code, buy_price=price, buy_date=date, shares=shares
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
        if pos.shares <= 0:
            del self.positions[ts_code]
        return revenue

    def can_buy(self, price: float, shares: int, commission: float = 0.0003) -> bool:
        cost = price * shares * (1 + commission)
        return cost <= self.cash

    def has_position(self, ts_code: str) -> bool:
        return ts_code in self.positions

    def get_position(self, ts_code: str) -> Optional[Position]:
        return self.positions.get(ts_code)

    def daily_update(self, date: str, prices: Dict[str, float]):
        """每日更新：持仓天数+1，记录净值"""
        for pos in self.positions.values():
            pos.update_hold_days()
        self.history.append({
            'date': date,
            'value': self.total_value(prices),
            'cash': self.cash,
            'positions': {k: v.to_dict() for k, v in self.positions.items()}
        })

    def position_count(self) -> int:
        return len(self.positions)

    def to_dict(self) -> dict:
        return {
            'cash': self.cash,
            'positions': {k: v.to_dict() for k, v in self.positions.items()},
            'history': self.history
        }
