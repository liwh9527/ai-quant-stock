"""低波动策略"""

from . import register_strategy

register_strategy("low_volatility", {
    "name": "低波动策略",
    "key": "low_volatility",
    "category": "风险平价",
    "description": "选波动率最低的股票，长期持有。低波动异象：低波动股票长期收益往往高于高波动股票。",
    "suitable": "不确定的市场、防守型配置",
    "params": {
        "max_positions": {"label": "最大持仓", "default": 5, "min": 3, "max": 10, "step": 1},
        "pct_chg_20d_max": {"label": "20日涨幅上限(%)", "default": 20, "min": 10, "max": 50, "step": 5},
        "rebalance_days": {"label": "调仓周期(天)", "default": 20, "min": 5, "max": 60, "step": 5},
    },
    "config": {
        "name": "低波动策略",
        "description": "选低波动股票长期持有，月度调仓",
        "screening": {
            "universe": "主板",
            "conditions": [
                {"field": "pe", "op": ">", "value": 0},
                {"field": "pe", "op": "<", "value": 30},
                {"field": "roe", "op": ">", "value": 10},
                {"field": "close", "op": ">", "value": 10},
                {"field": "pct_chg_20d", "op": ">", "value": -5},
                {"field": "pct_chg_20d", "op": "<", "value": 20},
            ],
            "sort": {"field": "pct_chg_20d", "order": "asc"},
            "limit": 5
        },
        "entry": {"timing": "open", "position_sizing": {"method": "equal"}},
        "exit": {"rules": [
            {"type": "stop_loss", "pct": -0.12, "action": "sell_immediate"}
        ]},
        "risk_control": {"max_positions": 5},
        "cost": {"commission": 0.0003, "stamp_tax": 0.001, "slippage": 0.001},
        "initial_cash": 1000000
    }
})
