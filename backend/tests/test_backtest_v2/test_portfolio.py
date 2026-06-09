"""Portfolio 和 Position 单元测试"""
import pytest
from app.services.backtest.portfolio import Portfolio, Position


class TestPosition:
    def test_create(self):
        pos = Position(ts_code='000001.SZ', buy_price=10.0, buy_date='20260601', shares=1000)
        assert pos.ts_code == '000001.SZ'
        assert pos.buy_price == 10.0
        assert pos.shares == 1000
        assert pos.hold_days == 0

    def test_market_value(self):
        pos = Position(ts_code='000001.SZ', buy_price=10.0, buy_date='20260601', shares=1000)
        assert pos.market_value(12.0) == 12000.0

    def test_profit_pct(self):
        pos = Position(ts_code='000001.SZ', buy_price=10.0, buy_date='20260601', shares=1000)
        assert pos.profit_pct(12.0) == pytest.approx(0.2)
        assert pos.profit_pct(8.0) == pytest.approx(-0.2)

    def test_update_hold_days(self):
        pos = Position(ts_code='000001.SZ', buy_price=10.0, buy_date='20260601', shares=1000)
        pos.update_hold_days()
        assert pos.hold_days == 1
        pos.update_hold_days()
        assert pos.hold_days == 2


class TestPortfolio:
    def test_initial_state(self):
        p = Portfolio(100000)
        assert p.cash == 100000
        assert p.position_count() == 0

    def test_buy(self):
        p = Portfolio(100000)
        assert p.buy('000001.SZ', 10.0, 1000, '20260601') is True
        assert p.has_position('000001.SZ')
        assert p.cash < 100000

    def test_buy_insufficient_cash(self):
        p = Portfolio(1000)
        assert p.buy('000001.SZ', 10.0, 1000, '20260601') is False
        assert not p.has_position('000001.SZ')

    def test_sell(self):
        p = Portfolio(100000)
        p.buy('000001.SZ', 10.0, 1000, '20260601')
        cash_before = p.cash
        p.sell('000001.SZ', 12.0, 1000, '20260602')
        assert p.cash > cash_before
        assert not p.has_position('000001.SZ')

    def test_sell_partial(self):
        p = Portfolio(100000)
        p.buy('000001.SZ', 10.0, 1000, '20260601')
        p.sell('000001.SZ', 12.0, 500, '20260602')
        assert p.has_position('000001.SZ')
        assert p.get_position('000001.SZ').shares == 500

    def test_total_value(self):
        p = Portfolio(100000)
        p.buy('000001.SZ', 10.0, 1000, '20260601')
        total = p.total_value({'000001.SZ': 10.0})
        assert total == pytest.approx(100000, rel=0.01)

    def test_daily_update(self):
        p = Portfolio(100000)
        p.buy('000001.SZ', 10.0, 1000, '20260601')
        p.daily_update('20260601', {'000001.SZ': 10.5})
        assert len(p.history) == 1
        assert p.get_position('000001.SZ').hold_days == 1

    def test_can_buy(self):
        p = Portfolio(100000)
        assert p.can_buy(10.0, 1000) is True
        assert p.can_buy(10.0, 100000) is False
