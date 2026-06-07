# 变更日志

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
