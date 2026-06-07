"""归因分析服务

提供投资组合收益来源分析：
- Brinson 归因模型：行业选择、个股选择、交互效应
- 因子归因：因子暴露、因子收益分解
"""

from app.services.attribution.brinson import BrinsonAttribution
from app.services.attribution.factor import FactorAttribution

__all__ = ["BrinsonAttribution", "FactorAttribution"]
