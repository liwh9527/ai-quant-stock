# AI 辅助量化选股工具

## 项目概述
A 股量化选股 Web 工具，详细需求和技术方案见 `project-brief.md`。

## 技术栈
- 前端：React + Vite + Tailwind CSS + ECharts + TradingView Lightweight Charts
- 后端：Python 3.11+ + FastAPI + SQLAlchemy + SQLite
- 回测：Backtrader + 自研适配层
- AI：DeepSeek API（主）/ 通义千问（备）
- 数据源：Tushare（主）/ AkShare / 东财（备）

## 开发规范

### 通用
- 使用中文注释和 commit message
- 每完成一个可运行的功能就 commit
- 改完后在 changelog.md 追加一行说明
- 移动端优先，确保手机浏览器可用

### 前端
- 样式用 Tailwind，不写自定义 CSS 文件
- 组件拆分粒度：一个文件不超过 200 行
- API 调用统一走 `src/services/` 层，不在组件里直接 fetch
- K 线图用 TradingView Lightweight Charts，其他图表用 ECharts

### 后端
- 路由定义在 `app/api/`，业务逻辑在 `app/services/`，不在路由里写业务
- 数据源调用统一走 `app/services/data/` 接口层，上层不直接调用 tushare/akshare
- AI 调用统一走 `app/services/ai/` 接口层，上层不直接调用具体模型 SDK
- 所有配置（API key、token）走环境变量，不硬编码
- 接口统一返回 `{"code": 0, "data": ..., "msg": ""}` 格式

### 数据库
- 用 SQLAlchemy ORM 操作数据库，不写裸 SQL
- model 定义在 `app/models/`
- 迁移用 Alembic

## 常用命令

### 前端
```bash
cd frontend
npm install          # 安装依赖
npm run dev          # 启动开发服务器
npm run build        # 生产构建
```

### 后端
```bash
cd backend
pip install -r requirements.txt    # 安装依赖
uvicorn app.main:app --reload      # 启动开发服务器
pytest                             # 运行测试
```

## 环境变量
```bash
# backend/.env
TUSHARE_TOKEN=xxx
DEEPSEEK_API_KEY=xxx
QWEN_API_KEY=xxx           # 备选
DATABASE_URL=sqlite:///data/quant.db
```

## 规格文档

详细的技术规格文档在 `specs/` 目录下：

```
specs/
├── README.md              # 规格文档索引 + 开发流程说明
├── 00-architecture.md     # 整体架构设计
├── 01-data-model.md       # 数据库模型
├── 02-data-source.md      # 数据源接入层
├── 03-ai-service.md       # AI 服务层
├── 04-stock-screening.md  # 自然语言选股
├── 05-backtest.md         # 策略回测
├── 06-signal.md           # 买卖信号
├── 07-factor.md           # 多因子系统
├── 08-attribution.md      # 归因分析
└── tasks.md               # 任务跟踪
```

### 开发流程

1. 阅读 `specs/README.md` 了解全局
2. 查看 `specs/tasks.md` 找到下一个待办任务
3. 阅读对应模块的 spec 文档
4. 按 spec 中的"实现顺序"逐步实现
5. 对照"验收标准"检查完成度
6. 更新 `tasks.md` 标记完成
7. `git commit` 提交

## 当前阶段
P0 — MVP：自然语言选股、策略回测、买卖信号
