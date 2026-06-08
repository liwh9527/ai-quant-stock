# 回测引擎 V2 重构计划

## 背景

当前回测引擎基于 Backtrader，只支持单股票技术指标策略（MACD/KDJ/RSI/均线），
无法满足多股票组合回测、自定义选股条件、动态仓位管理等需求。

用户需求的"竞价涨停连板策略"需要：
- 每日从全市场选股（5000+ 只股票）
- 多条件组合筛选（涨停、竞价涨幅、市值、换手率等）
- 动态仓位管理（分级仓位、最大持仓数）
- T+1 交易规则
- 连板持有、断板卖出逻辑

## 问题清单

| # | 问题 | 影响 |
|---|------|------|
| 1 | 只支持单股票 | 无法回测多股票组合策略 |
| 2 | 策略配置固定 | 只支持技术指标，不支持自定义条件 |
| 3 | 无选股逻辑 | 不能每日从全市场选股 |
| 4 | 数据从 API 获取 | 未利用数据库已有数据，速度慢 |
| 5 | 不支持 T+1 | A 股 T+1 规则未处理 |
| 6 | 无连板逻辑 | 无法实现涨停追踪策略 |

## 目标架构

```
┌─────────────────────────────────────────────────┐
│                  StrategyConfig                  │
│                                                  │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│  │ 选股条件    │ │ 买入规则    │ │ 卖出规则      │ │
│  │ screening   │ │ entry      │ │ exit         │ │
│  └────────────┘ └────────────┘ └──────────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│  │ 仓位管理    │ │ 风控规则    │ │ 大盘择时      │ │
│  │ position    │ │ risk       │ │ market_timing│ │
│  └────────────┘ └────────────┘ └──────────────┘ │
└───────────────────────┬─────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│           PortfolioBacktestEngine                │
│                                                  │
│  for each trading_day:                           │
│    1. check_market_timing()    # 大盘择时        │
│    2. check_risk_control()     # 风控检查        │
│    3. screen_stocks()          # 每日选股        │
│    4. check_existing_positions() # 持仓检查      │
│    5. generate_orders()        # 生成订单        │
│    6. execute_orders()         # 执行交易(T+1)  │
│    7. update_portfolio()       # 更新净值        │
│    8. log_daily_snapshot()     # 记录快照        │
└───────────────────────┬─────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│               BacktestResult                    │
│                                                  │
│  metrics        # 收益/回撤/夏普/胜率            │
│  equity_curve   # 每日净值曲线                   │
│  trades         # 交易记录                      │
│  positions      # 每日持仓快照                   │
│  screening_log  # 每日选股日志                   │
└─────────────────────────────────────────────────┘
```

## 实施阶段

### Phase 1: 数据管理器 (DataManager)

**目标**: 统一数据访问层，数据库优先 + API 补充

**文件**:
- `backend/app/services/data/data_manager.py` (新建)

**功能**:
```python
class DataManager:
    """统一数据管理器"""
    
    def get_daily(self, ts_codes, start_date, end_date):
        """获取日线数据，优先查数据库"""
        
    def get_financial(self, ts_codes, date):
        """获取财务指标，最近一期"""
        
    def get_daily_basic(self, ts_codes, date):
        """获取估值数据（PE/PB/换手率/流通市值）"""
        
    def get_index_daily(self, index_code, start_date, end_date):
        """获取指数日线"""
        
    def check_limit_up(self, ts_code, date):
        """判断是否涨停"""
        
    def get_auction_pct(self, ts_code, date):
        """获取竞价涨幅"""
```

**数据源优先级**:
1. SQLite 数据库（已有 30 万条日线、32 万条估值数据）
2. tinyshare API（数据库缺失时实时拉取并入库）

**工作量**: 2 小时

---

### Phase 2: 每日选股引擎 (DailyScreeningEngine)

**目标**: 支持多条件组合选股，从全市场筛选

**文件**:
- `backend/app/services/backtest/screening_engine.py` (新建)

**功能**:
```python
class DailyScreeningEngine:
    """每日选股引擎"""
    
    def screen(self, date, config, data_manager):
        """
        执行每日选股
        
        Args:
            date: 交易日期
            config: 选股条件配置
            data_manager: 数据管理器
            
        Returns:
            候选股票列表（已排序）
        """
```

**支持的条件类型**:
| 条件 | 字段 | 运算符 |
|------|------|--------|
| 涨停 | prev_limit_up | == true |
| 竞价涨幅 | auction_pct | > < >= <= |
| 换手率 | turnover_rate | > < |
| 流通市值 | circ_mv | > < |
| 股价 | close | > < |
| 板块 | market | == != |
| ST | is_st | == true/false |
| 行业 | industry | in not_in |
| 成交额 | amount | > < |
| PE | pe | > < |
| PB | pb | > < |
| ROE | roe | > < |

**排序**: 支持任意字段排序（升序/降序）

**工作量**: 3 小时

---

### Phase 3: 多股票组合回测框架 (PortfolioBacktestEngine)

**目标**: 替代 Backtrader，支持多股票组合回测

**文件**:
- `backend/app/services/backtest/portfolio_engine.py` (新建)
- `backend/app/services/backtest/portfolio.py` (新建，组合管理)
- `backend/app/services/backtest/order.py` (新建，订单管理)

**核心类**:
```python
class Portfolio:
    """投资组合"""
    cash: float                    # 现金
    positions: Dict[str, Position] # 持仓 {ts_code: Position}
    
    def total_value(self, prices): # 总市值
    def buy(ts_code, price, shares, date):  # 买入
    def sell(ts_code, price, shares, date): # 卖出
    
class Position:
    """单只股票持仓"""
    ts_code: str
    buy_price: float
    buy_date: date
    shares: int
    hold_days: int

class Order:
    """交易订单"""
    ts_code: str
    action: BUY/SELL
    price: float
    shares: int
    reason: str
    
class PortfolioBacktestEngine:
    """多股票组合回测引擎"""
    
    def run(self, config, start_date, end_date):
        """
        执行回测
        
        每日流程:
        1. check_market_timing() - 大盘择时
        2. check_risk_control() - 风控检查（连亏暂停等）
        3. screen_stocks() - 每日选股
        4. check_positions() - 持仓检查（止损/断板/连板）
        5. generate_orders() - 生成订单
        6. execute_orders() - 执行订单（T+1）
        7. update_portfolio() - 更新净值
        """
```

**T+1 规则实现**:
- 买入订单在 T+1 日生效（开盘价买入）
- 卖出订单在 T 日收盘执行（收盘价卖出）
- 买入当天不能卖出

**工作量**: 4 小时

---

### Phase 4: 策略 DSL 解析器

**目标**: 用 JSON 配置描述策略，不需要写代码

**文件**:
- `backend/app/services/backtest/strategy_parser.py` (新建)
- `backend/app/services/backtest/strategy_schema.json` (新建)

**策略配置格式**:
```json
{
  "name": "竞价涨停连板策略",
  "version": "1.0",
  
  "screening": {
    "universe": "主板非ST",
    "conditions": [
      {"field": "prev_limit_up", "op": "==", "value": true},
      {"field": "auction_pct", "op": ">", "value": 0.03},
      {"field": "circ_mv", "op": "<", "value": 2000000},
      {"field": "turnover_ratio", "op": ">", "value": 0.1},
      {"field": "close", "op": "<", "value": 50}
    ],
    "sort": {"field": "auction_pct", "order": "desc"},
    "limit": 3
  },
  
  "entry": {
    "timing": "open",
    "position_sizing": {
      "method": "tiered",
      "tiers": [
        {"condition": "auction_pct >= 0.07", "ratio": 1.0},
        {"condition": "auction_pct >= 0.05", "ratio": 0.5},
        {"condition": "auction_pct >= 0.03", "ratio": 0.33}
      ]
    }
  },
  
  "exit": {
    "rules": [
      {"type": "consecutive_limit_up", "action": "hold"},
      {"type": "break_limit_up", "action": "sell_at_close"},
      {"type": "stop_loss", "pct": -0.05, "action": "sell_immediate"}
    ]
  },
  
  "risk_control": {
    "max_positions": 3,
    "market_timing": {
      "enabled": true,
      "index": "000001.SH",
      "condition": "close > ma5"
    },
    "consecutive_loss_pause": {
      "enabled": true,
      "threshold": 3,
      "pause_days": 1
    }
  },
  
  "cost": {
    "commission": 0.0003,
    "stamp_tax": 0.001,
    "slippage": 0.001
  }
}
```

**工作量**: 3 小时

---

### Phase 5: 回测 API 改造

**目标**: 支持新的回测引擎和策略 DSL

**文件**:
- `backend/app/api/backtest.py` (修改)

**新增接口**:
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/backtest/run` | POST | 支持 JSON 策略配置 |
| `/api/backtest/run/dsl` | POST | 执行 DSL 策略回测 |
| `/api/backtest/validate` | POST | 验证策略配置合法性 |
| `/api/backtest/templates` | GET | 获取内置策略模板 |

**向后兼容**: 保留原有自然语言策略接口，内部转为 DSL 执行

**工作量**: 2 小时

---

### Phase 6: 竞价涨停策略集成

**目标**: 将已验证的竞价涨停连板策略集成为内置模板

**文件**:
- `backend/app/services/backtest/templates/auction_limit_up.json` (新建)

**内容**: Phase 4 中的策略配置 JSON

**验证**: 用历史数据回测，对比独立脚本结果（收益率 130.87%，盈亏比 2.36）

**工作量**: 2 小时

---

## 文件清单

### 新建文件
| 文件 | 说明 |
|------|------|
| `backend/app/services/data/data_manager.py` | 统一数据管理器 |
| `backend/app/services/backtest/screening_engine.py` | 每日选股引擎 |
| `backend/app/services/backtest/portfolio_engine.py` | 多股票组合回测引擎 |
| `backend/app/services/backtest/portfolio.py` | 投资组合管理 |
| `backend/app/services/backtest/order.py` | 订单管理 |
| `backend/app/services/backtest/strategy_parser.py` | 策略 DSL 解析器 |
| `backend/app/services/backtest/strategy_schema.json` | 策略配置 JSON Schema |
| `backend/app/services/backtest/templates/*.json` | 内置策略模板 |
| `backend/tests/test_backtest_v2/` | V2 引擎测试 |

### 修改文件
| 文件 | 说明 |
|------|------|
| `backend/app/api/backtest.py` | 新增 DSL 回测接口 |
| `backend/app/services/backtest/__init__.py` | 导出新引擎 |
| `backend/app/services/data/__init__.py` | 导出 DataManager |
| `specs/tasks.md` | 更新任务跟踪 |

## 依赖关系

```
Phase 1 (DataManager)
    │
    ▼
Phase 2 (ScreeningEngine) ──────────┐
    │                                │
    ▼                                ▼
Phase 3 (PortfolioEngine)    Phase 4 (DSL Parser)
    │                                │
    └────────────┬───────────────────┘
                 │
                 ▼
           Phase 5 (API)
                 │
                 ▼
           Phase 6 (集成)
```

Phase 1 → Phase 2 → Phase 3 可串行
Phase 2 → Phase 4 可并行
Phase 3 + Phase 4 → Phase 5

## 验收标准

1. **DataManager**: 能从数据库获取日线/财务/估值数据，缺失时自动从 API 补充
2. **ScreeningEngine**: 能执行多条件选股，结果与独立脚本一致
3. **PortfolioEngine**: 能执行多股票组合回测，支持 T+1 规则
4. **DSL Parser**: 能解析 JSON 策略配置并执行回测
5. **API**: 前端可通过 API 执行自定义策略回测
6. **集成**: 竞价涨停策略通过 API 回测，结果与独立脚本一致（收益 ±5%）

## 风险

| 风险 | 应对 |
|------|------|
| tinyshare API 限流 | DataManager 做好缓存和批量查询 |
| 回测速度慢 | 数据库索引优化 + 批量查询 |
| 策略 DSL 表达力不足 | 预留 Python 代码扩展点 |
| Backtrader 兼容性 | V2 引擎独立于 Backtrader，可并存 |
