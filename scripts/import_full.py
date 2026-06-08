"""全量数据导入脚本（tinyshare 并发版）

使用 tinyshare（Tushare 兼容）并发导入股票列表、财务指标、日线行情。
支持断点续传：跳过已有完整数据的股票。
"""
import sys
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from datetime import date, timedelta
import tinyshare as ts
import pandas as pd
from app.core.database import SessionLocal, engine, Base
from app.models.stock import Stock
from app.models.daily import DailyQuote
from app.models.financial import FinancialIndicator

TOKEN = 'ovL7T12Mct8o5nWWRM1h9W8S2x6PhQf3uXci67G1mbWv34na646MTSLU6d37ddd7'
WORKERS = 20  # 并发线程数

# 每个线程需要独立的 tushare pro 实例
_local = threading.local()


def get_pro():
    """获取线程独立的 pro 实例"""
    if not hasattr(_local, 'pro'):
        _local.pro = ts.pro_api()
    return _local.pro


def ensure_tables():
    Base.metadata.create_all(engine)
    print("数据库表已就绪")


def import_stock_list(session):
    """导入股票列表"""
    print("=" * 50)
    print("1. 导入股票列表...")
    pro = get_pro()
    df = pro.stock_basic(
        exchange='', list_status='L',
        fields='ts_code,symbol,name,area,industry,market,list_date'
    )
    count = 0
    for _, row in df.iterrows():
        ts_code = row['ts_code']
        existing = session.get(Stock, ts_code)
        if existing:
            existing.name = row.get('name', existing.name)
            existing.symbol = row.get('symbol', existing.symbol)
            existing.area = row.get('area', existing.area)
            existing.industry = row.get('industry', existing.industry)
            existing.market = row.get('market', existing.market)
            ld = row.get('list_date')
            if ld:
                existing.list_date = pd.Timestamp(ld).date()
        else:
            ld = row.get('list_date')
            session.add(Stock(
                ts_code=ts_code, symbol=row.get('symbol', ''),
                name=row.get('name', ''), area=row.get('area'),
                industry=row.get('industry'), market=row.get('market'),
                list_date=pd.Timestamp(ld).date() if ld else None,
            ))
        count += 1
    session.commit()
    print(f"   股票列表: {count} 条")


def _fetch_financial(ts_code, start_date, end_date):
    """获取单只股票的财务数据（API 调用）"""
    pro = get_pro()
    df_fin = pro.fina_indicator(
        ts_code=ts_code, start_date=start_date, end_date=end_date,
        fields='ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets,current_ratio,eps,bps'
    )
    df_val = pro.daily_basic(
        ts_code=ts_code, start_date=start_date, end_date=end_date,
        fields='ts_code,trade_date,pe,pb,ps'
    )
    pe = pb = ps = None
    if df_val is not None and not df_val.empty:
        pe = df_val.iloc[0].get("pe")
        pb = df_val.iloc[0].get("pb")
        ps = df_val.iloc[0].get("ps")
    return ts_code, df_fin, pe, pb, ps


def _save_financial_batch(results):
    """批量保存财务数据到数据库"""
    session = SessionLocal()
    saved = 0
    try:
        for ts_code, df_fin, pe, pb, ps in results:
            if df_fin is None or df_fin.empty:
                continue
            for _, row in df_fin.iterrows():
                ed = row.get("end_date")
                ed_val = pd.Timestamp(ed).date() if ed else None
                existing = session.query(FinancialIndicator).filter(
                    FinancialIndicator.ts_code == ts_code,
                    FinancialIndicator.end_date == ed_val,
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
                    existing.pe = pe; existing.pb = pb; existing.ps = ps
                else:
                    session.add(FinancialIndicator(
                        ts_code=ts_code, end_date=ed_val,
                        roe=row.get("roe"), roa=row.get("roa"),
                        gross_margin=row.get("grossprofit_margin"),
                        net_margin=row.get("netprofit_margin"),
                        debt_ratio=row.get("debt_to_assets"),
                        current_ratio=row.get("current_ratio"),
                        eps=row.get("eps"), bvps=row.get("bps"),
                        pe=pe, pb=pb, ps=ps,
                    ))
                saved += 1
        session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()
    return saved


def import_financial_data(ts_codes, start_date, end_date):
    """并发导入财务指标"""
    print("=" * 50)
    print(f"2. 导入财务指标（{len(ts_codes)} 只，{WORKERS} 并发）...")
    sd = start_date.strftime("%Y%m%d")
    ed = end_date.strftime("%Y%m%d")

    batch = []
    done = 0
    total_saved = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(_fetch_financial, code, sd, ed): code
            for code in ts_codes
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                batch.append(result)
            except Exception:
                pass

            # 每 100 只批量写入
            if len(batch) >= 100:
                total_saved += _save_financial_batch(batch)
                batch = []
                done += 100
                print(f"   [{done}/{len(ts_codes)}] 已完成...")

    if batch:
        total_saved += _save_financial_batch(batch)

    print(f"   财务指标导入完成: {total_saved} 条记录")


def _fetch_daily(ts_code, start_date, end_date):
    """获取单只股票的日线数据"""
    pro = get_pro()
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    return ts_code, df


def _save_daily_batch(results):
    """批量保存日线数据"""
    session = SessionLocal()
    saved = 0
    try:
        for ts_code, df in results:
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                td = row.get("trade_date")
                td_val = pd.Timestamp(td).date() if td else None
                existing = session.query(DailyQuote).filter(
                    DailyQuote.ts_code == ts_code,
                    DailyQuote.trade_date == td_val,
                ).first()
                if existing:
                    continue
                session.add(DailyQuote(
                    ts_code=ts_code, trade_date=td_val,
                    open=row.get("open"), high=row.get("high"),
                    low=row.get("low"), close=row.get("close"),
                    pre_close=row.get("pre_close"), change=row.get("change"),
                    pct_chg=row.get("pct_chg"), vol=row.get("vol"),
                    amount=row.get("amount"),
                ))
                saved += 1
        session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()
    return saved


def import_daily_quotes(ts_codes, start_date, end_date):
    """并发导入日线行情"""
    print("=" * 50)
    print(f"3. 导入日线行情（{len(ts_codes)} 只，{WORKERS} 并发）...")
    sd = start_date.strftime("%Y%m%d")
    ed = end_date.strftime("%Y%m%d")

    batch = []
    done = 0
    total_saved = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(_fetch_daily, code, sd, ed): code
            for code in ts_codes
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                batch.append(result)
            except Exception:
                pass

            if len(batch) >= 100:
                total_saved += _save_daily_batch(batch)
                batch = []
                done += 100
                print(f"   [{done}/{len(ts_codes)}] 已完成...")

    if batch:
        total_saved += _save_daily_batch(batch)

    print(f"   日线导入完成: {total_saved} 条记录")


def show_stats(session):
    """显示统计"""
    print("=" * 50)
    print("数据库统计:")
    print(f"   股票数量: {session.query(Stock).count()}")
    print(f"   财务记录: {session.query(FinancialIndicator).count()}")
    print(f"   日线记录: {session.query(DailyQuote).count()}")

    print("\n筛选测试: PE<20 & ROE>10%")
    results = (
        session.query(Stock.ts_code, Stock.name, Stock.industry,
                      FinancialIndicator.roe, FinancialIndicator.pe)
        .join(FinancialIndicator)
        .filter(FinancialIndicator.pe.isnot(None), FinancialIndicator.roe.isnot(None))
        .filter(FinancialIndicator.pe < 20, FinancialIndicator.roe > 10)
        .order_by(FinancialIndicator.roe.desc())
        .limit(10).all()
    )
    print(f"   结果: {len(results)} 条")
    for r in results:
        pe_str = f"{r.pe:.2f}" if r.pe else "N/A"
        print(f"   {r.ts_code} {r.name:8s} {r.industry or '':8s} ROE={r.roe:.2f}% PE={pe_str}")


def main():
    print("全量数据导入（tinyshare 并发版）")
    print("=" * 50)

    ts.set_token(TOKEN)
    session = SessionLocal()

    ensure_tables()
    import_stock_list(session)

    # 断点续传：获取需要导入的股票代码
    end_date = date.today()
    fin_start = date(2025, 1, 1)
    daily_start = end_date - timedelta(days=90)

    # 财务数据：跳过已有 PE 数据的股票
    fin_done = set(s[0] for s in session.query(FinancialIndicator.ts_code)
                   .filter(FinancialIndicator.pe.isnot(None)).distinct().all())
    all_codes = [s.ts_code for s in session.query(Stock.ts_code).all()]
    fin_codes = [c for c in all_codes if c not in fin_done]
    print(f"   财务数据: 已有 {len(fin_done)} 只，待导入 {len(fin_codes)} 只")

    # 日线数据：跳过已有最近数据的股票
    daily_done = set(s[0] for s in session.query(DailyQuote.ts_code)
                     .filter(DailyQuote.trade_date >= daily_start).distinct().all())
    daily_codes = [c for c in all_codes if c not in daily_done]
    print(f"   日线数据: 已有 {len(daily_done)} 只，待导入 {len(daily_codes)} 只")

    session.close()

    if fin_codes:
        import_financial_data(fin_codes, fin_start, end_date)

    if daily_codes:
        import_daily_quotes(daily_codes, daily_start, end_date)

    session = SessionLocal()
    show_stats(session)
    session.close()

    print("\n导入完成！")


if __name__ == "__main__":
    main()
