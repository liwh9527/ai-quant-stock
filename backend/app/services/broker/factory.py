"""Broker 工厂 — 根据配置切换券商实现

配置项（通过 .env 或环境变量）：
    BROKER_TYPE: mx | xtquant | sim （默认 mx）
    MX_BASE_URL: 妙想 API 地址（默认 https://mxxysb.com）
    MX_ACCOUNT: 模拟账户名称
    MX_ACCOUNT_INDEX: 账户序号（默认 0）
    MX_APIKEY: 妙想 API 密钥（dfcfs 模式）
"""
import logging
from typing import Optional

from .base import BrokerBase

logger = logging.getLogger(__name__)

# 全局 Broker 实例（单例）
_broker_instance: Optional[BrokerBase] = None


def get_broker() -> BrokerBase:
    """获取 Broker 实例（单例模式）

    根据配置创建对应的 Broker：
        mx      → 东财妙想模拟盘（默认）
        xtquant → MiniQMT（TODO）
        sim     → 自研模拟引擎（TODO）
    """
    global _broker_instance
    if _broker_instance is not None:
        return _broker_instance

    from app.core.config import settings
    broker_type = settings.BROKER_TYPE.lower()

    if broker_type == 'mx':
        from .mx_broker import MxBroker
        _broker_instance = MxBroker(
            base_url=settings.MX_BASE_URL,
            account=settings.MX_ACCOUNT,
            account_index=settings.MX_ACCOUNT_INDEX,
            apikey=settings.MX_APIKEY,
        )
        logger.info(f"创建妙想 Broker: {_broker_instance.base_url}")

    elif broker_type == 'xtquant':
        # TODO: MiniQMT 实现
        raise NotImplementedError("MiniQMT Broker 尚未实现，请使用 BROKER_TYPE=mx")

    elif broker_type == 'sim':
        # TODO: 自研模拟引擎
        raise NotImplementedError("SimBroker 尚未实现，请使用 BROKER_TYPE=mx")

    else:
        raise ValueError(f"不支持的 Broker 类型: {broker_type}，可选: mx, xtquant, sim")

    return _broker_instance


def reset_broker():
    """重置 Broker 实例（用于测试或切换）"""
    global _broker_instance
    _broker_instance = None
