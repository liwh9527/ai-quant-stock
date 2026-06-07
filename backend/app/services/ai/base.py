"""AI 服务基类定义

提供统一的 AI 服务接口，所有具体模型实现需继承此基类。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class AIServiceBase(ABC):
    """AI 服务基类

    定义了 AI 服务的统一接口，包括：
    - chat: 通用对话
    - parse_screening_intent: 解析选股意图
    - generate_strategy: 生成回测策略
    - analyze_stock: 个股分析
    """

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """通用对话接口

        Args:
            messages: 对话消息列表，每条消息包含 role 和 content
            temperature: 温度参数，控制输出随机性 (0.0-1.0)
            max_tokens: 最大输出 token 数

        Returns:
            AI 回复的文本内容
        """
        pass

    @abstractmethod
    async def parse_screening_intent(self, user_input: str) -> Dict:
        """解析选股意图，返回结构化筛选条件

        将用户自然语言描述转换为可执行的筛选条件 JSON。

        Args:
            user_input: 用户输入的自然语言选股描述
                例如："找 PE<20、ROE>15% 的消费行业股票"

        Returns:
            结构化的筛选条件字典，格式：
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
        """
        pass

    @abstractmethod
    async def generate_strategy(self, user_input: str) -> Dict:
        """将自然语言描述转换为回测策略配置

        Args:
            user_input: 用户描述的交易策略
                例如："当 MACD 金叉时买入，死叉时卖出，止损 5%"

        Returns:
            结构化的策略配置字典，格式：
            {
                "name": "策略名称",
                "description": "策略描述",
                "entry_rules": [...],
                "exit_rules": [...],
                "position_size": 0.1,
                "stop_loss": 0.05,
                "take_profit": 0.1,
                "benchmark": "000300.SH"
            }
        """
        pass

    @abstractmethod
    async def analyze_stock(self, stock_data: Dict) -> str:
        """生成个股分析报告

        Args:
            stock_data: 股票数据字典，包含行情、财务等信息

        Returns:
            Markdown 格式的分析报告
        """
        pass

    async def close(self):
        """关闭底层 HTTP 客户端连接"""
        pass
