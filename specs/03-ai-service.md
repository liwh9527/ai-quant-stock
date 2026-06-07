# AI 服务层

## 目标

封装 DeepSeek、通义千问等 AI 模型的调用，提供统一的 AI 服务接口，支持自然语言解析、策略生成等功能。

## 用户故事

作为开发者，我想要一个统一的 AI 服务层，以便切换模型时不影响业务代码。

## 技术设计

### 接口定义

```python
# backend/app/services/ai/base.py

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class AIServiceBase(ABC):
    """AI 服务基类"""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """通用对话接口"""
        pass

    @abstractmethod
    async def parse_screening_intent(
        self,
        user_input: str
    ) -> Dict:
        """解析选股意图，返回结构化筛选条件"""
        pass

    @abstractmethod
    async def generate_strategy(
        self,
        user_input: str
    ) -> Dict:
        """将自然语言描述转换为回测策略"""
        pass

    @abstractmethod
    async def analyze_stock(
        self,
        stock_data: Dict
    ) -> str:
        """生成个股分析报告"""
        pass
```

### DeepSeek 实现

```python
# backend/app/services/ai/deepseek_service.py

import httpx
from app.core.config import settings

class DeepSeekService(AIServiceBase):
    BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"}
        )

    async def chat(self, messages, temperature=0.7, max_tokens=2000):
        response = await self.client.post(
            "/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def parse_screening_intent(self, user_input: str) -> Dict:
        """解析选股意图"""
        system_prompt = """你是一个量化选股助手。用户会用自然语言描述选股条件，你需要将其解析为结构化的 JSON 格式。

输出格式：
{
  "conditions": [
    {"field": "pe", "operator": "<", "value": 20},
    {"field": "roe", "operator": ">", "value": 15}
  ],
  "industry": "消费",
  "market": null,
  "sort_by": "roe",
  "sort_order": "desc",
  "limit": 20
}

支持的字段：pe, pb, ps, roe, roa, gross_margin, net_margin, revenue_yoy, net_profit_yoy, debt_ratio, market_cap
支持的运算符：>, <, >=, <=, =, !=
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        result = await self.chat(messages, temperature=0.1)
        import json
        return json.loads(result)

    async def generate_strategy(self, user_input: str) -> Dict:
        """将自然语言转换为策略配置"""
        system_prompt = """你是一个量化策略助手。用户会用自然语言描述交易策略，你需要将其解析为结构化的策略配置。

输出格式：
{
  "name": "策略名称",
  "description": "策略描述",
  "entry_rules": [
    {"indicator": "macd", "condition": "golden_cross", "params": {}}
  ],
  "exit_rules": [
    {"indicator": "macd", "condition": "death_cross", "params": {}}
  ],
  "position_size": 0.1,
  "stop_loss": 0.05,
  "take_profit": 0.1,
  "benchmark": "000300.SH"
}
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        result = await self.chat(messages, temperature=0.1)
        import json
        return json.loads(result)
```

### 通义千问实现（备用）

```python
# backend/app/services/ai/qwen_service.py

class QwenService(AIServiceBase):
    """通义千问实现，接口类似"""
    pass
```

### AI 服务工厂

```python
# backend/app/services/ai/factory.py

from app.core.config import settings

def get_ai_service() -> AIServiceBase:
    """根据配置返回 AI 服务实例"""
    provider = settings.AI_PROVIDER  # "deepseek" or "qwen"

    if provider == "deepseek":
        from .deepseek_service import DeepSeekService
        return DeepSeekService()
    elif provider == "qwen":
        from .qwen_service import QwenService
        return QwenService()
    else:
        raise ValueError(f"Unknown AI provider: {provider}")
```

## 核心功能

### 1. 选股意图解析

输入：`"找 PE<20、ROE>15% 的消费行业股票"`
输出：
```json
{
  "conditions": [
    {"field": "pe", "operator": "<", "value": 20},
    {"field": "roe", "operator": ">", "value": 15}
  ],
  "industry": "消费",
  "sort_by": "roe",
  "sort_order": "desc"
}
```

### 2. 策略生成

输入：`"当 MACD 金叉时买入，死叉时卖出，止损 5%"`
输出：
```json
{
  "name": "MACD 金叉死叉策略",
  "entry_rules": [{"indicator": "macd", "condition": "golden_cross"}],
  "exit_rules": [{"indicator": "macd", "condition": "death_cross"}],
  "stop_loss": 0.05
}
```

### 3. 个股分析

输入：股票数据 JSON
输出：Markdown 格式的分析报告

## 验收标准

- [ ] AIServiceBase 接口定义完成
- [ ] DeepSeekService 实现完成
- [ ] 选股意图解析准确率 > 80%
- [ ] 策略生成功能可用
- [ ] 个股分析报告生成可用
- [ ] AI 服务工厂可切换模型
- [ ] 环境变量配置 API Key
