"""信号生成器

根据技术指标生成买卖信号，支持 MACD、KDJ、均线交叉。
"""

import logging
from datetime import date
from typing import Any

import pandas as pd

from app.services.data.base import DataSourceBase
from app.services.signal.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class SignalGenerator:
    """买卖信号生成器"""

    def __init__(self, data_source: DataSourceBase):
        self.data = data_source

    def generate(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
        indicators: list[str],
        params: dict[str, Any] | None = None,
    ) -> dict:
        """生成买卖信号

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            indicators: 要使用的指标列表，如 ["macd", "kdj", "ma"]
            params: 各指标参数，如 {"macd": {"fast": 12}, "kdj": {"n": 9}}

        Returns:
            包含 signals 和 chart_data 的字典
        """
        if params is None:
            params = {}

        # 获取行情数据，多取一些用于指标预热
        from datetime import timedelta

        warmup_start = start_date - timedelta(days=120)
        df = self.data.get_daily_quotes(ts_code, warmup_start, end_date)

        if df.empty:
            return {"signals": [], "chart_data": {"kline": [], "macd": [], "kdj": []}}

        # 确保按日期升序
        df = df.sort_values("trade_date").reset_index(drop=True)

        # 将 trade_date 设为索引便于计算
        df_indexed = df.set_index("trade_date")

        signals: list[dict] = []
        chart_data: dict[str, list] = {"kline": [], "macd": [], "kdj": [], "ma": []}

        # 生成 K 线数据
        for _, row in df.iterrows():
            chart_data["kline"].append({
                "date": row["trade_date"].strftime("%Y-%m-%d"),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("vol", 0),
            })

        # MACD 信号
        if "macd" in indicators:
            macd_params = params.get("macd", {})
            dif, dea, hist = TechnicalIndicators.macd(df_indexed, **macd_params)
            macd_signals = self._macd_signals(df_indexed, dif, dea, hist, start_date)
            signals.extend(macd_signals)

            # MACD 图表数据
            for dt, val in dif.items():
                chart_data["macd"].append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "dif": round(float(val), 4),
                    "dea": round(float(dea.loc[dt]), 4),
                    "hist": round(float(hist.loc[dt]), 4),
                })

        # KDJ 信号
        if "kdj" in indicators:
            kdj_params = params.get("kdj", {})
            k, d, j = TechnicalIndicators.kdj(df_indexed, **kdj_params)
            kdj_signals = self._kdj_signals(df_indexed, k, d, j, start_date)
            signals.extend(kdj_signals)

            # KDJ 图表数据
            for dt in k.index:
                chart_data["kdj"].append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "k": round(float(k.loc[dt]), 2),
                    "d": round(float(d.loc[dt]), 2),
                    "j": round(float(j.loc[dt]), 2),
                })

        # 均线信号
        if "ma" in indicators:
            ma_params = params.get("ma", {})
            ma_dict = TechnicalIndicators.ma(df_indexed, **ma_params)
            ma_signals = self._ma_signals(df_indexed, ma_dict, start_date)
            signals.extend(ma_signals)

            # 均线图表数据
            for dt in df_indexed.index:
                item: dict[str, Any] = {"date": dt.strftime("%Y-%m-%d")}
                for name, series in ma_dict.items():
                    val = series.loc[dt]
                    item[name] = round(float(val), 2) if pd.notna(val) else None
                chart_data["ma"].append(item)

        # 按日期排序
        signals.sort(key=lambda x: x["date"])

        return {
            "signals": signals,
            "chart_data": chart_data,
        }

    def _macd_signals(
        self,
        df: pd.DataFrame,
        dif: pd.Series,
        dea: pd.Series,
        hist: pd.Series,
        start_date: date,
    ) -> list[dict]:
        """生成 MACD 金叉/死叉信号"""
        signals: list[dict] = []
        dates = df.index.tolist()
        start_ts = pd.Timestamp(start_date)

        for i in range(1, len(dates)):
            # 只返回 start_date 之后的信号
            if dates[i] < start_ts:
                continue

            curr_dif = dif.iloc[i]
            prev_dif = dif.iloc[i - 1]
            curr_dea = dea.iloc[i]
            prev_dea = dea.iloc[i - 1]
            price = df["close"].iloc[i]

            # 金叉：DIF 上穿 DEA
            if curr_dif > curr_dea and prev_dif <= prev_dea:
                strength = min(abs(curr_dif - curr_dea) / price * 100, 1.0)
                signals.append({
                    "date": dates[i].strftime("%Y-%m-%d"),
                    "type": "BUY",
                    "indicator": "macd",
                    "price": round(float(price), 2),
                    "strength": round(float(strength), 2),
                    "reason": "MACD 金叉，DIF 上穿 DEA",
                })

            # 死叉：DIF 下穿 DEA
            if curr_dif < curr_dea and prev_dif >= prev_dea:
                strength = min(abs(curr_dif - curr_dea) / price * 100, 1.0)
                signals.append({
                    "date": dates[i].strftime("%Y-%m-%d"),
                    "type": "SELL",
                    "indicator": "macd",
                    "price": round(float(price), 2),
                    "strength": round(float(strength), 2),
                    "reason": "MACD 死叉，DIF 下穿 DEA",
                })

        return signals

    def _kdj_signals(
        self,
        df: pd.DataFrame,
        k: pd.Series,
        d: pd.Series,
        j: pd.Series,
        start_date: date,
    ) -> list[dict]:
        """生成 KDJ 超买/超卖信号"""
        signals: list[dict] = []
        dates = df.index.tolist()
        start_ts = pd.Timestamp(start_date)

        for i in range(1, len(dates)):
            if dates[i] < start_ts:
                continue

            curr_k = k.iloc[i]
            prev_k = k.iloc[i - 1]
            curr_d = d.iloc[i]
            prev_d = d.iloc[i - 1]
            curr_j = j.iloc[i]
            price = df["close"].iloc[i]

            # 金叉：K 上穿 D 且处于超卖区域（< 20）
            if curr_k > curr_d and prev_k <= prev_d and curr_j < 30:
                strength = min((30 - curr_j) / 30, 1.0)
                signals.append({
                    "date": dates[i].strftime("%Y-%m-%d"),
                    "type": "BUY",
                    "indicator": "kdj",
                    "price": round(float(price), 2),
                    "strength": round(float(abs(strength)), 2),
                    "reason": f"KDJ 金叉（J={curr_j:.1f}），K 上穿 D，超卖区域",
                })

            # 死叉：K 下穿 D 且处于超买区域（> 80）
            if curr_k < curr_d and prev_k >= prev_d and curr_j > 70:
                strength = min((curr_j - 70) / 30, 1.0)
                signals.append({
                    "date": dates[i].strftime("%Y-%m-%d"),
                    "type": "SELL",
                    "indicator": "kdj",
                    "price": round(float(price), 2),
                    "strength": round(float(abs(strength)), 2),
                    "reason": f"KDJ 死叉（J={curr_j:.1f}），K 下穿 D，超买区域",
                })

        return signals

    def _ma_signals(
        self,
        df: pd.DataFrame,
        ma_dict: dict[str, pd.Series],
        start_date: date,
    ) -> list[dict]:
        """生成均线交叉信号（短期均线上穿/下穿长期均线）"""
        signals: list[dict] = []

        # 按周期排序的均线名称
        ma_names = sorted(ma_dict.keys(), key=lambda x: int(x.replace("ma", "")))

        if len(ma_names) < 2:
            return signals

        dates = df.index.tolist()
        start_ts = pd.Timestamp(start_date)

        # 检查相邻周期的均线交叉
        for idx in range(len(ma_names) - 1):
            short_ma = ma_dict[ma_names[idx]]
            long_ma = ma_dict[ma_names[idx + 1]]

            for i in range(1, len(dates)):
                if dates[i] < start_ts:
                    continue

                curr_short = short_ma.iloc[i]
                prev_short = short_ma.iloc[i - 1]
                curr_long = long_ma.iloc[i]
                prev_long = long_ma.iloc[i - 1]

                # 跳过 NaN
                if pd.isna(curr_short) or pd.isna(prev_short) or pd.isna(curr_long) or pd.isna(prev_long):
                    continue

                price = df["close"].iloc[i]
                short_name = ma_names[idx].upper()
                long_name = ma_names[idx + 1].upper()

                # 金叉：短期均线上穿长期均线
                if curr_short > curr_long and prev_short <= prev_long:
                    strength = min(abs(curr_short - curr_long) / price * 100, 1.0)
                    signals.append({
                        "date": dates[i].strftime("%Y-%m-%d"),
                        "type": "BUY",
                        "indicator": "ma",
                        "price": round(float(price), 2),
                        "strength": round(float(strength), 2),
                        "reason": f"{short_name} 上穿 {long_name}，均线金叉",
                    })

                # 死叉：短期均线下穿长期均线
                if curr_short < curr_long and prev_short >= prev_long:
                    strength = min(abs(curr_short - curr_long) / price * 100, 1.0)
                    signals.append({
                        "date": dates[i].strftime("%Y-%m-%d"),
                        "type": "SELL",
                        "indicator": "ma",
                        "price": round(float(price), 2),
                        "strength": round(float(strength), 2),
                        "reason": f"{short_name} 下穿 {long_name}，均线死叉",
                    })

        return signals


class StopLossRule:
    """止损止盈规则"""

    @staticmethod
    def fixed_stop_loss(
        entry_price: float,
        current_price: float,
        stop_pct: float = 0.05,
    ) -> bool:
        """固定比例止损

        Args:
            entry_price: 入场价格
            current_price: 当前价格
            stop_pct: 止损比例，默认 5%

        Returns:
            是否触发止损
        """
        return current_price <= entry_price * (1 - stop_pct)

    @staticmethod
    def trailing_stop(
        entry_price: float,
        highest_price: float,
        current_price: float,
        trail_pct: float = 0.05,
    ) -> bool:
        """移动止损

        Args:
            entry_price: 入场价格
            highest_price: 持仓期间最高价
            current_price: 当前价格
            trail_pct: 回撤比例，默认 5%

        Returns:
            是否触发止损
        """
        stop_price = highest_price * (1 - trail_pct)
        return current_price <= stop_price

    @staticmethod
    def take_profit(
        entry_price: float,
        current_price: float,
        profit_pct: float = 0.1,
    ) -> bool:
        """止盈

        Args:
            entry_price: 入场价格
            current_price: 当前价格
            profit_pct: 止盈比例，默认 10%

        Returns:
            是否触发止盈
        """
        return current_price >= entry_price * (1 + profit_pct)
