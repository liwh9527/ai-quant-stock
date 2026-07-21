"""共享持仓模型 — 回测与实盘共用"""
from dataclasses import dataclass


@dataclass
class Position:
    """单只股票持仓

    支持 T+1 规则：买入当日 available_shares = 0，次日起 = shares
    """
    ts_code: str                     # 股票代码
    buy_price: float                 # 买入均价
    buy_date: str                    # 首次买入日期 (YYYYMMDD)
    shares: int                      # 持仓数量
    hold_days: int = 0               # 持仓天数
    available_shares: int = -1       # 可卖数量，-1 表示与 shares 相同（回测兼容）

    # ---- 计算属性 ----

    @property
    def frozen_shares(self) -> int:
        """冻结数量（T+0 不可卖）"""
        if self.available_shares < 0:
            return 0  # 回测模式，不区分
        return self.shares - self.available_shares

    def market_value(self, current_price: float) -> float:
        """持仓市值"""
        return current_price * self.shares

    def profit_pct(self, current_price: float) -> float:
        """盈亏比例"""
        return (current_price - self.buy_price) / self.buy_price if self.buy_price else 0

    def profit_amount(self, current_price: float) -> float:
        """盈亏金额"""
        return (current_price - self.buy_price) * self.shares

    def update_hold_days(self):
        """持仓天数 +1，T+0 解冻"""
        self.hold_days += 1
        if self.available_shares < 0:
            pass  # 回测模式
        else:
            self.available_shares = self.shares  # 次日全部可卖

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        return {
            'ts_code': self.ts_code,
            'buy_price': self.buy_price,
            'buy_date': self.buy_date,
            'shares': self.shares,
            'hold_days': self.hold_days,
            'available_shares': self.available_shares if self.available_shares >= 0 else self.shares,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Position':
        data = data.copy()
        if 'available_shares' not in data:
            data['available_shares'] = data.get('shares', 0)
        return cls(**data)
