"""健康检查接口"""

from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "code": 0,
        "data": {
            "status": "ok",
            "env": settings.APP_ENV,
        },
        "msg": ""
    }


@router.get("/api/info")
async def app_info():
    """应用信息"""
    return {
        "code": 0,
        "data": {
            "name": "AI 辅助量化选股工具",
            "version": "0.1.0",
            "env": settings.APP_ENV,
        },
        "msg": ""
    }
