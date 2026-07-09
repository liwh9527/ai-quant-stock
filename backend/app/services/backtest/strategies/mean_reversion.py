"""均值回归策略"""

from . import register_strategy

register_strategy("mean_reversion", {
    "name": "均值回归策略",
    "key": "mean_reversion",
    "category": "均值回归",
    "description": "RSI超卖+股价低于20日均线时买入，回归均值后卖出。适合震荡市高抛低吸。",
    "suitable": "震荡市、箱体整理行情",
    "params": {
        "rsi_threshold": {"label": "RSI超卖阈值", "default": 30, "min": 20, "max": 40, "step": 5},
        "ma_period": {"label": "均线周期", "default": 20, "min": 10, "max": 60, "step": 5},
        "max_positions": {"label": "最大持仓", "default": 5, "min": 3, "max": 10, "step": 1},
        "take_profit": {"label": "止盈比例", "default": 0.08, "min": 0.03, "max": 0.15, "step": 0.01},
    },
    "config": {
        "name": "均值回归策略",
        "description": "RSI超卖+价格低于均线买入，回归均值卖出",
        "screening": {
            "universe": "all",
            "conditions": [
                {"field": "pe", "op": ">", "value": 0},
                {"field": "pe", "op": "<", "value": 50},
                {"field": "close", "op": ">", "value": 5},
                {"field": "pct_chg_5d", "op": "<", "value": -3},
            ],
            "sort": {"field": "pct_chg_5d", "order": "asc"},
            "limit": 5
        },
        "entry": {"timing": "open", "position_sizing": {"method": "equal"}},
        "exit": {"rules": [
            {"type": "stop_loss", "pct": -0.08, "action": "sell_immediate"}
        ]},
        "risk_control": {
            "max_positions": 5,
            "market_timing": {"enabled": False},
            "consecutive_loss_pause": {"enabled": True, "threshold": 3, "pause_days": 2}
        },
        "cost": {"commission": 0.0003, "stamp_tax": 0.001, "slippage": 0.001},
        "initial_cash": 1000000
    }
})
