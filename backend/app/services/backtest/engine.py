"""BacktestEngine - 回测引擎

集成 Backtrader，配置初始资金、佣金、滑点，运行回测并提取指标。
"""

import logging
import math
from datetime import date, timedelta
from typing import Dict, List, Optional

# Monkey-patch Backtrader 兼容新版 pandas（__bool__ 问题）
import backtrader.lineiterator as _bt_li
if not getattr(_bt_li.LineSeries, '_original_bool_patched', False):
    _bt_li.LineSeries.__bool__ = lambda self: True
    _bt_li.LineSeries._original_bool_patched = True

import backtrader as bt
import numpy as np
import pandas as pd

from app.services.backtest.strategy import AIStrategy

logger = logging.getLogger(__name__)


class PandasDataFeed(bt.feeds.PandasData):
    """自定义 Pandas 数据源，适配 A 股日线数据格式"""

    params = (
        ("datetime", "trade_date"),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "vol"),
        ("openinterest", -1),
    )


class BacktestEngine:
    """回测引擎

    封装 Backtrader Cerebro，提供简化的回测执行接口。
    """

    def __init__(
        self,
        strategy_config: Dict,
        ts_code: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000,
        commission_rate: float = 0.0003,
        slippage: float = 0.001,
        benchmark_code: Optional[str] = None,
    ):
        self.config = strategy_config
        self.ts_code = ts_code
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.benchmark_code = benchmark_code or "000300.SH"

        self.cerebro = bt.Cerebro()

    def setup(self, stock_df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame] = None):
        """配置回测引擎

        Args:
            stock_df: 股票日线数据 DataFrame
            benchmark_df: 基准指数日线数据 DataFrame（可选）
        """
        # 设置初始资金
        self.cerebro.broker.setcash(self.initial_capital)

        # 设置佣金（买入卖出各收一次）
        self.cerebro.broker.setcommission(commission=self.commission_rate)

        # 设置滑点
        self.cerebro.broker.set_slippage_perc(self.slippage)

        # 启用收盘价执行模式（当天信号，当天收盘价执行）
        self.cerebro.broker.set_coc(True)

        # 添加印花税（卖出千一）
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        self.cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
        self.cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")

        # 添加股票数据
        data_feed = PandasDataFeed(
            dataname=stock_df,
            fromdate=pd.Timestamp(self.start_date),
            todate=pd.Timestamp(self.end_date),
        )
        self.cerebro.adddata(data_feed, name=self.ts_code)

        # 添加基准数据（如果提供）
        self._benchmark_df = benchmark_df
        if benchmark_df is not None and not benchmark_df.empty:
            bench_feed = PandasDataFeed(
                dataname=benchmark_df,
                fromdate=pd.Timestamp(self.start_date),
                todate=pd.Timestamp(self.end_date),
            )
            self.cerebro.adddata(bench_feed, name="benchmark")

        # 添加策略
        self.cerebro.addstrategy(
            AIStrategy,
            config=self.config,
            ts_code=self.ts_code,
        )

    def run(self) -> Dict:
        """执行回测并返回结果

        Returns:
            包含指标、收益曲线、交易记录的字典
        """
        results = self.cerebro.run()
        strategy = results[0]

        # 提取各项指标
        metrics = self._extract_metrics(strategy)
        equity_curve = self._extract_equity_curve(strategy)
        trades = strategy.trades

        return {
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
        }

    @staticmethod
    def _safe_round(val, ndigits=2):
        """安全 round，处理 NaN/None"""
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            return 0.0
        return round(float(val), ndigits)

    def _extract_metrics(self, strategy) -> Dict:
        """提取回测指标"""
        final_value = self.cerebro.broker.getvalue()

        # 总收益率
        total_return = (final_value / self.initial_capital - 1) * 100

        # 从 analyzers 提取数据
        returns_analyzer = strategy.analyzers.returns.get_analysis()
        drawdown_analyzer = strategy.analyzers.drawdown.get_analysis()
        sharpe_analyzer = strategy.analyzers.sharpe.get_analysis()
        trade_analyzer = strategy.analyzers.trades.get_analysis()
        time_return = strategy.analyzers.timereturn.get_analysis()

        # 年化收益率
        annual_return = returns_analyzer.get("rnorm100", 0) or 0

        # 最大回撤
        max_drawdown = drawdown_analyzer.get("max", {}).get("drawdown", 0) or 0
        max_drawdown *= -1

        # 夏普比率
        sharpe_ratio = sharpe_analyzer.get("sharperatio", 0) or 0

        # 波动率（年化）
        volatility = 0
        if time_return:
            daily_returns = [v for v in time_return.values() if v is not None and not math.isnan(v)]
            if daily_returns:
                volatility = float(np.std(daily_returns)) * math.sqrt(252) * 100

        # 胜率和交易次数
        total_trades = trade_analyzer.get("total", {}).get("total", 0) or 0
        won_trades = trade_analyzer.get("won", {}).get("total", 0) or 0
        win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0

        # 平均持仓天数
        avg_holding_days = self._calc_avg_holding_days(strategy.trades)

        # 基准收益率
        benchmark_return = self._calc_benchmark_return() or 0

        return {
            "total_return": self._safe_round(total_return),
            "annual_return": self._safe_round(annual_return),
            "max_drawdown": self._safe_round(max_drawdown),
            "sharpe_ratio": self._safe_round(sharpe_ratio),
            "volatility": self._safe_round(volatility),
            "win_rate": self._safe_round(win_rate),
            "trade_count": int(total_trades),
            "avg_holding_days": self._safe_round(avg_holding_days, 1),
            "benchmark_return": self._safe_round(benchmark_return),
            "excess_return": self._safe_round(total_return - benchmark_return),
            "initial_capital": self.initial_capital,
            "final_value": self._safe_round(final_value),
        }

    def _extract_equity_curve(self, strategy) -> List[Dict]:
        """提取每日收益曲线"""
        time_return = strategy.analyzers.timereturn.get_analysis()
        if not time_return:
            return []

        curve = []
        cumulative = self.initial_capital

        # 计算基准累计收益
        benchmark_cumulative = self.initial_capital
        benchmark_returns = self._calc_benchmark_daily_returns()

        for dt, daily_ret in sorted(time_return.items()):
            cumulative *= 1 + daily_ret
            dt_str = dt.strftime("%Y-%m-%d")

            # 基准
            bench_val = None
            if benchmark_returns and dt in benchmark_returns:
                benchmark_cumulative *= 1 + benchmark_returns[dt]
                bench_val = round(benchmark_cumulative, 2)

            curve.append(
                {
                    "date": dt_str,
                    "strategy": round(cumulative, 2),
                    "benchmark": bench_val,
                }
            )

        return curve

    def _calc_avg_holding_days(self, trades: List[Dict]) -> float:
        """计算平均持仓天数"""
        if not trades:
            return 0

        # 配对买卖计算持仓天数
        holding_days = []
        buy_date = None
        for trade in trades:
            if trade["action"] == "BUY" and buy_date is None:
                buy_date = trade["date"]
            elif trade["action"] == "SELL" and buy_date is not None:
                d1 = date.fromisoformat(buy_date)
                d2 = date.fromisoformat(trade["date"])
                holding_days.append((d2 - d1).days)
                buy_date = None

        return sum(holding_days) / len(holding_days) if holding_days else 0

    def _calc_benchmark_return(self) -> float:
        """计算基准收益率"""
        if self._benchmark_df is None or self._benchmark_df.empty:
            return 0

        try:
            df = self._benchmark_df.copy()
            col = "trade_date" if "trade_date" in df.columns else df.index.name
            if col and col in df.columns:
                df = df.sort_values(col)

            start_price = df.iloc[0]["close"]
            end_price = df.iloc[-1]["close"]
            return (end_price / start_price - 1) * 100
        except Exception as e:
            logger.warning(f"计算基准收益率失败: {e}")
            return 0

    def _calc_benchmark_daily_returns(self) -> Dict:
        """计算基准每日收益率，用于绘制基准曲线"""
        if self._benchmark_df is None or self._benchmark_df.empty:
            return {}

        try:
            df = self._benchmark_df.copy()
            if "trade_date" in df.columns:
                df = df.set_index("trade_date")
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            daily_ret = df["close"].pct_change().fillna(0)
            return daily_ret.to_dict()
        except Exception as e:
            logger.warning(f"计算基准日收益失败: {e}")
            return {}
