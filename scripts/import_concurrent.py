"""并发数据导入（tinyshare）

并发导入：daily扩展至2年、moneyflow、income、balancesheet
"""
import sys, os, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from datetime import date, timedelta
import tinyshare as ts
import pandas as pd
from sqlalchemy import Column, String, Float, Date, Integer, UniqueConstraint, text
from app.core.database import SessionLocal, engine, Base
from app.models.stock import Stock
from app.models.daily import DailyQuote

TOKEN = 'ovL7T12Mct8o5nWWRM1h9W8S2x6PhQf3uXci67G1mbWv34na646MTSLU6d37ddd7'
WORKERS = 15

_local = threading.local()
def get_pro():
    if not hasattr(_local, 'pro'):
        _local.pro = ts.pro_api()
    return _local.pro


# === 模型定义 ===

class MoneyFlow(Base):
    __tablename__ = 'moneyflow'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    buy_sm_vol = Column(Float); buy_sm_amount = Column(Float)
    sell_sm_vol = Column(Float); sell_sm_amount = Column(Float)
    buy_md_vol = Column(Float); buy_md_amount = Column(Float)
    sell_md_vol = Column(Float); sell_md_amount = Column(Float)
    buy_lg_vol = Column(Float); buy_lg_amount = Column(Float)
    sell_lg_vol = Column(Float); sell_lg_amount = Column(Float)
    buy_elg_vol = Column(Float); buy_elg_amount = Column(Float)
    sell_elg_vol = Column(Float); sell_elg_amount = Column(Float)
    net_mf_vol = Column(Float); net_mf_amount = Column(Float)
    __table_args__ = (UniqueConstraint('ts_code', 'trade_date', name='uix_moneyflow'),)

class Income(Base):
    __tablename__ = 'income'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, index=True)
    ann_date = Column(Date); end_date = Column(Date, index=True)
    revenue = Column(Float); n_income = Column(Float); n_income_attr_p = Column(Float)
    operate_profit = Column(Float); ebit = Column(Float)
    basic_eps = Column(Float); diluted_eps = Column(Float)
    __table_args__ = (UniqueConstraint('ts_code', 'end_date', name='uix_income'),)

class BalanceSheet(Base):
    __tablename__ = 'balancesheet'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, index=True)
    ann_date = Column(Date); end_date = Column(Date, index=True)
    total_assets = Column(Float); total_liab = Column(Float); total_hldr_eqy = Column(Float)
    total_cur_assets = Column(Float); total_cur_liab = Column(Float)
    total_ncl = Column(Float); money_cap = Column(Float)
    __table_args__ = (UniqueConstraint('ts_code', 'end_date', name='uix_balancesheet'),)


def ensure_tables():
    Base.metadata.create_all(engine)
    print("表结构已就绪")


# === 并发导入函数 ===

def fetch_daily_stock(ts_code, start_date, end_date):
    """获取单只股票日线"""
    pro = get_pro()
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    return ts_code, df

def save_daily_batch(results):
    session = SessionLocal()
    saved = 0
    try:
        for ts_code, df in results:
            if df is None or df.empty: continue
            for _, row in df.iterrows():
                td = pd.Timestamp(row['trade_date']).date()
                existing = session.query(DailyQuote).filter(
                    DailyQuote.ts_code == ts_code, DailyQuote.trade_date == td).first()
                if existing: continue
                session.add(DailyQuote(
                    ts_code=ts_code, trade_date=td,
                    open=row.get('open'), high=row.get('high'), low=row.get('low'),
                    close=row.get('close'), pre_close=row.get('pre_close'),
                    change=row.get('change'), pct_chg=row.get('pct_chg'),
                    vol=row.get('vol'), amount=row.get('amount'),
                ))
                saved += 1
        session.commit()
    except: session.rollback()
    finally: session.close()
    return saved

def import_daily_extend(start_date, end_date):
    """并发扩展日线数据"""
    session = SessionLocal()
    existing_codes = set(s[0] for s in session.query(DailyQuote.ts_code).distinct().all())
    all_codes = [s.ts_code for s in session.query(Stock.ts_code).filter(Stock.market.like('%主板%')).all()]
    codes = [c for c in all_codes if c not in existing_codes]
    # 也补充已有数据的时间范围
    codes_with_data = [c for c in all_codes if c in existing_codes]
    session.close()

    sd = start_date.strftime('%Y%m%d')
    ed = end_date.strftime('%Y%m%d')

    # 先补充新股票
    targets = codes + codes_with_data
    print(f"日线扩展: {len(targets)} 只股票, {start_date} ~ {end_date}")

    batch = []
    done = 0
    total_saved = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(fetch_daily_stock, c, sd, ed): c for c in targets}
        for future in as_completed(futures):
            try:
                result = future.result()
                batch.append(result)
            except: pass
            if len(batch) >= 200:
                total_saved += save_daily_batch(batch)
                batch = []
                done += 200
                if done % 1000 == 0:
                    print(f"  [{done}/{len(targets)}] 已保存 {total_saved} 条")
    if batch:
        total_saved += save_daily_batch(batch)
    print(f"日线扩展完成: {total_saved} 条新增")


def fetch_moneyflow(ts_code, start_date, end_date):
    pro = get_pro()
    df = pro.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)
    return ts_code, df

def save_moneyflow_batch(results):
    session = SessionLocal()
    saved = 0
    try:
        for ts_code, df in results:
            if df is None or df.empty: continue
            for _, row in df.iterrows():
                td = pd.Timestamp(row['trade_date']).date()
                existing = session.query(MoneyFlow).filter(
                    MoneyFlow.ts_code == ts_code, MoneyFlow.trade_date == td).first()
                if existing: continue
                session.add(MoneyFlow(
                    ts_code=ts_code, trade_date=td,
                    buy_sm_vol=row.get('buy_sm_vol'), buy_sm_amount=row.get('buy_sm_amount'),
                    sell_sm_vol=row.get('sell_sm_vol'), sell_sm_amount=row.get('sell_sm_amount'),
                    buy_md_vol=row.get('buy_md_vol'), buy_md_amount=row.get('buy_md_amount'),
                    sell_md_vol=row.get('sell_md_vol'), sell_md_amount=row.get('sell_md_amount'),
                    buy_lg_vol=row.get('buy_lg_vol'), buy_lg_amount=row.get('buy_lg_amount'),
                    sell_lg_vol=row.get('sell_lg_vol'), sell_lg_amount=row.get('sell_lg_amount'),
                    buy_elg_vol=row.get('buy_elg_vol'), buy_elg_amount=row.get('buy_elg_amount'),
                    sell_elg_vol=row.get('sell_elg_vol'), sell_elg_amount=row.get('sell_elg_amount'),
                    net_mf_vol=row.get('net_mf_vol'), net_mf_amount=row.get('net_mf_amount'),
                ))
                saved += 1
        session.commit()
    except: session.rollback()
    finally: session.close()
    return saved

def import_moneyflow(start_date, end_date):
    session = SessionLocal()
    codes = [s.ts_code for s in session.query(Stock.ts_code).filter(Stock.market.like('%主板%')).all()]
    session.close()

    sd = start_date.strftime('%Y%m%d')
    ed = end_date.strftime('%Y%m%d')
    print(f"资金流向: {len(codes)} 只股票, {start_date} ~ {end_date}")

    batch = []
    done = 0
    total_saved = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(fetch_moneyflow, c, sd, ed): c for c in codes}
        for future in as_completed(futures):
            try:
                result = future.result()
                batch.append(result)
            except: pass
            if len(batch) >= 200:
                total_saved += save_moneyflow_batch(batch)
                batch = []
                done += 200
                if done % 1000 == 0:
                    print(f"  [{done}/{len(codes)}] 已保存 {total_saved} 条")
    if batch:
        total_saved += save_moneyflow_batch(batch)
    print(f"资金流向完成: {total_saved} 条")


def fetch_financial(ts_code, api_name):
    pro = get_pro()
    if api_name == 'income':
        df = pro.income(ts_code=ts_code, start_date='20240101', end_date='20260609',
                       fields='ts_code,ann_date,end_date,revenue,n_income,n_income_attr_p,operate_profit,ebit,basic_eps,diluted_eps')
    else:
        df = pro.balancesheet(ts_code=ts_code, start_date='20240101', end_date='20260609',
                             fields='ts_code,ann_date,end_date,total_assets,total_liab,total_hldr_eqy,total_cur_assets,total_cur_liab,total_ncl,money_cap')
    return ts_code, df

def save_financial_batch(results, model_cls, session_maker):
    session = SessionLocal()
    saved = 0
    try:
        for ts_code, df in results:
            if df is None or df.empty: continue
            for _, row in df.iterrows():
                ed = row.get('end_date')
                ed_val = pd.Timestamp(ed).date() if ed else None
                if not ed_val: continue
                existing = session.query(model_cls).filter(
                    model_cls.ts_code == ts_code, model_cls.end_date == ed_val).first()
                if existing: continue
                ann = row.get('ann_date')
                ann_val = pd.Timestamp(ann).date() if ann else None

                if model_cls == Income:
                    session.add(Income(
                        ts_code=ts_code, ann_date=ann_val, end_date=ed_val,
                        revenue=row.get('revenue'), n_income=row.get('n_income'),
                        n_income_attr_p=row.get('n_income_attr_p'),
                        operate_profit=row.get('operate_profit'), ebit=row.get('ebit'),
                        basic_eps=row.get('basic_eps'), diluted_eps=row.get('diluted_eps'),
                    ))
                else:
                    session.add(BalanceSheet(
                        ts_code=ts_code, ann_date=ann_val, end_date=ed_val,
                        total_assets=row.get('total_assets'), total_liab=row.get('total_liab'),
                        total_hldr_eqy=row.get('total_hldr_eqy'),
                        total_cur_assets=row.get('total_cur_assets'), total_cur_liab=row.get('total_cur_liab'),
                        total_ncl=row.get('total_ncl'), money_cap=row.get('money_cap'),
                    ))
                saved += 1
        session.commit()
    except: session.rollback()
    finally: session.close()
    return saved

def import_financial_statements(api_name, model_cls):
    session = SessionLocal()
    codes = [s.ts_code for s in session.query(Stock.ts_code).all()]
    session.close()

    print(f"{api_name}: {len(codes)} 只股票")
    batch = []
    done = 0
    total_saved = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(fetch_financial, c, api_name): c for c in codes}
        for future in as_completed(futures):
            try:
                result = future.result()
                batch.append(result)
            except: pass
            if len(batch) >= 200:
                total_saved += save_financial_batch(batch, model_cls, SessionLocal)
                batch = []
                done += 200
                if done % 1000 == 0:
                    print(f"  [{done}/{len(codes)}] 已保存 {total_saved} 条")
    if batch:
        total_saved += save_financial_batch(batch, model_cls, SessionLocal)
    print(f"{api_name}完成: {total_saved} 条")


def main():
    print("并发数据导入")
    print("=" * 60)

    ts.set_token(TOKEN)
    ensure_tables()

    end_date = date.today()
    daily_start = end_date - timedelta(days=730)  # 2年
    flow_start = end_date - timedelta(days=90)     # 资金流向90天

    import_daily_extend(daily_start, end_date)
    import_moneyflow(flow_start, end_date)
    import_financial_statements('income', Income)
    import_financial_statements('balancesheet', BalanceSheet)

    print("\n全部导入完成！")

if __name__ == "__main__":
    main()
