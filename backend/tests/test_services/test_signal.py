"""买卖信号模块单元测试"""
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from unittest.mock import MagicMock, patch


class TestTechnicalIndicators:
    """技术指标计算测试"""

    def _make_df(self, n=50):
        """生成测试用 DataFrame"""
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=n)
        close = pd.Series(np.cumsum(np.random.randn(n) * 0.5) + 10, index=dates)
        high = close + abs(np.random.randn(n) * 0.3)
        low = close - abs(np.random.randn(n) * 0.3)
        open_ = close.shift(1).fillna(close.iloc[0])
        vol = pd.Series(np.random.randint(1000, 10000, n), index=dates, dtype=float)
        return pd.DataFrame({
            "open": open_, "high": high, "low": low,
            "close": close, "vol": vol, "amount": close * vol
        })

    def test_macd_returns_three_series(self):
        """MACD 应返回 DIF, DEA, MACD 柱"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df()
        dif, dea, macd_hist = TechnicalIndicators.macd(df)
        assert len(dif) == len(df)
        assert len(dea) == len(df)
        assert len(macd_hist) == len(df)

    def test_macd_custom_params(self):
        """MACD 自定义参数"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df(100)
        dif, dea, hist = TechnicalIndicators.macd(df, fast=5, slow=10, signal=3)
        assert len(dif) == 100
        # 快线周期更短，响应更快
        assert not dif.isna().all()

    def test_macd_relation(self):
        """MACD 柱 = (DIF - DEA) * 2"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df(60)
        dif, dea, hist = TechnicalIndicators.macd(df)
        expected = (dif - dea) * 2
        pd.testing.assert_series_equal(hist, expected, check_names=False)

    def test_kdj_returns_three_series(self):
        """KDJ 应返回 K, D, J"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df()
        k, d, j = TechnicalIndicators.kdj(df)
        assert len(k) == len(df)
        assert len(d) == len(df)
        assert len(j) == len(df)

    def test_kdj_relation(self):
        """J = 3K - 2D"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df(60)
        k, d, j = TechnicalIndicators.kdj(df)
        expected = 3 * k - 2 * d
        pd.testing.assert_series_equal(j, expected, check_names=False)

    def test_kdj_constant_price_no_error(self):
        """KDJ 在恒定价格下不应报错"""
        from app.services.signal.indicators import TechnicalIndicators
        dates = pd.date_range("2024-01-01", periods=30)
        df = pd.DataFrame({
            "close": 10.0, "high": 10.0, "low": 10.0,
            "open": 10.0, "vol": 1000.0
        }, index=dates)
        k, d, j = TechnicalIndicators.kdj(df)
        # 恒定价格时 denom=0，应返回 NaN
        assert k.iloc[-1] is not None  # 不应抛异常

    def test_ma_returns_dict(self):
        """均线应返回字典"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df()
        result = TechnicalIndicators.ma(df, periods=[5, 10, 20])
        assert "ma5" in result
        assert "ma10" in result
        assert "ma20" in result

    def test_ma_default_periods(self):
        """均线默认周期 [5, 10, 20, 60]"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df(100)
        result = TechnicalIndicators.ma(df)
        assert set(result.keys()) == {"ma5", "ma10", "ma20", "ma60"}

    def test_ma_values_reasonable(self):
        """均线值应在合理范围内"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df()
        result = TechnicalIndicators.ma(df, periods=[5])
        valid = result["ma5"].dropna()
        assert len(valid) > 0
        # 均线值应在 close 的 min/max 范围内
        assert valid.min() >= df["close"].min()
        assert valid.max() <= df["close"].max()

    def test_ma_length_matches_df(self):
        """均线长度应与 DataFrame 一致"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df(80)
        result = TechnicalIndicators.ma(df, periods=[10])
        assert len(result["ma10"]) == 80


class TestSignalGenerator:
    """信号生成器测试"""

    def _make_df(self, n=120):
        """生成带足够预热期的测试数据"""
        np.random.seed(42)
        dates = pd.date_range("2023-10-01", periods=n)
        close = pd.Series(np.cumsum(np.random.randn(n) * 0.5) + 10, index=dates)
        high = close + abs(np.random.randn(n) * 0.3)
        low = close - abs(np.random.randn(n) * 0.3)
        open_ = close.shift(1).fillna(close.iloc[0])
        vol = pd.Series(np.random.randint(1000, 10000, n), index=dates, dtype=float)
        df = pd.DataFrame({
            "open": open_, "high": high, "low": low,
            "close": close, "vol": vol, "amount": close * vol
        })
        # 确保 trade_date 列存在
        df["trade_date"] = dates
        return df

    def test_generate_returns_dict(self):
        """generate 应返回包含 signals 和 chart_data 的字典"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = self._make_df()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            indicators=["macd"],
        )
        assert "signals" in result
        assert "chart_data" in result
        assert isinstance(result["signals"], list)

    def test_generate_macd_signals(self):
        """MACD 信号生成"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = self._make_df()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 20),
            indicators=["macd"],
        )
        # MACD 图表数据应存在
        assert len(result["chart_data"]["macd"]) > 0
        # 信号应有正确结构
        for sig in result["signals"]:
            assert "date" in sig
            assert "type" in sig
            assert sig["type"] in ("BUY", "SELL")
            assert "indicator" in sig
            assert "price" in sig
            assert "strength" in sig
            assert "reason" in sig

    def test_generate_kdj_signals(self):
        """KDJ 信号生成"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = self._make_df()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 20),
            indicators=["kdj"],
        )
        assert len(result["chart_data"]["kdj"]) > 0

    def test_generate_ma_signals(self):
        """均线信号生成"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = self._make_df()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 20),
            indicators=["ma"],
        )
        assert len(result["chart_data"]["ma"]) > 0

    def test_generate_multiple_indicators(self):
        """多指标同时生成"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = self._make_df()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 20),
            indicators=["macd", "kdj", "ma"],
        )
        assert len(result["chart_data"]["macd"]) > 0
        assert len(result["chart_data"]["kdj"]) > 0
        assert len(result["chart_data"]["ma"]) > 0

    def test_generate_empty_data(self):
        """无数据时返回空结果"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = pd.DataFrame()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            indicators=["macd"],
        )
        assert result["signals"] == []
        assert result["chart_data"]["kline"] == []

    def test_generate_custom_params(self):
        """自定义指标参数"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = self._make_df()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 20),
            indicators=["macd"],
            params={"macd": {"fast": 5, "slow": 10, "signal": 3}},
        )
        assert "chart_data" in result

    def test_kline_data_structure(self):
        """K 线数据结构验证"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = self._make_df()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            indicators=[],
        )
        for item in result["chart_data"]["kline"]:
            assert "date" in item
            assert "open" in item
            assert "high" in item
            assert "low" in item
            assert "close" in item
            assert "volume" in item

    def test_signals_sorted_by_date(self):
        """信号应按日期排序"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        mock_source.get_daily_quotes.return_value = self._make_df()
        gen = SignalGenerator(mock_source)

        result = gen.generate(
            ts_code="000001.SZ",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 20),
            indicators=["macd", "kdj", "ma"],
        )
        dates = [s["date"] for s in result["signals"]]
        assert dates == sorted(dates)


class TestStopLossRule:
    """止损止盈规则测试"""

    def test_fixed_stop_loss_triggered(self):
        """固定止损触发"""
        from app.services.signal.generator import StopLossRule
        entry_price = 10.0
        current_price = 9.4  # 跌幅 6%
        assert StopLossRule.fixed_stop_loss(entry_price, current_price, stop_pct=0.05)

    def test_fixed_stop_loss_not_triggered(self):
        """固定止损未触发"""
        from app.services.signal.generator import StopLossRule
        entry_price = 10.0
        current_price = 9.6  # 跌幅 4%
        assert not StopLossRule.fixed_stop_loss(entry_price, current_price, stop_pct=0.05)

    def test_fixed_stop_loss_exact_boundary(self):
        """固定止损边界值（恰好等于止损价）"""
        from app.services.signal.generator import StopLossRule
        entry_price = 10.0
        current_price = 9.5  # 恰好 5%
        assert StopLossRule.fixed_stop_loss(entry_price, current_price, stop_pct=0.05)

    def test_fixed_stop_loss_custom_pct(self):
        """自定义止损比例"""
        from app.services.signal.generator import StopLossRule
        assert StopLossRule.fixed_stop_loss(100, 88, stop_pct=0.10)
        assert not StopLossRule.fixed_stop_loss(100, 92, stop_pct=0.10)

    def test_take_profit_triggered(self):
        """止盈触发"""
        from app.services.signal.generator import StopLossRule
        entry_price = 10.0
        current_price = 11.2  # 涨幅 12%
        assert StopLossRule.take_profit(entry_price, current_price, profit_pct=0.1)

    def test_take_profit_not_triggered(self):
        """止盈未触发"""
        from app.services.signal.generator import StopLossRule
        entry_price = 10.0
        current_price = 10.8  # 涨幅 8%
        assert not StopLossRule.take_profit(entry_price, current_price, profit_pct=0.1)

    def test_take_profit_custom_pct(self):
        """自定义止盈比例"""
        from app.services.signal.generator import StopLossRule
        assert StopLossRule.take_profit(100, 125, profit_pct=0.20)
        assert not StopLossRule.take_profit(100, 115, profit_pct=0.20)

    def test_trailing_stop_triggered(self):
        """移动止损触发"""
        from app.services.signal.generator import StopLossRule
        entry_price = 10.0
        highest_price = 12.0
        current_price = 11.3  # 从最高回撤 5.8%
        assert StopLossRule.trailing_stop(entry_price, highest_price, current_price, trail_pct=0.05)

    def test_trailing_stop_not_triggered(self):
        """移动止损未触发"""
        from app.services.signal.generator import StopLossRule
        assert not StopLossRule.trailing_stop(10.0, 12.0, 11.8, trail_pct=0.05)

    def test_trailing_stop_custom_pct(self):
        """自定义移动止损比例"""
        from app.services.signal.generator import StopLossRule
        assert StopLossRule.trailing_stop(10, 100, 85, trail_pct=0.15)
        assert not StopLossRule.trailing_stop(10, 100, 90, trail_pct=0.15)


class TestSignalAPI:
    """信号 API 测试"""

    def test_generate_endpoint_structure(self):
        """信号生成 API 返回结构验证"""
        from app.api.signal import SignalGenerateRequest
        req = SignalGenerateRequest(ts_code="000001.SZ")
        assert req.ts_code == "000001.SZ"
        assert req.indicators == ["macd", "kdj", "ma"]
        assert req.params == {}

    def test_generate_request_custom_indicators(self):
        """自定义指标列表"""
        from app.api.signal import SignalGenerateRequest
        req = SignalGenerateRequest(
            ts_code="600036.SH",
            indicators=["macd"],
            start_date="2024-01-01",
            end_date="2024-06-01",
        )
        assert req.indicators == ["macd"]
        assert req.start_date == "2024-01-01"
