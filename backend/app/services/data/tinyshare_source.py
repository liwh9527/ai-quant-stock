"""TinyShare 数据源实现

使用 tinyshare（Tushare 兼容）获取 A 股数据，无频率限制。
"""

import logging
from datetime import date

import pandas as pd

from .base import DataSourceBase

logger = logging.getLogger(__name__)


class TinyShareSource(DataSourceBase):
    """TinyShare 数据源（Tushare 兼容，无频率限制）"""

    def __init__(self, token: str = ""):
        import tinyshare as ts
        if token:
            ts.set_token(token)
        self.pro = ts.pro_api()
        logger.info("TinyShare 数据源初始化完成")

    def get_stock_list(self) -> pd.DataFrame:
        df = self.pro.stock_basic(
            exchange='', list_status='L',
            fields='ts_code,symbol,name,area,industry,market,list_date'
        )
        logger.info(f"获取股票列表: {len(df)} 条")
        return df

    def get_daily_quotes(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        df = self.pro.daily(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # 统一日期格式
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"])

        # 按日期升序排列（tinyshare 返回的是倒序）
        df = df.sort_values("trade_date").reset_index(drop=True)

        logger.info(f"获取日线行情 {ts_code}: {len(df)} 条")
        return df

    def get_financial_indicators(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        df = self.pro.fina_indicator(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            fields='ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets,current_ratio,eps,bps'
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # 列名映射
        col_map = {
            "grossprofit_margin": "gross_margin",
            "netprofit_margin": "net_margin",
            "debt_to_assets": "debt_ratio",
            "bps": "bvps",
        }
        df = df.rename(columns=col_map)

        # 获取最新估值
        df_val = self.pro.daily_basic(
            ts_code=ts_code,
            start_date=end_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            fields='ts_code,pe,pb,ps'
        )
        pe = pb = ps = None
        if df_val is not None and not df_val.empty:
            pe = df_val.iloc[0].get("pe")
            pb = df_val.iloc[0].get("pb")
            ps = df_val.iloc[0].get("ps")

        df["pe"] = pe
        df["pb"] = pb
        df["ps"] = ps
        df["ts_code"] = ts_code

        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"])
        if "ann_date" not in df.columns:
            df["ann_date"] = None

        logger.info(f"获取财务指标 {ts_code}: {len(df)} 条")
        return df

    def get_index_daily(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        df = self.pro.index_daily(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            return pd.DataFrame()

        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"])

        # 按日期升序排列
        df = df.sort_values("trade_date").reset_index(drop=True)

        df["ts_code"] = ts_code
        logger.info(f"获取指数日线 {ts_code}: {len(df)} 条")
        return df
