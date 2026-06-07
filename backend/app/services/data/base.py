"""数据源基类定义

所有数据源实现必须继承此基类，确保接口统一。
"""

from abc import ABC, abstractmethod
from typing import Optional
from datetime import date

import pandas as pd


class DataSourceBase(ABC):
    """数据源基类，定义统一的数据访问接口"""

    @abstractmethod
    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表

        Returns:
            DataFrame，包含列: ts_code, symbol, name, area, industry, market, list_date
        """
        pass

    @abstractmethod
    def get_daily_quotes(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """获取日线行情

        Args:
            ts_code: 股票代码，如 "000001.SZ"
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame，包含列: ts_code, trade_date, open, high, low, close,
                              pre_close, change, pct_chg, vol, amount
        """
        pass

    @abstractmethod
    def get_financial_indicators(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """获取财务指标

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame，包含列: ts_code, ann_date, end_date, roe, roa,
                              gross_margin, net_margin, revenue_yoy,
                              net_profit_yoy, pe, pb, ps, debt_ratio,
                              current_ratio, eps, bvps
        """
        pass

    @abstractmethod
    def get_index_daily(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """获取指数日线（用于基准对比）

        Args:
            ts_code: 指数代码，如 "000300.SH"（沪深300）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame，包含列: ts_code, trade_date, open, high, low,
                              close, vol, amount
        """
        pass
