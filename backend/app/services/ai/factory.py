"""AI 服务工厂

根据配置返回对应的 AI 服务实例，实现模型切换不影响业务代码。
"""

import logging

from app.core.config import settings
from .base import AIServiceBase

logger = logging.getLogger(__name__)


def get_ai_service() -> AIServiceBase:
    """根据配置返回 AI 服务实例

    通过 settings.AI_PROVIDER 配置项决定使用哪个 AI 模型：
    - "deepseek": 使用 DeepSeek Service
    - "qwen": 使用通义千问 Service

    Returns:
        AIServiceBase 的具体实现实例

    Raises:
        ValueError: 当配置了不支持的 AI provider 时
    """
    provider = settings.AI_PROVIDER.lower()

    if provider == "deepseek":
        from .deepseek_service import DeepSeekService

        logger.info("使用 DeepSeek AI 服务")
        return DeepSeekService()
    elif provider == "qwen":
        from .qwen_service import QwenService

        logger.info("使用通义千问 AI 服务")
        return QwenService()
    else:
        raise ValueError(
            f"不支持的 AI 服务商: {provider}，可选值: deepseek, qwen"
        )
