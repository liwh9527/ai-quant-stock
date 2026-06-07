"""TradeSignal 模型 - 交易信号"""

from sqlalchemy import Column, Integer, String, Float, Date, Text, ForeignKey, Index
from app.core.database import Base


class TradeSignal(Base):
    """交易信号表"""

    __tablename__ = "trade_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)       # 主键
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)  # 股票代码
    signal_date = Column(Date, nullable=False)                       # 信号日期
    signal_type = Column(String(10), nullable=False)                 # 信号类型：BUY / SELL
    strategy_name = Column(String(50))                               # 策略名称
    signal_source = Column(String(50))                               # 信号来源（MACD/KDJ/自定义）
    price = Column(Float)                                            # 信号价格
    strength = Column(Float)                                         # 信号强度（0-1）
    reason = Column(Text)                                            # 信号原因描述

    __table_args__ = (
        Index("idx_signal_ts_date", "ts_code", "signal_date"),
    )

    def __repr__(self):
        return f"<TradeSignal {self.ts_code} {self.signal_date} {self.signal_type}>"
