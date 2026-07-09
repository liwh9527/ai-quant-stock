# 变更日志

## 2026-07-08

- 新增统一策略库（10 个标准化策略）
  - 动量轮动、海龟交易、多因子、趋势择时、价值投资
  - 竞价涨停连板、均值回归、通道突破、低波动、双均线
  - 策略注册中心：列表、详情、按分类过滤
  - API：`GET /api/backtest/strategies`、`POST /api/backtest/strategies/{key}/run`
  - 前端回测页面新增策略库 Tab，卡片展示，一键运行

## 2026-07-06

- 集成 Tushare 高速代理 API
  - 新增 `TUSHARE_API_URL` 配置项，支持代理/官方 API 切换
  - 更新 `TushareSource` 支持代理 URL 注入
  - 更新工厂模式传递代理 URL
  - 代理限速：每分钟 100 次，总量不限

- 新增批量历史数据导入脚本
  - 按日期批量获取日线行情和每日指标（效率最高）
  - 逐只股票获取财务指标
  - 自动限速、断点续传、失败重试
  - 支持 `--only` 和 `--years` 参数

## 2026-06-27

- 修复 screening.py 死代码 Bug
  - 将 label 生成代码从 `_rule_parse` 方法的 return 之后移到之前
  - 提取 `_add_labels` 方法，供 `_rule_parse` 和 `parse_query` 共用
  - 修复 7 个失败的测试用例

- 修复前端测试框架
  - 从 Jest 迁移到 Vitest
  - 更新 package.json：移除 Jest 依赖，添加 Vitest 依赖
  - 更新 vite.config.js：添加 test 配置（jsdom 环境）
  - 更新测试文件：使用 vi.mock/vi.fn 替代 jest.mock/jest.fn
  - 更新组件文件：添加 React import 以支持 JSX 测试
  - 所有 33 个前端测试通过

- 更新 specs/README.md
  - 更新模块状态为"已完成"
  - 添加 Phase 4 和 Phase 5 信息
  - 更新待办事项

- 拆分超大文件
  - Attribution.jsx: 499 行 → 269 行（提取 MetricCard、PctValue、图表、表格组件）
  - Screening.jsx: 438 行 → 259 行（提取 SortableHeader、ConditionTag、StockResultTable 组件）
  - 创建 components/attribution/ 和 components/screening/ 目录

- 清理脚本目录
  - 添加 scripts/README.md 文档
  - 创建 run_backtest.py 统一回测运行器
  - 支持参数化策略运行

- 更新 tasks.md 进度
  - 修正 V2 回测引擎进度为 100%
  - 更新总进度为 99%（仅剩 dividend 数据导入）

## 2026-06-09

- 回测引擎 V2 重构计划
  - 创建 `specs/backtest-engine-v2.md` 详细计划文档
  - 设计多股票组合回测框架架构
  - 设计策略 DSL（JSON 配置化策略）
  - 设计每日选股引擎
  - 设计统一数据管理器（DataManager）
  - 规划 6 个实施阶段，预计 16 小时工作量
  - 更新 `specs/tasks.md` 新增 Phase 5 任务

- 竞价涨停连板策略回测验证
  - 实现竞价涨停连板策略独立回测脚本
  - T+1 交易规则修正（买入当天不能卖出）
  - 仓位管理优化（总资金 1/3 分配）
  - 连板追踪逻辑（涨停持有，断板卖出）
  - 止损规则（跌破买入价-5%）
  - 回测结果：收益率+130.87%，盈亏比2.36，最大回撤29.94%

- 数据库补充
  - 导入 daily_basic 估值数据（329,504 条，PE/PB/PS/换手率/流通市值）
  - 导入 index_daily 指数日线（1,464 条，上证/沪深300/中证500）
  - 新增 TinyShare 数据源支持（Tushare 兼容，无频率限制）

## 2026-06-07

- 初始化项目：AI 辅助量化选股工具
- 创建 CLAUDE.md 开发规范
- 创建 project-brief.md 需求文档
- 建立 Spec-Driven Development 规格文档体系（specs/）
  - 整体架构设计
  - 数据库模型规格
  - 数据源接入层规格
  - AI 服务层规格
  - 自然语言选股规格
  - 策略回测规格
  - 买卖信号规格
  - 多因子系统规格
  - 归因分析规格
  - 任务跟踪文档

- 初始化后端项目结构（FastAPI + SQLAlchemy）
  - 创建 backend/ 目录结构（api, core, models, services, utils, tests, alembic）
  - 创建 requirements.txt 依赖清单
  - 创建 app/main.py FastAPI 入口，配置 CORS
  - 创建 app/core/config.py 环境变量配置（pydantic-settings）
  - 创建 app/core/database.py SQLAlchemy 数据库连接
  - 创建 app/core/deps.py 依赖注入
  - 创建 app/api/health.py 健康检查接口
  - 创建 .env.example 环境变量模板
  - 统一响应格式 {"code": 0, "data": ..., "msg": ""}

- 实现 AI 服务层（specs/03-ai-service）
  - 创建 AIServiceBase 抽象基类（chat, parse_screening_intent, generate_strategy, analyze_stock）
  - 实现 DeepSeekService（基于 DeepSeek Chat API，httpx 异步调用）
  - 实现 QwenService（基于通义千问 DashScope API，作为备用）
  - 创建 AI 服务工厂（根据 AI_PROVIDER 配置切换模型）
  - 在 config.py 中新增 AI_PROVIDER、DEEPSEEK_BASE_URL、QWEN_BASE_URL 配置项

- 实现数据源接入层（specs/02-data-source）
  - 创建 DataSourceBase 抽象基类（get_stock_list, get_daily_quotes, get_financial_indicators, get_index_daily）
  - 实现 TushareSource（Tushare Pro API，日期格式转换，列名映射）
  - 实现 AkShareSource（akshare 库，中文列名映射，多接口组合）
  - 创建数据源工厂（根据 DATA_SOURCE_TYPE 配置切换 tushare/akshare）
  - 实现 DataCache 缓存层（内存缓存，MD5 键，自动淘汰策略）
  - 实现 DataImportService 落库服务（股票列表、日线行情、财务指标增量导入）
  - 在 config.py 中新增 DATA_SOURCE_TYPE 配置项

- 实现策略回测模块（specs/05-backtest）
  - 创建 BacktestEngine 回测引擎（集成 Backtrader，支持资金/佣金/滑点配置，提取收益指标）
  - 创建 AIStrategy 策略适配层（将 AI 策略配置转为 Backtrader 策略，支持 MACD/KDJ/MA/EMA/RSI/BOLL）
  - 创建回测 API（POST /api/backtest/run 创建任务，GET /api/backtest/result/{task_id} 查询结果）
  - 创建回测历史列表 API（GET /api/backtest/list）
  - 创建前端策略回测页面（策略描述输入、参数配置、收益曲线、指标卡片、交易记录）
  - 新增 ECharts 依赖用于收益曲线绘制
  - 注册回测路由到 FastAPI 主入口

- 实现自然语言选股模块（specs/04-stock-screening）
  - 创建 ScreeningService 选股服务（parse_query 调用 AI 解析、search 执行多条件筛选、支持 PE/ROE/行业等组合条件）
  - 创建选股 API（POST /api/screening/parse 解析意图，POST /api/screening/search 执行筛选，支持分页和排序）
  - 创建前端自然语言选股页面（自然语言输入框、可编辑/删除的条件标签、股票结果表格、移动端卡片布局、分页）
  - 更新 App.jsx 添加选股导航（默认首页）
  - 更新 api.js 添加选股 API 函数
  - 注册选股路由到 FastAPI 主入口

- 实现归因分析模块（specs/08-attribution）
  - 创建 BrinsonAttribution 归因模型（行业选择收益、个股选择收益、交互效应）
  - 创建 FactorAttribution 因子归因（因子暴露计算、因子收益分解）
  - 创建归因 API（POST /api/attribution/return 收益归因，POST /api/attribution/factor 因子归因）
  - 创建前端归因分析页面（选择回测任务、收益分解柱状图、行业贡献表格、因子贡献图表）
  - 注册归因路由到 FastAPI 主入口
  - 更新 api.js 添加归因 API 函数

- 实现多因子系统模块（specs/07-factor）
  - 创建因子定义模块（11个因子：价值PE/PB/PS、成长营收同比/净利润同比、质量ROE/ROA/毛利率、动量5日/20日、波动20日波动率）
  - 创建因子分析器（calc_ic 信息系数、calc_ir 信息比率、group_returns 分组收益、calc_correlation 因子相关性矩阵）
  - 创建多因子评分器（Z-Score 标准化、因子方向调整、加权评分、全市场排名）
  - 创建因子 API（GET /api/factor/list 因子列表、POST /api/factor/test 因子测试、POST /api/factor/score 多因子评分）
  - 创建前端多因子系统页面（因子库分类展示、因子测试配置与结果图表、多因子评分配置与排名表格）
  - 注册因子路由到 FastAPI 主入口
  - 更新 api.js 添加因子 API 函数

- 实现买卖信号模块（specs/06-signal）
  - 创建 TechnicalIndicators 技术指标计算（MACD/KDJ/均线）
  - 创建 SignalGenerator 信号生成器（MACD 金叉死叉、KDJ 超买超卖、均线交叉信号，含止损止盈规则）
  - 创建信号 API（POST /api/signal/generate 生成信号并持久化，GET /api/signal/list 查询信号列表）
  - 创建前端 K 线图组件（TradingView Lightweight Charts，支持信号标注）
  - 创建 MACD/KDJ 指标副图组件（ECharts）
  - 创建买卖信号页面（股票选择、指标选择、时间范围、K 线图+信号标注、信号列表）
  - 注册信号路由到 FastAPI 主入口
  - 更新 api.js 添加信号 API 函数
  - 新增 lightweight-charts 前端依赖

- 定义数据库 ORM 模型（specs/01-data-model）
  - 创建 app/models/__init__.py 统一导出所有模型
  - 创建 app/models/stock.py Stock 股票基础信息表
  - 创建 app/models/daily.py DailyQuote 日线行情表（含唯一约束和复合索引）
  - 创建 app/models/weekly.py WeeklyQuote 周线行情表（含唯一约束）
  - 创建 app/models/financial.py FinancialIndicator 财务指标表（盈利/成长/估值/负债/每股指标）
  - 创建 app/models/signal.py TradeSignal 交易信号表（含复合索引）
  - 创建 app/models/backtest.py BacktestResult 回测结果表（收益/风险/交易统计指标）
  - 创建 app/models/watchlist.py UserWatchlist 自选股表
  - 所有模型继承 app.core.database.Base，使用 SQLAlchemy 2.0 声明式语法
  - 外键关联 stocks.ts_code，索引和约束按规格文档定义

- 完善策略回测前端页面（specs/05-backtest）
  - 回测页面包含：策略描述 textarea、日期/资金/基准参数配置、开始回测按钮
  - 结果展示：指标卡片（总收益率、年化收益率、最大回撤、夏普比率、胜率等）
  - 收益曲线图表（ECharts）+ 交易记录表格
  - 支持策略示例快捷输入、佣金率/滑点高级参数
  - 标记 05-backtest 全部任务为已完成

- 修复回测页面 API 响应处理 bug
  - 修复 Backtest.jsx 中因 axios 拦截器已解包 {code, data, msg} 导致 res.code 始终为 undefined 的问题
  - 移除多余的 code 检查逻辑，直接使用拦截器返回的 data

## 2026-06-08

- 修复 SignalGenerator 中 Timestamp 与 datetime.date 比较的 bug
  - _macd_signals、_kdj_signals、_ma_signals 方法中 dates[i] < start_date 会抛 TypeError
  - 统一使用 pd.Timestamp(start_date) 进行比较

- 修复前端 Jest 配置
  - 将 jest.config.js 改为 jest.config.cjs（package.json 使用 ESM）
  - 修正 setupFilesAfterSetup 为 setupFilesAfterEnv（Jest 正确配置键名）

- 增强买卖信号模块测试（specs/06-signal）
  - 新增 SignalGenerator 完整测试（MACD/KDJ/MA/多指标/空数据/自定义参数/K线结构/排序）
  - 新增 TechnicalIndicators 补充测试（自定义参数/恒定价格/长度验证）
  - 新增 StopLossRule 边界值和自定义比例测试
  - 新增信号 API 测试（generate/list 端点、数据库写入验证）
  - 修复信号 API 测试中的数据库 mock 问题（dependency_overrides）

- 增强归因分析模块测试（specs/08-attribution）
  - 新增 BrinsonAttribution 完整测试（summary/details 字段、同权重无选择效应、超额收益分解、排序、加权收益、独有行业、精度验证）
  - 新增 FactorAttribution 完整测试（字段验证、中文名称映射、空组合、缺失因子值、零权重、排序、占比求和、单股票、未知因子名）
  - 新增归因 API 测试（return/factor 端点、默认参数、交易记录）

- 编写前端组件测试（specs/09-testing）
  - SignalTable 组件测试（空数据、标题、日期、买卖标签、指标、价格、原因）
  - MetricsCards 组件测试（空数据、标签、数值、颜色、零值）
  - API 服务层测试（函数导出验证）

- 生成测试覆盖率报告
  - 后端：52% 总覆盖率，147 个测试全部通过
  - 前端：MetricsCards 100%、SignalTable 100%，33 个测试全部通过

- 更新 tasks.md，所有 86 个任务标记为已完成（100%）
