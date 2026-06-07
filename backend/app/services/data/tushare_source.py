"""Tushare 数据源实现

使用 Tushare Pro API 获取 A 股数据。
"""

import logging
from datetime import date

import pandas as pd
import tushare as ts

from .base import DataSourceBase

logger = logging.getLogger(__name__)


class TushareSource(DataSourceBase):
    """Tushare 数据源"""

    def __init__(self, token: str):
        self.pro = ts.pro_api(token)
        logger.info("Tushare 数据源初始化完成")

    def get_stock_list(self) -> pd.DataFrame:
        """调用 stock_basic 接口获取股票列表"""
        df = self.pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
        # 将 list_date 转为日期类型
        if not df.empty and "list_date" in df.columns:
            df["list_date"] = pd.to_datetime(df["list_date"], format="%Y%m%d")
        logger.info(f"获取股票列表: {len(df)} 条")
        return df

    def get_daily_quotes(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """调用 daily 接口获取日线行情"""
        df = self.pro.daily(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if not df.empty:
            # 统一日期格式
            df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        logger.info(f"获取日线行情 {ts_code}: {len(df)} 条")
        return df

    def get_financial_indicators(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """调用 fina_indicator 接口获取财务指标"""
        df = self.pro.fina_indicator(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            fields=(
                "ts_code,ann_date,end_date,roe,roe_waa,roa,grossprofit_margin,"
                "netprofit_margin,revenue_yoy,net_profit_yoy,pe_ttm,pb,ps_ttm,"
                "debt_to_assets,current_ratio,eps,bps"
            ),
        )
        if df.empty:
            return df

        # 统一日期格式
        for col in ["ann_date", "end_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], format="%Y%m%d")

        # 重命名列以匹配统一接口
        rename_map = {
            "roe_waa": "roe",
            "grossprofit_margin": "gross_margin",
            "netprofit_margin": "net_margin",
            "pe_ttm": "pe",
            "ps_ttm": "ps",
            "debt_to_assets": "debt_ratio",
            "bps": "bvps",
        }
        # 只重命名存在的列
        actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
        # 如果原始列名已经是目标名，跳过（如 roe 本身存在则不重命名 roe_waa 覆盖它）
        if "roe" in df.columns and "roe_waa" in df.columns:
            df = df.drop(columns=["roe"])
        df = df.rename(columns=actual_rename)

        logger.info(f"获取财务指标 {ts_code}: {len(df)} 条")
        return df

    def get_index_daily(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """调用 index_daily 接口获取指数日线"""
        df = self.pro.index_daily(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        logger.info(f"获取指数日线 {ts_code}: {len(df)} 条")
        return df
