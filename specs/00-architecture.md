# 整体架构设计

## 目标

建立前后端分离的 Web 应用架构，确保各层职责清晰、可独立演进。

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | React 18 + Vite + Tailwind CSS | SPA，移动端优先 |
| 图表 | ECharts + TradingView Lightweight Charts | K 线用 TV，其他用 ECharts |
| 后端 | Python 3.11+ + FastAPI | 异步 API |
| ORM | SQLAlchemy 2.0 | 后续可切 PostgreSQL |
| 数据库 | SQLite | 轻量，适配 2 核 2G |
| 回测 | Backtrader + 自研适配层 | 适配 AI 策略描述 |
| AI | DeepSeek API（主）/ 通义千问（备） | 统一接口层 |
| 数据源 | Tushare（主）/ AkShare / 东财（备） | 统一数据层 |

## 架构分层

```
┌─────────────────────────────────────────┐
│              Frontend (React)           │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐  │
│  │  Pages  │ │Components│ │  Hooks   │  │
│  └────┬────┘ └─────────┘ └──────────┘  │
│       │                                 │
│  ┌────┴────┐                            │
│  │Services │  ← API 调用层              │
│  └────┬────┘                            │
└───────┼─────────────────────────────────┘
        │ HTTP (JSON)
┌───────┼─────────────────────────────────┐
│       ▼        Backend (FastAPI)        │
│  ┌─────────┐                            │
│  │  API    │  ← 路由层，不含业务逻辑     │
│  └────┬────┘                            │
│       │                                 │
│  ┌────┴────────────────────────────┐    │
│  │         Services (业务逻辑)      │    │
│  │  ┌────────┐ ┌────────┐ ┌──────┐ │    │
│  │  │  AI    │ │  Data  │ │Backtest│ │    │
│  │  │Service │ │Service │ │Engine │ │    │
│  │  └────────┘ └────────┘ └──────┘ │    │
│  └─────────────────────────────────┘    │
│       │                                 │
│  ┌────┴────┐  ┌─────────┐              │
│  │ Models  │  │  Utils  │              │
│  │(SQLAlch)│  └─────────┘              │
│  └────┬────┘                            │
└───────┼─────────────────────────────────┘
        │
   ┌────┴────┐
   │  SQLite │
   └─────────┘
```

## 目录结构

```
ai-quant-stock/
├── frontend/                    # React 前端
│   ├── src/
│   │   ├── components/          # 通用 UI 组件
│   │   │   ├── ui/              # 基础组件（Button, Card, Modal...）
│   │   │   ├── chart/           # 图表组件
│   │   │   └── layout/          # 布局组件
│   │   ├── pages/               # 页面组件
│   │   │   ├── Home.jsx         # 首页
│   │   │   ├── Screening.jsx    # 选股页
│   │   │   ├── Backtest.jsx     # 回测页
│   │   │   └── Signal.jsx       # 信号页
│   │   ├── hooks/               # 自定义 hooks
│   │   ├── services/            # API 调用层
│   │   │   ├── api.js           # axios 封装
│   │   │   ├── screening.js     # 选股 API
│   │   │   ├── backtest.js      # 回测 API
│   │   │   └── signal.js        # 信号 API
│   │   ├── utils/               # 工具函数
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── index.html
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── package.json
│
├── backend/                     # Python 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 入口
│   │   ├── api/                 # 路由层
│   │   │   ├── __init__.py
│   │   │   ├── screening.py     # 选股路由
│   │   │   ├── backtest.py      # 回测路由
│   │   │   └── signal.py        # 信号路由
│   │   ├── core/                # 核心配置
│   │   │   ├── __init__.py
│   │   │   ├── config.py        # 环境变量配置
│   │   │   ├── database.py      # 数据库连接
│   │   │   └── deps.py          # 依赖注入
│   │   ├── models/              # SQLAlchemy 模型
│   │   │   ├── __init__.py
│   │   │   ├── stock.py         # 股票基础数据
│   │   │   ├── daily.py         # 日线数据
│   │   │   ├── financial.py     # 财务数据
│   │   │   └── signal.py        # 信号数据
│   │   ├── services/            # 业务逻辑层
│   │   │   ├── __init__.py
│   │   │   ├── ai/              # AI 服务
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py      # AI 基类
│   │   │   │   ├── deepseek.py  # DeepSeek 实现
│   │   │   │   └── qwen.py      # 通义千问实现
│   │   │   ├── data/            # 数据源服务
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py      # 数据源基类
│   │   │   │   ├── tushare.py   # Tushare 实现
│   │   │   │   └── akshare.py   # AkShare 实现
│   │   │   ├── backtest/        # 回测引擎
│   │   │   │   ├── __init__.py
│   │   │   │   ├── engine.py    # Backtrader 适配
│   │   │   │   └── strategy.py  # 策略定义
│   │   │   ├── factor/          # 因子系统
│   │   │   ├── signal/          # 信号系统
│   │   │   └── analysis/        # 归因分析
│   │   └── utils/               # 工具函数
│   ├── tests/                   # 测试
│   ├── alembic/                 # 数据库迁移
│   ├── requirements.txt
│   └── alembic.ini
│
├── data/                        # SQLite 数据文件
├── deploy/                      # 部署配置
│   ├── nginx.conf
│   └── supervisor.conf
├── scripts/                     # 数据初始化脚本
├── specs/                       # 规格文档
├── CLAUDE.md                    # AI 开发规范
├── project-brief.md             # 项目需求
└── changelog.md                 # 变更日志
```

## API 设计规范

### 统一响应格式

```json
{
  "code": 0,
  "data": {},
  "msg": ""
}
```

- `code = 0`：成功
- `code > 0`：业务错误（如参数校验失败）
- `code < 0`：系统错误（如数据库连接失败）

### 错误码定义

| 范围 | 说明 |
|------|------|
| 0 | 成功 |
| 1001-1999 | 参数错误 |
| 2001-2999 | 数据源错误 |
| 3001-3999 | AI 服务错误 |
| 4001-4999 | 回测错误 |
| -1 | 系统未知错误 |

### 分页参数

```
GET /api/stocks?page=1&page_size=20
```

响应：
```json
{
  "code": 0,
  "data": {
    "list": [],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

## 验收标准

- [ ] 前后端可独立启动
- [ ] API 统一响应格式
- [ ] 目录结构符合规范
- [ ] 环境变量配置生效
- [ ] 前端可调用后端 API 并展示数据
