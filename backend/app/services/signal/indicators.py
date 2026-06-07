"""技术指标计算模块

提供 MACD、KDJ、均线等常用技术指标的计算。
"""

import pandas as pd
import numpy as np


class TechnicalIndicators:
    """技术指标计算"""

    @staticmethod
    def macd(
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """计算 MACD 指标

        Args:
            df: 行情数据，需包含 close 列
            fast: 快线周期，默认 12
            slow: 慢线周期，默认 26
            signal: 信号线周期，默认 9

        Returns:
            (DIF, DEA, MACD柱) 三个序列
        """
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        macd_hist = (dif - dea) * 2
        return dif, dea, macd_hist

    @staticmethod
    def kdj(
        df: pd.DataFrame,
        n: int = 9,
        m1: int = 3,
        m2: int = 3,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """计算 KDJ 指标

        Args:
            df: 行情数据，需包含 close, high, low 列
            n: RSV 周期，默认 9
            m1: K 线平滑参数，默认 3
            m2: D 线平滑参数，默认 3

        Returns:
            (K, D, J) 三个序列
        """
        low_n = df["low"].rolling(window=n).min()
        high_n = df["high"].rolling(window=n).max()
        # 防止除零
        denom = high_n - low_n
        denom = denom.replace(0, np.nan)
        rsv = (df["close"] - low_n) / denom * 100
        k = rsv.ewm(com=m1 - 1, adjust=False).mean()
        d = k.ewm(com=m2 - 1, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    @staticmethod
    def ma(
        df: pd.DataFrame,
        periods: list[int] | None = None,
    ) -> dict[str, pd.Series]:
        """计算均线

        Args:
            df: 行情数据，需包含 close 列
            periods: 均线周期列表，默认 [5, 10, 20, 60]

        Returns:
            字典，key 为 "ma5" 等，value 为对应均线序列
        """
        if periods is None:
            periods = [5, 10, 20, 60]
        result: dict[str, pd.Series] = {}
        for p in periods:
            result[f"ma{p}"] = df["close"].rolling(window=p).mean()
        return result
