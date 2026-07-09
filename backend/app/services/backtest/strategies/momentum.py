"""动量轮动策略"""

from . import register_strategy

register_strategy("momentum", {
    "name": "动量轮动策略",
    "key": "momentum",
    "category": "动量",
    "description": "按20日涨幅排名选股，每周调仓，大盘MA20上方才入场。适合牛市环境。",
    "suitable": "趋势向上、板块轮动明显的市场",
    "params": {
        "momentum_period": {"label": "动量周期", "default": 20, "min": 5, "max": 60, "step": 5},
        "rebalance_days": {"label": "调仓周期(天)", "default": 5, "min": 1, "max": 20, "step": 1},
        "max_positions": {"label": "最大持仓", "default": 5, "min": 1, "max": 10, "step": 1},
        "index_ma_period": {"label": "大盘均线周期", "default": 20, "min": 5, "max": 60, "step": 5},
    },
    "config": {
        "name": "动量轮动策略",
        "description": "20日涨幅排名选前5，每周调仓，大盘MA20择时",
        "screening": {
            "universe": "all",
            "conditions": [
                {"field": "pct_chg_20d", "op": ">", "value": 0},
                {"field": "turnover_rate", "op": ">", "value": 0.5},
                {"field": "close", "op": ">", "value": 5},
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
