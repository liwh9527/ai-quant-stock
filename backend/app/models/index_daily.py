"""IndexDaily 模型 - 指数日线行情"""

from sqlalchemy import Column, Integer, String, Float, Date, UniqueConstraint
from app.core.database import Base


class IndexDaily(Base):
    """指数日线行情表"""

    __tablename__ = "index_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False)           # 指数代码
    trade_date = Column(Date, nullable=False)              # 交易日期
    open = Column(Float)                                   # 开盘价
    high = Column(Float)                                   # 最高价
    low = Column(Float)                                    # 最低价
    close = Column(Float)                                  # 收盘价
    vol = Column(Float)                                    # 成交量
    amount = Column(Float)                                 # 成交额
    pct_chg = Column(Float)                                # 涨跌幅（%）

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_index_ts_date"),
    )

    def __repr__(self):
        return f"<IndexDaily {self.ts_code} {self.trade_date}>"
