"""BacktestResult 模型 - 回测结果"""

from sqlalchemy import Column, Integer, String, Float, Date, Text, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class BacktestResult(Base):
    """回测结果表"""

    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)       # 主键
    strategy_name = Column(String(100), nullable=False)              # 策略名称
    strategy_desc = Column(Text)                                     # 策略描述
    start_date = Column(Date)                                        # 回测开始日期
    end_date = Column(Date)                                          # 回测结束日期

    # 收益指标
    total_return = Column(Float)                                     # 总收益率（%）
    annual_return = Column(Float)                                    # 年化收益率（%）
    benchmark_return = Column(Float)                                 # 基准收益率（%）
    excess_return = Column(Float)                                    # 超额收益率（%）

    # 风险指标
    max_drawdown = Column(Float)                                     # 最大回撤（%）
    sharpe_ratio = Column(Float)                                     # 夏普比率
    volatility = Column(Float)                                       # 波动率（%）
    win_rate = Column(Float)                                         # 胜率（%）

    # 交易统计
    trade_count = Column(Integer)                                    # 交易次数
    avg_holding_days = Column(Float)                                 # 平均持仓天数

    # 配置快照
    params_json = Column(Text)                                       # 策略参数 JSON
    created_at = Column(DateTime, server_default=func.now())         # 创建时间

    def __repr__(self):
        return f"<BacktestResult {self.strategy_name} ({self.start_date} ~ {self.end_date})>"
