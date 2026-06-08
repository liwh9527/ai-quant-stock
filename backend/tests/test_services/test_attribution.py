"""归因分析模块单元测试"""
import pytest
import pandas as pd
import numpy as np


class TestBrinsonAttribution:
    """Brinson 归因模型测试"""

    def test_attribution_basic(self):
        """基本归因分析"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [
            {"industry": "银行", "weight": 0.3, "return": 0.1},
            {"industry": "银行", "weight": 0.2, "return": 0.08},
            {"industry": "消费", "weight": 0.3, "return": 0.15},
            {"industry": "消费", "weight": 0.2, "return": 0.05}
        ]
        benchmark = [
            {"industry": "银行", "weight": 0.5, "return": 0.06},
            {"industry": "消费", "weight": 0.5, "return": 0.10}
        ]

        result = model.analyze(portfolio, benchmark)
        assert result is not None
        assert isinstance(result, dict)
        assert "summary" in result
        assert "details" in result

    def test_attribution_has_industries(self):
        """归因结果应包含行业"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [
            {"industry": "银行", "weight": 0.6, "return": 0.1},
            {"industry": "消费", "weight": 0.4, "return": 0.15}
        ]
        benchmark = [
            {"industry": "银行", "weight": 0.5, "return": 0.06},
            {"industry": "消费", "weight": 0.5, "return": 0.10}
        ]

        result = model.analyze(portfolio, benchmark)
        assert "details" in result
        industries = [d["industry"] for d in result["details"]]
        assert "银行" in industries
        assert "消费" in industries


class TestFactorAttribution:
    """因子归因测试"""

    def test_factor_attribution_basic(self):
        """基本因子归因"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        # 简单验证类可实例化
        assert model is not None
        assert hasattr(model, "analyze")
