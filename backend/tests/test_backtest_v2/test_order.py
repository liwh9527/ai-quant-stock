"""OrderManager 单元测试"""
import pytest
from app.services.backtest.order import Order, OrderManager


class TestOrder:
    def test_create_buy_order(self):
        o = Order(ts_code='000001.SZ', action=Order.BUY, price=10.0, shares=1000, date='20260601')
        assert o.ts_code == '000001.SZ'
        assert o.action == 'BUY'
        assert o.executed is False

    def test_to_dict(self):
        o = Order(ts_code='000001.SZ', action=Order.BUY, price=10.0, shares=1000, date='20260601')
        d = o.to_dict()
        assert d['ts_code'] == '000001.SZ'
        assert d['action'] == 'BUY'


class TestOrderManager:
    def test_add_order(self):
        mgr = OrderManager()
        mgr.add_order(Order(ts_code='000001.SZ', action=Order.BUY, price=10.0, shares=1000, date='20260601'))
        assert mgr.get_pending_count() == 1

    def test_buy_order_immediate(self):
        """买入订单当日执行（竞价买入）"""
        mgr = OrderManager()
        mgr.add_order(Order(ts_code='000001.SZ', action=Order.BUY, price=10.0, shares=1000, date='20260601'))

        # 当天执行（用开盘价）
        executed = mgr.execute_pending('20260601', {'000001.SZ': 10.5}, {'000001.SZ': 11.0})
        assert len(executed) == 1
        assert executed[0].execute_price == 10.5  # 开盘价
        assert executed[0].executed is True

    def test_sell_order_t_plus_1(self):
        """卖出订单 T+1 执行"""
        mgr = OrderManager()
        mgr.add_order(Order(ts_code='000001.SZ', action=Order.SELL, price=10.0, shares=1000, date='20260601'))

        # 当天不执行
        executed = mgr.execute_pending('20260601', {'000001.SZ': 10.0}, {'000001.SZ': 11.0})
        assert len(executed) == 0

        # 第二天执行（用收盘价）
        executed = mgr.execute_pending('20260602', {'000001.SZ': 10.0}, {'000001.SZ': 11.0})
        assert len(executed) == 1
        assert executed[0].execute_price == 11.0  # 收盘价

    def test_multiple_orders(self):
        """多个订单混合执行"""
        mgr = OrderManager()
        mgr.add_order(Order(ts_code='000001.SZ', action=Order.BUY, price=10.0, shares=1000, date='20260601'))
        mgr.add_order(Order(ts_code='000002.SZ', action=Order.SELL, price=20.0, shares=500, date='20260601'))

        executed = mgr.execute_pending('20260601',
                                       {'000001.SZ': 10.5, '000002.SZ': 20.5},
                                       {'000001.SZ': 11.0, '000002.SZ': 21.0})
        # 买入当日执行，卖出需要 T+1
        assert len(executed) == 1
        assert executed[0].action == 'BUY'
        assert executed[0].execute_price == 10.5  # 开盘价

    def test_pending_count(self):
        mgr = OrderManager()
        assert mgr.get_pending_count() == 0
        mgr.add_order(Order(ts_code='000001.SZ', action=Order.BUY, price=10.0, shares=1000, date='20260601'))
        assert mgr.get_pending_count() == 1
