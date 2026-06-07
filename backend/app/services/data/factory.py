"""数据源工厂

根据配置返回对应的数据源实例。
"""

import logging

from app.core.config import settings

from .base import DataSourceBase

logger = logging.getLogger(__name__)


def get_data_source() -> DataSourceBase:
    """根据 DATA_SOURCE_TYPE 配置返回数据源实例

    Returns:
        DataSourceBase 的具体实现实例

    Raises:
        ValueError: 未知的数据源类型
    """
    source_type = settings.DATA_SOURCE_TYPE

    if source_type == "tushare":
        from .tushare_source import TushareSource

        if not settings.TUSHARE_TOKEN:
            logger.warning("TUSHARE_TOKEN 未配置，数据源可能无法正常工作")
        return TushareSource(token=settings.TUSHARE_TOKEN)

    elif source_type == "akshare":
        from .akshare_source import AkShareSource

        return AkShareSource()

    else:
        raise ValueError(f"未知的数据源类型: {source_type}，可选值: tushare, akshare")
