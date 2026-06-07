"""数据落库服务

将数据源拉取的数据导入本地数据库，支持增量更新。
"""

import logging
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.stock import Stock
from app.models.daily import DailyQuote
from app.models.financial import FinancialIndicator

from .base import DataSourceBase
from .factory import get_data_source

logger = logging.getLogger(__name__)


class DataImportService:
    """数据落库服务"""

    def __init__(self, source: DataSourceBase = None):
        self.source = source or get_data_source()

    def import_stock_list(self) -> int:
        """导入股票列表到 stocks 表

        Returns:
            新增/更新的记录数
        """
        df = self.source.get_stock_list()
        if df.empty:
            logger.warning("股票列表为空，跳过导入")
            return 0

        db: Session = SessionLocal()
        count = 0
        try:
            for _, row in df.iterrows():
                ts_code = row.get("ts_code")
                if not ts_code:
                    continue

                existing = db.get(Stock, ts_code)
                if existing:
                    # 更新已有记录
                    existing.name = row.get("name", existing.name)
                    existing.symbol = row.get("symbol", existing.symbol)
                    existing.area = row.get("area", existing.area)
                    existing.industry = row.get("industry", existing.industry)
                    existing.market = row.get("market", existing.market)
                    list_date = row.get("list_date")
                    if list_date is not None:
                        existing.list_date = (
                            pd.Timestamp(list_date).date()
                            if not isinstance(list_date, date)
                            else list_date
                        )
                else:
                    # 新增记录
                    list_date = row.get("list_date")
                    stock = Stock(
                        ts_code=ts_code,
                        symbol=row.get("symbol", ""),
                        name=row.get("name", ""),
                        area=row.get("area"),
                        industry=row.get("industry"),
                        market=row.get("market"),
                        list_date=(
                            pd.Timestamp(list_date).date()
                            if list_date is not None and not isinstance(list_date, date)
                            else list_date
                        ),
                    )
                    db.add(stock)
                count += 1

            db.commit()
            logger.info(f"股票列表导入完成: {count} 条")
        except Exception as e:
            db.rollback()
            logger.error(f"股票列表导入失败: {e}")
            raise
        finally:
            db.close()

        return count

    def import_daily_quotes(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> int:
        """导入日线数据到 daily_quotes 表

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            新增的记录数
        """
        df = self.source.get_daily_quotes(ts_code, start_date, end_date)
        if df.empty:
            logger.warning(f"日线数据为空: {ts_code}")
            return 0

        db: Session = SessionLocal()
        count = 0
        try:
            for _, row in df.iterrows():
                trade_date = row.get("trade_date")
                if trade_date is not None and not isinstance(trade_date, date):
                    trade_date = pd.Timestamp(trade_date).date()

                # 检查是否已存在
                existing = db.execute(
                    select(DailyQuote).where(
                        DailyQuote.ts_code == ts_code,
                        DailyQuote.trade_date == trade_date,
                    )
                ).scalar_one_or_none()

                if existing:
                    continue  # 跳过已有数据

                quote = DailyQuote(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    open=row.get("open"),
                    high=row.get("high"),
                    low=row.get("low"),
                    close=row.get("close"),
                    pre_close=row.get("pre_close"),
                    change=row.get("change"),
                    pct_chg=row.get("pct_chg"),
                    vol=row.get("vol"),
                    amount=row.get("amount"),
                )
                db.add(quote)
                count += 1

            db.commit()
            logger.info(f"日线数据导入完成 {ts_code}: {count} 条新增")
        except Exception as e:
            db.rollback()
            logger.error(f"日线数据导入失败 {ts_code}: {e}")
            raise
        finally:
            db.close()

        return count

    def import_financial_indicators(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> int:
        """导入财务数据到 financial_indicators 表

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            新增的记录数
        """
        df = self.source.get_financial_indicators(ts_code, start_date, end_date)
        if df.empty:
            logger.warning(f"财务数据为空: {ts_code}")
            return 0

        db: Session = SessionLocal()
        count = 0
        try:
            for _, row in df.iterrows():
                end_date_val = row.get("end_date")
                if end_date_val is not None and not isinstance(end_date_val, date):
                    end_date_val = pd.Timestamp(end_date_val).date()

                # 检查是否已存在
                existing = db.execute(
                    select(FinancialIndicator).where(
                        FinancialIndicator.ts_code == ts_code,
                        FinancialIndicator.end_date == end_date_val,
                    )
                ).scalar_one_or_none()

                if existing:
                    # 更新已有记录
                    for field in [
                        "roe", "roa", "gross_margin", "net_margin",
                        "revenue_yoy", "net_profit_yoy", "pe", "pb", "ps",
                        "debt_ratio", "current_ratio", "eps", "bvps",
                    ]:
                        val = row.get(field)
                        if val is not None:
                            setattr(existing, field, val)
                    ann_date = row.get("ann_date")
                    if ann_date is not None:
                        existing.ann_date = (
                            pd.Timestamp(ann_date).date()
                            if not isinstance(ann_date, date)
                            else ann_date
                        )
                else:
                    ann_date = row.get("ann_date")
                    indicator = FinancialIndicator(
                        ts_code=ts_code,
                        ann_date=(
                            pd.Timestamp(ann_date).date()
                            if ann_date is not None and not isinstance(ann_date, date)
                            else ann_date
                        ),
                        end_date=end_date_val,
                        roe=row.get("roe"),
                        roa=row.get("roa"),
                        gross_margin=row.get("gross_margin"),
                        net_margin=row.get("net_margin"),
                        revenue_yoy=row.get("revenue_yoy"),
                        net_profit_yoy=row.get("net_profit_yoy"),
                        pe=row.get("pe"),
                        pb=row.get("pb"),
                        ps=row.get("ps"),
                        debt_ratio=row.get("debt_ratio"),
                        current_ratio=row.get("current_ratio"),
                        eps=row.get("eps"),
                        bvps=row.get("bvps"),
                    )
                    db.add(indicator)
                count += 1

            db.commit()
            logger.info(f"财务数据导入完成 {ts_code}: {count} 条")
        except Exception as e:
            db.rollback()
            logger.error(f"财务数据导入失败 {ts_code}: {e}")
            raise
        finally:
            db.close()

        return count
