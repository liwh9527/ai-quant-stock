"""数据库模型包

导出所有 ORM 模型，便于 Alembic 自动发现和统一引用。
"""

from app.models.stock import Stock
from app.models.daily import DailyQuote
from app.models.weekly import WeeklyQuote
from app.models.financial import FinancialIndicator
from app.models.signal import TradeSignal
from app.models.backtest import BacktestResult
from app.models.watchlist import UserWatchlist

__all__ = [
    "Stock",
    "DailyQuote",
    "WeeklyQuote",
    "FinancialIndicator",
    "TradeSignal",
    "BacktestResult",
    "UserWatchlist",
]
