"""StrategyParser 单元测试"""
import pytest
from app.services.backtest.strategy_parser import StrategyParser


@pytest.fixture
def parser():
    return StrategyParser()


class TestStrategyParser:
    def test_parse_valid_config(self, parser):
        config = {
            'screening': {'conditions': [{'field': 'close', 'op': '<', 'value': 50}]},
            'entry': {'timing': 'open'},
            'exit': {'rules': []}
        }
        result = parser.parse(config)
        assert result['screening']['conditions'][0]['field'] == 'close'

    def test_parse_missing_section(self, parser):
        config = {'screening': {'conditions': []}}
        with pytest.raises(ValueError, match='缺少必要部分'):
            parser.parse(config)

    def test_parse_invalid_operator(self, parser):
        config = {
            'screening': {'conditions': [{'field': 'close', 'op': 'LIKE', 'value': 50}]},
            'entry': {},
            'exit': {}
        }
        with pytest.raises(ValueError, match='不支持的操作符'):
            parser.parse(config)

    def test_parse_fills_defaults(self, parser):
        config = {
            'screening': {'conditions': []},
            'entry': {},
            'exit': {}
        }
        result = parser.parse(config)
        assert result['name'] == '未命名策略'
        assert result['risk_control']['max_positions'] == 3
        assert result['cost']['commission'] == 0.0003

    def test_get_builtin_templates(self, parser):
        templates = parser.get_builtin_templates()
        assert 'auction_limit_up' in templates
        assert 'value_investing' in templates

    def test_parse_file(self, parser, tmp_path):
        import json
        config = {
            'screening': {'conditions': []},
            'entry': {},
            'exit': {}
        }
        f = tmp_path / 'test.json'
        f.write_text(json.dumps(config), encoding='utf-8')
        result = parser.parse_file(str(f))
        assert result['name'] == '未命名策略'
