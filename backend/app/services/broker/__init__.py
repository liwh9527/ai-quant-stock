"""券商接口层

提供统一的 Broker 抽象，支持多种券商实现：
  - MxBroker: 东财妙想模拟盘
  - XtQuantBroker: MiniQMT（TODO）
  - SimBroker: 自研模拟引擎（TODO）
"""
from .base import BrokerBase, BrokerError, AccountInfo, QuoteData
from .factory import get_broker, reset_broker

__all__ = [
    'BrokerBase', 'BrokerError', 'AccountInfo', 'QuoteData',
    'get_broker', 'reset_broker',
]
