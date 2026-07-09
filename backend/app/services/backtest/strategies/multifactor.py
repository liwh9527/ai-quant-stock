"""多因子选股策略"""

from . import register_strategy

register_strategy("multifactor", {
    "name": "多因子选股策略",
    "key": "multifactor",
    "category": "多因子",
    "description": "综合动量、波动率、均线、成交量、RSI五个因子加权评分选股，每周调仓。",
    "suitable": "各类市场环境，因子权重可根据市场风格调整",
    "params": {
        "w_momentum": {"label": "动量权重", "default": 0.30, "min": 0, "max": 1, "step": 0.05},
        "w_volatility": {"label": "波动率权重", "default": 0.20, "min": 0, "max": 1, "step": 0.05},
        "w_ma": {"label": "均线权重", "default": 0.25, "min": 0, "max": 1, "step": 0.05},
        "max_positions": {"label": "最大持仓", "default": 5, "min": 3, "max": 10, "step": 1},
    },
    "config": {
        "name": "多因子选股策略",
        "description": "动量30%+波动20%+均线25%+成交量15%+RSI10%综合评分",
        "screening": {
            "universe": "all",
            "conditions": [
                {"field": "pct_chg_20d", "op": ">", "value": 0},
                {"field": "turnover_rate", "op": ">", "value": 0.5},
                {"field": "close", "op": ">", "value": 5},
                {"field": "pe", "op": ">", "value": 0},
                {"field": "pe", "op": "<", "value": 100},
            ],
            "sort": {"field": "pct_chg_20d", "order": "desc"},
            "limit": 5
        },
        "entry": {"timing": "open", "position_sizing": {"method": "equal"}},
        "exit": {"rules": [
            {"type": "stop_loss", "pct": -0.08, "action": "sell_immediate"}
        ]},
        "risk_control": {
            "max_positions": 5,
            "market_timing": {"enabled": True, "index": "000300.SH", "condition": "close > ma20"},
            "consecutive_loss_pause": {"enabled": True, "threshold": 3, "pause_days": 2}
        },
        "cost": {"commission": 0.0003, "stamp_tax": 0.001, "slippage": 0.001},
        "initial_cash": 1000000
    }
})
