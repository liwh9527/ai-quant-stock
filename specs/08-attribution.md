# 归因分析

## 目标

分析投资组合收益的来源，包括行业选择、个股选择、因子贡献等维度。

## 用户故事

作为投资者，我想要了解收益的来源（是行业选择还是个股选择），以便优化投资策略。

## 页面设计

```
┌─────────────────────────────────────────┐
│  归因分析                                │
├─────────────────────────────────────────┤
│  ┌─ 选择组合 ──────────────────────┐    │
│  │ 回测任务：[MACD策略_2024 ▼]     │    │
│  │ [开始分析]                        │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 收益分解 ──────────────────────┐    │
│  │                                  │    │
│  │  行业选择: +12.3%  ████████      │    │
│  │  个股选择: +8.5%   █████         │    │
│  │  交互效应: +1.2%   █             │    │
│  │  基准收益: +15.0%  ██████████    │    │
│  │  ─────────────────────────────  │    │
│  │  超额收益: +7.0%   ████          │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 行业贡献 ──────────────────────┐    │
│  │  行业      收益    占比   贡献   │    │
│  │  消费      +18%    30%   +5.4%  │    │
│  │  科技      +12%    25%   +3.0%  │    │
│  │  金融      +8%     20%   +1.6%  │    │
│  │  医药      -5%     15%   -0.75% │    │
│  │  能源      +10%    10%   +1.0%  │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 因子贡献 ──────────────────────┐    │
│  │  因子      贡献   占比            │    │
│  │  价值      +3.2%  45%  ████████  │    │
│  │  动量      +2.1%  30%  █████     │    │
│  │  质量      +1.7%  25%  ████      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## API 接口

### 收益归因分析

```
POST /api/attribution/return
```

请求：
```json
{
  "backtest_id": "backtest_20240101_001",
  "benchmark": "000300.SH"
}
```

### 因子归因分析

```
POST /api/attribution/factor
```

请求：
```json
{
  "backtest_id": "backtest_20240101_001",
  "factors": ["roe", "pe", "momentum_20d"]
}
```

## 核心逻辑

### 行业归因（Brinson 模型）

```python
# backend/app/services/attribution/brinson.py

class BrinsonAttribution:
    """Brinson 归因模型"""

    def analyze(self, portfolio, benchmark) -> Dict:
        """
        收益分解：
        - 行业选择收益 (Allocation)
        - 个股选择收益 (Selection)
        - 交互效应 (Interaction)
        """
        industries = set(portfolio["industry"].unique())
        results = {}

        for ind in industries:
            port_weight = portfolio[portfolio["industry"] == ind]["weight"].sum()
            bench_weight = benchmark[benchmark["industry"] == ind]["weight"].sum()
            port_return = portfolio[portfolio["industry"] == ind]["return"].mean()
            bench_return = benchmark[benchmark["industry"] == ind]["return"].mean()

            # 行业选择
            allocation = (port_weight - bench_weight) * bench_return

            # 个股选择
            selection = bench_weight * (port_return - bench_return)

            # 交互效应
            interaction = (port_weight - bench_weight) * (port_return - bench_return)

            results[ind] = {
                "allocation": allocation,
                "selection": selection,
                "interaction": interaction,
                "total": allocation + selection + interaction
            }

        return results
```

### 因子归因

```python
class FactorAttribution:
    """因子归因"""

    def analyze(self, portfolio, factor_exposures) -> Dict:
        """
        分解收益到各因子贡献
        """
        factor_returns = {}

        for factor in factor_exposures.columns:
            # 因子暴露 * 因子收益
            exposure = factor_exposures[factor]
            factor_return = self._calc_factor_return(portfolio, factor)
            factor_returns[factor] = {
                "exposure": exposure.mean(),
                "return": factor_return,
                "contribution": exposure.mean() * factor_return
            }

        return factor_returns
```

## 验收标准

- [ ] 行业归因分析正确
- [ ] 个股选择归因正确
- [ ] 因子归因分析可用
- [ ] 收益分解图表正确
- [ ] 行业贡献图表正确
- [ ] 因子贡献图表正确
- [ ] 移动端界面可用
