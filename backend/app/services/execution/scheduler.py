"""交易调度器 — 管理引擎生命周期和定时任务

功能：
  - 创建并启动执行引擎
  - 盘中定时扫描止损/止盈（每 30 秒）
  - 收盘后记录账户快照
  - 交易时段判断
"""
import asyncio
import logging
from datetime import datetime, time
from typing import Optional

from ..shared.portfolio import Portfolio
from ..broker import get_broker
from .engine import ExecutionEngine
from .risk_manager import RiskManager, RiskConfig

logger = logging.getLogger(__name__)

# 全局状态
_engine: Optional[ExecutionEngine] = None
_scan_task: Optional[asyncio.Task] = None
_running = False


def is_trading_hours() -> bool:
    """判断当前是否在交易时段（9:15 - 15:00）"""
    now = datetime.now()
    # 周末不交易
    if now.weekday() >= 5:
        return False
    t = now.time()
    return time(9, 15) <= t <= time(15, 0)


def is_trading_day() -> bool:
    """判断今天是否是交易日（简化判断：周一到周五）"""
    return datetime.now().weekday() < 5


async def create_and_start_engine(
    risk_config: Optional[RiskConfig] = None,
    auto_execute: bool = True,
) -> ExecutionEngine:
    """创建并启动执行引擎

    Args:
        risk_config: 风控配置，None 使用默认
        auto_execute: True 自动执行，False 手动确认

    Returns:
        启动后的 ExecutionEngine
    """
    global _engine

    broker = get_broker()
    portfolio = Portfolio(initial_cash=500000)
    risk_mgr = RiskManager(risk_config or RiskConfig())

    _engine = ExecutionEngine(
        broker=broker,
        portfolio=portfolio,
        risk_manager=risk_mgr,
        auto_execute=auto_execute,
        on_order_update=_on_order_update,
    )

    await _engine.start()
    logger.info("交易引擎已启动")
    return _engine


async def start_scan_loop(interval: int = 30):
    """启动盘中止损/止盈扫描循环

    Args:
        interval: 扫描间隔（秒）
    """
    global _scan_task, _running

    if _scan_task and not _scan_task.done():
        logger.warning("扫描循环已在运行")
        return

    _running = True
    _scan_task = asyncio.create_task(_scan_loop(interval))
    logger.info(f"扫描循环已启动，间隔 {interval} 秒")


async def stop_scan_loop():
    """停止扫描循环"""
    global _running, _scan_task
    _running = False
    if _scan_task and not _scan_task.done():
        _scan_task.cancel()
        try:
            await _scan_task
        except asyncio.CancelledError:
            pass
    logger.info("扫描循环已停止")


async def _scan_loop(interval: int):
    """盘中扫描主循环"""
    global _engine, _running

    while _running:
        try:
            # 只在交易时段扫描
            if is_trading_hours() and _engine and _engine.is_running:
                orders = await _engine.scan_risk()
                if orders:
                    logger.info(f"风控扫描: 触发 {len(orders)} 笔止损/止盈订单")

                # 同步持仓
                await _engine.sync_positions()

            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"扫描循环异常: {e}")
            await asyncio.sleep(interval)


def _on_order_update(order):
    """订单状态变更回调"""
    logger.info(
        f"订单更新: {order.action} {order.ts_code} "
        f"{order.filled_shares}股@{order.filled_price} "
        f"状态={order.status.value}"
    )


async def shutdown():
    """关闭所有组件"""
    global _engine, _running
    _running = False
    await stop_scan_loop()
    if _engine:
        await _engine.stop()
        _engine = None
    logger.info("交易系统已关闭")
