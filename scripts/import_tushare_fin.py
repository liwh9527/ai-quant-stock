"""Tushare 财务数据导入脚本

使用 Tushare 的 fina_indicator 和 daily_basic 接口导入财务指标和估值数据。
这两个接口与 stock_basic 频率限制不同，可以正常使用。
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from datetime import date
import tushare as ts
import pandas as pd
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.stock import Stock
from app.models.financial import FinancialIndicator


def import_financial_data(pro, session, ts_code, start_date, end_date):
    """导入单只股票的财务指标"""
    try:
        # 财务指标（ROE/ROA/毛利率等）
        df_fin = pro.fina_indicator(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            fields='ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets,current_ratio,eps,bps'
        )

        # 最新估值（PE/PB/PS）
        df_val = pro.daily_basic(
            ts_code=ts_code,
            start_date=end_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            fields='ts_code,pe,pb,ps'
        )

        pe = pb = ps = None
        if df_val is not None and not df_val.empty:
            pe = df_val.iloc[0].get("pe")
            pb = df_val.iloc[0].get("pb")
            ps = df_val.iloc[0].get("ps")

        if df_fin is None or df_fin.empty:
            return 0

        count = 0
        for _, row in df_fin.iterrows():
            end_date_val = row.get("end_date")
            if end_date_val:
                end_date_val = pd.Timestamp(end_date_val).date()

            # 检查是否已存在
            existing = session.query(FinancialIndicator).filter(
                FinancialIndicator.ts_code == ts_code,
                FinancialIndicator.end_date == end_date_val,
            ).first()

            if existing:
                existing.roe = row.get("roe")
                existing.roa = row.get("roa")
                existing.gross_margin = row.get("grossprofit_margin")
                existing.net_margin = row.get("netprofit_margin")
                existing.debt_ratio = row.get("debt_to_assets")
                existing.current_ratio = row.get("current_ratio")
                existing.eps = row.get("eps")
                existing.bvps = row.get("bps")
                existing.pe = pe
                existing.pb = pb
                existing.ps = ps
            else:
                indicator = FinancialIndicator(
                    ts_code=ts_code,
                    end_date=end_date_val,
                    roe=row.get("roe"),
                    roa=row.get("roa"),
                    gross_margin=row.get("grossprofit_margin"),
                    net_margin=row.get("netprofit_margin"),
                    debt_ratio=row.get("debt_to_assets"),
                    current_ratio=row.get("current_ratio"),
                    eps=row.get("eps"),
                    bvps=row.get("bps"),
                    pe=pe,
                    pb=pb,
                    ps=ps,
                )
                session.add(indicator)
            count += 1

        session.commit()
        return count

    except Exception as e:
        session.rollback()
        return 0


def main():
    print("Tushare 财务数据导入")
    print("=" * 50)

    ts.set_token(settings.TUSHARE_TOKEN)
    pro = ts.pro_api()
    session = SessionLocal()

    start_date = date(2025, 1, 1)
    end_date = date.today()

    # 获取数据库中的股票列表
    stocks = session.query(Stock).limit(100).all()
    print(f"待导入: {len(stocks)} 只股票")

    success = 0
    fail = 0
    for i, stock in enumerate(stocks):
        count = import_financial_data(pro, session, stock.ts_code, start_date, end_date)
        if count > 0:
            success += 1
            print(f"  [{i+1}/{len(stocks)}] {stock.ts_code} {stock.name}: {count} 条")
        else:
            fail += 1
        time.sleep(0.3)  # 控制频率

    print(f"\n导入完成: {success} 成功, {fail} 失败")

    # 统计
    fin_count = session.query(FinancialIndicator).count()
    print(f"财务记录总数: {fin_count}")

    # 测试筛选
    results = (
        session.query(Stock.ts_code, Stock.name, FinancialIndicator.roe, FinancialIndicator.pe)
        .join(FinancialIndicator)
        .filter(FinancialIndicator.pe < 20, FinancialIndicator.roe > 5)
        .limit(5)
        .all()
    )
    print(f"\n筛选 PE<20 & ROE>5: {len(results)} 条")
    for r in results:
        print(f"  {r.ts_code} {r.name} PE={r.pe:.2f} ROE={r.roe:.2f}%")

    session.close()


if __name__ == "__main__":
    main()
