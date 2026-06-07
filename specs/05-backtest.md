# 策略回测

## 目标

支持自然语言描述策略，自动回测历史数据，输出收益曲线、风险指标和交易统计。

## 用户故事

作为投资者，我想要描述一个交易策略（如"MACD 金叉买入，死叉卖出"），系统自动回测并展示收益情况，以便评估策略有效性。

## 页面设计

### 布局

```
┌─────────────────────────────────────────┐
│  策略回测                                │
├─────────────────────────────────────────┤
│  ┌─ 策略配置 ──────────────────────┐    │
│  │ 策略描述：[MACD 金叉买入，死叉卖出] │    │
│  │ 回测区间：[2020-01-01] ~ [2024-12-31]│
│  │ 初始资金：[100000]                │    │
│  │ 基准：[沪深300 ▼]                │    │
│  │ [开始回测]                        │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 收益曲线 ──────────────────────┐    │
│  │  ██████████████████████████████  │    │
│  │  █ 策略收益 vs 基准收益          █  │    │
│  │  ██████████████████████████████  │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 指标卡片 ──────────────────────┐    │
│  │ 总收益: 45.2%  年化: 12.3%      │    │
│  │ 最大回撤: -15.8%  夏普: 1.25    │    │
│  │ 胜率: 58.3%  交易次数: 42       │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 交易记录 ──────────────────────┐    │
│  │ 日期      操作  代码    价格   盈亏 │    │
│  │ 2020-03-15 买入 000001  12.50  --  │    │
│  │ 2020-06-20 卖出 000001  15.80 +26% │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## API 接口

### 创建回测任务

```
POST /api/backtest/run
```

请求：
```json
{
  "strategy_description": "MACD 金叉买入，死叉卖出",
  "start_date": "2020-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 100000,
  "benchmark": "000300.SH",
  "commission_rate": 0.0003,
  "slippage": 0.001
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "task_id": "backtest_20240101_001",
    "status": "running"
  },
  "msg": ""
}
```

### 查询回测结果

```
GET /api/backtest/result/{task_id}
```

响应：
```json
{
  "code": 0,
  "data": {
    "status": "completed",
    "metrics": {
      "total_return": 45.2,
      "annual_return": 12.3,
      "max_drawdown": -15.8,
      "sharpe_ratio": 1.25,
      "win_rate": 58.3,
      "trade_count": 42,
      "avg_holding_days": 15.3
    },
    "equity_curve": [
      {"date": "2020-01-01", "strategy": 100000, "benchmark": 100000},
      {"date": "2020-01-02", "strategy": 100500, "benchmark": 100300}
    ],
    "trades": [
      {
        "date": "2020-03-15",
        "action": "BUY",
        "ts_code": "000001.SZ",
        "price": 12.50,
        "shares": 1000,
        "pnl": null
      }
    ]
  },
  "msg": ""
}
```

## 核心逻辑

### 回测引擎

```python
# backend/app/services/backtest/engine.py

import backtrader as bt

class BacktestEngine:
    def __init__(self, strategy_config: Dict):
        self.config = strategy_config
        self.cerebro = bt.Cerebro()

    def setup(self):
        """配置回测引擎"""
        # 设置初始资金
        self.cerebro.broker.setcash(self.config["initial_capital"])
        # 设置佣金
        self.cerebro.broker.setcommission(
            commission=self.config.get("commission_rate", 0.0003)
        )
        # 添加策略
        self.cerebro.addstrategy(
            AIStrategy,
            config=self.config
        )

    def run(self) -> Dict:
        """执行回测"""
        self.setup()
        results = self.cerebro.run()
        return self._extract_metrics(results)

    def _extract_metrics(self, results) -> Dict:
        """提取回测指标"""
        strategy = results[0]
        return {
            "total_return": strategy.broker.getvalue() / self.config["initial_capital"] - 1,
            "sharpe_ratio": self._calc_sharpe(strategy),
            "max_drawdown": self._calc_max_drawdown(strategy),
            # ...
        }
```

### AI 策略适配

```python
# backend/app/services/backtest/strategy.py

class AIStrategy(bt.Strategy):
    """将 AI 生成的策略配置转换为 Backtrader 策略"""

    params = (("config", None),)

    def __init__(self):
        self.config = self.params.config
        self._setup_indicators()

    def _setup_indicators(self):
        """根据配置添加技术指标"""
        for rule in self.config.get("entry_rules", []):
            if rule["indicator"] == "macd":
                self.macd = bt.indicators.MACD(self.data.close)

    def next(self):
        """每根 K 线执行"""
        if self._check_entry_rules():
            self.buy()
        elif self._check_exit_rules():
            self.sell()
```

### 交易成本建模

- 佣金：默认万三（0.03%）
- 印花税：卖出千一（0.1%）
- 滑点：默认 0.1%

### 幸存者偏差处理

- 数据库包含已退市股票数据
- 回测时包含已退市股票的完整生命周期

### 未来信息防泄漏

- 所有指标计算使用截止到当前日期的数据
- 财务数据使用公告日而非报告期

## 验收标准

- [ ] 自然语言描述可转换为策略配置
- [ ] 收益曲线正确绘制
- [ ] 风险指标计算正确
- [ ] 交易记录完整
- [ ] 支持基准对比
- [ ] 交易成本建模生效
- [ ] 无未来信息泄漏
- [ ] 移动端界面可用
