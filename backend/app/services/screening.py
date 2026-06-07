"""选股服务

提供自然语言选股的核心业务逻辑：
- parse_query: 调用 AI 解析自然语言查询为结构化筛选条件
- search: 根据筛选条件从数据库查询符合条件的股票
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy import func, desc, asc
from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.models.financial import FinancialIndicator
from app.models.daily import DailyQuote
from app.services.ai import AIServiceBase

logger = logging.getLogger(__name__)

# 筛选条件中支持的字段映射（前端字段名 -> 数据库列）
FIELD_MAP = {
    "pe": FinancialIndicator.pe,
    "pb": FinancialIndicator.pb,
    "ps": FinancialIndicator.ps,
    "roe": FinancialIndicator.roe,
    "roa": FinancialIndicator.roa,
    "gross_margin": FinancialIndicator.gross_margin,
    "net_margin": FinancialIndicator.net_margin,
    "revenue_yoy": FinancialIndicator.revenue_yoy,
    "net_profit_yoy": FinancialIndicator.net_profit_yoy,
    "debt_ratio": FinancialIndicator.debt_ratio,
    "current_ratio": FinancialIndicator.current_ratio,
    "eps": FinancialIndicator.eps,
    "bvps": FinancialIndicator.bvps,
    "market_cap": None,  # 需要从其他表获取，暂不支持
}

# 排序字段映射
SORT_FIELD_MAP = {
    "pe": FinancialIndicator.pe,
    "pb": FinancialIndicator.pb,
    "roe": FinancialIndicator.roe,
    "roa": FinancialIndicator.roa,
    "gross_margin": FinancialIndicator.gross_margin,
    "net_margin": FinancialIndicator.net_margin,
    "revenue_yoy": FinancialIndicator.revenue_yoy,
    "net_profit_yoy": FinancialIndicator.net_profit_yoy,
}


class ScreeningService:
    """选股服务"""

    def __init__(self, ai_service: AIServiceBase, db: Session):
        self.ai = ai_service
        self.db = db

    async def parse_query(self, query: str) -> Dict:
        """解析自然语言查询

        调用 AI 服务将用户输入转换为结构化筛选条件。

        Args:
            query: 用户输入的自然语言选股描述

        Returns:
            结构化的筛选条件字典
        """
        result = await self.ai.parse_screening_intent(query)

        # 给每个条件生成可读的 label
        conditions = result.get("conditions", [])
        for cond in conditions:
            if "label" not in cond:
                field = cond.get("field", "")
                operator = cond.get("operator", "")
                value = cond.get("value", "")
                # 字段中文映射
                field_names = {
                    "pe": "PE", "pb": "PB", "ps": "PS",
                    "roe": "ROE", "roa": "ROA",
                    "gross_margin": "毛利率", "net_margin": "净利率",
                    "revenue_yoy": "营收同比", "net_profit_yoy": "净利润同比",
                    "debt_ratio": "资产负债率", "current_ratio": "流动比率",
                    "eps": "每股收益", "bvps": "每股净资产",
                    "market_cap": "市值",
                }
                field_cn = field_names.get(field, field.upper())
                suffix = "%" if field in (
                    "roe", "roa", "gross_margin", "net_margin",
                    "revenue_yoy", "net_profit_yoy", "debt_ratio",
                ) else ""
                cond["label"] = f"{field_cn} {operator} {value}{suffix}"

        return result

    def search(
        self,
        conditions: List[Dict],
        industry: Optional[str] = None,
        market: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """执行筛选查询

        根据条件从数据库查询符合条件的股票，返回分页结果。

        Args:
            conditions: 筛选条件列表
            industry: 行业筛选
            market: 市场筛选
            sort_by: 排序字段
            sort_order: 排序方向 (asc/desc)
            page: 页码
            page_size: 每页数量

        Returns:
            包含 list、total、page、page_size 的字典
        """
        # 构建基础查询：关联 Stock、FinancialIndicator、最新 DailyQuote
        # 子查询：获取每只股票最新的财务指标
        latest_fin_subq = (
            self.db.query(
                FinancialIndicator.ts_code,
                func.max(FinancialIndicator.end_date).label("max_end_date"),
            )
            .group_by(FinancialIndicator.ts_code)
            .subquery()
        )

        # 子查询：获取每只股票最新的日线行情
        latest_daily_subq = (
            self.db.query(
                DailyQuote.ts_code,
                func.max(DailyQuote.trade_date).label("max_trade_date"),
            )
            .group_by(DailyQuote.ts_code)
            .subquery()
        )

        # 主查询
        query = (
            self.db.query(
                Stock.ts_code,
                Stock.name,
                Stock.industry,
                Stock.market,
                FinancialIndicator.pe,
                FinancialIndicator.pb,
                FinancialIndicator.ps,
                FinancialIndicator.roe,
                FinancialIndicator.roa,
                FinancialIndicator.gross_margin,
                FinancialIndicator.net_margin,
                FinancialIndicator.revenue_yoy,
                FinancialIndicator.net_profit_yoy,
                FinancialIndicator.debt_ratio,
                DailyQuote.close,
                DailyQuote.pct_chg,
            )
            .join(FinancialIndicator, Stock.ts_code == FinancialIndicator.ts_code)
            .join(
                latest_fin_subq,
                (FinancialIndicator.ts_code == latest_fin_subq.c.ts_code)
                & (FinancialIndicator.end_date == latest_fin_subq.c.max_end_date),
            )
            .outerjoin(DailyQuote, Stock.ts_code == DailyQuote.ts_code)
            .outerjoin(
                latest_daily_subq,
                (DailyQuote.ts_code == latest_daily_subq.c.ts_code)
                & (DailyQuote.trade_date == latest_daily_subq.c.max_trade_date),
            )
        )

        # 应用行业筛选
        if industry:
            query = query.filter(Stock.industry.like(f"%{industry}%"))

        # 应用市场筛选
        if market:
            query = query.filter(Stock.market.like(f"%{market}%"))

        # 应用筛选条件
        query = self._apply_conditions(query, conditions)

        # 统计总数
        total = query.count()

        # 应用排序
        if sort_by and sort_by in SORT_FIELD_MAP:
            order_col = SORT_FIELD_MAP[sort_by]
            if sort_order == "asc":
                query = query.order_by(asc(order_col))
            else:
                query = query.order_by(desc(order_col))
        else:
            # 默认按 ROE 降序
            query = query.order_by(desc(FinancialIndicator.roe))

        # 应用分页
        offset = (page - 1) * page_size
        rows = query.offset(offset).limit(page_size).all()

        # 构建结果列表
        result_list = []
        for row in rows:
            result_list.append({
                "ts_code": row.ts_code,
                "name": row.name,
                "industry": row.industry or "",
                "market": row.market or "",
                "pe": round(row.pe, 2) if row.pe is not None else None,
                "pb": round(row.pb, 2) if row.pb is not None else None,
                "roe": round(row.roe, 2) if row.roe is not None else None,
                "roa": round(row.roa, 2) if row.roa is not None else None,
                "gross_margin": round(row.gross_margin, 2) if row.gross_margin is not None else None,
                "net_margin": round(row.net_margin, 2) if row.net_margin is not None else None,
                "revenue_yoy": round(row.revenue_yoy, 2) if row.revenue_yoy is not None else None,
                "net_profit_yoy": round(row.net_profit_yoy, 2) if row.net_profit_yoy is not None else None,
                "close": round(row.close, 2) if row.close is not None else None,
                "pct_chg": round(row.pct_chg, 2) if row.pct_chg is not None else None,
            })

        return {
            "list": result_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _apply_conditions(self, query, conditions: List[Dict]):
        """应用筛选条件到查询对象

        Args:
            query: SQLAlchemy 查询对象
            conditions: 筛选条件列表

        Returns:
            添加了筛选条件的查询对象
        """
        for cond in conditions:
            field_name = cond.get("field", "")
            operator = cond.get("operator", "")
            value = cond.get("value")

            if field_name not in FIELD_MAP or FIELD_MAP[field_name] is None:
                logger.warning(f"跳过不支持的筛选字段: {field_name}")
                continue

            col = FIELD_MAP[field_name]

            if operator == ">":
                query = query.filter(col > value)
            elif operator == "<":
                query = query.filter(col < value)
            elif operator == ">=":
                query = query.filter(col >= value)
            elif operator == "<=":
                query = query.filter(col <= value)
            elif operator == "=":
                query = query.filter(col == value)
            elif operator == "!=":
                query = query.filter(col != value)
            else:
                logger.warning(f"跳过不支持的运算符: {operator}")

        return query
