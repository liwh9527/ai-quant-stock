# 多因子系统

## 目标

构建因子库，支持因子有效性分析和多因子综合评分，用于选股和策略构建。

## 用户故事

作为量化投资者，我想要测试不同因子的有效性，并用多因子综合评分来筛选股票，以便找到更有效的选股策略。

## 页面设计

### 因子库页面

```
┌─────────────────────────────────────────┐
│  因子库                                  │
├─────────────────────────────────────────┤
│  ┌─ 因子分类 ──────────────────────┐    │
│  │ [价值] [成长] [动量] [质量] [波动] │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 因子列表 ──────────────────────┐    │
│  │ 名称      分类    IC    IR   状态 │    │
│  │ PE_TTM    价值   0.05  0.3  有效  │    │
│  │ ROE       质量   0.08  0.5  有效  │    │
│  │ 动量_20日  动量   0.03  0.2  一般  │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

### 因子测试页面

```
┌─────────────────────────────────────────┐
│  因子测试                                │
├─────────────────────────────────────────┤
│  ┌─ 测试配置 ──────────────────────┐    │
│  │ 因子：[ROE ▼]                    │    │
│  │ 分组数：[5 ▼]                    │    │
│  │ 回测区间：[2020-01-01] ~ [2024-12-31]│
│  │ [开始测试]                        │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 分组收益对比 ──────────────────┐    │
│  │ ██████████████████████████████  │    │
│  │ Group1 ~ Group5 收益曲线         │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 因子有效性指标 ────────────────┐    │
│  │ IC: 0.08  IR: 0.5  ICIR: 0.65  │    │
│  │ 多头收益: 15.2%  空头收益: -8.3% │    │
│  │ 多空收益: 23.5%                  │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## API 接口

### 获取因子列表

```
GET /api/factor/list
```

### 因子测试

```
POST /api/factor/test
```

请求：
```json
{
  "factor_name": "roe",
  "groups": 5,
  "start_date": "2020-01-01",
  "end_date": "2024-12-31"
}
```

### 多因子评分

```
POST /api/factor/score
```

请求：
```json
{
  "factors": [
    {"name": "roe", "weight": 0.4},
    {"name": "pe", "weight": -0.3},
    {"name": "momentum_20d", "weight": 0.3}
  ],
  "top_n": 20
}
```

## 核心逻辑

### 因子定义

```python
# backend/app/services/factor/definitions.py

FACTOR_DEFINITIONS = {
    # 价值因子
    "pe": {"name": "市盈率", "category": "value", "field": "pe"},
    "pb": {"name": "市净率", "category": "value", "field": "pb"},
    "ps": {"name": "市销率", "category": "value", "field": "ps"},

    # 成长因子
    "revenue_yoy": {"name": "营收同比", "category": "growth", "field": "revenue_yoy"},
    "net_profit_yoy": {"name": "净利润同比", "category": "growth", "field": "net_profit_yoy"},

    # 质量因子
    "roe": {"name": "净资产收益率", "category": "quality", "field": "roe"},
    "roa": {"name": "总资产收益率", "category": "quality", "field": "roa"},
    "gross_margin": {"name": "销售毛利率", "category": "quality", "field": "gross_margin"},

    # 动量因子
    "momentum_5d": {"name": "5日动量", "category": "momentum", "calc": "momentum"},
    "momentum_20d": {"name": "20日动量", "category": "momentum", "calc": "momentum"},

    # 波动因子
    "volatility_20d": {"name": "20日波动率", "category": "volatility", "calc": "volatility"},
}
```

### 因子有效性分析

```python
# backend/app/services/factor/analyzer.py

class FactorAnalyzer:
    def calc_ic(self, factor_values, returns) -> float:
        """计算信息系数 (IC)"""
        return factor_values.corr(returns)

    def calc_ir(self, ic_series) -> float:
        """计算信息比率 (IR)"""
        return ic_series.mean() / ic_series.std()

    def group_returns(self, df, factor_name, groups=5) -> Dict:
        """分组收益分析"""
        df["group"] = pd.qcut(df[factor_name], groups, labels=False)
        group_returns = df.groupby("group")["next_return"].mean()
        return group_returns
```

### 多因子评分

```python
class FactorScorer:
    def score(self, df, factors) -> pd.DataFrame:
        """多因子综合评分"""
        scores = pd.DataFrame(index=df.index)

        for factor in factors:
            name = factor["name"]
            weight = factor["weight"]

            # 标准化
            normalized = (df[name] - df[name].mean()) / df[name].std()

            # 加权
            scores[name] = normalized * weight

        # 综合得分
        df["total_score"] = scores.sum(axis=1)
        return df.sort_values("total_score", ascending=False)
```

## 验收标准

- [ ] 因子库定义完整
- [ ] 因子 IC/IR 计算正确
- [ ] 分组收益分析可用
- [ ] 多因子评分功能可用
- [ ] 因子相关性分析可用
- [ ] 图表展示正确
- [ ] 移动端界面可用
