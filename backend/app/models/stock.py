"""Stock 模型 - 股票基础信息"""

from sqlalchemy import Column, String, Date, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Stock(Base):
    """股票基础信息表"""

    __tablename__ = "stocks"

    ts_code = Column(String(20), primary_key=True)          # 股票代码（如 000001.SZ）
    symbol = Column(String(10), nullable=False)              # 股票代码（如 000001）
    name = Column(String(50), nullable=False)                # 股票名称
    area = Column(String(20))                                # 地域
    industry = Column(String(50))                            # 所属行业
    market = Column(String(10))                              # 市场（主板/创业板/科创板）
    list_date = Column(Date)                                 # 上市日期
    delist_date = Column(Date)                               # 退市日期（NULL = 未退市）
    is_hs = Column(String(10))                               # 是否沪深港通
    created_at = Column(DateTime, server_default=func.now()) # 创建时间
    updated_at = Column(                                     # 更新时间
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<Stock {self.ts_code} {self.name}>"
