"""AI 服务层

提供统一的 AI 服务接口，支持多种大模型切换。

使用示例：
    from app.services.ai import get_ai_service

    service = get_ai_service()
    result = await service.parse_screening_intent("找 PE<20 的消费股")
"""

from .base import AIServiceBase
from .factory import get_ai_service

__all__ = ["AIServiceBase", "get_ai_service"]
