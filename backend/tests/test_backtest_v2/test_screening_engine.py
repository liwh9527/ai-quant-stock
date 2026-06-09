"""ScreeningEngine 单元测试"""
import pytest
from unittest.mock import MagicMock
from app.services.backtest.screening_engine import DailyScreeningEngine


@pytest.fixture
def engine():
    return DailyScreeningEngine()


ALL_DAILY = {
    '000001.SZ': {'ts_code': '000001.SZ', 'open': 10.0, 'close': 11.0, 'pre_close': 10.0},
    '000002.SZ': {'ts_code': '000002.SZ', 'open': 15.0, 'close': 16.0, 'pre_close': 15.0},
    '300001.SZ': {'ts_code': '300001.SZ', 'open': 20.0, 'close': 22.0, 'pre_close': 20.0},
    '000004.SZ': {'ts_code': '000004.SZ', 'open': 5.0, 'close': 5.5, 'pre_close': 5.0},
}
ALL_BASIC = {
    '000001.SZ': {'ts_code': '000001.SZ', 'turnover_rate': 5.0, 'circ_mv': 1000000},
    '000002.SZ': {'ts_code': '000002.SZ', 'turnover_rate': 3.0, 'circ_mv': 500000},
    '300001.SZ': {'ts_code': '300001.SZ', 'turnover_rate': 8.0, 'circ_mv': 300000},
    '000004.SZ': {'ts_code': '000004.SZ', 'turnover_rate': 15.0, 'circ_mv': 200000},
}


@pytest.fixture
def mock_dm():
    """模拟 DataManager"""
    dm = MagicMock()
    dm.get_all_stocks.return_value = [
        {'ts_code': '000001.SZ', 'name': '平安银行', 'industry': '银行', 'market': '主板'},
        {'ts_code': '000002.SZ', 'name': '万科A', 'industry': '房地产', 'market': '主板'},
        {'ts_code': '300001.SZ', 'name': '特锐德', 'industry': '电气设备', 'market': '创业板'},
        {'ts_code': '000004.SZ', 'name': '*ST国华', 'industry': '计算机', 'market': '主板'},
    ]
    # 按输入 codes 过滤返回
    dm.get_daily_for_date.side_effect = lambda codes, date: {c: ALL_DAILY[c] for c in codes if c in ALL_DAILY}
    dm.get_daily_basic.side_effect = lambda codes, date: {c: ALL_BASIC[c] for c in codes if c in ALL_BASIC}
    dm.get_financial.return_value = {}
    dm.get_prev_limit_up_stocks.return_value = ['000001.SZ', '000002.SZ']
    return dm


class TestScreeningEngine:
    def test_screen_basic(self, engine, mock_dm):
        config = {
            'universe': 'all',
            'conditions': [],
            'sort': {'field': 'close', 'order': 'desc'},
            'limit': 10
        }
        results = engine.screen('20260608', config, mock_dm)
        assert len(results) > 0

    def test_screen_exclude_st(self, engine, mock_dm):
        config = {
            'universe': 'all',
            'conditions': [],
            'limit': 10
        }
        results = engine.screen('20260608', config, mock_dm)
        codes = [r['ts_code'] for r in results]
        assert '000004.SZ' not in codes  # *ST 被排除

    def test_screen_filter_main_board(self, engine, mock_dm):
        config = {
            'universe': '主板',
            'conditions': [],
            'limit': 10
        }
        results = engine.screen('20260608', config, mock_dm)
        codes = [r['ts_code'] for r in results]
        assert '300001.SZ' not in codes  # 创业板被排除

    def test_screen_prev_limit_up(self, engine, mock_dm):
        config = {
            'universe': 'all',
            'conditions': [{'field': 'prev_limit_up', 'op': '==', 'value': True}],
            'limit': 10
        }
        results = engine.screen('20260608', config, mock_dm)
        for r in results:
            assert r.get('prev_limit_up') is True

    def test_screen_price_filter(self, engine, mock_dm):
        config = {
            'universe': 'all',
            'conditions': [{'field': 'close', 'op': '<', 'value': 15}],
            'limit': 10
        }
        results = engine.screen('20260608', config, mock_dm)
        for r in results:
            assert r['close'] < 15

    def test_screen_sort_desc(self, engine, mock_dm):
        config = {
            'universe': 'all',
            'conditions': [],
            'sort': {'field': 'close', 'order': 'desc'},
            'limit': 10
        }
        results = engine.screen('20260608', config, mock_dm)
        closes = [r['close'] for r in results]
        assert closes == sorted(closes, reverse=True)

    def test_screen_limit(self, engine, mock_dm):
        config = {
            'universe': 'all',
            'conditions': [],
            'limit': 1
        }
        results = engine.screen('20260608', config, mock_dm)
        assert len(results) <= 1

    def test_screen_auction_pct(self, engine, mock_dm):
        """竞价涨幅计算"""
        config = {
            'universe': 'all',
            'conditions': [{'field': 'auction_pct', 'op': '>', 'value': 0.05}],
            'limit': 10
        }
        results = engine.screen('20260608', config, mock_dm)
        for r in results:
            assert r.get('auction_pct', 0) > 0.05
