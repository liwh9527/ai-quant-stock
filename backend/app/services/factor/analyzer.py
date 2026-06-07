"""因子分析器

提供因子有效性分析功能：
- calc_ic: 计算信息系数（IC）
- calc_ir: 计算信息比率（IR）
- group_returns: 分组收益分析
- correlation: 因子相关性矩阵
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FactorAnalyzer:
    """因子分析器

    用于评估单个因子的有效性，包括 IC/IR 计算和分组收益分析。
    """

    def calc_ic(self, factor_values: pd.Series, returns: pd.Series) -> float:
        """计算信息系数（IC）

        IC = corr(因子值, 未来收益率)，衡量因子的预测能力。

        Args:
            factor_values: 因子值序列
            returns: 未来收益率序列

        Returns:
            IC 值，范围 [-1, 1]
        """
        # 对齐并去除 NaN
        df = pd.DataFrame({"factor": factor_values, "return": returns}).dropna()
        if len(df) < 5:
            return 0.0

        # 使用 Spearman 秩相关（更稳健）
        ic = df["factor"].corr(df["return"], method="spearman")
        return round(float(ic), 4) if not np.isnan(ic) else 0.0

    def calc_ic_series(
        self,
        df: pd.DataFrame,
        factor_col: str,
        return_col: str,
        date_col: str = "trade_date",
    ) -> pd.Series:
        """按日期计算 IC 序列

        Args:
            df: 包含因子值、收益率、日期的 DataFrame
            factor_col: 因子列名
            return_col: 收益率列名
            date_col: 日期列名

        Returns:
            按日期索引的 IC 序列
        """
        ic_list = []
        for date, group in df.groupby(date_col):
            ic = self.calc_ic(group[factor_col], group[return_col])
            ic_list.append({"date": date, "ic": ic})

        if not ic_list:
            return pd.Series(dtype=float)

        result = pd.DataFrame(ic_list).set_index("date")["ic"]
        return result

    def calc_ir(self, ic_series: pd.Series) -> float:
        """计算信息比率（IR）

        IR = mean(IC) / std(IC)，衡量因子预测的稳定性。

        Args:
            ic_series: IC 时间序列

        Returns:
            IR 值
        """
        if len(ic_series) < 2:
            return 0.0

        std = ic_series.std()
        if std == 0 or np.isnan(std):
            return 0.0

        ir = ic_series.mean() / std
        return round(float(ir), 4)

    def group_returns(
        self,
        df: pd.DataFrame,
        factor_col: str,
        return_col: str = "next_return",
        groups: int = 5,
    ) -> Dict:
        """分组收益分析

        按因子值将股票分为 N 组，计算每组的平均收益。

        Args:
            df: 包含因子值和未来收益率的 DataFrame
            factor_col: 因子列名
            return_col: 收益率列名
            groups: 分组数

        Returns:
            包含分组收益数据的字典
        """
        data = df[[factor_col, return_col]].dropna()
        if len(data) < groups * 2:
            return {"error": "数据量不足，无法进行分组分析"}

        try:
            data["group"] = pd.qcut(
                data[factor_col], groups, labels=False, duplicates="drop"
            )
        except ValueError:
            # 当值过于集中时，使用等距分组
            data["group"] = pd.cut(
                data[factor_col], groups, labels=False
            )

        group_stats = data.groupby("group")[return_col].agg(["mean", "std", "count"])
        group_stats = group_stats.reset_index()
        group_stats["group"] = group_stats["group"].astype(int) + 1  # 从 1 开始编号

        # 计算多头、空头、多空收益
        long_return = float(group_stats.iloc[-1]["mean"])  # 最高一组
        short_return = float(group_stats.iloc[0]["mean"])  # 最低一组
        long_short_return = long_return - short_return

        return {
            "groups": [
                {
                    "group": int(row["group"]),
                    "mean_return": round(float(row["mean"]), 4),
                    "std": round(float(row["std"]), 4) if not np.isnan(row["std"]) else 0,
                    "count": int(row["count"]),
                }
                for _, row in group_stats.iterrows()
            ],
            "long_return": round(long_return, 4),
            "short_return": round(short_return, 4),
            "long_short_return": round(long_short_return, 4),
        }

    def calc_factor_summary(
        self,
        df: pd.DataFrame,
        factor_col: str,
        return_col: str = "next_return",
        date_col: str = "trade_date",
        groups: int = 5,
    ) -> Dict:
        """计算因子综合分析结果

        整合 IC/IR 计算和分组收益分析。

        Args:
            df: 完整数据
            factor_col: 因子列名
            return_col: 收益率列名
            date_col: 日期列名
            groups: 分组数

        Returns:
            包含 ic、ir、ic_series、group_returns 的综合结果
        """
        # 按日期计算 IC 序列
        ic_series = self.calc_ic_series(df, factor_col, return_col, date_col)

        # 总体 IC
        overall_ic = self.calc_ic(df[factor_col], df[return_col])

        # IR
        ir = self.calc_ir(ic_series)

        # IC > 0 的比例
        ic_positive_ratio = round(
            float((ic_series > 0).mean()), 4
        ) if len(ic_series) > 0 else 0.0

        # 分组收益
        grp = self.group_returns(df, factor_col, return_col, groups)

        return {
            "ic": overall_ic,
            "ir": ir,
            "ic_positive_ratio": ic_positive_ratio,
            "ic_series": [
                {"date": str(date), "ic": round(float(v), 4)}
                for date, v in ic_series.items()
            ],
            "group_returns": grp,
        }

    def calc_correlation(self, df: pd.DataFrame, factor_cols: List[str]) -> Dict:
        """计算因子间相关性矩阵

        Args:
            df: 包含各因子列的 DataFrame
            factor_cols: 因子列名列表

        Returns:
            相关性矩阵（字典形式）
        """
        valid_cols = [c for c in factor_cols if c in df.columns]
        if len(valid_cols) < 2:
            return {"error": "可用因子不足，无法计算相关性"}

        corr_matrix = df[valid_cols].corr(method="spearman")

        result = {
            "factors": valid_cols,
            "matrix": [
                [round(float(corr_matrix.iloc[i, j]), 4) for j in range(len(valid_cols))]
                for i in range(len(valid_cols))
            ],
        }
        return result
