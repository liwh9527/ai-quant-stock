"""交易 API — 引擎控制、持仓、订单、信号、风控"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/trading", tags=["trading"])


# ---- 请求模型 ----

class OrderRequest(BaseModel):
    ts_code: str
    action: str  # BUY / SELL
    price: float
    shares: int
    reason: str = "手动下单"


class RiskConfigUpdate(BaseModel):
    max_positions: Optional[int] = None
    max_single_position_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None


# ---- 全局引擎实例（单例） ----

_engine = None


def get_engine():
    """获取全局执行引擎"""
    return _engine


def set_engine(engine):
    """设置全局执行引擎"""
    global _engine
    _engine = engine


# ---- API 路由 ----

@router.post("/start")
async def start_engine():
    """启动交易引擎"""
    import traceback
    try:
        from app.services.broker import get_broker, reset_broker

        reset_broker()
        broker = get_broker()

        # Create engine
        from app.services.shared.portfolio import Portfolio
        from app.services.execution.risk_manager import RiskManager, RiskConfig
        from app.services.execution.engine import ExecutionEngine

        portfolio = Portfolio(initial_cash=500000)
        risk_mgr = RiskManager(RiskConfig())

        engine = ExecutionEngine(
            broker=broker,
            portfolio=portfolio,
            risk_manager=risk_mgr,
            auto_execute=True,
        )
        set_engine(engine)

        # Start engine (connects to broker)
        await engine.start()

        return {"code": 0, "data": {"status": "started"}, "msg": "引擎已启动"}
    except Exception as e:
        traceback.print_exc()
        return {"code": -1, "data": None, "msg": f"启动失败: {type(e).__name__}: {str(e)}"}


@router.get("/test")
async def test_endpoint():
    """测试端点"""
    return {"code": 0, "data": {"test": "ok"}, "msg": ""}


@router.post("/stop")
async def stop_engine():
    """停止交易引擎"""
    engine = get_engine()
    if not engine or not engine.is_running:
        return {"code": 0, "data": {"status": "not_running"}, "msg": "引擎未运行"}

    await engine.stop()
    return {"code": 0, "data": {"status": "stopped"}, "msg": "引擎已停止"}


@router.get("/status")
async def get_status():
    """获取引擎状态"""
    engine = get_engine()
    if not engine:
        return {"code": 0, "data": {"running": False, "message": "引擎未初始化"}, "msg": ""}

    status = engine.get_status()
    return {"code": 0, "data": status, "msg": ""}


@router.get("/account")
async def get_account():
    """查询账户资金"""
    engine = get_engine()
    if not engine or not engine.is_running:
        raise HTTPException(status_code=400, detail="引擎未运行")

    account = await engine.broker.query_account()
    return {
        "code": 0,
        "data": {
            "total_assets": account.total_assets,
            "available_cash": account.available_cash,
            "market_value": account.market_value,
            "frozen_cash": account.frozen_cash,
        },
        "msg": ""
    }


@router.get("/positions")
async def get_positions():
    """查询当前持仓"""
    engine = get_engine()
    if not engine or not engine.is_running:
        raise HTTPException(status_code=400, detail="引擎未运行")

    await engine.sync_positions()
    positions = []
    for ts_code, pos in engine.portfolio.positions.items():
        quote = await engine.broker.get_quote(ts_code)
        current_price = quote.price if quote else pos.buy_price
        positions.append({
            "ts_code": pos.ts_code,
            "buy_price": pos.buy_price,
            "buy_date": pos.buy_date,
            "shares": pos.shares,
            "available_shares": pos.available_shares if pos.available_shares >= 0 else pos.shares,
            "hold_days": pos.hold_days,
            "current_price": current_price,
            "market_value": pos.market_value(current_price),
            "profit_pct": pos.profit_pct(current_price),
            "profit_amount": pos.profit_amount(current_price),
        })

    return {"code": 0, "data": positions, "msg": ""}


@router.post("/order")
async def place_order(req: OrderRequest):
    """手动下单"""
    engine = get_engine()
    if not engine or not engine.is_running:
        raise HTTPException(status_code=400, detail="引擎未运行")

    if req.action.upper() == 'BUY':
        order = await engine.buy(req.ts_code, req.price, req.shares, req.reason)
    elif req.action.upper() == 'SELL':
        order = await engine.sell(req.ts_code, req.price, req.shares, req.reason)
    else:
        raise HTTPException(status_code=400, detail=f"不支持的操作: {req.action}")

    if not order:
        raise HTTPException(status_code=400, detail="下单失败")

    return {
        "code": 0,
        "data": order.to_dict(),
        "msg": ""
    }


@router.get("/orders")
async def get_orders(date: Optional[str] = None, status: Optional[str] = None):
    """查询订单列表"""
    engine = get_engine()
    if not engine:
        return {"code": 0, "data": [], "msg": ""}

    from app.services.shared.order import OrderStatus
    orders = engine.get_orders()

    if status:
        try:
            st = OrderStatus(status.upper())
            orders = [o for o in orders if o.status == st]
        except ValueError:
            pass

    if date:
        orders = [o for o in orders if o.created_at.startswith(date)]
    else:
        # 默认返回今日
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        orders = [o for o in orders if o.created_at.startswith(today)]

    return {"code": 0, "data": [o.to_dict() for o in orders], "msg": ""}


@router.get("/signals")
async def get_signals():
    """获取待确认信号（手动模式）"""
    engine = get_engine()
    if not engine:
        return {"code": 0, "data": [], "msg": ""}

    return {"code": 0, "data": engine.get_pending_signals(), "msg": ""}


@router.post("/signals/{index}/confirm")
async def confirm_signal(index: int):
    """确认待执行信号"""
    engine = get_engine()
    if not engine or not engine.is_running:
        raise HTTPException(status_code=400, detail="引擎未运行")

    order = await engine.confirm_order(index)
    if not order:
        raise HTTPException(status_code=404, detail="信号不存在")

    return {"code": 0, "data": order.to_dict(), "msg": ""}


@router.post("/risk/scan")
async def scan_risk():
    """手动触发止损/止盈扫描"""
    engine = get_engine()
    if not engine or not engine.is_running:
        raise HTTPException(status_code=400, detail="引擎未运行")

    orders = await engine.scan_risk()
    return {
        "code": 0,
        "data": {
            "triggered": len(orders),
            "orders": [o.to_dict() for o in orders],
        },
        "msg": ""
    }


@router.get("/risk/status")
async def get_risk_status():
    """获取风控状态"""
    engine = get_engine()
    if not engine:
        return {"code": 0, "data": {}, "msg": ""}

    return {"code": 0, "data": engine.risk_manager.to_dict(), "msg": ""}


@router.put("/risk/config")
async def update_risk_config(req: RiskConfigUpdate):
    """更新风控配置"""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=400, detail="引擎未初始化")

    config = engine.risk_manager.config
    if req.max_positions is not None:
        config.max_positions = req.max_positions
    if req.max_single_position_pct is not None:
        config.max_single_position_pct = req.max_single_position_pct
    if req.stop_loss_pct is not None:
        config.stop_loss_pct = req.stop_loss_pct
    if req.trailing_stop_pct is not None:
        config.trailing_stop_pct = req.trailing_stop_pct
    if req.take_profit_pct is not None:
        config.take_profit_pct = req.take_profit_pct
    if req.max_drawdown_pct is not None:
        config.max_drawdown_pct = req.max_drawdown_pct

    return {"code": 0, "data": engine.risk_manager.to_dict(), "msg": "风控配置已更新"}
