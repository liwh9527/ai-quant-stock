"""Brinson 归因模型

将投资组合超额收益分解为：
- 行业选择收益 (Allocation)：行业配置权重差异带来的收益
- 个股选择收益 (Selection)：行业内选股能力带来的收益
- 交互效应 (Interaction)：权重差异与选股能力的交叉影响
"""

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)


class BrinsonAttribution:
    """Brinson 归因模型

    基于 Brinson-Fachler 模型，将组合超额收益分解为
    Allocation、Selection、Interaction 三个部分。
    """

    def analyze(
        self,
        portfolio: List[Dict],
        benchmark: List[Dict],
    ) -> Dict:
        """执行 Brinson 归因分析

        Args:
            portfolio: 组合持仓列表，每项包含 industry / weight / return
            benchmark: 基准持仓列表，每项包含 industry / weight / return

        Returns:
            {
                "summary": { allocation, selection, interaction, benchmark_return, excess_return },
                "details": [ { industry, port_weight, bench_weight, port_return, bench_return,
                               allocation, selection, interaction, total } ],
            }
        """
        # 提取行业集合
        port_industries = {item["industry"] for item in portfolio}
        bench_industries = {item["industry"] for item in benchmark}
        all_industries = port_industries | bench_industries

        details = []
        total_allocation = 0.0
        total_selection = 0.0
        total_interaction = 0.0
        total_bench_return = 0.0

        for ind in all_industries:
            # 获取该行业的组合数据
            port_items = [p for p in portfolio if p["industry"] == ind]
            bench_items = [b for b in benchmark if b["industry"] == ind]

            port_weight = sum(p.get("weight", 0) for p in port_items)
            bench_weight = sum(b.get("weight", 0) for b in bench_items)

            # 行业内加权平均收益
            port_return = self._weighted_return(port_items)
            bench_return = self._weighted_return(bench_items)

            # 基准总收益 = 各行业权重 * 行业收益
            total_bench_return += bench_weight * bench_return

            # Brinson 分解
            allocation = (port_weight - bench_weight) * bench_return
            selection = bench_weight * (port_return - bench_return)
            interaction = (port_weight - bench_weight) * (port_return - bench_return)
            total = allocation + selection + interaction

            total_allocation += allocation
            total_selection += selection
            total_interaction += interaction

            details.append({
                "industry": ind,
                "port_weight": round(port_weight, 4),
                "bench_weight": round(bench_weight, 4),
                "port_return": round(port_return, 4),
                "bench_return": round(bench_return, 4),
                "allocation": round(allocation, 4),
                "selection": round(selection, 4),
                "interaction": round(interaction, 4),
                "total": round(total, 4),
            })

        # 按 total 贡献降序排列
        details.sort(key=lambda x: x["total"], reverse=True)

        excess_return = total_allocation + total_selection + total_interaction

        return {
            "summary": {
                "allocation": round(total_allocation, 4),
                "selection": round(total_selection, 4),
                "interaction": round(total_interaction, 4),
                "benchmark_return": round(total_bench_return, 4),
                "excess_return": round(excess_return, 4),
            },
            "details": details,
        }

    @staticmethod
    def _weighted_return(items: List[Dict]) -> float:
        """计算加权平均收益率

        Args:
            items: 包含 weight 和 return 的字典列表

        Returns:
            加权平均收益率（权重之和为 0 时返回 0）
        """
        total_weight = sum(item.get("weight", 0) for item in items)
        if total_weight <= 0:
            return 0.0
        return sum(
            item.get("weight", 0) * item.get("return", 0) for item in items
        ) / total_weight
