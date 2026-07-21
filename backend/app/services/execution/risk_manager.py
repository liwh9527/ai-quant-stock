"""风控模块 — 交易前检查 + 持仓风控

买入前检查：
  - 最大持仓数量
  - 单只股票最大仓位比例
  - 总仓位上限
  - 涨跌停板禁止买入
  - ST 股禁止买入
  - 黑名单过滤

持仓风控：
  - 个股固定止损
  - 个股移动止损
  - 个股止盈
  - 组合最大回撤暂停
  - 连续亏损暂停
"""
import logging
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from ..shared.order import Order
from ..shared.position import Position
from ..shared.portfolio import Portfolio

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """风控配置"""
    # 仓位控制
    max_positions: int = 10                    # 最大持仓数量
    max_single_position_pct: float = 0.15      # 单只最大仓位比例
    max_total_position_pct: float = 0.85       # 总仓位上限

    # 止损止盈
    stop_loss_pct: float = -0.05               # 固定止损 (-5%)
    trailing_stop_pct: float = -0.05           # 移动止损 (从最高点回撤 5%)
    take_profit_pct: float = 0.15              # 止盈 (+15%)

    # 组合风控
    max_drawdown_pct: float = -0.10            # 组合最大回撤 (-10%)，触发暂停
    consecutive_loss_pause: int = 3            # 连续亏损 N 次暂停
    pause_days: int = 3                        # 暂停天数

    # 过滤
    block_st: bool = True                      # 禁止买入 ST 股
    block_limit_up: bool = True                # 涨停板禁止买入
    block_limit_down: bool = True              # 跌停板禁止卖出
    blacklist: List[str] = field(default_factory=list)  # 黑名单股票代码


class RiskCheckResult:
    """风控检查结果"""

    def __init__(self):
        self.passed: bool = True
        self.reasons: List[str] = []  # 拒绝原因列表

    def reject(self, reason: str):
        self.passed = False
        self.reasons.append(reason)

    def __bool__(self):
        return self.passed

    def __str__(self):
        if self.passed:
            return "风控检查通过"
        return f"风控拒绝: {'; '.join(self.reasons)}"


class RiskManager:
    """风控管理器"""

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self._consecutive_losses: int = 0
        self._pause_until: Optional[str] = None  # 暂停到某日
        self._peak_value: float = 0.0             # 组合历史最高净值
        self._trade_log: List[Dict] = []          # 交易记录

    # ---- 买入前检查 ----

    def check_buy(
        self,
        order: Order,
        portfolio: Portfolio,
        current_price: float,
        account_total: float,
        is_st: bool = False,
        is_limit_up: bool = False,
    ) -> RiskCheckResult:
        """买入前风控检查

        Args:
            order: 买入订单
            portfolio: 当前组合
            current_price: 当前价格
            account_total: 账户总资产
            is_st: 是否 ST 股
            is_limit_up: 是否涨停

        Returns:
            RiskCheckResult
        """
        result = RiskCheckResult()

        # 1. 暂停期检查
        if self._pause_until:
            result.reject(f"风控暂停中，暂停至 {self._pause_until}")
            return result

        # 2. 最大持仓数量
        if portfolio.position_count() >= self.config.max_positions:
            result.reject(f"持仓数量已达上限 {self.config.max_positions}")

        # 3. 单只仓位比例
        order_amount = order.price * order.shares
        if account_total > 0:
            position_pct = order_amount / account_total
            if position_pct > self.config.max_single_position_pct:
                result.reject(
                    f"单只仓位 {position_pct:.1%} 超过上限 {self.config.max_single_position_pct:.1%}"
                )

        # 4. 总仓位比例
        current_market_value = sum(
            pos.market_value(current_price) for pos in portfolio.positions.values()
        )
        if account_total > 0:
            total_pct = (current_market_value + order_amount) / account_total
            if total_pct > self.config.max_total_position_pct:
                result.reject(
                    f"总仓位 {total_pct:.1%} 超过上限 {self.config.max_total_position_pct:.1%}"
                )

        # 5. ST 股过滤
        if self.config.block_st and is_st:
            result.reject("禁止买入 ST 股")

        # 6. 涨停板过滤
        if self.config.block_limit_up and is_limit_up:
            result.reject("涨停板禁止买入")

        # 7. 黑名单
        if order.ts_code in self.config.blacklist:
            result.reject(f"{order.ts_code} 在黑名单中")

        # 8. 资金充足性
        if not portfolio.can_buy(order.price, order.shares):
            result.reject("资金不足")

        # 9. 已有持仓检查（不重复买入）
        if portfolio.has_position(order.ts_code):
            result.reject(f"已持有 {order.ts_code}，不重复买入")

        if result.passed:
            logger.info(f"风控通过: 买入 {order.ts_code} {order.shares}股@{order.price}")
        else:
            logger.warning(f"风控拒绝: {order.ts_code} - {result}")

        return result

    # ---- 卖出前检查 ----

    def check_sell(
        self,
        order: Order,
        portfolio: Portfolio,
        is_limit_down: bool = False,
    ) -> RiskCheckResult:
        """卖出前风控检查"""
        result = RiskCheckResult()

        # 1. 持仓检查
        if not portfolio.has_position(order.ts_code):
            result.reject(f"无持仓 {order.ts_code}")

        # 2. T+1 可卖检查
        if not portfolio.can_sell(order.ts_code, order.shares):
            pos = portfolio.get_position(order.ts_code)
            avail = pos.available_shares if pos else 0
            result.reject(f"{order.ts_code} 可卖 {avail} 股，不足 {order.shares} 股（T+1 冻结）")

        # 3. 跌停板检查
        if self.config.block_limit_down and is_limit_down:
            result.reject("跌停板禁止卖出")

        return result

    # ---- 持仓风控（止损/止盈） ----

    def check_positions(
        self,
        portfolio: Portfolio,
        current_prices: Dict[str, float],
        highest_prices: Dict[str, float],
    ) -> List[Order]:
        """检查所有持仓的止损/止盈，返回需要卖出的订单

        Args:
            portfolio: 当前组合
            current_prices: {ts_code: 当前价}
            highest_prices: {ts_code: 持仓期间最高价}

        Returns:
            需要执行的卖出订单列表
        """
        sell_orders = []

        for ts_code, pos in portfolio.positions.items():
            current = current_prices.get(ts_code, pos.buy_price)
            highest = highest_prices.get(ts_code, current)
            profit_pct = pos.profit_pct(current)

            # 固定止损：当前价 <= 买入价 * (1 - 止损比例)
            if current <= pos.buy_price * (1 - abs(self.config.stop_loss_pct)):
                sell_orders.append(Order(
                    ts_code=ts_code,
                    action='SELL',
                    price=current,
                    shares=pos.shares,
                    reason=f"固定止损: 亏损 {profit_pct:.1%}",
                    signal_source='risk_stop_loss',
                ))
                logger.warning(f"触发止损: {ts_code} 亏损 {profit_pct:.1%}")
                continue

            # 移动止损：当前价 <= 最高价 * (1 - 回撤比例)
            stop_price = highest * (1 - abs(self.config.trailing_stop_pct))
            if current <= stop_price:
                sell_orders.append(Order(
                    ts_code=ts_code,
                    action='SELL',
                    price=current,
                    shares=pos.shares,
                    reason=f"移动止损: 从最高 {highest:.2f} 回撤",
                    signal_source='risk_trailing_stop',
                ))
                logger.warning(f"触发移动止损: {ts_code} 最高 {highest:.2f} 当前 {current:.2f}")
                continue

            # 止盈：当前价 >= 买入价 * (1 + 止盈比例)
            if current >= pos.buy_price * (1 + self.config.take_profit_pct):
                sell_orders.append(Order(
                    ts_code=ts_code,
                    action='SELL',
                    price=current,
                    shares=pos.shares,
                    reason=f"止盈: 盈利 {profit_pct:.1%}",
                    signal_source='risk_take_profit',
                ))
                logger.info(f"触发止盈: {ts_code} 盈利 {profit_pct:.1%}")

        return sell_orders

    # ---- 组合风控 ----

    def check_portfolio_drawdown(self, current_value: float) -> bool:
        """检查组合最大回撤

        Args:
            current_value: 当前组合净值

        Returns:
            True if 暂停交易（回撤超限）
        """
        if self._peak_value <= 0:
            self._peak_value = current_value
            return False

        if current_value > self._peak_value:
            self._peak_value = current_value

        drawdown = (current_value - self._peak_value) / self._peak_value
        if drawdown <= self.config.max_drawdown_pct:
            logger.warning(f"组合回撤 {drawdown:.1%} 超过阈值 {self.config.max_drawdown_pct:.1%}，暂停交易")
            return True
        return False

    def record_trade_result(self, pnl: float):
        """记录交易结果，用于连续亏损暂停"""
        if pnl < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.config.consecutive_loss_pause:
                logger.warning(
                    f"连续亏损 {self._consecutive_losses} 次，暂停 {self.config.pause_days} 天"
                )
        else:
            self._consecutive_losses = 0

    def set_pause(self, until_date: str):
        """设置暂停交易"""
        self._pause_until = until_date

    def clear_pause(self):
        """清除暂停"""
        self._pause_until = None
        self._consecutive_losses = 0

    @property
    def is_paused(self) -> bool:
        return self._pause_until is not None

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        return {
            'config': {
                'max_positions': self.config.max_positions,
                'max_single_position_pct': self.config.max_single_position_pct,
                'max_total_position_pct': self.config.max_total_position_pct,
                'stop_loss_pct': self.config.stop_loss_pct,
                'trailing_stop_pct': self.config.trailing_stop_pct,
                'take_profit_pct': self.config.take_profit_pct,
                'max_drawdown_pct': self.config.max_drawdown_pct,
                'consecutive_loss_pause': self.config.consecutive_loss_pause,
                'pause_days': self.config.pause_days,
                'block_st': self.config.block_st,
                'block_limit_up': self.config.block_limit_up,
                'blacklist': self.config.blacklist,
            },
            'state': {
                'consecutive_losses': self._consecutive_losses,
                'pause_until': self._pause_until,
                'peak_value': self._peak_value,
            },
        }
