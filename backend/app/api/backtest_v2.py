"""回测 API — 支持 DSL 策略 + 策略库"""
from fastapi import APIRouter, HTTPException
from app.core.database import SessionLocal
from app.services.data.data_manager import DataManager
from app.services.backtest.strategy_parser import StrategyParser
from app.services.backtest.portfolio_engine import PortfolioBacktestEngine
from app.services.backtest.strategies import list_strategies, get_strategy, get_categories

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


# ========== 策略库 API ==========

@router.get("/strategies")
async def api_list_strategies(category: str = None):
    """获取策略库列表"""
    strategies = list_strategies(category)
    # 返回摘要信息（不含完整 config）
    items = []
    for s in strategies:
        items.append({
            "key": s["key"],
            "name": s["name"],
            "category": s["category"],
            "description": s["description"],
            "suitable": s.get("suitable", ""),
            "params": s.get("params", {}),
        })
    return {"code": 0, "data": items, "msg": "success"}


@router.get("/strategies/categories")
async def api_get_categories():
    """获取策略分类列表"""
    categories = get_categories()
    return {"code": 0, "data": categories, "msg": "success"}


@router.get("/strategies/{key}")
async def api_get_strategy(key: str):
    """获取策略详情（含完整配置）"""
    strategy = get_strategy(key)
    if not strategy:
        return {"code": 1, "msg": f"策略不存在: {key}", "data": None}
    return {"code": 0, "data": strategy, "msg": "success"}


@router.post("/strategies/{key}/run")
async def api_run_strategy(key: str, params: dict = None):
    """运行策略回测

    params: 可选，覆盖策略默认参数，如 {"start_date": "20210101", "end_date": "20260101", "max_positions": 3}
    """
    strategy = get_strategy(key)
    if not strategy:
        return {"code": 1, "msg": f"策略不存在: {key}", "data": None}

    import copy
    config = copy.deepcopy(strategy["config"])

    # 合并用户参数
    params = params or {}
    start_date = params.pop("start_date", "20210701")
    end_date = params.pop("end_date", "20260701")

    # 覆盖 config 中的参数
    if "max_positions" in params:
        config.setdefault("risk_control", {})["max_positions"] = params["max_positions"]
    if "initial_cash" in params:
        config["initial_cash"] = params["initial_cash"]
    if "stop_loss" in params:
        config.setdefault("exit", {}).setdefault("rules", [])
        for rule in config["exit"]["rules"]:
            if rule.get("type") == "stop_loss":
                rule["pct"] = params["stop_loss"]

    # 解析并运行
    try:
        parsed = parser.parse(config)
    except ValueError as e:
        return {"code": 1, "msg": f"策略配置错误: {str(e)}", "data": None}

    dm = DataManager()
    try:
        engine = PortfolioBacktestEngine(dm)
        result = engine.run(parsed, start_date, end_date)
        return {"code": 0, "data": result.to_dict(), "msg": "success"}
    except Exception as e:
        return {"code": 2, "msg": f"回测执行错误: {str(e)}", "data": None}
    finally:
        dm.close()
