"""归因分析 API 测试"""

import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_db


@pytest.fixture
async def client():
    """创建测试用异步 HTTP 客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def override_db():
    """覆盖数据库依赖"""
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield mock_db
    app.dependency_overrides.clear()


class TestReturnAttributionAPI:
    """收益归因接口测试"""

    @pytest.mark.asyncio
    async def test_return_attribution_no_backtest(self, client):
        """未找到回测任务时应返回错误"""
        with patch("app.api.attribution._get_backtest_result", return_value=None):
            response = await client.post("/api/attribution/return", json={
                "backtest_id": "nonexistent",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == -1
        assert "未找到" in data["msg"]

    @pytest.mark.asyncio
    async def test_return_attribution_success(self, client):
        """收益归因成功"""
        mock_backtest = {
            "task_id": "test_123",
            "strategy_config": {"ts_code": "000001.SZ"},
            "metrics": {"total_return": 15.5},
            "trades": [],
        }

        with patch("app.api.attribution._get_backtest_result", return_value=mock_backtest):
            response = await client.post("/api/attribution/return", json={
                "backtest_id": "test_123",
                "benchmark": "000300.SH",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "summary" in data["data"]
        assert "details" in data["data"]

    @pytest.mark.asyncio
    async def test_return_attribution_default_benchmark(self, client):
        """默认基准为 000300.SH"""
        mock_backtest = {
            "task_id": "test_456",
            "strategy_config": {"ts_code": "000001.SZ"},
            "metrics": {"total_return": 10.0},
            "trades": [],
        }

        with patch("app.api.attribution._get_backtest_result", return_value=mock_backtest):
            response = await client.post("/api/attribution/return", json={
                "backtest_id": "test_456",
            })

        data = response.json()
        assert data["code"] == 0
        assert data["data"]["benchmark"] == "000300.SH"

    @pytest.mark.asyncio
    async def test_return_attribution_with_trades(self, client):
        """有交易记录时的收益归因"""
        mock_backtest = {
            "task_id": "test_trades",
            "strategy_config": {"ts_code": "000001.SZ"},
            "metrics": {"total_return": 20.0},
            "trades": [
                {"ts_code": "000001.SZ", "name": "平安银行", "industry": "银行", "profit_pct": 0.05},
                {"ts_code": "600036.SH", "name": "招商银行", "industry": "银行", "profit_pct": 0.08},
            ],
        }

        with patch("app.api.attribution._get_backtest_result", return_value=mock_backtest):
            response = await client.post("/api/attribution/return", json={
                "backtest_id": "test_trades",
            })

        data = response.json()
        assert data["code"] == 0
        assert len(data["data"]["details"]) > 0


class TestFactorAttributionAPI:
    """因子归因接口测试"""

    @pytest.mark.asyncio
    async def test_factor_attribution_no_backtest(self, client):
        """未找到回测任务时应返回错误"""
        with patch("app.api.attribution._get_backtest_result", return_value=None):
            response = await client.post("/api/attribution/factor", json={
                "backtest_id": "nonexistent",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == -1

    @pytest.mark.asyncio
    async def test_factor_attribution_success(self, client):
        """因子归因成功"""
        mock_backtest = {
            "task_id": "test_789",
            "strategy_config": {"ts_code": "000001.SZ"},
            "metrics": {"total_return": 12.0},
            "trades": [],
        }
        mock_portfolio = [
            {
                "ts_code": "000001.SZ", "name": "平安银行", "weight": 1.0, "return": 0.12,
                "factor_values": {"roe": 15.0, "pe": 8.0}
            }
        ]

        with patch("app.api.attribution._get_backtest_result", return_value=mock_backtest), \
             patch("app.api.attribution._build_portfolio_with_factors", return_value=mock_portfolio):
            response = await client.post("/api/attribution/factor", json={
                "backtest_id": "test_789",
                "factors": ["roe", "pe"],
            })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "summary" in data["data"]
        assert "factors" in data["data"]

    @pytest.mark.asyncio
    async def test_factor_attribution_default_factors(self, client):
        """默认因子列表"""
        mock_backtest = {
            "task_id": "test_default",
            "strategy_config": {"ts_code": "000001.SZ"},
            "metrics": {"total_return": 8.0},
            "trades": [],
        }
        mock_portfolio = [
            {
                "ts_code": "000001.SZ", "name": "测试", "weight": 1.0, "return": 0.08,
                "factor_values": {"roe": 15, "pe": 8, "momentum_20d": 5}
            }
        ]

        with patch("app.api.attribution._get_backtest_result", return_value=mock_backtest), \
             patch("app.api.attribution._build_portfolio_with_factors", return_value=mock_portfolio):
            response = await client.post("/api/attribution/factor", json={
                "backtest_id": "test_default",
            })

        data = response.json()
        assert data["code"] == 0
        # factors 字段被 FactorAttribution.analyze() 的结果覆盖，为因子详情列表
        factor_names = [f["factor"] for f in data["data"]["factors"]]
        assert "roe" in factor_names
        assert "pe" in factor_names
        assert "momentum_20d" in factor_names
