"""策略回测服务层

基于 Backtrader 引擎，提供策略回测能力。
支持 AI 生成的策略配置自动转换为可执行策略。

使用示例：
    from app.services.backtest import BacktestEngine

    engine = BacktestEngine(strategy_config)
    result = engine.run(stock_df, benchmark_df)
"""

from .engine import BacktestEngine
from .strategy import AIStrategy

__all__ = ["BacktestEngine", "AIStrategy"]
