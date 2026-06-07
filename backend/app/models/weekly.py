"""WeeklyQuote 模型 - 周线行情"""

from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint
from app.core.database import Base


class WeeklyQuote(Base):
    """周线行情表"""

    __tablename__ = "weekly_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)       # 主键
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)  # 股票代码
    trade_date = Column(Date, nullable=False)                        # 交易日期
    open = Column(Float)                                             # 开盘价
    high = Column(Float)                                             # 最高价
    low = Column(Float)                                              # 最低价
    close = Column(Float)                                            # 收盘价
    vol = Column(Float)                                              # 成交量（手）
    amount = Column(Float)                                           # 成交额（千元）

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_weekly_ts_date"),
    )

    def __repr__(self):
        return f"<WeeklyQuote {self.ts_code} {self.trade_date}>"
