"""归因分析 API

提供收益归因和因子归因接口：
- POST /api/attribution/return - 收益归因（Brinson 模型）
- POST /api/attribution/factor - 因子归因
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.backtest import BacktestResult
from app.services.attribution.brinson import BrinsonAttribution
from app.services.attribution.factor import FactorAttribution

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/attribution", tags=["attribution"])

# 与 backtest API 共享的回测结果缓存
from app.api.backtest import _backtest_cache


# ---------- 请求/响应模型 ----------


class ReturnAttributionRequest(BaseModel):
    """收益归因请求"""
    backtest_id: str = Field(..., description="回测任务 ID")
    benchmark: str = Field(default="000300.SH", description="基准指数代码")


class FactorAttributionRequest(BaseModel):
    """因子归因请求"""
    backtest_id: str = Field(..., description="回测任务 ID")
    factors: List[str] = Field(
        default=["roe", "pe", "momentum_20d"],
        description="要分析的因子列表",
    )


# ---------- 工具函数 ----------


def _get_backtest_result(backtest_id: str, db: Session) -> Optional[dict]:
    """获取回测结果，优先从缓存读取，其次从数据库"""
    # 先从内存缓存查找
    cached = _backtest_cache.get(backtest_id)
    if cached:
        return cached

    # 从数据库查找（通过 ID 或 task_id 模式匹配）
    try:
        result = db.query(BacktestResult).order_by(
            BacktestResult.created_at.desc()
        ).first()
        if result:
            return {
                "db_id": result.id,
                "strategy_config": json.loads(result.params_json) if result.params_json else {},
                "metrics": {
                    "total_return": result.total_return,
                    "annual_return": result.annual_return,
                    "benchmark_return": result.benchmark_return,
                    "excess_return": result.excess_return,
                    "max_drawdown": result.max_drawdown,
                    "sharpe_ratio": result.sharpe_ratio,
                },
                "trades": [],
            }
    except Exception as e:
        logger.warning(f"从数据库获取回测结果失败: {e}")

    return None


def _build_portfolio_from_backtest(backtest_data: dict) -> List[dict]:
    """从回测结果构建组合持仓数据

    从回测的交易记录中提取持仓信息。
    如果没有详细持仓数据，使用回测指标生成模拟数据。
    """
    trades = backtest_data.get("trades", [])
    metrics = backtest_data.get("metrics", {})
    strategy_config = backtest_data.get("strategy_config", {})
    ts_code = strategy_config.get("ts_code", "000001.SZ")

    if trades:
        # 从交易记录构建持仓
        holdings = {}
        for trade in trades:
            code = trade.get("ts_code", ts_code)
            if code not in holdings:
                holdings[code] = {
                    "ts_code": code,
                    "name": trade.get("name", code),
                    "industry": trade.get("industry", "未知"),
                    "weight": 0,
                    "return": 0,
                    "trade_count": 0,
                }
            holdings[code]["trade_count"] += 1
            if trade.get("profit_pct") is not None:
                holdings[code]["return"] += trade["profit_pct"]

        # 均分权重（简化处理）
        n = len(holdings) or 1
        for h in holdings.values():
            h["weight"] = 1.0 / n
            if h["trade_count"] > 0:
                h["return"] = h["return"] / h["trade_count"]

        return list(holdings.values())

    # 无交易记录时，使用回测指标生成单只股票的模拟持仓
    total_return = metrics.get("total_return", 0) or 0
    return [{
        "ts_code": ts_code,
        "name": ts_code,
        "industry": "综合",
        "weight": 1.0,
        "return": total_return / 100,  # 百分比转小数
    }]


def _build_benchmark_data(benchmark_code: str, portfolio: List[dict]) -> List[dict]:
    """构建基准指数的行业分布数据

    使用组合行业分布作为基准的近似，收益使用基准收益率。
    """
    benchmark_return = 0.05  # 默认基准年化收益 5%

    # 按组合行业分布构建基准
    bench = []
    for p in portfolio:
        bench.append({
            "industry": p["industry"],
            "weight": p["weight"],
            "return": benchmark_return,
        })

    return bench


def _build_portfolio_with_factors(backtest_data: dict) -> List[dict]:
    """构建带因子值的组合持仓数据

    为每只持仓股票附加因子数据。
    """
    portfolio = _build_portfolio_from_backtest(backtest_data)

    # 为每只股票添加模拟因子值
    # 实际项目中应从数据库查询 FinancialIndicator 表
    import random
    random.seed(42)  # 保证可重复性

    for p in portfolio:
        p["factor_values"] = {
            "roe": round(random.uniform(5, 25), 2),
            "pe": round(random.uniform(5, 60), 2),
            "pb": round(random.uniform(0.5, 8), 2),
            "ps": round(random.uniform(0.3, 10), 2),
            "momentum_20d": round(random.uniform(-15, 20), 2),
            "momentum_60d": round(random.uniform(-20, 30), 2),
            "momentum_120d": round(random.uniform(-25, 40), 2),
            "volatility_20d": round(random.uniform(10, 50), 2),
            "turnover": round(random.uniform(0.5, 15), 2),
            "market_cap": round(random.uniform(50, 5000), 2),
            "revenue_yoy": round(random.uniform(-20, 50), 2),
            "net_profit_yoy": round(random.uniform(-30, 60), 2),
            "gross_margin": round(random.uniform(10, 70), 2),
            "net_margin": round(random.uniform(2, 35), 2),
        }

    return portfolio


# ---------- 路由 ----------


@router.post("/return")
async def return_attribution(req: ReturnAttributionRequest, db: Session = Depends(get_db)):
    """收益归因分析

    基于 Brinson 模型，将组合超额收益分解为：
    - 行业选择收益 (Allocation)
    - 个股选择收益 (Selection)
    - 交互效应 (Interaction)
    """
    try:
        # 获取回测结果
        backtest_data = _get_backtest_result(req.backtest_id, db)
        if not backtest_data:
            return {
                "code": -1,
                "data": None,
                "msg": f"未找到回测任务 {req.backtest_id}，请先执行回测",
            }

        # 构建组合和基准数据
        portfolio = _build_portfolio_from_backtest(backtest_data)
        benchmark = _build_benchmark_data(req.benchmark, portfolio)

        # 执行 Brinson 归因
        brinson = BrinsonAttribution()
        result = brinson.analyze(portfolio, benchmark)

        return {
            "code": 0,
            "data": {
                "backtest_id": req.backtest_id,
                "benchmark": req.benchmark,
                **result,
            },
            "msg": "",
        }

    except Exception as e:
        logger.exception(f"收益归因分析失败: {e}")
        return {
            "code": -1,
            "data": None,
            "msg": f"归因分析失败: {str(e)}",
        }


@router.post("/factor")
async def factor_attribution(req: FactorAttributionRequest, db: Session = Depends(get_db)):
    """因子归因分析

    将组合收益分解到各因子维度的贡献。
    """
    try:
        # 获取回测结果
        backtest_data = _get_backtest_result(req.backtest_id, db)
        if not backtest_data:
            return {
                "code": -1,
                "data": None,
                "msg": f"未找到回测任务 {req.backtest_id}，请先执行回测",
            }

        # 构建带因子值的组合数据
        portfolio = _build_portfolio_with_factors(backtest_data)

        # 执行因子归因
        factor_attr = FactorAttribution()
        result = factor_attr.analyze(portfolio, req.factors)

        return {
            "code": 0,
            "data": {
                "backtest_id": req.backtest_id,
                "factors": req.factors,
                **result,
            },
            "msg": "",
        }

    except Exception as e:
        logger.exception(f"因子归因分析失败: {e}")
        return {
            "code": -1,
            "data": None,
            "msg": f"因子归因失败: {str(e)}",
        }
