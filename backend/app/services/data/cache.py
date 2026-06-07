"""数据缓存层

对数据源调用进行内存缓存，减少重复 API 请求。
"""

import hashlib
import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd

from .base import DataSourceBase

logger = logging.getLogger(__name__)


class DataCache(DataSourceBase):
    """数据缓存装饰层，包装 DataSourceBase 实现缓存逻辑"""

    def __init__(self, source: DataSourceBase, max_size: int = 256):
        self.source = source
        self._cache: dict[str, pd.DataFrame] = {}
        self._max_size = max_size
        logger.info(f"数据缓存层初始化，最大缓存条数: {max_size}")

    def _make_key(self, method: str, *args) -> str:
        """生成缓存键"""
        parts = [method] + [str(a) for a in args]
        return hashlib.md5("|".join(parts).encode()).hexdigest()

    def _evict_if_needed(self):
        """缓存淘汰：超过最大条数时清空最早的一半"""
        if len(self._cache) >= self._max_size:
            keys = list(self._cache.keys())
            for k in keys[: len(keys) // 2]:
                del self._cache[k]
            logger.info(f"缓存淘汰，当前条数: {len(self._cache)}")

    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表（带缓存）"""
        key = self._make_key("stock_list")
        if key not in self._cache:
            self._evict_if_needed()
            self._cache[key] = self.source.get_stock_list()
        return self._cache[key]

    def get_daily_quotes(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """获取日线行情（带缓存）"""
        key = self._make_key("daily", ts_code, start_date, end_date)
        if key not in self._cache:
            self._evict_if_needed()
            self._cache[key] = self.source.get_daily_quotes(
                ts_code, start_date, end_date
            )
        return self._cache[key]

    def get_financial_indicators(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """获取财务指标（带缓存）"""
        key = self._make_key("financial", ts_code, start_date, end_date)
        if key not in self._cache:
            self._evict_if_needed()
            self._cache[key] = self.source.get_financial_indicators(
                ts_code, start_date, end_date
            )
        return self._cache[key]

    def get_index_daily(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """获取指数日线（带缓存）"""
        key = self._make_key("index_daily", ts_code, start_date, end_date)
        if key not in self._cache:
            self._evict_if_needed()
            self._cache[key] = self.source.get_index_daily(
                ts_code, start_date, end_date
            )
        return self._cache[key]

    def clear(self):
        """清空所有缓存"""
        self._cache.clear()
        logger.info("缓存已清空")
