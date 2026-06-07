# 任务跟踪

## Phase 1: 基础设施

### 00-architecture 整体架构
- [x] 初始化前端项目 (React + Vite + Tailwind)
- [x] 初始化后端项目 (FastAPI + SQLAlchemy)
- [x] 配置环境变量
- [x] 实现统一响应格式
- [x] 实现错误码定义
- [ ] 前后端联调测试

### 01-data-model 数据库模型
- [x] 定义 Stock 模型
- [x] 定义 DailyQuote 模型
- [x] 定义 WeeklyQuote 模型
- [x] 定义 FinancialIndicator 模型
- [x] 定义 TradeSignal 模型
- [x] 定义 BacktestResult 模型
- [x] 定义 UserWatchlist 模型
- [ ] 配置 Alembic 迁移
- [ ] 生成初始迁移脚本
- [ ] 执行数据库迁移

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
- [ ] 实现后端筛选服务
- [ ] 实现意图解析 API
- [ ] 实现筛选执行 API
- [ ] 实现前端输入组件
- [ ] 实现条件标签组件
- [ ] 实现结果列表组件
- [ ] 前后端联调
- [ ] 编写单元测试 (pytest)

### 05-backtest 策略回测
- [ ] 集成 Backtrader 引擎
- [ ] 实现策略适配层
- [ ] 实现回测任务 API
- [ ] 实现结果查询 API
- [ ] 实现收益曲线图表
- [ ] 实现指标卡片组件
- [ ] 实现交易记录列表
- [ ] 前后端联调
- [ ] 编写单元测试 (pytest)

### 06-signal 买卖信号
- [ ] 实现 MACD 信号生成
- [ ] 实现 KDJ 信号生成
- [ ] 实现均线信号生成
- [ ] 实现信号生成 API
- [ ] 实现 K 线图组件
- [ ] 实现信号标注
- [ ] 实现信号列表组件
- [ ] 前后端联调
- [ ] 编写单元测试 (pytest)

## Phase 3: P1 增强功能

### 07-factor 多因子系统
- [ ] 定义因子库
- [ ] 实现因子 IC/IR 计算
- [ ] 实现分组收益分析
- [ ] 实现多因子评分
- [ ] 实现因子相关性分析
- [ ] 实现前端因子库页面
- [ ] 实现前端因子测试页面
- [ ] 前后端联调
- [ ] 编写单元测试 (pytest)

### 08-attribution 归因分析
- [ ] 实现 Brinson 归因模型
- [ ] 实现因子归因
- [ ] 实现行业归因 API
- [ ] 实现因子归因 API
- [ ] 实现前端归因页面
- [ ] 实现收益分解图表
- [ ] 实现行业贡献图表
- [ ] 前后端联调
- [ ] 编写单元测试 (pytest)

## Phase 4: 测试与质量保证

### 09-testing 测试规范
- [ ] 配置 pytest 环境
- [ ] 编写 conftest.py (fixtures)
- [ ] 编写模型层测试
- [ ] 编写服务层测试
- [ ] 编写 API 层测试
- [ ] 编写 Mock 外部服务测试
- [ ] 编写边界条件测试
- [ ] 编写错误处理测试
- [ ] 编写前端组件测试
- [ ] 配置 CI/CD 流水线
- [ ] 运行测试并确保通过
- [ ] 生成测试覆盖率报告

## 进度统计

| 模块 | 总任务 | 已完成 | 进度 |
|------|--------|--------|------|
| 00-architecture | 6 | 5 | 83% |
| 01-data-model | 10 | 7 | 70% |
| 02-data-source | 7 | 7 | 100% |
| 03-ai-service | 7 | 7 | 100% |
| 04-stock-screening | 8 | 0 | 0% |
| 05-backtest | 9 | 0 | 0% |
| 06-signal | 9 | 0 | 0% |
| 07-factor | 9 | 0 | 0% |
| 08-attribution | 9 | 0 | 0% |
| 09-testing | 12 | 0 | 0% |
| **总计** | **86** | **26** | **30%** |
