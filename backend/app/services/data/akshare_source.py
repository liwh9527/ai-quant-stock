"""AkShare 数据源实现

使用 akshare 库获取 A 股数据（Tushare 备用方案）。
"""

import logging
from datetime import date

import pandas as pd

from .base import DataSourceBase

logger = logging.getLogger(__name__)


class AkShareSource(DataSourceBase):
    """AkShare 数据源"""

    def __init__(self):
        import akshare as ak
        self.ak = ak
        logger.info("AkShare 数据源初始化完成")

    def get_stock_list(self) -> pd.DataFrame:
        """调用 stock_info_a_code_name 获取股票列表"""
        df = self.ak.stock_info_a_code_name()
        # 统一列名为 ts_code 格式
        if "code" in df.columns:
            df = df.rename(columns={"code": "symbol", "name": "name"})
        # 添加 ts_code 列（akshare 不直接提供）
        if "ts_code" not in df.columns and "symbol" in df.columns:
            df["ts_code"] = df["symbol"].apply(self._symbol_to_ts_code)
        # 补充缺失列
        for col in ["area", "industry", "market", "list_date"]:
            if col not in df.columns:
                df[col] = None
        logger.info(f"获取股票列表: {len(df)} 条")
        return df

    def get_daily_quotes(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """调用 stock_zh_a_hist 获取日线行情"""
        symbol = ts_code.split(".")[0]
        df = self.ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="qfq",
        )
        if df.empty:
            return df

        # akshare 返回的列名是中文，统一为英文
        col_map = {
            "日期": "trade_date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "vol",
            "成交额": "amount",
            "涨跌幅": "pct_chg",
            "涨跌额": "change",
        }
        df = df.rename(columns=col_map)
        df["ts_code"] = ts_code
        # 统一日期格式
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
        # 补充 pre_close 列
        if "pre_close" not in df.columns:
            df["pre_close"] = df["close"].shift(1)
        logger.info(f"获取日线行情 {ts_code}: {len(df)} 条")
        return df

    def get_financial_indicators(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """获取财务指标（组合多个 akshare 接口）"""
        symbol = ts_code.split(".")[0]

        try:
            # 获取主要财务指标
            df_main = self.ak.stock_financial_abstract_ths(symbol=symbol)
        except Exception as e:
            logger.warning(f"获取财务指标失败 {ts_code}: {e}")
            return pd.DataFrame()

        if df_main.empty:
            return df_main

        # 尝试从主要指标中提取字段
        col_map = {
            "报告期": "end_date",
            "净资产收益率": "roe",
            "总资产报酬率": "roa",
            "销售毛利率": "gross_margin",
            "销售净利率": "net_margin",
            "营业总收入同比增长率": "revenue_yoy",
            "净利润同比增长率": "net_profit_yoy",
            "市盈率": "pe",
            "市净率": "pb",
            "市销率": "ps",
            "资产负债率": "debt_ratio",
            "流动比率": "current_ratio",
            "基本每股收益": "eps",
            "每股净资产": "bvps",
        }
        actual_rename = {k: v for k, v in col_map.items() if k in df_main.columns}
        df = df_main.rename(columns=actual_rename)
        df["ts_code"] = ts_code

        # 清理百分号字符串，转为 float
        pct_fields = [
            "roe", "roa", "gross_margin", "net_margin",
            "revenue_yoy", "net_profit_yoy", "debt_ratio",
        ]
        for field in pct_fields:
            if field in df.columns:
                df[field] = df[field].apply(self._parse_pct)

        # 清理数值字段
        num_fields = ["pe", "pb", "ps", "current_ratio", "eps", "bvps"]
        for field in num_fields:
            if field in df.columns:
                df[field] = pd.to_numeric(df[field], errors="coerce")

        # 日期处理
        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"])
        if "ann_date" not in df.columns:
            df["ann_date"] = None

        # 按日期过滤
        if "end_date" in df.columns:
            df = df[
                (df["end_date"] >= pd.Timestamp(start_date))
                & (df["end_date"] <= pd.Timestamp(end_date))
            ]

        logger.info(f"获取财务指标 {ts_code}: {len(df)} 条")
        return df

    def get_index_daily(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """调用 stock_zh_index_daily 获取指数日线"""
        symbol = ts_code.split(".")[0]
        df = self.ak.stock_zh_index_daily(symbol=f"sh{symbol}")
        if df.empty:
            return df

        # 统一列名
        col_map = {
            "date": "trade_date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "vol",
        }
        df = df.rename(columns=col_map)
        df["ts_code"] = ts_code

        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df = df[
                (df["trade_date"] >= pd.Timestamp(start_date))
                & (df["trade_date"] <= pd.Timestamp(end_date))
            ]

        if "amount" not in df.columns:
            df["amount"] = None

        logger.info(f"获取指数日线 {ts_code}: {len(df)} 条")
        return df

    @staticmethod
    def _parse_pct(val) -> float | None:
        """将百分号字符串转为 float，如 '5.25%' -> 5.25"""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        s = str(val).strip()
        if s.endswith("%"):
            s = s[:-1]
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _symbol_to_ts_code(symbol: str) -> str:
        """将纯数字代码转为 ts_code 格式（如 000001 -> 000001.SZ）"""
        if symbol.startswith(("6", "5")):
            return f"{symbol}.SH"
        return f"{symbol}.SZ"
