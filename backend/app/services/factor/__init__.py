"""多因子系统服务模块

提供因子定义、因子分析和多因子评分功能。
"""

from app.services.factor.definitions import FACTOR_DEFINITIONS, get_factor_list
from app.services.factor.analyzer import FactorAnalyzer
from app.services.factor.scorer import FactorScorer

__all__ = [
    "FACTOR_DEFINITIONS",
    "get_factor_list",
    "FactorAnalyzer",
    "FactorScorer",
]
