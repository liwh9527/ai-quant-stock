"""买卖信号 API

提供信号生成和查询接口。
"""

import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.signal import TradeSignal
from app.services.data import get_data_source, DataCache
from app.services.signal import SignalGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/signal", tags=["signal"])


# ---------- 请求/响应模型 ----------


class SignalGenerateRequest(BaseModel):
    """信号生成请求"""

    ts_code: str = Field(..., description="股票代码，如 000001.SZ")
    indicators: list[str] = Field(
        default=["macd", "kdj", "ma"],
        description="指标列表，可选: macd, kdj, ma",
    )
    start_date: Optional[str] = Field(None, description="开始日期，格式 YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="结束日期，格式 YYYY-MM-DD")
    params: dict = Field(default_factory=dict, description="各指标参数")


class SignalGenerateResponse(BaseModel):
    """信号生成响应"""

    signals: list[dict]
    chart_data: dict


# ---------- 工具函数 ----------


def _get_generator() -> SignalGenerator:
    """获取信号生成器实例"""
    source = get_data_source()
    cached = DataCache(source)
    return SignalGenerator(cached)


# ---------- 路由 ----------


@router.post("/generate")
async def generate_signals(req: SignalGenerateRequest, db: Session = Depends(get_db)):
    """生成买卖信号

    根据指定的技术指标和参数，计算买卖信号并返回图表数据。
    同时将信号持久化到数据库。
    """
    # 解析日期，默认最近 60 天
    end = date.fromisoformat(req.end_date) if req.end_date else date.today()
    start = (
        date.fromisoformat(req.start_date) if req.start_date else end - timedelta(days=60)
    )

    generator = _get_generator()
    result = generator.generate(
        ts_code=req.ts_code,
        start_date=start,
        end_date=end,
        indicators=req.indicators,
        params=req.params,
    )

    # 将信号写入数据库
    saved_count = 0
    for sig in result["signals"]:
        # 去重：同一股票同一日期同一指标同类型不重复插入
        exists = (
            db.query(TradeSignal)
            .filter(
                TradeSignal.ts_code == req.ts_code,
                TradeSignal.signal_date == sig["date"],
                TradeSignal.signal_source == sig["indicator"],
                TradeSignal.signal_type == sig["type"],
            )
            .first()
        )
        if not exists:
            db_signal = TradeSignal(
                ts_code=req.ts_code,
                signal_date=sig["date"],
                signal_type=sig["type"],
                strategy_name="technical",
                signal_source=sig["indicator"],
                price=sig["price"],
                strength=sig["strength"],
                reason=sig["reason"],
            )
            db.add(db_signal)
            saved_count += 1

    if saved_count > 0:
        db.commit()
        logger.info(f"保存 {saved_count} 条信号到数据库")

    return {
        "code": 0,
        "data": result,
        "msg": "",
    }


@router.get("/list")
async def list_signals(
    ts_code: Optional[str] = Query(None, description="股票代码"),
    signal_type: Optional[str] = Query(None, description="信号类型: BUY/SELL"),
    indicator: Optional[str] = Query(None, description="信号来源: macd/kdj/ma"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """获取信号列表

    支持按股票代码、信号类型、指标来源筛选，分页返回。
    """
    query = db.query(TradeSignal)

    if ts_code:
        query = query.filter(TradeSignal.ts_code == ts_code)
    if signal_type:
        query = query.filter(TradeSignal.signal_type == signal_type)
    if indicator:
        query = query.filter(TradeSignal.signal_source == indicator)

    total = query.count()

    items = (
        query.order_by(TradeSignal.signal_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    records = [
        {
            "id": item.id,
            "ts_code": item.ts_code,
            "date": item.signal_date.strftime("%Y-%m-%d"),
            "type": item.signal_type,
            "indicator": item.signal_source,
            "price": item.price,
            "strength": item.strength,
            "reason": item.reason,
        }
        for item in items
    ]

    return {
        "code": 0,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "records": records,
        },
        "msg": "",
    }
