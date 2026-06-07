"""健康检查 API 测试"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    """创建测试用异步 HTTP 客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthCheck:
    """健康检查接口测试"""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """测试 /health 接口返回正常"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_response_format(self, client):
        """测试 /health 接口返回格式正确"""
        response = await client.get("/health")
        data = response.json()
        assert "code" in data
        assert "data" in data
        assert "msg" in data

    @pytest.mark.asyncio
    async def test_health_contains_env(self, client):
        """测试 /health 返回包含环境信息"""
        response = await client.get("/health")
        data = response.json()
        assert "env" in data["data"]


class TestAppInfo:
    """应用信息接口测试"""

    @pytest.mark.asyncio
    async def test_api_info_endpoint(self, client):
        """测试 /api/info 接口返回正常"""
        response = await client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_api_info_contains_name(self, client):
        """测试 /api/info 返回包含应用名称"""
        response = await client.get("/api/info")
        data = response.json()
        assert data["data"]["name"] == "AI 辅助量化选股工具"

    @pytest.mark.asyncio
    async def test_api_info_contains_version(self, client):
        """测试 /api/info 返回包含版本号"""
        response = await client.get("/api/info")
        data = response.json()
        assert "version" in data["data"]


class TestRootEndpoint:
    """根路径接口测试"""

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client):
        """测试根路径 / 接口"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "message" in data["data"]
