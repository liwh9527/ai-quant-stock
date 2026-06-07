"""选股 API

提供自然语言选股的接口：
- POST /api/screening/parse - 解析选股意图
- POST /api/screening/search - 执行筛选
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ai import get_ai_service
from app.services.screening import ScreeningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/screening", tags=["screening"])


# ---------- 请求/响应模型 ----------


class ParseRequest(BaseModel):
    """解析选股意图请求"""
    query: str = Field(..., min_length=1, max_length=500, description="自然语言选股描述")


class ConditionItem(BaseModel):
    """单个筛选条件"""
    field: str
    operator: str
    value: float
    label: Optional[str] = None


class SearchRequest(BaseModel):
    """执行筛选请求"""
    conditions: List[ConditionItem] = Field(default_factory=list)
    industry: Optional[str] = Field(default=None, description="行业筛选")
    market: Optional[str] = Field(default=None, description="市场筛选")
    sort_by: Optional[str] = Field(default=None, description="排序字段")
    sort_order: str = Field(default="desc", description="排序方向")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


# ---------- 路由 ----------


@router.post("/parse")
async def parse_screening_intent(req: ParseRequest, db: Session = Depends(get_db)):
    """解析选股意图

    将自然语言描述转换为结构化筛选条件。
    """
    try:
        ai_service = get_ai_service()
        service = ScreeningService(ai_service, db)
        result = await service.parse_query(req.query)

        return {
            "code": 0,
            "data": result,
            "msg": "",
        }
    except Exception as e:
        logger.exception(f"解析选股意图失败: {e}")
        return {
            "code": -1,
            "data": None,
            "msg": f"解析失败: {str(e)}",
        }


@router.post("/search")
async def search_stocks(req: SearchRequest, db: Session = Depends(get_db)):
    """执行选股筛选

    根据筛选条件查询符合条件的股票列表。
    """
    try:
        ai_service = get_ai_service()
        service = ScreeningService(ai_service, db)

        conditions = [c.model_dump() for c in req.conditions]
        result = service.search(
            conditions=conditions,
            industry=req.industry,
            market=req.market,
            sort_by=req.sort_by,
            sort_order=req.sort_order,
            page=req.page,
            page_size=req.page_size,
        )

        return {
            "code": 0,
            "data": result,
            "msg": "",
        }
    except Exception as e:
        logger.exception(f"选股筛选失败: {e}")
        return {
            "code": -1,
            "data": None,
            "msg": f"筛选失败: {str(e)}",
        }
