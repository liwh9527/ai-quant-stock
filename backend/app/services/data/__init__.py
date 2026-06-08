"""数据源接入层

提供统一的数据访问接口，支持 Tushare / AkShare 切换。

使用示例：
    from app.services.data import get_data_source, DataCache, DataManager

    # 直接使用
    source = get_data_source()
    df = source.get_stock_list()

    # 带缓存
    cached = DataCache(source)
    df = cached.get_stock_list()

    # 回测用数据管理器（数据库优先 + API 补充）
    dm = DataManager()
    df = dm.get_daily("000001.SZ", "2024-01-01", "2024-06-30")
"""

from .base import DataSourceBase
from .factory import get_data_source
from .cache import DataCache
from .import_service import DataImportService
from .data_manager import DataManager

__all__ = [
    "DataSourceBase",
    "get_data_source",
    "DataCache",
    "DataImportService",
    "DataManager",
]
