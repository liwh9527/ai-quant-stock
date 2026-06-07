# 买卖信号

## 目标

基于技术指标（MACD、KDJ、均线等）生成买卖信号，支持自定义规则，提供信号列表和图表标注。

## 用户故事

作为投资者，我想要系统自动根据技术指标生成买卖信号，以便及时发现交易机会。

## 页面设计

### 布局

```
┌─────────────────────────────────────────┐
│  买卖信号                                │
├─────────────────────────────────────────┤
│  ┌─ 信号配置 ──────────────────────┐    │
│  │ 股票：[000001.SZ ▼]             │    │
│  │ 指标：[MACD ▼] [KDJ ▼] [均线 ▼] │    │
│  │ 时间范围：[最近30天 ▼]           │    │
│  │ [生成信号]                        │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ K 线图 + 信号标注 ─────────────┐    │
│  │  ┌─────────────────────────────┐ │    │
│  │  │ K 线图                      │ │    │
│  │  │  ↑ 买入信号 (绿色箭头)      │ │    │
│  │  │  ↓ 卖出信号 (红色箭头)      │ │    │
│  │  └─────────────────────────────┘ │    │
│  │  ┌─────────────────────────────┐ │    │
│  │  │ MACD 指标图                 │ │    │
│  │  └─────────────────────────────┘ │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 信号列表 ──────────────────────┐    │
│  │ 日期      类型  指标    价格   强度 │    │
│  │ 2024-01-15 买入  MACD   12.50  0.8 │    │
│  │ 2024-01-20 卖出  KDJ    13.80  0.6 │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## API 接口

### 生成信号

```
POST /api/signal/generate
```

请求：
```json
{
  "ts_code": "000001.SZ",
  "indicators": ["macd", "kdj", "ma"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "params": {
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "kdj": {"n": 9, "m1": 3, "m2": 3},
    "ma": {"periods": [5, 10, 20, 60]}
  }
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "signals": [
      {
        "date": "2024-01-15",
        "type": "BUY",
        "indicator": "macd",
        "price": 12.50,
        "strength": 0.8,
        "reason": "MACD 金叉，DIF 上穿 DEA"
      }
    ],
    "chart_data": {
      "kline": [],
      "macd": [],
      "kdj": []
    }
  },
  "msg": ""
}
```

### 获取信号列表

```
GET /api/signal/list?ts_code=000001.SZ&page=1&page_size=20
```

## 核心逻辑

### 技术指标计算

```python
# backend/app/services/signal/indicators.py

import pandas as pd
import numpy as np

class TechnicalIndicators:
    """技术指标计算"""

    @staticmethod
    def macd(df, fast=12, slow=26, signal=9):
        """计算 MACD"""
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        macd_hist = (dif - dea) * 2
        return dif, dea, macd_hist

    @staticmethod
    def kdj(df, n=9, m1=3, m2=3):
        """计算 KDJ"""
        low_n = df["low"].rolling(window=n).min()
        high_n = df["high"].rolling(window=n).max()
        rsv = (df["close"] - low_n) / (high_n - low_n) * 100
        k = rsv.ewm(com=m1-1, adjust=False).mean()
        d = k.ewm(com=m2-1, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    @staticmethod
    def ma(df, periods=[5, 10, 20, 60]):
        """计算均线"""
        result = {}
        for p in periods:
            result[f"ma{p}"] = df["close"].rolling(window=p).mean()
        return result
```

### 信号生成器

```python
# backend/app/services/signal/generator.py

class SignalGenerator:
    def __init__(self, data_source: DataSourceBase):
        self.data = data_source

    def generate(self, ts_code, indicators, params) -> List[Dict]:
        """生成买卖信号"""
        df = self.data.get_daily_quotes(ts_code)
        signals = []

        if "macd" in indicators:
            signals.extend(self._macd_signals(df, params.get("macd", {})))

        if "kdj" in indicators:
            signals.extend(self._kdj_signals(df, params.get("kdj", {})))

        # 按日期排序
        signals.sort(key=lambda x: x["date"])
        return signals

    def _macd_signals(self, df, params) -> List[Dict]:
        """MACD 信号"""
        dif, dea, hist = TechnicalIndicators.macd(
            df, **params
        )
        signals = []

        # 金叉：DIF 上穿 DEA
        for i in range(1, len(df)):
            if dif.iloc[i] > dea.iloc[i] and dif.iloc[i-1] <= dea.iloc[i-1]:
                signals.append({
                    "date": df.index[i].strftime("%Y-%m-%d"),
                    "type": "BUY",
                    "indicator": "macd",
                    "price": df["close"].iloc[i],
                    "strength": min(abs(dif.iloc[i] - dea.iloc[i]) / df["close"].iloc[i] * 100, 1.0),
                    "reason": "MACD 金叉，DIF 上穿 DEA"
                })

            # 死叉：DIF 下穿 DEA
            if dif.iloc[i] < dea.iloc[i] and dif.iloc[i-1] >= dea.iloc[i-1]:
                signals.append({
                    "date": df.index[i].strftime("%Y-%m-%d"),
                    "type": "SELL",
                    "indicator": "macd",
                    "price": df["close"].iloc[i],
                    "strength": min(abs(dif.iloc[i] - dea.iloc[i]) / df["close"].iloc[i] * 100, 1.0),
                    "reason": "MACD 死叉，DIF 下穿 DEA"
                })

        return signals
```

### 止损止盈规则

```python
class StopLossRule:
    """止损止盈规则"""

    @staticmethod
    def fixed_stop_loss(entry_price, current_price, stop_pct=0.05):
        """固定比例止损"""
        return current_price <= entry_price * (1 - stop_pct)

    @staticmethod
    def trailing_stop(entry_price, highest_price, current_price, trail_pct=0.05):
        """移动止损"""
        stop_price = highest_price * (1 - trail_pct)
        return current_price <= stop_price

    @staticmethod
    def take_profit(entry_price, current_price, profit_pct=0.1):
        """止盈"""
        return current_price >= entry_price * (1 + profit_pct)
```

## 验收标准

- [ ] MACD 信号正确生成
- [ ] KDJ 信号正确生成
- [ ] 均线信号正确生成
- [ ] K 线图正确展示
- [ ] 信号标注在图表上
- [ ] 信号列表可筛选和排序
- [ ] 止损止盈规则生效
- [ ] 移动端界面可用
