"""趋势择时策略"""

from . import register_strategy

register_strategy("trend_timing", {
    "name": "趋势择时策略",
    "key": "trend_timing",
    "category": "趋势",
    "description": "大盘MA20上方才入场，选均线之上且放量的股票，根据波动率动态调仓位。",
    "suitable": "趋势明确的市场，能有效规避大级别下跌",
    "params": {
        "max_positions": {"label": "最大持仓", "default": 4, "min": 2, "max": 8, "step": 1},
        "index_ma_period": {"label": "大盘均线周期", "default": 20, "min": 10, "max": 60, "step": 5},
        "rebalance_days": {"label": "调仓周期(天)", "default": 5, "min": 1, "max": 20, "step": 1},
    },
    "config": {
        "name": "趋势择时策略",
        "description": "大盘MA20上方才入场，选均线之上放量股",
        "screening": {
            "universe": "all",
            "conditions": [
                {"field": "close", "op": ">", "value": 5},
                {"field": "turnover_rate", "op": ">", "value": 1},
                {"field": "pct_chg_5d", "op": ">", "value": 0},
            ],
            "sort": {"field": "pct_chg_20d", "order": "desc"},
            "limit": 5
        },
        "entry": {"timing": "open", "position_sizing": {"method": "equal"}},
        "exit": {"rules": [
            {"type": "stop_loss", "pct": -0.06, "action": "sell_immediate"}
        ]},
        "risk_control": {
            "max_positions": 4,
            "market_timing": {"enabled": True, "index": "000300.SH", "condition": "close > ma20"},
            "consecutive_loss_pause": {"enabled": True, "threshold": 3, "pause_days": 2}
        },
        "cost": {"commission": 0.0003, "stamp_tax": 0.001, "slippage": 0.001},
        "initial_cash": 1000000
    }
})
