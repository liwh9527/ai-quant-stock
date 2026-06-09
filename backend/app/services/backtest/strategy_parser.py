"""策略 DSL 解析器"""
import json
from typing import Dict, Any


class StrategyParser:
    """解析 JSON 策略配置"""

    REQUIRED_SECTIONS = ['screening', 'entry', 'exit']

    def parse(self, config: Dict) -> Dict:
        """解析并验证策略配置"""
        self._validate(config)
        return self._normalize(config)

    def parse_file(self, path: str) -> Dict:
        """从文件加载策略"""
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return self.parse(config)

    def _validate(self, config: Dict):
        """验证策略配置合法性"""
        for section in self.REQUIRED_SECTIONS:
            if section not in config:
                raise ValueError(f"策略配置缺少必要部分: {section}")

        # 验证选股条件
        conditions = config.get('screening', {}).get('conditions', [])
        for i, cond in enumerate(conditions):
            if 'field' not in cond:
                raise ValueError(f"条件 {i} 缺少 field")
            if 'op' not in cond:
                raise ValueError(f"条件 {i} 缺少 op")
            if cond['op'] not in ('>', '<', '>=', '<=', '==', '!=', 'in', 'not_in'):
                raise ValueError(f"条件 {i} 不支持的操作符: {cond['op']}")

        # 验证仓位管理
        sizing = config.get('entry', {}).get('position_sizing', {})
        method = sizing.get('method', 'equal')
        if method not in ('equal', 'tiered', 'risk_parity'):
            raise ValueError(f"不支持的仓位管理方式: {method}")

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """递归合并字典，override 覆盖 base"""
        result = {**base}
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _normalize(self, config: Dict) -> Dict:
        """规范化配置，填充默认值（深层合并）"""
        defaults = {
            'name': '未命名策略',
            'version': '1.0',
            'screening': {'universe': 'all', 'conditions': [], 'limit': 10},
            'entry': {'timing': 'open', 'position_sizing': {'method': 'equal'}},
            'exit': {'rules': []},
            'risk_control': {
                'max_positions': 3,
                'market_timing': {'enabled': False, 'index': '000001.SH', 'condition': 'close > ma5'},
                'consecutive_loss_pause': {'enabled': False, 'threshold': 3, 'pause_days': 1}
            },
            'cost': {'commission': 0.0003, 'stamp_tax': 0.001, 'slippage': 0.001},
            'initial_cash': 1000000
        }

        return self._deep_merge(defaults, config)

    def get_builtin_templates(self) -> Dict[str, Dict]:
        """获取内置策略模板"""
        return {
            'auction_limit_up': {
                'name': '竞价涨停连板策略',
                'description': '每日从涨停股中筛选竞价涨幅最高的买入，断板卖出',
                'screening': {
                    'universe': 'all',
                    'conditions': [
                        {'field': 'prev_limit_up', 'op': '==', 'value': True},
                        {'field': 'circ_mv', 'op': '<', 'value': 2000000},
                        {'field': 'close', 'op': '<', 'value': 50}
                    ],
                    'sort': {'field': 'auction_pct', 'order': 'desc'},
                    'limit': 3
                },
                'entry': {
                    'timing': 'open',
                    'position_sizing': {'method': 'equal'}
                },
                'exit': {
                    'rules': [
                        {'type': 'break_limit_up', 'action': 'sell_at_close'},
                        {'type': 'stop_loss', 'pct': -0.05, 'action': 'sell_immediate'}
                    ]
                },
                'risk_control': {
                    'max_positions': 3,
                    'market_timing': {'enabled': True, 'index': '000001.SH', 'condition': 'close > ma5'},
                    'consecutive_loss_pause': {'enabled': True, 'threshold': 3, 'pause_days': 1}
                },
                'cost': {'commission': 0.0003, 'stamp_tax': 0.001, 'slippage': 0.001},
                'initial_cash': 1000000
            },
            'value_investing': {
                'name': '价值投资策略',
                'description': '低PE高ROE选股，长期持有',
                'screening': {
                    'universe': '主板',
                    'conditions': [
                        {'field': 'pe', 'op': '>', 'value': 0},
                        {'field': 'pe', 'op': '<', 'value': 20},
                        {'field': 'roe', 'op': '>', 'value': 15},
                        {'field': 'pb', 'op': '>', 'value': 0},
                        {'field': 'pb', 'op': '<', 'value': 3}
                    ],
                    'sort': {'field': 'roe', 'order': 'desc'},
                    'limit': 5
                },
                'entry': {'timing': 'open', 'position_sizing': {'method': 'equal'}},
                'exit': {'rules': [{'type': 'stop_loss', 'pct': -0.1, 'action': 'sell_immediate'}]},
                'risk_control': {'max_positions': 5},
                'cost': {'commission': 0.0003, 'stamp_tax': 0.001, 'slippage': 0.001},
                'initial_cash': 1000000
            }
        }
