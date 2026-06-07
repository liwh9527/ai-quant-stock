"""使用 Mock 测试 Tushare 数据源

所有外部 API 调用均使用 unittest.mock 模拟，不依赖真实 Tushare 服务。
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import date

import pandas as pd

from app.services.data.tushare_source import TushareSource


class TestTushareSourceMock:
    """使用 Mock 测试 Tushare 数据源"""

    @patch("app.services.data.tushare_source.ts")
    def test_init_creates_pro_api(self, mock_ts):
        """测试初始化时调用 ts.pro_api"""
        mock_ts.pro_api.return_value = MagicMock()
        source = TushareSource(token="test_token")
        mock_ts.pro_api.assert_called_once_with("test_token")
        assert source.pro is not None

    @patch("app.services.data.tushare_source.ts")
    def test_get_stock_list_success(self, mock_ts):
        """测试成功获取股票列表"""
        mock_df = pd.DataFrame({
            "ts_code": ["000001.SZ", "600036.SH"],
            "symbol": ["000001", "600036"],
            "name": ["平安银行", "招商银行"],
            "area": ["深圳", "深圳"],
            "industry": ["银行", "银行"],
            "market": ["主板", "主板"],
            "list_date": ["19910403", "20020409"],
        })
        mock_pro = MagicMock()
        mock_pro.stock_basic.return_value = mock_df
        mock_ts.pro_api.return_value = mock_pro

        source = TushareSource(token="test_token")
        result = source.get_stock_list()

        assert len(result) == 2
        assert "ts_code" in result.columns
        assert list(result["name"]) == ["平安银行", "招商银行"]

    @patch("app.services.data.tushare_source.ts")
    def test_get_stock_list_empty_result(self, mock_ts):
        """测试空结果"""
        mock_pro = MagicMock()
        mock_pro.stock_basic.return_value = pd.DataFrame()
        mock_ts.pro_api.return_value = mock_pro

        source = TushareSource(token="test_token")
        result = source.get_stock_list()

        assert len(result) == 0

    @patch("app.services.data.tushare_source.ts")
    def test_get_stock_list_api_failure(self, mock_ts):
        """测试 API 调用失败"""
        mock_pro = MagicMock()
        mock_pro.stock_basic.side_effect = Exception("API Error")
        mock_ts.pro_api.return_value = mock_pro

        source = TushareSource(token="test_token")
        with pytest.raises(Exception) as exc_info:
            source.get_stock_list()
        assert "API Error" in str(exc_info.value)

    @patch("app.services.data.tushare_source.ts")
    def test_get_daily_quotes_success(self, mock_ts):
        """测试成功获取日线行情"""
        mock_df = pd.DataFrame({
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": ["20240101", "20240102"],
            "open": [10.0, 10.5],
            "close": [10.5, 11.0],
            "high": [11.0, 11.5],
            "low": [9.8, 10.2],
            "pre_close": [9.9, 10.5],
            "change": [0.6, 0.5],
            "pct_chg": [6.06, 4.76],
            "vol": [100000, 120000],
            "amount": [1000000, 1200000],
        })
        mock_pro = MagicMock()
        mock_pro.daily.return_value = mock_df
        mock_ts.pro_api.return_value = mock_pro

        source = TushareSource(token="test_token")
        result = source.get_daily_quotes(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert len(result) == 2
        assert "trade_date" in result.columns
        assert "close" in result.columns

    @patch("app.services.data.tushare_source.ts")
    def test_get_financial_indicators_success(self, mock_ts):
        """测试成功获取财务指标"""
        mock_df = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "ann_date": ["20240401"],
            "end_date": ["20231231"],
            "roe_waa": [15.3],
            "roa": [8.1],
            "grossprofit_margin": [35.0],
            "netprofit_margin": [20.5],
            "revenue_yoy": [12.5],
            "net_profit_yoy": [18.0],
            "pe_ttm": [8.5],
            "pb": [1.2],
            "ps_ttm": [3.0],
            "debt_to_assets": [60.0],
            "current_ratio": [1.5],
            "eps": [2.0],
            "bps": [15.0],
        })
        mock_pro = MagicMock()
        mock_pro.fina_indicator.return_value = mock_df
        mock_ts.pro_api.return_value = mock_pro

        source = TushareSource(token="test_token")
        result = source.get_financial_indicators(
            ts_code="000001.SZ",
            start_date=date(2023, 1, 1),
            end_date=date(2024, 1, 1),
        )

        assert len(result) == 1
        # 验证列名重命名
        assert "roe" in result.columns
        assert "gross_margin" in result.columns
        assert "net_margin" in result.columns
        assert "pe" in result.columns
        assert "ps" in result.columns
        assert "debt_ratio" in result.columns
        assert "bvps" in result.columns

    @patch("app.services.data.tushare_source.ts")
    def test_get_index_daily_success(self, mock_ts):
        """测试成功获取指数日线"""
        mock_df = pd.DataFrame({
            "ts_code": ["000300.SH", "000300.SH"],
            "trade_date": ["20240101", "20240102"],
            "open": [3500.0, 3520.0],
            "close": [3520.0, 3550.0],
            "high": [3530.0, 3560.0],
            "low": [3490.0, 3510.0],
            "vol": [1000000, 1100000],
            "amount": [5000000, 5500000],
        })
        mock_pro = MagicMock()
        mock_pro.index_daily.return_value = mock_df
        mock_ts.pro_api.return_value = mock_pro

        source = TushareSource(token="test_token")
        result = source.get_index_daily(
            ts_code="000300.SH",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert len(result) == 2
        assert "trade_date" in result.columns

    @patch("app.services.data.tushare_source.ts")
    def test_get_daily_quotes_empty_result(self, mock_ts):
        """测试日线行情空结果"""
        mock_pro = MagicMock()
        mock_pro.daily.return_value = pd.DataFrame()
        mock_ts.pro_api.return_value = mock_pro

        source = TushareSource(token="test_token")
        result = source.get_daily_quotes(
            ts_code="999999.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert len(result) == 0
