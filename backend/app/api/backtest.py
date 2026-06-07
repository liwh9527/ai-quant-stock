"""策略回测 API

提供回测任务创建和结果查询接口。
"""

import json
import logging
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.backtest import BacktestResult
from app.services.ai import get_ai_service
from app.services.backtest import BacktestEngine
from app.services.data import get_data_source, DataCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

# 内存缓存回测结果（生产环境应使用 Redis）
_backtest_cache: dict = {}


# ---------- 请求/响应模型 ----------


class BacktestRunRequest(BaseModel):
    """回测任务请求"""

    strategy_description: str = Field(..., description="策略描述，如 'MACD 金叉买入，死叉卖出'")
    ts_code: str = Field(default="000001.SZ", description="股票代码")
    start_date: str = Field(default="2020-01-01", description="回测开始日期")
    end_date: str = Field(default="2024-12-31", description="回测结束日期")
    initial_capital: float = Field(default=100000, description="初始资金")
    benchmark: str = Field(default="000300.SH", description="基准指数代码")
    commission_rate: float = Field(default=0.0003, description="佣金率")
    slippage: float = Field(default=0.001, description="滑点")


# ---------- 工具函数 ----------


def _generate_task_id() -> str:
    """生成回测任务 ID"""
    short_uuid = uuid.uuid4().hex[:8]
    return f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{short_uuid}"


def _get_stock_data(source, ts_code: str, start_date: str, end_date: str):
    """获取股票日线数据"""
    try:
        df = source.get_daily_quotes(
            ts_code=ts_code,
            start_date=date.fromisoformat(start_date),
            end_date=date.fromisoformat(end_date),
        )
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning(f"获取股票数据失败: {e}")

    # 备用：从数据库查询
    return None


def _get_benchmark_data(source, benchmark_code: str, start_date: str, end_date: str):
    """获取基准指数日线数据"""
    try:
        df = source.get_daily_quotes(
            ts_code=benchmark_code,
            start_date=date.fromisoformat(start_date),
            end_date=date.fromisoformat(end_date),
        )
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning(f"获取基准数据失败: {e}")
    return None


# ---------- 路由 ----------


@router.post("/run")
async def run_backtest(req: BacktestRunRequest, db: Session = Depends(get_db)):
    """创建回测任务

    接收自然语言策略描述，通过 AI 解析为策略配置，
    然后使用 Backtrader 引擎执行回测。
    """
    task_id = _generate_task_id()

    try:
        # 1. AI 解析策略
        ai_service = get_ai_service()
        try:
            strategy_config = await ai_service.generate_strategy(req.strategy_description)
        except Exception as e:
            logger.error(f"AI 策略解析失败: {e}")
            # 使用默认 MACD 策略作为回退
            strategy_config = _fallback_strategy(req.strategy_description)

        # 2. 获取股票数据
        source = get_data_source()
        cached = DataCache(source)

        stock_df = _get_stock_data(cached, req.ts_code, req.start_date, req.end_date)
        if stock_df is None or stock_df.empty:
            return {
                "code": -1,
                "data": None,
                "msg": f"无法获取 {req.ts_code} 的行情数据，请确认股票代码和日期范围",
            }

        benchmark_df = _get_benchmark_data(cached, req.benchmark, req.start_date, req.end_date)

        # 3. 执行回测
        engine = BacktestEngine(
            strategy_config=strategy_config,
            ts_code=req.ts_code,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            commission_rate=req.commission_rate,
            slippage=req.slippage,
            benchmark_code=req.benchmark,
        )
        engine.setup(stock_df, benchmark_df)
        result = engine.run()

        # 4. 保存到数据库
        metrics = result["metrics"]
        db_result = BacktestResult(
            strategy_name=strategy_config.get("name", "未知策略"),
            strategy_desc=req.strategy_description,
            start_date=date.fromisoformat(req.start_date),
            end_date=date.fromisoformat(req.end_date),
            total_return=metrics["total_return"],
            annual_return=metrics["annual_return"],
            benchmark_return=metrics["benchmark_return"],
            excess_return=metrics["excess_return"],
            max_drawdown=metrics["max_drawdown"],
            sharpe_ratio=metrics["sharpe_ratio"],
            volatility=metrics["volatility"],
            win_rate=metrics["win_rate"],
            trade_count=metrics["trade_count"],
            avg_holding_days=metrics["avg_holding_days"],
            params_json=json.dumps(
                {
                    "ts_code": req.ts_code,
                    "initial_capital": req.initial_capital,
                    "commission_rate": req.commission_rate,
                    "slippage": req.slippage,
                    "benchmark": req.benchmark,
                    "strategy_config": strategy_config,
                },
                ensure_ascii=False,
            ),
        )
        db.add(db_result)
        db.commit()
        db.refresh(db_result)

        # 5. 缓存结果
        full_result = {
            "task_id": task_id,
            "status": "completed",
            "db_id": db_result.id,
            "strategy_config": strategy_config,
            **result,
        }
        _backtest_cache[task_id] = full_result

        return {
            "code": 0,
            "data": {
                "task_id": task_id,
                "status": "completed",
                "strategy_config": strategy_config,
                "metrics": result["metrics"],
                "equity_curve": result["equity_curve"],
                "trades": result["trades"],
            },
            "msg": "",
        }

    except Exception as e:
        logger.exception(f"回测执行失败: {e}")
        return {
            "code": -1,
            "data": {"task_id": task_id, "status": "failed"},
            "msg": f"回测执行失败: {str(e)}",
        }


@router.get("/result/{task_id}")
async def get_backtest_result(task_id: str):
    """查询回测结果"""
    result = _backtest_cache.get(task_id)
    if not result:
        return {
            "code": -1,
            "data": None,
            "msg": "未找到该回测任务，请检查 task_id 是否正确",
        }

    return {
        "code": 0,
        "data": {
            "task_id": task_id,
            "status": result.get("status", "unknown"),
            "metrics": result.get("metrics", {}),
            "equity_curve": result.get("equity_curve", []),
            "trades": result.get("trades", []),
            "strategy_config": result.get("strategy_config", {}),
        },
        "msg": "",
    }


@router.get("/list")
async def list_backtest_results(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """查询历史回测记录列表"""
    query = db.query(BacktestResult)
    total = query.count()

    items = (
        query.order_by(BacktestResult.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    records = [
        {
            "id": item.id,
            "strategy_name": item.strategy_name,
            "strategy_desc": item.strategy_desc,
            "start_date": item.start_date.strftime("%Y-%m-%d") if item.start_date else None,
            "end_date": item.end_date.strftime("%Y-%m-%d") if item.end_date else None,
            "total_return": item.total_return,
            "annual_return": item.annual_return,
            "max_drawdown": item.max_drawdown,
            "sharpe_ratio": item.sharpe_ratio,
            "win_rate": item.win_rate,
            "trade_count": item.trade_count,
            "created_at": item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else None,
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


def _fallback_strategy(description: str) -> dict:
    """AI 不可用时的默认策略回退

    根据关键词简单匹配，生成策略配置。
    """
    desc_lower = description.lower()

    # 尝试识别策略类型
    if "kdj" in desc_lower:
        return {
            "name": "KDJ 策略",
            "description": description,
            "entry_rules": [
                {"indicator": "kdj", "condition": "golden_cross", "params": {"period": 9}}
            ],
            "exit_rules": [
                {"indicator": "kdj", "condition": "death_cross", "params": {"period": 9}}
            ],
            "position_size": 0.95,
            "stop_loss": 0.05,
            "take_profit": 0.1,
        }

    if "rsi" in desc_lower:
        return {
            "name": "RSI 策略",
            "description": description,
            "entry_rules": [
                {"indicator": "rsi", "condition": "rsi_oversold", "params": {"period": 14}}
            ],
            "exit_rules": [
                {"indicator": "rsi", "condition": "rsi_overbought", "params": {"period": 14}}
            ],
            "position_size": 0.95,
            "stop_loss": 0.05,
            "take_profit": 0.1,
        }

    if "均线" in desc_lower or "ma" in desc_lower:
        return {
            "name": "均线策略",
            "description": description,
            "entry_rules": [
                {"indicator": "ma", "condition": "golden_cross", "params": {"period": 20}}
            ],
            "exit_rules": [
                {"indicator": "ma", "condition": "death_cross", "params": {"period": 20}}
            ],
            "position_size": 0.95,
            "stop_loss": 0.05,
            "take_profit": 0.1,
        }

    # 默认 MACD 策略
    return {
        "name": "MACD 策略",
        "description": description,
        "entry_rules": [
            {"indicator": "macd", "condition": "golden_cross", "params": {"fast": 12, "slow": 26, "signal": 9}}
        ],
        "exit_rules": [
            {"indicator": "macd", "condition": "death_cross", "params": {"fast": 12, "slow": 26, "signal": 9}}
        ],
        "position_size": 0.95,
        "stop_loss": 0.05,
        "take_profit": 0.1,
    }
