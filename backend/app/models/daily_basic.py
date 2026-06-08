"""DailyBasic 模型 - 每日估值指标"""

from sqlalchemy import Column, Integer, String, Float, Date, UniqueConstraint
from app.core.database import Base


class DailyBasic(Base):
    """每日估值指标表（PE/PB/换手率/市值等）"""

    __tablename__ = "daily_basic"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False)           # 股票代码
    trade_date = Column(Date, nullable=False)              # 交易日期
    turnover_rate = Column(Float)                          # 换手率（%）
    turnover_rate_f = Column(Float)                        # 换手率（自由流通股）
    total_mv = Column(Float)                               # 总市值（万元）
    circ_mv = Column(Float)                                # 流通市值（万元）
    pe = Column(Float)                                     # 市盈率
    pb = Column(Float)                                     # 市净率
    ps = Column(Float)                                     # 市销率

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_basic_ts_date"),
    )

    def __repr__(self):
        return f"<DailyBasic {self.ts_code} {self.trade_date}>"
