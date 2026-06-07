"""AIStrategy - 将 AI 生成的策略配置转换为 Backtrader 策略

支持的指标：MACD、KDJ、MA、EMA、RSI、BOLL
支持的条件：golden_cross、death_cross、above、below
"""

import logging
from typing import Dict, List

import backtrader as bt

logger = logging.getLogger(__name__)


class AIStrategy(bt.Strategy):
    """AI 策略适配层

    将 AI 生成的结构化策略配置（entry_rules / exit_rules）
    转换为 Backtrader 可执行的策略逻辑。
    """

    params = (
        ("config", None),
        ("ts_code", ""),
    )

    def __init__(self):
        self.config = self.p.config or {}
        self.order = None
        self.buy_price = None
        self.buy_date = None
        self.trades: List[Dict] = []  # 记录交易

        # 指标容器
        self._entry_indicators = []
        self._exit_indicators = []

        # 止损止盈参数
        self._stop_loss = self.config.get("stop_loss", 0)
        self._take_profit = self.config.get("take_profit", 0)
        self._position_size = self.config.get("position_size", 0.95)

        # 初始化指标
        self._setup_indicators()

    def _setup_indicators(self):
        """根据策略配置添加技术指标"""
        for rule in self.config.get("entry_rules", []):
            ind = self._create_indicator(rule)
            if ind:
                self._entry_indicators.append((ind, rule))

        for rule in self.config.get("exit_rules", []):
            ind = self._create_indicator(rule)
            if ind:
                self._exit_indicators.append((ind, rule))

        # 如果没有配置任何退出指标，使用和入场相同的指标
        if not self._exit_indicators and self._entry_indicators:
            self._exit_indicators = list(self._entry_indicators)

    def _create_indicator(self, rule: Dict):
        """根据规则创建 Backtrader 指标对象"""
        indicator = rule.get("indicator", "").lower()
        condition = rule.get("condition", "")
        params = rule.get("params", {})

        if indicator == "macd":
            fast = params.get("fast", 12)
            slow = params.get("slow", 26)
            sig = params.get("signal", 9)
            return bt.indicators.MACD(
                self.data.close,
                period_me1=fast,
                period_me2=slow,
                period_signal=sig,
            )

        elif indicator == "kdj":
            period = params.get("period", 9)
            # KDJ 使用 Stochastic 指标
            return bt.indicators.Stochastic(
                self.data,
                period=period,
                period_dfast=3,
                period_dslow=3,
            )

        elif indicator == "ma":
            period = params.get("period", 20)
            return bt.indicators.SMA(self.data.close, period=period)

        elif indicator == "ema":
            period = params.get("period", 20)
            return bt.indicators.EMA(self.data.close, period=period)

        elif indicator == "rsi":
            period = params.get("period", 14)
            return bt.indicators.RSI(self.data.close, period=period)

        elif indicator == "boll":
            period = params.get("period", 20)
            devfactor = params.get("devfactor", 2.0)
            return bt.indicators.BollingerBands(
                self.data.close, period=period, devfactor=devfactor
            )

        else:
            logger.warning(f"不支持的指标: {indicator}")
            return None

    def _check_condition(self, indicator, condition: str) -> bool:
        """检查指标是否满足指定条件

        Args:
            indicator: Backtrader 指标对象
            condition: 条件类型

        Returns:
            是否满足条件
        """
        try:
            if condition == "golden_cross":
                # 金叉：短线上穿长线
                if hasattr(indicator, "macd") and hasattr(indicator, "signal"):
                    # MACD 金叉
                    return (
                        indicator.macd[0] > indicator.signal[0]
                        and indicator.macd[-1] <= indicator.signal[-1]
                    )
                elif hasattr(indicator, "percK") and hasattr(indicator, "percD"):
                    # KDJ 金叉
                    return (
                        indicator.percK[0] > indicator.percD[0]
                        and indicator.percK[-1] <= indicator.percD[-1]
                    )

            elif condition == "death_cross":
                # 死叉：短线下穿长线
                if hasattr(indicator, "macd") and hasattr(indicator, "signal"):
                    return (
                        indicator.macd[0] < indicator.signal[0]
                        and indicator.macd[-1] >= indicator.signal[-1]
                    )
                elif hasattr(indicator, "percK") and hasattr(indicator, "percD"):
                    return (
                        indicator.percK[0] < indicator.percD[0]
                        and indicator.percK[-1] >= indicator.percD[-1]
                    )

            elif condition == "above":
                # 价格在指标上方
                if hasattr(indicator, "lines") and hasattr(indicator.lines, "sma"):
                    return self.data.close[0] > indicator.lines.sma[0]
                return self.data.close[0] > indicator[0]

            elif condition == "below":
                # 价格在指标下方
                if hasattr(indicator, "lines") and hasattr(indicator.lines, "sma"):
                    return self.data.close[0] < indicator.lines.sma[0]
                return self.data.close[0] < indicator[0]

            elif condition == "rsi_oversold":
                # RSI 超卖
                return indicator[0] < 30

            elif condition == "rsi_overbought":
                # RSI 超买
                return indicator[0] > 70

        except (IndexError, AttributeError) as e:
            logger.debug(f"条件检查异常: {e}")
            return False

        return False

    def next(self):
        """每根 K 线执行一次"""
        # 如果有未完成的订单，跳过
        if self.order:
            return

        # 检查止损止盈（已持仓时）
        if self.position:
            self._check_stop_loss_take_profit()

        # 未持仓 -> 检查入场条件
        if not self.position:
            if self._check_entry():
                # 按仓位比例计算买入数量
                cash = self.broker.getcash()
                size = int(cash * self._position_size / self.data.close[0])
                size = (size // 100) * 100  # A 股最小 100 股
                if size > 0:
                    self.order = self.buy(size=size)
                    self.buy_price = self.data.close[0]
                    self.buy_date = self.data.datetime.date(0)
        else:
            # 已持仓 -> 检查出场条件
            if self._check_exit():
                self.order = self.sell(size=self.position.size)

    def _check_entry(self) -> bool:
        """检查入场条件（所有规则必须同时满足）"""
        if not self._entry_indicators:
            return False
        for ind, rule in self._entry_indicators:
            if not self._check_condition(ind, rule.get("condition", "")):
                return False
        return True

    def _check_exit(self) -> bool:
        """检查出场条件（任一规则满足即出场）"""
        if not self._exit_indicators:
            return False
        for ind, rule in self._exit_indicators:
            if self._check_condition(ind, rule.get("condition", "")):
                return True
        return False

    def _check_stop_loss_take_profit(self):
        """检查止损止盈"""
        if not self.buy_price or not self.position:
            return

        current_price = self.data.close[0]
        pnl_pct = (current_price - self.buy_price) / self.buy_price

        # 止损
        if self._stop_loss > 0 and pnl_pct <= -self._stop_loss:
            logger.info(
                f"触发止损: 买入价 {self.buy_price:.2f}, "
                f"当前价 {current_price:.2f}, 亏损 {pnl_pct:.2%}"
            )
            self.order = self.sell(size=self.position.size)
            return

        # 止盈
        if self._take_profit > 0 and pnl_pct >= self._take_profit:
            logger.info(
                f"触发止盈: 买入价 {self.buy_price:.2f}, "
                f"当前价 {current_price:.2f}, 盈利 {pnl_pct:.2%}"
            )
            self.order = self.sell(size=self.position.size)

    def notify_order(self, order):
        """订单状态回调"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.trades.append(
                    {
                        "date": self.data.datetime.date(0).strftime("%Y-%m-%d"),
                        "action": "BUY",
                        "ts_code": self.p.ts_code,
                        "price": round(order.executed.price, 2),
                        "shares": order.executed.size,
                        "cost": round(order.executed.value, 2),
                        "pnl": None,
                    }
                )
            elif order.issell():
                pnl_pct = None
                if self.buy_price:
                    pnl_pct = round(
                        (order.executed.price - self.buy_price)
                        / self.buy_price
                        * 100,
                        2,
                    )
                self.trades.append(
                    {
                        "date": self.data.datetime.date(0).strftime("%Y-%m-%d"),
                        "action": "SELL",
                        "ts_code": self.p.ts_code,
                        "price": round(order.executed.price, 2),
                        "shares": order.executed.size,
                        "cost": round(order.executed.value, 2),
                        "pnl": pnl_pct,
                    }
                )
                self.buy_price = None
                self.buy_date = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            logger.warning(f"订单未成交: {order.status}")

        self.order = None
