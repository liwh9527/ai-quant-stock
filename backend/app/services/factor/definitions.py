"""因子定义

定义所有可用因子的元信息，包括名称、分类、数据库字段或计算方式。
"""

from typing import Dict, List

# 因子分类名称映射
CATEGORY_NAMES = {
    "value": "价值因子",
    "growth": "成长因子",
    "quality": "质量因子",
    "momentum": "动量因子",
    "volatility": "波动因子",
}

# 因子定义表
FACTOR_DEFINITIONS: Dict[str, Dict] = {
    # ---- 价值因子 ----
    "pe": {
        "name": "市盈率",
        "category": "value",
        "field": "pe",
        "description": "市盈率（PE_TTM），越低越便宜",
        "direction": -1,  # 负向：PE 越低越好
    },
    "pb": {
        "name": "市净率",
        "category": "value",
        "field": "pb",
        "description": "市净率（PB），越低越便宜",
        "direction": -1,
    },
    "ps": {
        "name": "市销率",
        "category": "value",
        "field": "ps",
        "description": "市销率（PS），越低越便宜",
        "direction": -1,
    },

    # ---- 成长因子 ----
    "revenue_yoy": {
        "name": "营收同比",
        "category": "growth",
        "field": "revenue_yoy",
        "description": "营业收入同比增长率（%）",
        "direction": 1,  # 正向：增长越快越好
    },
    "net_profit_yoy": {
        "name": "净利润同比",
        "category": "growth",
        "field": "net_profit_yoy",
        "description": "净利润同比增长率（%）",
        "direction": 1,
    },

    # ---- 质量因子 ----
    "roe": {
        "name": "净资产收益率",
        "category": "quality",
        "field": "roe",
        "description": "净资产收益率 ROE（%），越高盈利能力越强",
        "direction": 1,
    },
    "roa": {
        "name": "总资产收益率",
        "category": "quality",
        "field": "roa",
        "description": "总资产收益率 ROA（%）",
        "direction": 1,
    },
    "gross_margin": {
        "name": "销售毛利率",
        "category": "quality",
        "field": "gross_margin",
        "description": "销售毛利率（%）",
        "direction": 1,
    },

    # ---- 动量因子 ----
    "momentum_5d": {
        "name": "5日动量",
        "category": "momentum",
        "calc": "momentum",
        "period": 5,
        "description": "过去5个交易日的收益率（%）",
        "direction": 1,
    },
    "momentum_20d": {
        "name": "20日动量",
        "category": "momentum",
        "calc": "momentum",
        "period": 20,
        "description": "过去20个交易日的收益率（%）",
        "direction": 1,
    },

    # ---- 波动因子 ----
    "volatility_20d": {
        "name": "20日波动率",
        "category": "volatility",
        "calc": "volatility",
        "period": 20,
        "description": "过去20个交易日日收益率的年化标准差",
        "direction": -1,  # 负向：波动越小越好
    },
}


def get_factor_list() -> List[Dict]:
    """获取因子列表，按分类分组返回

    Returns:
        因子列表，每个元素包含 key、name、category、category_name、description、direction
    """
    result = []
    for key, defn in FACTOR_DEFINITIONS.items():
        result.append({
            "key": key,
            "name": defn["name"],
            "category": defn["category"],
            "category_name": CATEGORY_NAMES.get(defn["category"], defn["category"]),
            "description": defn.get("description", ""),
            "direction": defn.get("direction", 1),
        })
    return result


def get_factor_keys_by_category(category: str) -> List[str]:
    """获取指定分类下的所有因子 key"""
    return [k for k, v in FACTOR_DEFINITIONS.items() if v["category"] == category]


def is_db_factor(factor_key: str) -> bool:
    """判断因子是否直接从数据库字段获取（而非需要计算）"""
    defn = FACTOR_DEFINITIONS.get(factor_key)
    if not defn:
        return False
    return "field" in defn
