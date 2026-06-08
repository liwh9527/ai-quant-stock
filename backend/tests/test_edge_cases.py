"""边界条件测试"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock, MagicMock


class TestScreeningEdgeCases:
    """选股边界条件测试"""

    def test_empty_conditions(self):
        """空筛选条件"""
        from app.services.screening import ScreeningService
        mock_ai = AsyncMock()
        mock_session = MagicMock()
        service = ScreeningService(mock_ai, mock_session)

        # 空条件应返回空结果或全部
        result = service.search(conditions=[], page=1, page_size=20)
        assert result is not None

    def test_invalid_field_name(self):
        """无效字段名应被跳过"""
        from app.services.screening import ScreeningService
        mock_ai = AsyncMock()
        mock_session = MagicMock()
        service = ScreeningService(mock_ai, mock_session)

        conditions = [{"field": "invalid_field", "operator": "<", "value": 20}]
        # 不应抛出异常
        result = service.search(conditions=conditions, page=1, page_size=20)
        assert result is not None

    def test_extreme_large_value(self):
        """极大数值"""
        from app.services.screening import ScreeningService
        mock_ai = AsyncMock()
        mock_session = MagicMock()
        service = ScreeningService(mock_ai, mock_session)

        conditions = [{"field": "pe", "operator": "<", "value": 999999}]
        result = service.search(conditions=conditions, page=1, page_size=20)
        assert result is not None


class TestIndicatorEdgeCases:
    """技术指标边界条件测试"""

    def test_short_dataframe(self):
        """短数据帧（不足计算周期）"""
        from app.services.signal.indicators import TechnicalIndicators
        df = pd.DataFrame({
            "open": [10.0, 10.5],
            "high": [11.0, 11.5],
            "low": [9.5, 10.0],
            "close": [10.5, 11.0],
            "vol": [1000.0, 2000.0],
            "amount": [10500.0, 22000.0]
        })
        dif, dea, macd_hist = TechnicalIndicators.macd(df)
        assert len(dif) == 2

    def test_constant_prices(self):
        """价格不变"""
        from app.services.signal.indicators import TechnicalIndicators
        n = 50
        df = pd.DataFrame({
            "open": [10.0] * n,
            "high": [10.0] * n,
            "low": [10.0] * n,
            "close": [10.0] * n,
            "vol": [1000.0] * n,
            "amount": [10000.0] * n
        })
        # 不应抛出异常
        dif, dea, macd_hist = TechnicalIndicators.macd(df)
        assert len(dif) == n

    def test_nan_values(self):
        """包含 NaN 值"""
        from app.services.signal.indicators import TechnicalIndicators
        df = pd.DataFrame({
            "open": [10.0, np.nan, 10.5, 11.0, 10.8],
            "high": [11.0, 11.5, np.nan, 11.5, 11.2],
            "low": [9.5, 10.0, 10.0, np.nan, 10.5],
            "close": [10.5, 11.0, 10.8, 11.2, 10.8],
            "vol": [1000.0, 2000.0, 1500.0, 1800.0, 1200.0],
            "amount": [10500.0, 22000.0, 16200.0, 20160.0, 12960.0]
        })
        # 不应抛出异常
        k, d, j = TechnicalIndicators.kdj(df)
        assert len(k) == 5
