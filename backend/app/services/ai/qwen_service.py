"""通义千问 AI 服务实现

使用阿里云通义千问 API（OpenAI 兼容模式）实现 AI 服务基类的所有接口。
作为 DeepSeek 的备用方案。
"""

import json
import logging
from typing import Dict, List

import httpx

from app.core.config import settings
from .base import AIServiceBase

logger = logging.getLogger(__name__)


class QwenService(AIServiceBase):
    """通义千问 AI 服务实现

    基于阿里云 DashScope 的 OpenAI 兼容接口，提供与 DeepSeekService
    相同的功能。使用 qwen-turbo 模型，性价比高。
    """

    def __init__(self):
        self.api_key = settings.QWEN_API_KEY
        self.client = httpx.AsyncClient(
            base_url=settings.QWEN_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """调用通义千问 API 进行对话"""
        response = await self.client.post(
            "/chat/completions",
            json={
                "model": "qwen-turbo",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def parse_screening_intent(self, user_input: str) -> Dict:
        """解析选股意图

        将自然语言选股描述转换为结构化的筛选条件 JSON。
        """
        system_prompt = """你是一个量化选股助手。用户会用自然语言描述选股条件，你需要将其解析为结构化的 JSON 格式。

输出格式（严格 JSON，不要包含任何其他文字）：
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

字段说明：
- conditions: 筛选条件列表，每个条件包含 field（字段）、operator（运算符）、value（值）
- industry: 行业筛选，可为 null 表示不限
- market: 市场筛选（如 "沪深300"、"创业板"），可为 null
- sort_by: 排序字段
- sort_order: 排序方向（asc/desc）
- limit: 返回数量上限，默认 20

支持的字段：pe, pb, ps, roe, roa, gross_margin, net_margin, revenue_yoy, net_profit_yoy, debt_ratio, market_cap
支持的运算符：>, <, >=, <=, =, !=

注意：value 必须是数字类型，不要加引号。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        result = await self.chat(messages, temperature=0.1)
        # 提取 JSON 部分（兼容 AI 可能返回多余文字的情况）
        result = result.strip()
        if result.startswith("```"):
            lines = result.split("\n")
            result = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )
        return json.loads(result)

    async def generate_strategy(self, user_input: str) -> Dict:
        """将自然语言转换为策略配置"""
        system_prompt = """你是一个量化策略助手。用户会用自然语言描述交易策略，你需要将其解析为结构化的策略配置。

输出格式（严格 JSON，不要包含任何其他文字）：
{
  "name": "策略名称",
  "description": "策略描述",
  "entry_rules": [
    {"indicator": "macd", "condition": "golden_cross", "params": {"fast": 12, "slow": 26, "signal": 9}}
  ],
  "exit_rules": [
    {"indicator": "macd", "condition": "death_cross", "params": {"fast": 12, "slow": 26, "signal": 9}}
  ],
  "position_size": 0.1,
  "stop_loss": 0.05,
  "take_profit": 0.1,
  "benchmark": "000300.SH"
}

字段说明：
- name: 策略名称
- description: 策略描述
- entry_rules: 买入规则列表，每个规则包含 indicator（指标）、condition（条件）、params（参数）
- exit_rules: 卖出规则列表，格式同上
- position_size: 单次仓位比例 (0.0-1.0)
- stop_loss: 止损比例 (0.0-1.0)
- take_profit: 止盈比例 (0.0-1.0)
- benchmark: 基准指数代码

支持的指标：macd, kdj, ma, ema, rsi, boll
支持的条件：golden_cross, death_cross, above, below, cross_above, cross_below"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        result = await self.chat(messages, temperature=0.1)
        result = result.strip()
        if result.startswith("```"):
            lines = result.split("\n")
            result = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )
        return json.loads(result)

    async def analyze_stock(self, stock_data: Dict) -> str:
        """生成个股分析报告"""
        system_prompt = """你是一个专业的 A 股分析师。请根据提供的股票数据，生成一份结构化的分析报告。

报告格式（Markdown）：
# {股票名称} ({股票代码}) 分析报告

## 基本信息
- 行业、市值等

## 估值分析
- PE、PB 等估值指标分析

## 财务分析
- 盈利能力、成长性、偿债能力

## 技术面分析
- 近期走势、关键指标

## 风险提示
- 主要风险点

## 总结建议
- 综合评价

要求：
1. 语言简洁专业
2. 数据引用准确
3. 风险提示客观
4. 不做具体买卖建议，仅提供分析参考"""

        data_str = json.dumps(stock_data, ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分析以下股票数据：\n\n{data_str}"},
        ]

        return await self.chat(messages, temperature=0.5)

    async def close(self):
        """关闭 HTTP 客户端连接"""
        await self.client.aclose()
