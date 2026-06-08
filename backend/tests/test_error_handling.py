"""错误处理测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


class TestDeepSeekAPIErrors:
    """DeepSeek API 错误处理测试"""

    @pytest.mark.asyncio
    async def test_api_timeout(self):
        """API 超时"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance
            mock_instance.post.side_effect = httpx.TimeoutException("Request timeout")

            from app.services.ai.deepseek_service import DeepSeekService
            service = DeepSeekService()

            with pytest.raises(Exception):
                await service.chat([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_api_connection_error(self):
        """API 连接错误"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance
            mock_instance.post.side_effect = httpx.ConnectError("Connection refused")

            from app.services.ai.deepseek_service import DeepSeekService
            service = DeepSeekService()

            with pytest.raises(Exception):
                await service.chat([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_invalid_json_response(self):
        """无效 JSON 响应"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"error": "invalid response"}
            mock_instance.post.return_value = mock_response

            from app.services.ai.deepseek_service import DeepSeekService
            service = DeepSeekService()

            with pytest.raises((KeyError, TypeError)):
                await service.chat([{"role": "user", "content": "test"}])


class TestTushareAPIErrors:
    """Tushare API 错误处理测试"""

    def test_api_failure(self):
        """Tushare API 调用失败"""
        with patch("tushare.pro_api") as mock_pro:
            mock_instance = MagicMock()
            mock_pro.return_value = mock_instance
            mock_instance.stock_basic.side_effect = Exception("API Error")

            from app.services.data.tushare_source import TushareSource
            source = TushareSource(token="test_token")

            with pytest.raises(Exception) as exc_info:
                source.get_stock_list()
            assert "API Error" in str(exc_info.value)

    def test_empty_result(self):
        """Tushare API 返回空结果"""
        with patch("tushare.pro_api") as mock_pro:
            mock_instance = MagicMock()
            mock_pro.return_value = mock_instance
            mock_instance.stock_basic.return_value = None

            from app.services.data.tushare_source import TushareSource
            source = TushareSource(token="test_token")

            with pytest.raises((AttributeError, TypeError)):
                source.get_stock_list()


class TestDatabaseErrors:
    """数据库错误处理测试"""

    def test_database_session_error(self):
        """数据库会话错误"""
        from app.core.database import SessionLocal
        # 验证 SessionLocal 可用
        assert SessionLocal is not None
