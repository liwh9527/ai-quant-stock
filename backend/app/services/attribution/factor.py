"""因子归因分析

将投资组合收益分解到各因子维度的贡献：
- 因子暴露计算：组合对各因子的敏感度
- 因子收益分解：各因子对总收益的贡献金额和占比
"""

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)

# 因子中文名称映射
FACTOR_NAME_MAP = {
    "roe": "ROE（净资产收益率）",
    "pe": "PE（市盈率）",
    "pb": "PB（市净率）",
    "ps": "PS（市销率）",
    "momentum_20d": "20日动量",
    "momentum_60d": "60日动量",
    "momentum_120d": "120日动量",
    "volatility_20d": "20日波动率",
    "volatility_60d": "60日波动率",
    "turnover": "换手率",
    "market_cap": "市值",
    "revenue_yoy": "营收同比",
    "net_profit_yoy": "净利润同比",
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "debt_ratio": "资产负债率",
    "current_ratio": "流动比率",
    "roa": "ROA（总资产收益率）",
    "eps": "每股收益",
    "bvps": "每股净资产",
}


class FactorAttribution:
    """因子归因

    基于 Barra 风格的多因子归因模型，将组合收益分解到
    各因子维度。
    """

    def analyze(
        self,
        portfolio: List[Dict],
        factors: List[str],
    ) -> Dict:
        """执行因子归因分析

        Args:
            portfolio: 组合持仓列表，每项包含：
                - ts_code: 股票代码
                - name: 股票名称
                - weight: 持仓权重
                - return: 个股收益率
                - factor_values: { factor_name: factor_value, ... }
            factors: 要分析的因子列表，如 ["roe", "pe", "momentum_20d"]

        Returns:
            {
                "summary": { total_return, factor_explained, residual },
                "factors": [
                    { factor, factor_cn, exposure, factor_return, contribution, pct }
                ],
            }
        """
        if not portfolio or not factors:
            return {
                "summary": {"total_return": 0, "factor_explained": 0, "residual": 0},
                "factors": [],
            }

        # 计算组合总收益（加权）
        total_weight = sum(p.get("weight", 0) for p in portfolio)
        if total_weight <= 0:
            return {
                "summary": {"total_return": 0, "factor_explained": 0, "residual": 0},
                "factors": [],
            }

        total_return = sum(
            p.get("weight", 0) * p.get("return", 0) for p in portfolio
        ) / total_weight

        # 对每个因子进行归因
        factor_results = []
        total_contribution = 0.0

        for factor in factors:
            result = self._analyze_single_factor(portfolio, factor, total_weight)
            factor_results.append(result)
            total_contribution += result["contribution"]

        # 计算各因子贡献占比
        abs_contribution = sum(abs(r["contribution"]) for r in factor_results)
        for r in factor_results:
            if abs_contribution > 0:
                r["pct"] = round(r["contribution"] / abs_contribution * 100, 2)
            else:
                r["pct"] = 0.0

        # 残差 = 总收益 - 因子解释收益
        residual = total_return - total_contribution

        # 按贡献绝对值降序排列
        factor_results.sort(key=lambda x: abs(x["contribution"]), reverse=True)

        return {
            "summary": {
                "total_return": round(total_return, 4),
                "factor_explained": round(total_contribution, 4),
                "residual": round(residual, 4),
            },
            "factors": factor_results,
        }

    def _analyze_single_factor(
        self,
        portfolio: List[Dict],
        factor: str,
        total_weight: float,
    ) -> Dict:
        """分析单个因子的归因

        Args:
            portfolio: 组合持仓列表
            factor: 因子名称
            total_weight: 组合总权重

        Returns:
            单个因子的归因结果
        """
        # 提取因子暴露值和收益率
        exposures = []
        returns = []
        weights = []

        for p in portfolio:
            factor_values = p.get("factor_values", {})
            if factor not in factor_values or factor_values[factor] is None:
                continue
            exposures.append(float(factor_values[factor]))
            returns.append(p.get("return", 0))
            weights.append(p.get("weight", 0))

        if not exposures:
            return {
                "factor": factor,
                "factor_cn": FACTOR_NAME_MAP.get(factor, factor),
                "exposure": 0.0,
                "factor_return": 0.0,
                "contribution": 0.0,
                "pct": 0.0,
            }

        exposures_arr = np.array(exposures)
        returns_arr = np.array(returns)
        weights_arr = np.array(weights)

        # 组合加权因子暴露
        avg_exposure = float(np.average(exposures_arr, weights=weights_arr))

        # 因子收益率：通过因子暴露与个股收益的回归系数估算
        # 简化方式：用因子暴露与收益的相关性 * 收益标准差来估算
        if len(exposures_arr) >= 2:
            # 标准化因子暴露
            std_exp = np.std(exposures_arr)
            if std_exp > 0:
                normalized_exp = (exposures_arr - np.mean(exposures_arr)) / std_exp
                # 因子收益 = 协方差(标准化暴露, 收益) / 方差(标准化暴露) * 平均暴露
                # 简化为：加权相关系数 * 收益波动
                cov = float(np.cov(normalized_exp, returns_arr, aweights=weights_arr)[0, 1])
                factor_return = cov * avg_exposure
            else:
                factor_return = float(np.average(returns_arr, weights=weights_arr))
        else:
            factor_return = float(returns_arr[0])

        # 因子贡献 = 因子暴露 * 因子收益
        contribution = avg_exposure * factor_return

        return {
            "factor": factor,
            "factor_cn": FACTOR_NAME_MAP.get(factor, factor),
            "exposure": round(avg_exposure, 4),
            "factor_return": round(factor_return, 4),
            "contribution": round(contribution, 4),
            "pct": 0.0,  # 外层统一计算
        }
