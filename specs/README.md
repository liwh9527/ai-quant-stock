# 规格文档索引

## 文档列表

| 编号 | 文档 | 模块 | 优先级 | 状态 |
|------|------|------|--------|------|
| 00 | [architecture.md](00-architecture.md) | 整体架构 | P0 | 待实现 |
| 01 | [data-model.md](01-data-model.md) | 数据库模型 | P0 | 待实现 |
| 02 | [data-source.md](02-data-source.md) | 数据源接入层 | P0 | 待实现 |
| 03 | [ai-service.md](03-ai-service.md) | AI 服务层 | P0 | 待实现 |
| 04 | [stock-screening.md](04-stock-screening.md) | 自然语言选股 | P0 | 待实现 |
| 05 | [backtest.md](05-backtest.md) | 策略回测 | P0 | 待实现 |
| 06 | [signal.md](06-signal.md) | 买卖信号 | P0 | 待实现 |
| 07 | [factor.md](07-factor.md) | 多因子系统 | P1 | 待实现 |
| 08 | [attribution.md](08-attribution.md) | 归因分析 | P1 | 待实现 |

## 开发流程

### 开始一个新模块前

1. 阅读本文档，了解全局进度
2. 查看 `tasks.md`，找到下一个待办任务
3. 阅读对应模块的 spec 文档

### 实现过程中

4. 按 spec 中的"实现顺序"逐步实现
5. 每完成一个子任务，在 `tasks.md` 中勾选
6. 对照"验收标准"检查完成度

### 完成后

7. 运行测试确认通过
8. 更新 `tasks.md` 标记模块完成
9. `git commit` 提交

## 依赖关系

```
00-architecture (基础)
    ├── 01-data-model (基础)
    │   ├── 02-data-source (依赖 data-model)
    │   │   ├── 04-stock-screening (依赖 data-source + ai-service)
    │   │   ├── 05-backtest (依赖 data-source)
    │   │   └── 06-signal (依赖 data-source)
    │   └── 07-factor (依赖 data-model + data-source)
    └── 03-ai-service (基础)
        ├── 04-stock-screening
        └── 08-attribution (依赖 factor + backtest)
```

## 实现顺序建议

```
Phase 1: 基础设施
  00-architecture → 01-data-model → 02-data-source → 03-ai-service

Phase 2: P0 核心功能
  04-stock-screening → 05-backtest → 06-signal

Phase 3: P1 增强功能
  07-factor → 08-attribution
```
