"""多因子评分

提供多因子综合评分功能：
- 标准化处理（Z-Score）
- 加权评分
- 全市场排名
"""

import logging
from typing import Dict, List

import numpy as np
import pandas as pd

from app.services.factor.definitions import FACTOR_DEFINITIONS

logger = logging.getLogger(__name__)


class FactorScorer:
    """多因子评分器

    对全市场股票进行多因子综合评分，输出排名结果。
    """

    def __init__(self):
        pass

    def normalize(self, series: pd.Series, method: str = "zscore") -> pd.Series:
        """标准化处理

        Args:
            series: 原始因子值
            method: 标准化方法，支持 "zscore"（Z 分数）和 "rank"（排名百分比）

        Returns:
            标准化后的序列
        """
        if method == "rank":
            # 排名百分比标准化（0~1）
            return series.rank(pct=True)

        # 默认 Z-Score 标准化
        mean = series.mean()
        std = series.std()
        if std == 0 or np.isnan(std):
            return pd.Series(0.0, index=series.index)
        return (series - mean) / std

    def score(
        self,
        df: pd.DataFrame,
        factors: List[Dict],
        top_n: int = 20,
    ) -> Dict:
        """多因子综合评分

        对 DataFrame 中的股票进行多因子加权评分并排名。

        Args:
            df: 包含股票数据的 DataFrame，需有 ts_code、name 列和各因子列
            factors: 因子配置列表，每项包含 name（因子 key）和 weight（权重）
            top_n: 返回前 N 只股票

        Returns:
            评分结果，包含 top 列表和统计信息
        """
        if df.empty:
            return {"top": [], "total": 0}

        scores = pd.DataFrame(index=df.index)

        factor_details = []
        for factor_cfg in factors:
            name = factor_cfg["name"]
            weight = factor_cfg["weight"]

            if name not in df.columns:
                logger.warning(f"因子 {name} 不在数据中，跳过")
                continue

            # 获取因子方向
            defn = FACTOR_DEFINITIONS.get(name, {})
            direction = defn.get("direction", 1)

            # 标准化
            normalized = self.normalize(df[name])

            # 考虑因子方向：direction=-1 表示值越小越好，需要反转
            adjusted = normalized * direction

            # 加权
            scores[name] = adjusted * weight

            factor_details.append({
                "key": name,
                "name": defn.get("name", name),
                "weight": weight,
                "direction": direction,
                "valid_count": int(df[name].notna().sum()),
            })

        if scores.empty:
            return {"top": [], "total": 0}

        # 综合得分
        df = df.copy()
        df["total_score"] = scores.sum(axis=1)

        # 按得分降序排名
        df = df.sort_values("total_score", ascending=False)
        df["rank"] = range(1, len(df) + 1)

        # 取 top_n
        top_df = df.head(top_n)

        # 构建返回结果
        top_list = []
        for _, row in top_df.iterrows():
            item = {
                "rank": int(row["rank"]),
                "ts_code": str(row.get("ts_code", "")),
                "name": str(row.get("name", "")),
                "total_score": round(float(row["total_score"]), 4),
            }
            # 附带各因子原始值
            for factor_cfg in factors:
                fname = factor_cfg["name"]
                if fname in row.index and not pd.isna(row[fname]):
                    item[fname] = round(float(row[fname]), 4)
                else:
                    item[fname] = None
            top_list.append(item)

        return {
            "top": top_list,
            "total": len(df),
            "factor_details": factor_details,
            "score_stats": {
                "mean": round(float(df["total_score"].mean()), 4),
                "std": round(float(df["total_score"].std()), 4),
                "min": round(float(df["total_score"].min()), 4),
                "max": round(float(df["total_score"].max()), 4),
            },
        }
