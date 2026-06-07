"""UserWatchlist 模型 - 自选股"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class UserWatchlist(Base):
    """自选股表"""

    __tablename__ = "user_watchlists"

    id = Column(Integer, primary_key=True, autoincrement=True)       # 主键
    group_name = Column(String(50), nullable=False)                  # 分组名称
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)  # 股票代码
    sort_order = Column(Integer, default=0)                          # 排序顺序
    created_at = Column(DateTime, server_default=func.now())         # 创建时间

    def __repr__(self):
        return f"<UserWatchlist {self.group_name} {self.ts_code}>"
