"""海龟交易策略"""

from . import register_strategy

register_strategy("turtle", {
    "name": "海龟交易策略",
    "key": "turtle",
    "category": "趋势",
    "description": "价格突破20日高点入场，跌破10日低点出场，ATR动态仓位管理。经典趋势跟踪策略。",
    "suitable": "趋势明确的市场，震荡市表现较差",
    "params": {
        "entry_period": {"label": "入场突破周期", "default": 20, "min": 10, "max": 55, "step": 5},
        "exit_period": {"label": "出场跌破周期", "default": 10, "min": 5, "max": 20, "step": 5},
        "max_positions": {"label": "最大持仓", "default": 4, "min": 1, "max": 8, "step": 1},
        "risk_per_trade": {"label": "单笔风险", "default": 0.02, "min": 0.01, "max": 0.05, "step": 0.005},
    },
    "config": {
        "name": "海龟交易策略",
        "description": "20日高点突破入场，10日低点出场，ATR动态仓位",
        "screening": {
            "universe": "主板",
            "conditions": [
                {"field": "close", "op": ">", "value": 10},
                {"field": "turnover_rate", "op": ">", "value": 1},
            ],
            "sort": {"field": "pct_chg_20d", "order": "desc"},
            "limit": 10
        },
        "entry": {"timing": "open", "position_sizing": {"method": "equal"}},
        "exit": {"rules": [
            {"type": "stop_loss", "pct": -0.06, "action": "sell_immediate"}
        ]},
        "risk_control": {
            "max_positions": 4,
            "market_timing": {"enabled": True, "index": "000300.SH", "condition": "close > ma20"},
            "consecutive_loss_pause": {"enabled": True, "threshold": 3, "pause_days": 3}
        },
        "cost": {"commission": 0.0003, "stamp_tax": 0.001, "slippage": 0.001},
        "initial_cash": 1000000
    }
})
