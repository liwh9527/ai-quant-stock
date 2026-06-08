"""归因分析模块单元测试"""
import pytest
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

    def test_summary_keys(self):
        """summary 应包含所有必需字段"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [{"industry": "科技", "weight": 1.0, "return": 0.12}]
        benchmark = [{"industry": "科技", "weight": 1.0, "return": 0.08}]

        result = model.analyze(portfolio, benchmark)
        summary = result["summary"]
        assert "allocation" in summary
        assert "selection" in summary
        assert "interaction" in summary
        assert "benchmark_return" in summary
        assert "excess_return" in summary

    def test_details_keys(self):
        """details 每项应包含所有必需字段"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [{"industry": "银行", "weight": 0.5, "return": 0.1}]
        benchmark = [{"industry": "银行", "weight": 0.5, "return": 0.06}]

        result = model.analyze(portfolio, benchmark)
        detail = result["details"][0]
        required_keys = ["industry", "port_weight", "bench_weight", "port_return",
                         "bench_return", "allocation", "selection", "interaction", "total"]
        for key in required_keys:
            assert key in detail, f"缺少字段: {key}"

    def test_same_allocation_no_allocation_effect(self):
        """相同权重配置时，行业选择收益应为 0"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [
            {"industry": "银行", "weight": 0.5, "return": 0.1},
            {"industry": "消费", "weight": 0.5, "return": 0.15},
        ]
        benchmark = [
            {"industry": "银行", "weight": 0.5, "return": 0.06},
            {"industry": "消费", "weight": 0.5, "return": 0.10},
        ]

        result = model.analyze(portfolio, benchmark)
        # 相同权重，allocation 应为 0
        assert abs(result["summary"]["allocation"]) < 1e-10

    def test_excess_return_equals_sum(self):
        """超额收益 = allocation + selection + interaction"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [
            {"industry": "银行", "weight": 0.6, "return": 0.12},
            {"industry": "消费", "weight": 0.4, "return": 0.08},
        ]
        benchmark = [
            {"industry": "银行", "weight": 0.4, "return": 0.06},
            {"industry": "消费", "weight": 0.6, "return": 0.10},
        ]

        result = model.analyze(portfolio, benchmark)
        s = result["summary"]
        expected = s["allocation"] + s["selection"] + s["interaction"]
        assert abs(s["excess_return"] - expected) < 1e-10

    def test_details_sorted_by_total(self):
        """行业明细应按 total 贡献降序排列"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [
            {"industry": "银行", "weight": 0.3, "return": 0.1},
            {"industry": "消费", "weight": 0.4, "return": 0.2},
            {"industry": "科技", "weight": 0.3, "return": 0.05},
        ]
        benchmark = [
            {"industry": "银行", "weight": 0.33, "return": 0.06},
            {"industry": "消费", "weight": 0.33, "return": 0.10},
            {"industry": "科技", "weight": 0.34, "return": 0.08},
        ]

        result = model.analyze(portfolio, benchmark)
        totals = [d["total"] for d in result["details"]]
        assert totals == sorted(totals, reverse=True)

    def test_weighted_return_static_method(self):
        """_weighted_return 静态方法测试"""
        from app.services.attribution.brinson import BrinsonAttribution
        items = [
            {"weight": 0.6, "return": 0.1},
            {"weight": 0.4, "return": 0.2},
        ]
        result = BrinsonAttribution._weighted_return(items)
        expected = (0.6 * 0.1 + 0.4 * 0.2) / 1.0
        assert abs(result - expected) < 1e-10

    def test_weighted_return_empty(self):
        """空列表加权收益为 0"""
        from app.services.attribution.brinson import BrinsonAttribution
        assert BrinsonAttribution._weighted_return([]) == 0.0

    def test_weighted_return_zero_weight(self):
        """零权重加权收益为 0"""
        from app.services.attribution.brinson import BrinsonAttribution
        items = [{"weight": 0, "return": 0.1}]
        assert BrinsonAttribution._weighted_return(items) == 0.0

    def test_industry_only_in_portfolio(self):
        """组合独有行业（基准没有）"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [
            {"industry": "银行", "weight": 0.5, "return": 0.1},
            {"industry": "新能源", "weight": 0.5, "return": 0.2},
        ]
        benchmark = [
            {"industry": "银行", "weight": 1.0, "return": 0.06},
        ]

        result = model.analyze(portfolio, benchmark)
        industries = [d["industry"] for d in result["details"]]
        assert "新能源" in industries

    def test_industry_only_in_benchmark(self):
        """基准独有行业（组合没有）"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [
            {"industry": "银行", "weight": 1.0, "return": 0.1},
        ]
        benchmark = [
            {"industry": "银行", "weight": 0.5, "return": 0.06},
            {"industry": "消费", "weight": 0.5, "return": 0.10},
        ]

        result = model.analyze(portfolio, benchmark)
        industries = [d["industry"] for d in result["details"]]
        assert "消费" in industries

    def test_rounding_precision(self):
        """结果应保留 4 位小数"""
        from app.services.attribution.brinson import BrinsonAttribution
        model = BrinsonAttribution()

        portfolio = [{"industry": "银行", "weight": 0.55, "return": 0.1234}]
        benchmark = [{"industry": "银行", "weight": 0.45, "return": 0.0678}]

        result = model.analyze(portfolio, benchmark)
        detail = result["details"][0]
        for key in ["port_weight", "bench_weight", "port_return", "bench_return",
                     "allocation", "selection", "interaction", "total"]:
            val = detail[key]
            # 检查小数位数不超过 4 位
            assert len(str(val).split(".")[-1]) <= 4, f"{key} 小数位数过多: {val}"


class TestFactorAttribution:
    """因子归因测试"""

    def test_factor_attribution_basic(self):
        """基本因子归因"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [
            {
                "ts_code": "000001.SZ", "name": "平安银行", "weight": 0.5, "return": 0.1,
                "factor_values": {"roe": 15.0, "pe": 8.0}
            },
            {
                "ts_code": "600036.SH", "name": "招商银行", "weight": 0.5, "return": 0.15,
                "factor_values": {"roe": 18.0, "pe": 10.0}
            },
        ]

        result = model.analyze(portfolio, ["roe", "pe"])
        assert "summary" in result
        assert "factors" in result
        assert len(result["factors"]) == 2

    def test_factor_summary_keys(self):
        """summary 应包含必需字段"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [{
            "ts_code": "000001.SZ", "name": "测试", "weight": 1.0, "return": 0.1,
            "factor_values": {"roe": 15.0}
        }]

        result = model.analyze(portfolio, ["roe"])
        summary = result["summary"]
        assert "total_return" in summary
        assert "factor_explained" in summary
        assert "residual" in summary

    def test_factor_item_keys(self):
        """因子项应包含必需字段"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [{
            "ts_code": "000001.SZ", "name": "测试", "weight": 1.0, "return": 0.1,
            "factor_values": {"roe": 15.0}
        }]

        result = model.analyze(portfolio, ["roe"])
        factor = result["factors"][0]
        assert "factor" in factor
        assert "factor_cn" in factor
        assert "exposure" in factor
        assert "factor_return" in factor
        assert "contribution" in factor
        assert "pct" in factor

    def test_factor_cn_name_mapping(self):
        """因子中文名称映射"""
        from app.services.attribution.factor import FactorAttribution, FACTOR_NAME_MAP
        model = FactorAttribution()

        portfolio = [{
            "ts_code": "000001.SZ", "name": "测试", "weight": 1.0, "return": 0.1,
            "factor_values": {"roe": 15.0, "pe": 8.0}
        }]

        result = model.analyze(portfolio, ["roe", "pe"])
        for f in result["factors"]:
            assert f["factor_cn"] == FACTOR_NAME_MAP[f["factor"]]

    def test_empty_portfolio(self):
        """空组合应返回空结果"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        result = model.analyze([], ["roe"])
        assert result["summary"]["total_return"] == 0
        assert result["factors"] == []

    def test_empty_factors(self):
        """空因子列表应返回空结果"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [{
            "ts_code": "000001.SZ", "name": "测试", "weight": 1.0, "return": 0.1,
            "factor_values": {"roe": 15.0}
        }]

        result = model.analyze(portfolio, [])
        assert result["factors"] == []

    def test_missing_factor_value(self):
        """缺少因子值时应跳过该股票"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [
            {
                "ts_code": "000001.SZ", "name": "平安", "weight": 0.5, "return": 0.1,
                "factor_values": {"roe": 15.0}
            },
            {
                "ts_code": "600036.SH", "name": "招商", "weight": 0.5, "return": 0.15,
                "factor_values": {}  # 缺少 roe
            },
        ]

        result = model.analyze(portfolio, ["roe"])
        # 只有平安银行的数据参与计算
        assert result["factors"][0]["factor"] == "roe"

    def test_zero_total_weight(self):
        """零权重组合应返回空结果"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [{
            "ts_code": "000001.SZ", "name": "测试", "weight": 0, "return": 0.1,
            "factor_values": {"roe": 15.0}
        }]

        result = model.analyze(portfolio, ["roe"])
        assert result["summary"]["total_return"] == 0

    def test_factors_sorted_by_abs_contribution(self):
        """因子应按贡献绝对值降序排列"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [
            {"ts_code": "000001.SZ", "name": "A", "weight": 0.5, "return": 0.1,
             "factor_values": {"roe": 15, "pe": 8, "pb": 1.2}},
            {"ts_code": "600036.SH", "name": "B", "weight": 0.5, "return": 0.2,
             "factor_values": {"roe": 20, "pe": 12, "pb": 2.0}},
        ]

        result = model.analyze(portfolio, ["roe", "pe", "pb"])
        contributions = [abs(f["contribution"]) for f in result["factors"]]
        assert contributions == sorted(contributions, reverse=True)

    def test_pct_sum_to_100(self):
        """各因子占比之和应为 100%（或接近）"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [
            {"ts_code": "000001.SZ", "name": "A", "weight": 0.5, "return": 0.1,
             "factor_values": {"roe": 15, "pe": 8}},
            {"ts_code": "600036.SH", "name": "B", "weight": 0.5, "return": 0.2,
             "factor_values": {"roe": 20, "pe": 12}},
        ]

        result = model.analyze(portfolio, ["roe", "pe"])
        total_pct = sum(f["pct"] for f in result["factors"])
        # 有贡献时占比之和应为 100%
        if result["summary"]["factor_explained"] != 0:
            assert abs(total_pct - 100) < 1

    def test_single_stock_single_factor(self):
        """单股票单因子归因"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [{
            "ts_code": "000001.SZ", "name": "平安", "weight": 1.0, "return": 0.1,
            "factor_values": {"roe": 15.0}
        }]

        result = model.analyze(portfolio, ["roe"])
        # 单股票时因子收益 = 个股收益
        assert result["summary"]["total_return"] == pytest.approx(0.1, abs=1e-4)

    def test_unknown_factor_name(self):
        """未知因子名称不应报错"""
        from app.services.attribution.factor import FactorAttribution
        model = FactorAttribution()

        portfolio = [{
            "ts_code": "000001.SZ", "name": "测试", "weight": 1.0, "return": 0.1,
            "factor_values": {"custom_factor": 42.0}
        }]

        result = model.analyze(portfolio, ["custom_factor"])
        assert result["factors"][0]["factor_cn"] == "custom_factor"


class TestAttributionAPI:
    """归因 API 测试"""

    def test_return_attribution_request(self):
        """收益归因请求模型"""
        from app.api.attribution import ReturnAttributionRequest
        req = ReturnAttributionRequest(backtest_id="test_123")
        assert req.backtest_id == "test_123"
        assert req.benchmark == "000300.SH"

    def test_factor_attribution_request(self):
        """因子归因请求模型"""
        from app.api.attribution import FactorAttributionRequest
        req = FactorAttributionRequest(backtest_id="test_456")
        assert req.backtest_id == "test_456"
        assert req.factors == ["roe", "pe", "momentum_20d"]

    def test_factor_attribution_request_custom_factors(self):
        """自定义因子列表"""
        from app.api.attribution import FactorAttributionRequest
        req = FactorAttributionRequest(
            backtest_id="test_789",
            factors=["roe", "pb", "volatility_20d"]
        )
        assert len(req.factors) == 3
