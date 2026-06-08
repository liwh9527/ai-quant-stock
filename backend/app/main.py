"""FastAPI 应用入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.health import router as health_router
from app.api.signal import router as signal_router
from app.api.backtest import router as backtest_router
from app.api.backtest_v2 import router as backtest_v2_router
from app.api.screening import router as screening_router
from app.api.attribution import router as attribution_router
from app.api.factor import router as factor_router

app = FastAPI(
    title="AI 辅助量化选股工具",
    description="A 股量化选股 Web 工具",
    version="0.1.0",
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health_router)
app.include_router(backtest_v2_router)
app.include_router(signal_router)
app.include_router(backtest_router)
app.include_router(screening_router)
app.include_router(attribution_router)
app.include_router(factor_router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "code": 0,
        "data": {"message": "AI 辅助量化选股工具 API"},
        "msg": ""
    }
