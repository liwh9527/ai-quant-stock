"""回测 API — 支持 DSL 策略"""
from fastapi import APIRouter, HTTPException
from app.core.database import SessionLocal
from app.services.data.data_manager import DataManager
from app.services.backtest.strategy_parser import StrategyParser
from app.services.backtest.portfolio_engine import PortfolioBacktestEngine

router = APIRouter(prefix="/api/backtest", tags=["回测"])
parser = StrategyParser()


@router.post("/run/dsl")
async def run_dsl_backtest(config: dict):
    """执行 DSL 策略回测"""
    try:
        parsed = parser.parse(config)
    except ValueError as e:
        return {"code": 1, "msg": f"策略配置错误: {str(e)}", "data": None}

    dm = DataManager()
    try:
        engine = PortfolioBacktestEngine(dm)
        start_date = config.get('start_date', '20240101')
        end_date = config.get('end_date', '20260608')
        result = engine.run(parsed, start_date, end_date)
        return {"code": 0, "data": result.to_dict(), "msg": "success"}
    except Exception as e:
        return {"code": 2, "msg": f"回测执行错误: {str(e)}", "data": None}
    finally:
        dm.close()


@router.post("/validate")
async def validate_strategy(config: dict):
    """验证策略配置合法性"""
    try:
        parsed = parser.parse(config)
        return {"code": 0, "data": {"valid": True, "parsed": parsed}, "msg": "策略配置合法"}
    except ValueError as e:
        return {"code": 1, "data": {"valid": False, "error": str(e)}, "msg": "策略配置非法"}


@router.get("/templates")
async def get_templates():
    """获取内置策略模板"""
    templates = parser.get_builtin_templates()
    return {"code": 0, "data": templates, "msg": "success"}
