# 任务跟踪

## Phase 1: 基础设施

### 00-architecture 整体架构
- [x] 初始化前端项目 (React + Vite + Tailwind)
- [x] 初始化后端项目 (FastAPI + SQLAlchemy)
- [x] 配置环境变量
- [x] 实现统一响应格式
- [x] 实现错误码定义
- [x] 前后端联调测试

### 01-data-model 数据库模型
- [x] 定义 Stock 模型
- [x] 定义 DailyQuote 模型
- [x] 定义 WeeklyQuote 模型
- [x] 定义 FinancialIndicator 模型
- [x] 定义 TradeSignal 模型
- [x] 定义 BacktestResult 模型
- [x] 定义 UserWatchlist 模型
- [x] 配置 Alembic 迁移
- [x] 生成初始迁移脚本
- [x] 执行数据库迁移

### 02-data-source 数据源接入层
- [x] 定义 DataSourceBase 接口
- [x] 实现 TushareSource
- [x] 实现 AkShareSource
- [x] 实现数据源工厂
- [x] 实现数据缓存层
- [x] 实现数据落库服务
- [x] 编写数据同步脚本

### 03-ai-service AI 服务层
- [x] 定义 AIServiceBase 接口
- [x] 实现 DeepSeekService
- [x] 实现 QwenService
- [x] 实现 AI 服务工厂
- [x] 实现选股意图解析
- [x] 实现策略生成
- [x] 实现个股分析

## Phase 2: P0 核心功能

### 04-stock-screening 自然语言选股
- [x] 实现后端筛选服务
- [x] 实现意图解析 API
- [x] 实现筛选执行 API
- [x] 实现前端输入组件
- [x] 实现条件标签组件
- [x] 实现结果列表组件
- [x] 前后端联调
- [x] 编写单元测试 (pytest)

### 05-backtest 策略回测
- [x] 集成 Backtrader 引擎
- [x] 实现策略适配层
- [x] 实现回测任务 API
- [x] 实现结果查询 API
- [x] 实现收益曲线图表
- [x] 实现指标卡片组件
- [x] 实现交易记录列表
- [x] 前后端联调
- [x] 编写单元测试 (pytest)

### 06-signal 买卖信号
- [x] 实现 MACD 信号生成
- [x] 实现 KDJ 信号生成
- [x] 实现均线信号生成
- [x] 实现信号生成 API
- [x] 实现 K 线图组件
- [x] 实现信号标注
- [x] 实现信号列表组件
- [x] 前后端联调
- [x] 编写单元测试 (pytest)

## Phase 3: P1 增强功能

### 07-factor 多因子系统
- [x] 定义因子库
- [x] 实现因子 IC/IR 计算
- [x] 实现分组收益分析
- [x] 实现多因子评分
- [x] 实现因子相关性分析
- [x] 实现前端因子库页面
- [x] 实现前端因子测试页面
- [x] 前后端联调
- [x] 编写单元测试 (pytest)

### 08-attribution 归因分析
- [x] 实现 Brinson 归因模型
- [x] 实现因子归因
- [x] 实现行业归因 API
- [x] 实现因子归因 API
- [x] 实现前端归因页面
- [x] 实现收益分解图表
- [x] 实现行业贡献图表
- [x] 前后端联调
- [x] 编写单元测试 (pytest)

## Phase 4: 测试与质量保证

### 09-testing 测试规范
- [x] 配置 pytest 环境
- [x] 编写 conftest.py (fixtures)
- [x] 编写模型层测试
- [x] 编写服务层测试
- [x] 编写 API 层测试
- [x] 编写 Mock 外部服务测试
- [x] 编写边界条件测试
- [x] 编写错误处理测试
- [x] 编写前端组件测试
- [x] 配置 CI/CD 流水线
- [x] 运行测试并确保通过
- [x] 生成测试覆盖率报告

## Phase 5: 回测引擎 V2 重构

> 详细计划见 `specs/backtest-engine-v2.md`

### 10-backtest-v2 回测引擎 V2
- [x] 实现 DataManager 统一数据管理器
- [x] 实现 DailyScreeningEngine 每日选股引擎
- [x] 实现 Portfolio 投资组合管理
- [x] 实现 Order 订单管理（支持 T+1）
- [x] 实现 PortfolioBacktestEngine 多股票组合回测引擎
- [x] 实现 StrategyParser 策略 DSL 解析器
- [x] 编写策略配置 JSON Schema
- [x] 改造回测 API 支持 DSL
- [x] 集成竞价涨停策略模板
- [x] 编写 V2 引擎单元测试
- [x] 用历史数据验证 V2 引擎结果

### 11-data-import 数据补充
- [x] 补充 daily 日线至 2 年（动量因子）
- [x] 导入 moneyflow 资金流向数据
- [x] 导入 income 利润表数据
- [x] 导入 balancesheet 资产负债表数据
- [ ] 导入 dividend 分红数据

## 进度统计

| 模块 | 总任务 | 已完成 | 进度 |
|------|--------|--------|------|
| 00-architecture | 6 | 6 | 100% |
| 01-data-model | 10 | 10 | 100% |
| 02-data-source | 7 | 7 | 100% |
| 03-ai-service | 7 | 7 | 100% |
| 04-stock-screening | 8 | 8 | 100% |
| 05-backtest | 9 | 9 | 100% |
| 06-signal | 9 | 9 | 100% |
| 07-factor | 9 | 9 | 100% |
| 08-attribution | 9 | 9 | 100% |
| 09-testing | 12 | 12 | 100% |
| 10-backtest-v2 | 11 | 1 | 9% |
| 11-data-import | 5 | 5 | 100% |
| **总计** | **102** | **87** | **85%** |
