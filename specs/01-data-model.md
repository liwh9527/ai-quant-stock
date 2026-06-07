# 数据库模型

## 目标

定义 SQLAlchemy ORM 模型，覆盖股票基础数据、行情数据、财务数据、信号数据等。

## 数据模型设计

### 1. Stock（股票基础信息）

```python
class Stock(Base):
    __tablename__ = "stocks"

    ts_code = Column(String(20), primary_key=True)    # 股票代码（如 000001.SZ）
    symbol = Column(String(10), nullable=False)        # 股票代码（如 000001）
    name = Column(String(50), nullable=False)          # 股票名称
    area = Column(String(20))                          # 地域
    industry = Column(String(50))                      # 所属行业
    market = Column(String(10))                        # 市场（主板/创业板/科创板）
    list_date = Column(Date)                           # 上市日期
    delist_date = Column(Date)                         # 退市日期（NULL = 未退市）
    is_hs = Column(String(10))                         # 是否沪深港通
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

### 2. DailyQuote（日线行情）

```python
class DailyQuote(Base):
    __tablename__ = "daily_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)
    trade_date = Column(Date, nullable=False)          # 交易日期
    open = Column(Float)                               # 开盘价
    high = Column(Float)                               # 最高价
    low = Column(Float)                                # 最低价
    close = Column(Float)                              # 收盘价
    pre_close = Column(Float)                          # 昨收价
    change = Column(Float)                             # 涨跌额
    pct_chg = Column(Float)                            # 涨跌幅（%）
    vol = Column(Float)                                # 成交量（手）
    amount = Column(Float)                             # 成交额（千元）

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date"),
        Index("idx_daily_ts_date", "ts_code", "trade_date"),
    )
```

### 3. WeeklyQuote（周线行情）

```python
class WeeklyQuote(Base):
    __tablename__ = "weekly_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)
    trade_date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    vol = Column(Float)
    amount = Column(Float)

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date"),
    )
```

### 4. FinancialIndicator（财务指标）

```python
class FinancialIndicator(Base):
    __tablename__ = "financial_indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)
    ann_date = Column(Date)                            # 公告日期
    end_date = Column(Date, nullable=False)            # 报告期

    # 盈利能力
    roe = Column(Float)                                # 净资产收益率（%）
    roa = Column(Float)                                # 总资产收益率（%）
    gross_margin = Column(Float)                       # 销售毛利率（%）
    net_margin = Column(Float)                         # 销售净利率（%）

    # 成长能力
    revenue_yoy = Column(Float)                        # 营收同比（%）
    net_profit_yoy = Column(Float)                     # 净利润同比（%）

    # 估值
    pe = Column(Float)                                 # 市盈率
    pb = Column(Float)                                 # 市净率
    ps = Column(Float)                                 # 市销率

    # 负债
    debt_ratio = Column(Float)                         # 资产负债率（%）
    current_ratio = Column(Float)                      # 流动比率

    # 每股指标
    eps = Column(Float)                                # 每股收益
    bvps = Column(Float)                               # 每股净资产

    __table_args__ = (
        UniqueConstraint("ts_code", "end_date"),
        Index("idx_fin_ts_end", "ts_code", "end_date"),
    )
```

### 5. TradeSignal（交易信号）

```python
class TradeSignal(Base):
    __tablename__ = "trade_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)
    signal_date = Column(Date, nullable=False)         # 信号日期
    signal_type = Column(String(10), nullable=False)   # BUY / SELL
    strategy_name = Column(String(50))                 # 策略名称
    signal_source = Column(String(50))                 # 信号来源（MACD/KDJ/自定义）
    price = Column(Float)                              # 信号价格
    strength = Column(Float)                           # 信号强度（0-1）
    reason = Column(Text)                              # 信号原因描述

    __table_args__ = (
        Index("idx_signal_ts_date", "ts_code", "signal_date"),
    )
```

### 6. BacktestResult（回测结果）

```python
class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False)
    strategy_desc = Column(Text)                       # 策略描述
    start_date = Column(Date)                          # 回测开始日期
    end_date = Column(Date)                            # 回测结束日期

    # 收益指标
    total_return = Column(Float)                       # 总收益率（%）
    annual_return = Column(Float)                      # 年化收益率（%）
    benchmark_return = Column(Float)                   # 基准收益率（%）
    excess_return = Column(Float)                      # 超额收益率（%）

    # 风险指标
    max_drawdown = Column(Float)                       # 最大回撤（%）
    sharpe_ratio = Column(Float)                       # 夏普比率
    volatility = Column(Float)                         # 波动率（%）
    win_rate = Column(Float)                           # 胜率（%）

    # 交易统计
    trade_count = Column(Integer)                      # 交易次数
    avg_holding_days = Column(Float)                   # 平均持仓天数

    # 配置快照
    params_json = Column(Text)                         # 策略参数 JSON
    created_at = Column(DateTime, default=func.now())
```

### 7. UserWatchlist（自选股）

```python
class UserWatchlist(Base):
    __tablename__ = "user_watchlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String(50), nullable=False)    # 分组名称
    ts_code = Column(String(20), ForeignKey("stocks.ts_code"), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
```

## 数据库初始化

### Alembic 迁移

```bash
cd backend
alembic init alembic
alembic revision --autogenerate -m "init tables"
alembic upgrade head
```

### 基础数据导入

需要导入的数据（通过 Tushare）：
1. 股票列表（stock_basic）
2. 最近 N 年的日线数据（daily）
3. 财务指标数据（fina_indicator）

## 验收标准

- [ ] 所有模型定义完成
- [ ] Alembic 迁移脚本生成成功
- [ ] 数据库表创建成功
- [ ] 基础数据导入脚本可运行
- [ ] 索引和约束生效
