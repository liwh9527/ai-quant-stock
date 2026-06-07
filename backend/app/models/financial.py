"""FinancialIndicator 模型 - 财务指标"""

from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint, Index
from app.core.database import Base


class FinancialIndicator(Base):
    """财务指标表"""

    __tablename__ = "financial_indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)       # 主键
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)  # 股票代码
    ann_date = Column(Date)                                          # 公告日期
    end_date = Column(Date, nullable=False)                          # 报告期

    # 盈利能力
    roe = Column(Float)                                              # 净资产收益率（%）
    roa = Column(Float)                                              # 总资产收益率（%）
    gross_margin = Column(Float)                                     # 销售毛利率（%）
    net_margin = Column(Float)                                       # 销售净利率（%）

    # 成长能力
    revenue_yoy = Column(Float)                                      # 营收同比（%）
    net_profit_yoy = Column(Float)                                   # 净利润同比（%）

    # 估值
    pe = Column(Float)                                               # 市盈率
    pb = Column(Float)                                               # 市净率
    ps = Column(Float)                                               # 市销率

    # 负债
    debt_ratio = Column(Float)                                       # 资产负债率（%）
    current_ratio = Column(Float)                                    # 流动比率

    # 每股指标
    eps = Column(Float)                                              # 每股收益
    bvps = Column(Float)                                             # 每股净资产

    __table_args__ = (
        UniqueConstraint("ts_code", "end_date", name="uq_fin_ts_end"),
        Index("idx_fin_ts_end", "ts_code", "end_date"),
    )

    def __repr__(self):
        return f"<FinancialIndicator {self.ts_code} {self.end_date}>"
