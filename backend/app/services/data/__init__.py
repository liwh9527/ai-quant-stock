"""数据源接入层

提供统一的数据访问接口，支持 Tushare / AkShare 切换。

使用示例：
    from app.services.data import get_data_source, DataCache

    # 直接使用
    source = get_data_source()
    df = source.get_stock_list()

    # 带缓存
    cached = DataCache(source)
    df = cached.get_stock_list()
"""

from .base import DataSourceBase
from .factory import get_data_source
from .cache import DataCache
from .import_service import DataImportService

__all__ = [
    "DataSourceBase",
    "get_data_source",
    "DataCache",
    "DataImportService",
]
