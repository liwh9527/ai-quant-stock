"""价值投资策略"""

from . import register_strategy

register_strategy("value", {
    "name": "价值投资策略",
    "key": "value",
    "category": "价值",
    "description": "低PE高ROE选股，低PB估值保护，长期持有。适合震荡市和慢牛行情。",
    "suitable": "估值合理的市场，偏好大盘蓝筹",
    "params": {
        "pe_max": {"label": "PE上限", "default": 20, "min": 10, "max": 30, "step": 5},
        "roe_min": {"label": "ROE下限(%)", "default": 15, "min": 10, "max": 25, "step": 5},
        "pb_max": {"label": "PB上限", "default": 3, "min": 1, "max": 5, "step": 1},
        "max_positions": {"label": "最大持仓", "default": 5, "min": 3, "max": 10, "step": 1},
    },
    "config": {
        "name": "价值投资策略",
        "description": "低PE高ROE选股，长期持有",
        "screening": {
            "universe": "主板",
            "conditions": [
                {"field": "pe", "op": ">", "value": 0},
                {"field": "pe", "op": "<", "value": 20},
                {"field": "roe", "op": ">", "value": 15},
                {"field": "pb", "op": ">", "value": 0},
                {"field": "pb", "op": "<", "value": 3},
            ],
            "sort": {"field": "roe", "order": "desc"},
            "limit": 5
        },
        "entry": {"timing": "open", "position_sizing": {"method": "equal"}},
        "exit": {"rules": [
            {"type": "stop_loss", "pct": -0.10, "action": "sell_immediate"}
        ]},
        "risk_control": {"max_positions": 5},
        "cost": {"commission": 0.0003, "stamp_tax": 0.001, "slippage": 0.001},
        "initial_cash": 1000000
    }
})
