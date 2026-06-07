"""买卖信号服务

基于技术指标（MACD、KDJ、均线）生成买卖信号。

使用示例：
    from app.services.signal import TechnicalIndicators, SignalGenerator

    # 计算指标
    dif, dea, hist = TechnicalIndicators.macd(df)

    # 生成信号
    generator = SignalGenerator(data_source)
    signals = generator.generate("000001.SZ", ["macd", "kdj"])
"""

from .indicators import TechnicalIndicators
from .generator import SignalGenerator, StopLossRule

__all__ = [
    "TechnicalIndicators",
    "SignalGenerator",
    "StopLossRule",
]
