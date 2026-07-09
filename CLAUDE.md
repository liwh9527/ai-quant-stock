# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

A 股量化选股 Web 工具，核心功能：自然语言选股、策略回测、买卖信号、多因子系统、归因分析。纯分析工具，不接入交易。

## 常用命令

### 前端

```bash
cd frontend
npm install          # 安装依赖
npm run dev          # 启动开发服务器 (Vite, 端口 5173)
npm run build        # 生产构建
npm run test         # 运行测试 (Vitest)
npm run test:watch   # 监听模式运行测试
```

### 后端

```bash
cd backend
pip install -r requirements.txt    # 安装依赖
uvicorn app.main:app --reload      # 启动开发服务器 (端口 8000)
pytest                             # 运行全部测试
pytest tests/test_services/test_screening.py  # 运行单个测试文件
pytest -k "test_parse"             # 按名称过滤测试
pytest --cov=app                   # 带覆盖率运行
```

### 数据导入

```bash
cd backend
python -m scripts.import_stock_list   # 导入股票列表
python -m scripts.import_daily        # 导入日线数据
python -m scripts.import_financial    # 导入财务指标
```

## 架构

### 前后端分离

- 前端 React + Vite (端口 5173)，通过 Vite proxy 转发 `/api` 请求到后端
- 后端 FastAPI (端口 8000)，所有接口返回统一格式 `{"code": 0, "data": ..., "msg": ""}`
- 前端 API 层 (`src/services/api.js`) 封装 axios，自动解包响应

### 后端分层架构

```
app/api/           → FastAPI 路由，只做参数校验和响应封装
app/services/      → 业务逻辑层
  ├── ai/          → AI 模型调用（DeepSeek/通义千问），工厂模式切换
  ├── data/        → 数据源统一接口（Tushare/AkShare），工厂模式切换
  ├── backtest/    → 回测引擎（Backtrader 封装 + 自研 V2 引擎）
  ├── factor/      → 多因子系统（定义、分析、评分）
  ├── signal/      → 买卖信号（技术指标 + 信号生成）
  └── attribution/ → 归因分析（Brinson + 因子归因）
app/models/        → SQLAlchemy ORM 模型
app/core/          → 配置、数据库连接、依赖注入
```

### 关键设计模式

1. **工厂模式** — `app/services/ai/factory.py` 和 `app/services/data/factory.py` 根据配置切换实现，业务层不感知具体 provider
2. **基类抽象** — `AIServiceBase` 定义 AI 接口（chat/parse_screening_intent/generate_strategy/analyze_stock），`DataSourceBase` 定义数据接口（get_stock_list/get_daily_quotes/get_financial_indicators/get_index_daily）
3. **依赖注入** — 通过 FastAPI 的 `Depends` 和 `app/core/deps.py` 注入数据库会话和 AI 服务
4. **选股双引擎** — `ScreeningService.parse_query` 先用正则规则解析，解析不全时 fallback 到 AI 解析

### 前端路由

| 路径 | 页面 | 功能 |
|------|------|------|
| `/` | Home | 首页 |
| `/screening` | Screening | 自然语言选股 |
| `/backtest` | Backtest | 策略回测 |
| `/signal` | Signal | 买卖信号 |
| `/factor` | Factor | 多因子系统 |
| `/attribution` | Attribution | 归因分析 |

### 数据库

- SQLite，文件位于 `data/quant.db`
- SQLAlchemy ORM，模型定义在 `app/models/`
- 核心表：`stock`（股票列表）、`daily_quote`（日线行情）、`financial_indicator`（财务指标）、`daily_basic`（每日基础指标）、`index_daily`（指数日线）

### 回测引擎

- **V1**：`app/services/backtest/engine.py` — 基于 Backtrader，`AIStrategy` 解析策略配置执行交易
- **V2**：`app/services/backtest/portfolio_engine.py` — 自研引擎，支持组合回测、多股票、行业分散

## 环境变量

在 `backend/.env` 中配置：

```bash
DATABASE_URL=sqlite:///data/quant.db
DATA_SOURCE_TYPE=tushare     # 可选: tushare, akshare, tinyshare
TUSHARE_TOKEN=xxx
AI_PROVIDER=deepseek         # 可选: deepseek, qwen
DEEPSEEK_API_KEY=xxx
QWEN_API_KEY=xxx
```

## 规格文档

`specs/` 目录包含完整的模块规格文档，开发新功能前先阅读对应 spec。关键依赖链：

```
00-architecture → 01-data-model → 02-data-source → 04/05/06 (选股/回测/信号)
                → 03-ai-service → 04-stock-screening
07-factor → 08-attribution
```

## 开发规范

- 使用中文注释和 commit message
- 每完成一个可运行的功能就 commit，改完后在 `changelog.md` 追加一行
- 移动端优先，确保手机浏览器可用
- 前端样式用 Tailwind，不写自定义 CSS 文件
- 前端组件拆分粒度：一个文件不超过 200 行
- 前端 API 调用统一走 `src/services/` 层，不在组件里直接 fetch
- 后端路由定义在 `app/api/`，业务逻辑在 `app/services/`，不在路由里写业务
- 数据源调用统一走 `app/services/data/` 接口层，上层不直接调用 tushare/akshare
- AI 调用统一走 `app/services/ai/` 接口层，上层不直接调用具体模型 SDK
- 所有配置（API key、token）走环境变量，不硬编码
