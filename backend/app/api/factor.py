"""多因子系统 API

提供因子列表、因子测试和多因子评分接口：
- GET  /api/factor/list   - 获取因子列表
- POST /api/factor/test   - 因子测试
- POST /api/factor/score  - 多因子评分
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.daily import DailyQuote
from app.models.financial import FinancialIndicator
from app.models.stock import Stock
from app.services.factor.definitions import FACTOR_DEFINITIONS, get_factor_list, is_db_factor
from app.services.factor.analyzer import FactorAnalyzer
from app.services.factor.scorer import FactorScorer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/factor", tags=["factor"])


# ---------- 请求/响应模型 ----------


class FactorTestRequest(BaseModel):
    """因子测试请求"""
    factor_name: str = Field(..., description="因子名称，如 roe、pe")
    groups: int = Field(default=5, ge=2, le=10, description="分组数")
    start_date: str = Field(default="2023-01-01", description="开始日期")
    end_date: str = Field(default="2024-12-31", description="结束日期")


class FactorWeightItem(BaseModel):
    """因子权重项"""
    name: str = Field(..., description="因子名称")
    weight: float = Field(..., description="权重，正数表示正向，负数表示反向")


class FactorScoreRequest(BaseModel):
    """多因子评分请求"""
    factors: List[FactorWeightItem] = Field(..., min_length=1, description="因子及权重列表")
    top_n: int = Field(default=20, ge=1, le=100, description="返回前 N 只股票")


# ---------- 工具函数 ----------


def _build_factor_data(
    db: Session,
    factor_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """构建因子分析所需的 DataFrame

    从数据库获取股票基础信息、最新财务指标和日线行情，
    计算未来收益率，返回合并后的 DataFrame。

    Args:
        db: 数据库会话
        factor_name: 因子名称
        start_date: 开始日期（用于动量/波动因子的计算窗口）
        end_date: 结束日期

    Returns:
        包含 ts_code、name、各因子列、next_return 的 DataFrame
    """
    defn = FACTOR_DEFINITIONS.get(factor_name)
    if not defn:
        raise ValueError(f"未知因子: {factor_name}")

    # 1. 获取最新财务指标
    latest_fin_subq = (
        db.query(
            FinancialIndicator.ts_code,
            func.max(FinancialIndicator.end_date).label("max_end_date"),
        )
        .group_by(FinancialIndicator.ts_code)
        .subquery()
    )

    fin_query = (
        db.query(
            Stock.ts_code,
            Stock.name,
            Stock.industry,
            FinancialIndicator.pe,
            FinancialIndicator.pb,
            FinancialIndicator.ps,
            FinancialIndicator.roe,
            FinancialIndicator.roa,
            FinancialIndicator.gross_margin,
            FinancialIndicator.net_margin,
            FinancialIndicator.revenue_yoy,
            FinancialIndicator.net_profit_yoy,
        )
        .join(FinancialIndicator, Stock.ts_code == FinancialIndicator.ts_code)
        .join(
            latest_fin_subq,
            (FinancialIndicator.ts_code == latest_fin_subq.c.ts_code)
            & (FinancialIndicator.end_date == latest_fin_subq.c.max_end_date),
        )
    )

    rows = fin_query.all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([
        {
            "ts_code": r.ts_code,
            "name": r.name,
            "industry": r.industry or "",
            "pe": r.pe,
            "pb": r.pb,
            "ps": r.ps,
            "roe": r.roe,
            "roa": r.roa,
            "gross_margin": r.gross_margin,
            "net_margin": r.net_margin,
            "revenue_yoy": r.revenue_yoy,
            "net_profit_yoy": r.net_profit_yoy,
        }
        for r in rows
    ])

    # 2. 计算动量/波动因子（需要日线数据）
    calc_type = defn.get("calc")
    if calc_type in ("momentum", "volatility"):
        period = defn.get("period", 20)
        df = _enrich_with_price_factors(db, df, period, calc_type, end_date)

    # 3. 计算未来收益率（取最近两个交易日的涨跌幅作为近似）
    # 实际应取未来 N 日收益率，这里用最近的 pct_chg 做演示
    latest_daily_subq = (
        db.query(
            DailyQuote.ts_code,
            func.max(DailyQuote.trade_date).label("max_date"),
        )
        .group_by(DailyQuote.ts_code)
        .subquery()
    )

    daily_rows = (
        db.query(DailyQuote.ts_code, DailyQuote.pct_chg)
        .join(
            latest_daily_subq,
            (DailyQuote.ts_code == latest_daily_subq.c.ts_code)
            & (DailyQuote.trade_date == latest_daily_subq.c.max_date),
        )
        .all()
    )

    if daily_rows:
        daily_df = pd.DataFrame([
            {"ts_code": r.ts_code, "next_return": r.pct_chg / 100 if r.pct_chg else 0}
            for r in daily_rows
        ])
        df = df.merge(daily_df, on="ts_code", how="left")
        df["next_return"] = df["next_return"].fillna(0)
    else:
        df["next_return"] = 0

    return df


def _enrich_with_price_factors(
    db: Session,
    df: pd.DataFrame,
    period: int,
    calc_type: str,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """为 DataFrame 补充动量或波动因子

    Args:
        db: 数据库会话
        df: 已有的股票 DataFrame
        period: 计算周期
        calc_type: "momentum" 或 "volatility"
        end_date: 截止日期

    Returns:
        添加了动量/波动列的 DataFrame
    """
    ts_codes = df["ts_code"].tolist()
    if not ts_codes:
        return df

    # 获取足够的历史数据
    if end_date:
        ed = date.fromisoformat(end_date)
    else:
        ed = date.today()

    # 多取一些天数以确保有足够交易日
    sd = ed - timedelta(days=period * 2 + 30)

    daily_data = (
        db.query(
            DailyQuote.ts_code,
            DailyQuote.trade_date,
            DailyQuote.close,
            DailyQuote.pct_chg,
        )
        .filter(
            DailyQuote.ts_code.in_(ts_codes),
            DailyQuote.trade_date >= sd,
            DailyQuote.trade_date <= ed,
        )
        .order_by(DailyQuote.ts_code, DailyQuote.trade_date)
        .all()
    )

    if not daily_data:
        col_name = f"{'momentum' if calc_type == 'momentum' else 'volatility'}_{period}d"
        df[col_name] = 0
        return df

    price_df = pd.DataFrame([
        {
            "ts_code": r.ts_code,
            "trade_date": r.trade_date,
            "close": r.close,
            "pct_chg": r.pct_chg,
        }
        for r in daily_data
    ])

    # 计算每个股票的动量或波动
    results = []
    for ts_code, group in price_df.groupby("ts_code"):
        group = group.sort_values("trade_date").tail(period + 1)
        if len(group) < 2:
            val = 0
        elif calc_type == "momentum":
            # 动量 = 最新收盘价 / N日前收盘价 - 1
            first_close = group.iloc[0]["close"]
            last_close = group.iloc[-1]["close"]
            val = (last_close / first_close - 1) * 100 if first_close else 0
        else:
            # 波动率 = 日收益率标准差 * sqrt(252)（年化）
            pct = group["pct_chg"].dropna()
            val = float(pct.std() * (252 ** 0.5)) if len(pct) > 1 else 0

        results.append({"ts_code": ts_code, "value": val})

    col_name = f"{'momentum' if calc_type == 'momentum' else 'volatility'}_{period}d"
    factor_df = pd.DataFrame(results).rename(columns={"value": col_name})
    df = df.merge(factor_df, on="ts_code", how="left")
    df[col_name] = df[col_name].fillna(0)

    return df


def _build_multi_factor_data(db: Session, factor_names: List[str]) -> pd.DataFrame:
    """构建多因子评分所需的 DataFrame

    Args:
        db: 数据库会话
        factor_names: 需要的因子名称列表

    Returns:
        包含所有因子列的 DataFrame
    """
    # 获取最新财务指标
    latest_fin_subq = (
        db.query(
            FinancialIndicator.ts_code,
            func.max(FinancialIndicator.end_date).label("max_end_date"),
        )
        .group_by(FinancialIndicator.ts_code)
        .subquery()
    )

    query = (
        db.query(
            Stock.ts_code,
            Stock.name,
            Stock.industry,
            FinancialIndicator.pe,
            FinancialIndicator.pb,
            FinancialIndicator.ps,
            FinancialIndicator.roe,
            FinancialIndicator.roa,
            FinancialIndicator.gross_margin,
            FinancialIndicator.net_margin,
            FinancialIndicator.revenue_yoy,
            FinancialIndicator.net_profit_yoy,
        )
        .join(FinancialIndicator, Stock.ts_code == FinancialIndicator.ts_code)
        .join(
            latest_fin_subq,
            (FinancialIndicator.ts_code == latest_fin_subq.c.ts_code)
            & (FinancialIndicator.end_date == latest_fin_subq.c.max_end_date),
        )
    )

    rows = query.all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([
        {
            "ts_code": r.ts_code,
            "name": r.name,
            "industry": r.industry or "",
            "pe": r.pe,
            "pb": r.pb,
            "ps": r.ps,
            "roe": r.roe,
            "roa": r.roa,
            "gross_margin": r.gross_margin,
            "net_margin": r.net_margin,
            "revenue_yoy": r.revenue_yoy,
            "net_profit_yoy": r.net_profit_yoy,
        }
        for r in rows
    ])

    # 检查是否需要动量/波动因子
    need_price_factors = []
    for fname in factor_names:
        defn = FACTOR_DEFINITIONS.get(fname, {})
        if defn.get("calc") in ("momentum", "volatility"):
            need_price_factors.append(fname)

    if need_price_factors:
        # 找出最大周期
        max_period = max(
            FACTOR_DEFINITIONS[f].get("period", 20)
            for f in need_price_factors
        )
        calc_types = set(FACTOR_DEFINITIONS[f]["calc"] for f in need_price_factors)

        for calc_type in calc_types:
            period = max(
                FACTOR_DEFINITIONS[f].get("period", 20)
                for f in need_price_factors
                if FACTOR_DEFINITIONS[f]["calc"] == calc_type
            )
            df = _enrich_with_price_factors(db, df, period, calc_type)

    return df


# ---------- 路由 ----------


@router.get("/list")
async def list_factors():
    """获取因子列表

    返回所有可用因子，按分类分组。
    """
    factors = get_factor_list()

    # 按分类分组
    grouped = {}
    for f in factors:
        cat = f["category_name"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(f)

    return {
        "code": 0,
        "data": {
            "factors": factors,
            "grouped": grouped,
            "categories": list(grouped.keys()),
        },
        "msg": "",
    }


@router.post("/test")
async def test_factor(req: FactorTestRequest, db: Session = Depends(get_db)):
    """因子测试

    对指定因子进行有效性分析，计算 IC/IR 和分组收益。
    """
    # 校验因子名称
    if req.factor_name not in FACTOR_DEFINITIONS:
        return {
            "code": -1,
            "data": None,
            "msg": f"未知因子: {req.factor_name}，可用因子: {list(FACTOR_DEFINITIONS.keys())}",
        }

    defn = FACTOR_DEFINITIONS[req.factor_name]

    try:
        # 构建数据
        df = _build_factor_data(db, req.factor_name, req.start_date, req.end_date)

        if df.empty:
            return {
                "code": -1,
                "data": None,
                "msg": "数据库中暂无足够的股票数据，请先同步数据",
            }

        # 确定因子列名
        if "field" in defn:
            factor_col = defn["field"]
        else:
            period = defn.get("period", 20)
            factor_col = f"{'momentum' if defn['calc'] == 'momentum' else 'volatility'}_{period}d"

        if factor_col not in df.columns:
            return {
                "code": -1,
                "data": None,
                "msg": f"因子列 {factor_col} 不存在",
            }

        # 执行分析
        analyzer = FactorAnalyzer()
        result = analyzer.calc_factor_summary(
            df,
            factor_col=factor_col,
            return_col="next_return",
            groups=req.groups,
        )

        # 附加因子元信息
        result["factor"] = {
            "key": req.factor_name,
            "name": defn["name"],
            "category": defn["category"],
            "description": defn.get("description", ""),
        }
        result["config"] = {
            "groups": req.groups,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "data_count": len(df),
        }

        return {"code": 0, "data": result, "msg": ""}

    except Exception as e:
        logger.exception(f"因子测试失败: {e}")
        return {"code": -1, "data": None, "msg": f"因子测试失败: {str(e)}"}


@router.post("/score")
async def score_factors(req: FactorScoreRequest, db: Session = Depends(get_db)):
    """多因子评分

    对全市场股票进行多因子加权评分，返回排名前 N 的股票。
    """
    # 校验因子名称
    for f in req.factors:
        if f.name not in FACTOR_DEFINITIONS:
            return {
                "code": -1,
                "data": None,
                "msg": f"未知因子: {f.name}",
            }

    try:
        factor_names = [f.name for f in req.factors]
        df = _build_multi_factor_data(db, factor_names)

        if df.empty:
            return {
                "code": -1,
                "data": None,
                "msg": "数据库中暂无足够的股票数据，请先同步数据",
            }

        # 执行评分
        scorer = FactorScorer()
        factors_cfg = [{"name": f.name, "weight": f.weight} for f in req.factors]
        result = scorer.score(df, factors=factors_cfg, top_n=req.top_n)

        result["config"] = {
            "factors": factors_cfg,
            "top_n": req.top_n,
        }

        return {"code": 0, "data": result, "msg": ""}

    except Exception as e:
        logger.exception(f"多因子评分失败: {e}")
        return {"code": -1, "data": None, "msg": f"多因子评分失败: {str(e)}"}
