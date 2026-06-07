"""策略回测服务

集成 Backtrader 引擎，支持 AI 生成的策略配置自动回测。

使用示例：
    from app.services.backtest import BacktestEngine

    engine = BacktestEngine(
        strategy_config=strategy_config,
        ts_code="000001.SZ",
        start_date="2020-01-01",
        end_date="2024-12-31",
    )
    engine.setup(stock_df, benchmark_df)
    result = engine.run()
"""

from .engine import BacktestEngine
from .strategy import AIStrategy

__all__ = ["BacktestEngine", "AIStrategy"]
