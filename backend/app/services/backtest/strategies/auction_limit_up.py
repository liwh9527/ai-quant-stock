"""竞价涨停连板策略"""

from . import register_strategy

register_strategy("auction_limit_up", {
    "name": "竞价涨停连板策略",
    "key": "auction_limit_up",
    "category": "事件驱动",
    "description": "每日从涨停股中筛选竞价涨幅最高的买入，断板卖出。高风险高收益的打板策略。",
    "suitable": "市场情绪高涨、涨停板活跃的环境",
    "params": {
        "max_positions": {"label": "最大持仓", "default": 3, "min": 1, "max": 5, "step": 1},
        "circ_mv_max": {"label": "流通市值上限(万)", "default": 2000000, "min": 500000, "max": 5000000, "step": 500000},
        "close_max": {"label": "股价上限", "default": 50, "min": 20, "max": 100, "step": 10},
        "stop_loss_pct": {"label": "止损比例", "default": -0.05, "min": -0.10, "max": -0.03, "step": 0.01},
    },
    "config": {
        "name": "竞价涨停连板策略",
        "description": "前日涨停+竞价涨幅最高买入，断板卖出",
        "screening": {
            "universe": "all",
            "conditions": [
                {"field": "prev_limit_up", "op": "==", "value": True},
                {"field": "circ_mv", "op": "<", "value": 2000000},
                {"field": "close", "op": "<", "value": 50},
            ],
            "sort": {"field": "auction_pct", "order": "desc"},
            "limit": 3
        },
        "entry": {"timing": "open", "position_sizing": {"method": "equal"}},
        "exit": {"rules": [
            {"type": "break_limit_up", "action": "sell_at_close"},
            {"type": "stop_loss", "pct": -0.05, "action": "sell_immediate"}
        ]},
        "risk_control": {
            "max_positions": 3,
            "market_timing": {"enabled": True, "index": "000001.SH", "condition": "close > ma5"},
            "consecutive_loss_pause": {"enabled": True, "threshold": 3, "pause_days": 1}
        },
        "cost": {"commission": 0.0003, "stamp_tax": 0.001, "slippage": 0.001},
        "initial_cash": 1000000
    }
})
