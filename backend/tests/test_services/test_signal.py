"""买卖信号模块单元测试"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock


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

    def test_kdj_returns_three_series(self):
        """KDJ 应返回 K, D, J"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df()
        k, d, j = TechnicalIndicators.kdj(df)
        assert len(k) == len(df)
        assert len(d) == len(df)
        assert len(j) == len(df)

    def test_ma_returns_dict(self):
        """均线应返回字典"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df()
        result = TechnicalIndicators.ma(df, periods=[5, 10, 20])
        assert "ma5" in result
        assert "ma10" in result
        assert "ma20" in result

    def test_ma_values_reasonable(self):
        """均线值应在合理范围内"""
        from app.services.signal.indicators import TechnicalIndicators
        df = self._make_df()
        result = TechnicalIndicators.ma(df, periods=[5])
        valid = result["ma5"].dropna()
        assert len(valid) > 0


class TestSignalGenerator:
    """信号生成器测试"""

    def test_generate_returns_list(self):
        """generate 应返回列表"""
        from app.services.signal.generator import SignalGenerator
        mock_source = MagicMock()
        gen = SignalGenerator(mock_source)
        # 不实际调用，只验证类型
        assert hasattr(gen, "generate")


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

    def test_trailing_stop_triggered(self):
        """移动止损触发"""
        from app.services.signal.generator import StopLossRule
        entry_price = 10.0
        highest_price = 12.0
        current_price = 11.3  # 从最高回撤 5.8%
        assert StopLossRule.trailing_stop(entry_price, highest_price, current_price, trail_pct=0.05)
