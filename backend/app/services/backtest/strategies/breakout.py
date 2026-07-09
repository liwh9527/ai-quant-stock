"""通道突破策略"""

from . import register_strategy

register_strategy("breakout", {
    "name": "通道突破策略",
    "key": "breakout",
    "category": "趋势",
    "description": "价格突破20日高点入场，跌破10日低点出场。经典趋势突破策略，配合成交量确认。",
    "suitable": "趋势启动初期、突破行情",
    "params": {
        "entry_period": {"label": "突破周期", "default": 20, "min": 10, "max": 60, "step": 5},
        "exit_period": {"label": "跌破周期", "default": 10, "min": 5, "max": 20, "step": 5},
        "max_positions": {"label": "最大持仓", "default": 5, "min": 3, "max": 10, "step": 1},
        "volume_ratio": {"label": "放量倍数", "default": 1.5, "min": 1.0, "max": 3.0, "step": 0.1},
    },
    "config": {
        "name": "通道突破策略",
        "description": "价格突破20日高点入场，跌破10日低点出场",
        "screening": {
            "universe": "all",
            "conditions": [
                {"field": "close", "op": ">", "value": 10},
                {"field": "turnover_rate", "op": ">", "value": 1},
                {"field": "pct_chg_20d", "op": ">", "value": 5},
            ],
            "sort": {"field": "pct_chg_20d", "order": "desc"},
            "limit": 5
        },
        "entry": {"timing": "open", "position_sizing": {"method": "equal"}},
        "exit": {"rules": [
            {"type": "stop_loss", "pct": -0.06, "action": "sell_immediate"}
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
