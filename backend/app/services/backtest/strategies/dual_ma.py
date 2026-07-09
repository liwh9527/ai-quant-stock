"""双均线策略"""

from . import register_strategy

register_strategy("dual_ma", {
    "name": "双均线策略",
    "key": "dual_ma",
    "category": "趋势",
    "description": "MA20上穿MA60买入，下穿卖出。牛市满仓、震荡市半仓、熊市空仓，根据大盘状态动态调仓。",
    "suitable": "趋势明确的市场，牛熊转换时效果好",
    "params": {
        "fast_ma": {"label": "快线周期", "default": 20, "min": 5, "max": 30, "step": 5},
        "slow_ma": {"label": "慢线周期", "default": 60, "min": 30, "max": 120, "step": 10},
        "max_positions": {"label": "最大持仓", "default": 5, "min": 3, "max": 10, "step": 1},
    },
    "config": {
        "name": "双均线策略",
        "description": "MA20/MA60交叉，大盘择时动态调仓",
        "screening": {
            "universe": "all",
            "conditions": [
                {"field": "close", "op": ">", "value": 10},
                {"field": "turnover_rate", "op": ">", "value": 0.5},
                {"field": "pct_chg_20d", "op": ">", "value": 0},
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
