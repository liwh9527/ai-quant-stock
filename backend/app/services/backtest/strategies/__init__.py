"""策略注册中心

统一管理所有量化策略，支持列表、详情、运行。
每个策略是一个 dict，包含 name/description/category/config/params。
"""

from typing import Dict, List, Optional

# 策略注册表
STRATEGY_REGISTRY: Dict[str, Dict] = {}


def register_strategy(key: str, strategy: Dict):
    """注册策略"""
    STRATEGY_REGISTRY[key] = strategy


def get_strategy(key: str) -> Optional[Dict]:
    """获取策略"""
    return STRATEGY_REGISTRY.get(key)


def list_strategies(category: Optional[str] = None) -> List[Dict]:
    """列出策略，可按分类过滤"""
    strategies = list(STRATEGY_REGISTRY.values())
    if category:
        strategies = [s for s in strategies if s.get("category") == category]
    return strategies


def get_categories() -> List[str]:
    """获取所有分类"""
    return list(set(s.get("category", "") for s in STRATEGY_REGISTRY.values()))


# 导入所有策略（触发注册）
from . import momentum  # noqa: F401
from . import turtle  # noqa: F401
from . import multifactor  # noqa: F401
from . import trend_timing  # noqa: F401
from . import value  # noqa: F401
from . import auction_limit_up  # noqa: F401
from . import mean_reversion  # noqa: F401
from . import breakout  # noqa: F401
from . import low_volatility  # noqa: F401
from . import dual_ma  # noqa: F401
