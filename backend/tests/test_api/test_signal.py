"""买卖信号 API 测试"""

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
    """覆盖数据库依赖，使用内存 mock"""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.query.return_value.count.return_value = 0
    mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    app.dependency_overrides[get_db] = lambda: mock_db
    yield mock_db
    app.dependency_overrides.clear()


class TestSignalGenerateAPI:
    """信号生成接口测试"""

    @pytest.mark.asyncio
    async def test_generate_returns_success(self, client):
        """信号生成接口应返回成功"""
        with patch("app.api.signal._get_generator") as mock_gen:
            mock_generator = MagicMock()
            mock_generator.generate.return_value = {
                "signals": [
                    {
                        "date": "2024-02-15",
                        "type": "BUY",
                        "indicator": "macd",
                        "price": 10.5,
                        "strength": 0.3,
                        "reason": "MACD 金叉",
                    }
                ],
                "chart_data": {
                    "kline": [{"date": "2024-02-15", "open": 10, "high": 11, "low": 9.5, "close": 10.5, "volume": 5000}],
                    "macd": [],
                    "kdj": [],
                    "ma": [],
                },
            }
            mock_gen.return_value = mock_generator

            response = await client.post("/api/signal/generate", json={
                "ts_code": "000001.SZ",
                "indicators": ["macd"],
                "start_date": "2024-01-01",
                "end_date": "2024-03-01",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "signals" in data["data"]
        assert "chart_data" in data["data"]

    @pytest.mark.asyncio
    async def test_generate_default_params(self, client):
        """信号生成使用默认参数"""
        with patch("app.api.signal._get_generator") as mock_gen:
            mock_generator = MagicMock()
            mock_generator.generate.return_value = {
                "signals": [],
                "chart_data": {"kline": [], "macd": [], "kdj": [], "ma": []},
            }
            mock_gen.return_value = mock_generator

            response = await client.post("/api/signal/generate", json={
                "ts_code": "000001.SZ",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_generate_saves_signals_to_db(self, override_db):
        """信号应保存到数据库"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.signal._get_generator") as mock_gen:
                mock_generator = MagicMock()
                mock_generator.generate.return_value = {
                    "signals": [
                        {
                            "date": "2024-02-15",
                            "type": "BUY",
                            "indicator": "macd",
                            "price": 10.5,
                            "strength": 0.3,
                            "reason": "MACD 金叉",
                        }
                    ],
                    "chart_data": {"kline": [], "macd": [], "kdj": [], "ma": []},
                }
                mock_gen.return_value = mock_generator

                response = await client.post("/api/signal/generate", json={
                    "ts_code": "000001.SZ",
                    "indicators": ["macd"],
                })

            data = response.json()
            assert data["code"] == 0
            # 验证 db.add 被调用（信号写入数据库）
            assert override_db.add.called


class TestSignalListAPI:
    """信号列表接口测试"""

    @pytest.mark.asyncio
    async def test_list_signals_returns_success(self, client):
        """信号列表接口应返回成功"""
        response = await client.get("/api/signal/list")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "total" in data["data"]
        assert "records" in data["data"]

    @pytest.mark.asyncio
    async def test_list_signals_with_params(self, client):
        """带参数的信号列表查询"""
        response = await client.get("/api/signal/list", params={
            "ts_code": "000001.SZ",
            "signal_type": "BUY",
            "indicator": "macd",
            "page": 1,
            "page_size": 10,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 10

    @pytest.mark.asyncio
    async def test_list_signals_pagination(self, client):
        """分页参数验证"""
        response = await client.get("/api/signal/list", params={
            "page": 2,
            "page_size": 5,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["page"] == 2
        assert data["data"]["page_size"] == 5
