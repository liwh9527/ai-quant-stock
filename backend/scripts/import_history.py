"""批量导入 5 年历史数据

使用 Tushare 代理 API，限速 100次/分钟。
按日期批量获取（一天全市场），效率最高。

用法:
    cd backend
    python -m scripts.import_history              # 导入全部
    python -m scripts.import_history --only daily  # 只导日线
    python -m scripts.import_history --only basic  # 只导每日指标
    python -m scripts.import_history --only fina   # 只导财务指标
    python -m scripts.import_history --only index  # 只导指数日线
    python -m scripts.import_history --years 3     # 只导 3 年
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, date
from typing import List

import pandas as pd
import tushare as ts

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import SessionLocal, engine, Base
from app.models.stock import Stock
from app.models.daily import DailyQuote
from app.models.daily_basic import DailyBasic
from app.models.financial import FinancialIndicator
from app.models.index_daily import IndexDaily

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 确保表存在
Base.metadata.create_all(bind=engine)

# ========== 配置 ==========
API_URL = settings.TUSHARE_API_URL
TOKEN = settings.TUSHARE_TOKEN
REQUEST_INTERVAL = 0.65  # 秒，确保不超过 100次/分钟
MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒

# 基准指数列表
BENCHMARK_INDEXES = [
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "000300.SH",  # 沪深300
    "000905.SH",  # 中证500
    "399006.SZ",  # 创业板指
]


class RateLimiter:
    """限速器"""

    def __init__(self, interval: float = REQUEST_INTERVAL):
        self.interval = interval
        self.last_call = 0

    def wait(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_call = time.time()


limiter = RateLimiter()


def get_pro():
    """获取 tushare pro api 实例"""
    ts.set_token(TOKEN)
    pro = ts.pro_api()
    if API_URL:
        pro._DataApi__http_url = API_URL
    return pro


def call_api(func, retries=MAX_RETRIES, **kwargs):
    """带重试的 API 调用"""
    for attempt in range(retries):
        try:
            limiter.wait()
            return func(**kwargs)
        except Exception as e:
            err_msg = str(e)
            if "exceed" in err_msg or "freq" in err_msg or "每分钟" in err_msg:
                logger.warning(f"触发限速，等待 {RETRY_DELAY}s 后重试 ({attempt+1}/{retries})")
                time.sleep(RETRY_DELAY)
            elif attempt < retries - 1:
                logger.warning(f"API 调用失败: {e}，重试 ({attempt+1}/{retries})")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"API 调用失败: {e}")
                raise
    return None


def get_trade_dates(start: str, end: str) -> List[str]:
    """获取交易日列表"""
    pro = get_pro()
    df = call_api(pro.trade_cal, exchange="SSE", start_date=start, end_date=end)
    if df is None or df.empty:
        return []
    dates = df[df["is_open"] == 1]["cal_date"].tolist()
    return sorted(dates)


# ========== 1. 股票列表 ==========

def import_stock_list():
    """更新股票列表"""
    logger.info("=" * 50)
    logger.info("更新股票列表")
    pro = get_pro()
    df = call_api(
        pro.stock_basic,
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,market,list_date",
    )
    if df is None or df.empty:
        logger.error("获取股票列表失败")
        return

    db = SessionLocal()
    count = 0
    try:
        for _, row in df.iterrows():
            ts_code = row["ts_code"]
            existing = db.get(Stock, ts_code)
            if existing:
                existing.name = row.get("name", existing.name)
                existing.industry = row.get("industry", existing.industry)
                existing.market = row.get("market", existing.market)
            else:
                stock = Stock(
                    ts_code=ts_code,
                    symbol=row.get("symbol", ""),
                    name=row.get("name", ""),
                    area=row.get("area"),
                    industry=row.get("industry"),
                    market=row.get("market"),
                    list_date=pd.Timestamp(row.get("list_date")).date() if row.get("list_date") else None,
                )
                db.add(stock)
            count += 1
        db.commit()
        logger.info(f"股票列表更新完成: {count} 条")
    except Exception as e:
        db.rollback()
        logger.error(f"股票列表更新失败: {e}")
    finally:
        db.close()


# ========== 2. 日线行情（按日期批量） ==========

def import_daily_quotes(years: int = 5):
    """按日期批量导入日线行情（原生 SQL bulk insert，极速）"""
    logger.info("=" * 50)
    logger.info(f"导入日线行情（近 {years} 年）")

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")

    trade_dates = get_trade_dates(start, end)
    logger.info(f"交易日范围: {trade_dates[0]} ~ {trade_dates[-1]}，共 {len(trade_dates)} 天")

    conn = engine.raw_connection()
    cur = conn.cursor()
    pro = get_pro()
    total_new = 0

    try:
        for i, td in enumerate(trade_dates):
            # 批量查出该日期已有的 ts_code
            cur.execute(
                "SELECT ts_code FROM daily_quotes WHERE trade_date = ?",
                (td[:4]+"-"+td[4:6]+"-"+td[6:],)
            )
            existing_codes = set(r[0] for r in cur.fetchall())
            if len(existing_codes) > 100:
                continue

            df = call_api(pro.daily, trade_date=td)
            if df is None or df.empty:
                continue

            # 构建批量插入数据
            rows = []
            for _, row in df.iterrows():
                ts_code = row["ts_code"]
                if ts_code in existing_codes:
                    continue
                trade_dt = pd.Timestamp(row["trade_date"]).date()
                rows.append((
                    ts_code, trade_dt.isoformat(),
                    row.get("open"), row.get("high"), row.get("low"),
                    row.get("close"), row.get("pre_close"),
                    row.get("change"), row.get("pct_chg"),
                    row.get("vol"), row.get("amount"),
                ))

            if rows:
                cur.executemany(
                    "INSERT OR IGNORE INTO daily_quotes "
                    "(ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows
                )
                conn.commit()
                total_new += len(rows)

            if (i + 1) % 50 == 0:
                logger.info(f"  进度: {i+1}/{len(trade_dates)} 天，累计新增 {total_new} 条")

        logger.info(f"日线行情导入完成，累计新增 {total_new} 条")
    except Exception as e:
        conn.rollback()
        logger.error(f"日线行情导入失败: {e}")
    finally:
        cur.close()
        conn.close()


# ========== 3. 每日指标（按日期批量） ==========

def import_daily_basic(years: int = 5):
    """按日期批量导入每日估值指标（原生 SQL bulk insert，极速）"""
    logger.info("=" * 50)
    logger.info(f"导入每日指标（近 {years} 年）")

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")

    trade_dates = get_trade_dates(start, end)
    logger.info(f"交易日范围: {trade_dates[0]} ~ {trade_dates[-1]}，共 {len(trade_dates)} 天")

    conn = engine.raw_connection()
    cur = conn.cursor()
    pro = get_pro()
    total_new = 0

    try:
        for i, td in enumerate(trade_dates):
            cur.execute(
                "SELECT ts_code FROM daily_basic WHERE trade_date = ?",
                (td[:4]+"-"+td[4:6]+"-"+td[6:],)
            )
            existing_codes = set(r[0] for r in cur.fetchall())
            if len(existing_codes) > 100:
                continue

            df = call_api(pro.daily_basic, trade_date=td)
            if df is None or df.empty:
                continue

            rows = []
            for _, row in df.iterrows():
                ts_code = row["ts_code"]
                if ts_code in existing_codes:
                    continue
                trade_dt = pd.Timestamp(row["trade_date"]).date()
                rows.append((
                    ts_code, trade_dt.isoformat(),
                    row.get("turnover_rate"), row.get("turnover_rate_f"),
                    row.get("total_mv"), row.get("circ_mv"),
                    row.get("pe"), row.get("pb"), row.get("ps"),
                ))

            if rows:
                cur.executemany(
                    "INSERT OR IGNORE INTO daily_basic "
                    "(ts_code, trade_date, turnover_rate, turnover_rate_f, total_mv, circ_mv, pe, pb, ps) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows
                )
                conn.commit()
                total_new += len(rows)

            if (i + 1) % 50 == 0:
                logger.info(f"  进度: {i+1}/{len(trade_dates)} 天，累计新增 {total_new} 条")

        logger.info(f"每日指标导入完成，累计新增 {total_new} 条")
    except Exception as e:
        conn.rollback()
        logger.error(f"每日指标导入失败: {e}")
    finally:
        cur.close()
        conn.close()


# ========== 4. 财务指标（按股票逐只） ==========

def import_financial_indicators(years: int = 5):
    """逐只股票导入财务指标（原生 SQL，REPLACE 处理冲突）"""
    logger.info("=" * 50)
    logger.info(f"导入财务指标（近 {years} 年）")

    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")

    conn = engine.raw_connection()
    cur = conn.cursor()
    pro = get_pro()

    # 获取所有股票列表
    cur.execute("SELECT ts_code FROM stocks")
    stock_codes = [r[0] for r in cur.fetchall()]
    logger.info(f"共 {len(stock_codes)} 只股票需要导入财务数据")

    total_new = 0

    try:
        for i, ts_code in enumerate(stock_codes):
            # 检查是否已有近期数据
            cur.execute(
                "SELECT MAX(end_date) FROM financial_indicators WHERE ts_code = ?",
                (ts_code,)
            )
            row = cur.fetchone()
            if row and row[0]:
                latest_end = datetime.strptime(str(row[0]), "%Y-%m-%d").date() if isinstance(row[0], str) else row[0]
                if latest_end > (datetime.now() - timedelta(days=400)).date():
                    continue

            df = call_api(
                pro.fina_indicator,
                ts_code=ts_code,
                start_date=start,
                end_date=end,
                fields=(
                    "ts_code,ann_date,end_date,roe,roe_waa,roa,"
                    "grossprofit_margin,netprofit_margin,"
                    "revenue_yoy,net_profit_yoy,pe_ttm,pb,ps_ttm,"
                    "debt_to_assets,current_ratio,eps,bps"
                ),
            )
            if df is None or df.empty:
                continue

            rows = []
            for _, r in df.iterrows():
                end_date_val = pd.Timestamp(r["end_date"]).date() if r.get("end_date") else None
                if not end_date_val:
                    continue
                ann_date_val = pd.Timestamp(r["ann_date"]).date() if r.get("ann_date") else None
                rows.append((
                    ts_code,
                    ann_date_val.isoformat() if ann_date_val else None,
                    end_date_val.isoformat(),
                    r.get("roe_waa"), r.get("roa"),
                    r.get("grossprofit_margin"), r.get("netprofit_margin"),
                    r.get("revenue_yoy"), r.get("net_profit_yoy"),
                    r.get("pe_ttm"), r.get("pb"), r.get("ps_ttm"),
                    r.get("debt_to_assets"), r.get("current_ratio"),
                    r.get("eps"), r.get("bps"),
                ))

            if rows:
                cur.executemany(
                    "INSERT OR REPLACE INTO financial_indicators "
                    "(ts_code, ann_date, end_date, roe, roa, gross_margin, net_margin, "
                    "revenue_yoy, net_profit_yoy, pe, pb, ps, debt_ratio, current_ratio, eps, bvps) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows
                )
                conn.commit()
                total_new += len(rows)

            if (i + 1) % 100 == 0:
                logger.info(f"  进度: {i+1}/{len(stock_codes)} 只，累计新增 {total_new} 条")

        logger.info(f"财务指标导入完成，累计新增 {total_new} 条")
    except Exception as e:
        conn.rollback()
        logger.error(f"财务指标导入失败: {e}")
    finally:
        cur.close()
        conn.close()


# ========== 5. 指数日线 ==========

def import_index_daily(years: int = 5):
    """导入基准指数日线（原生 SQL）"""
    logger.info("=" * 50)
    logger.info(f"导入指数日线（近 {years} 年）")

    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")

    conn = engine.raw_connection()
    cur = conn.cursor()
    pro = get_pro()
    total_new = 0

    try:
        for idx_code in BENCHMARK_INDEXES:
            cur.execute("SELECT trade_date FROM index_daily WHERE ts_code = ?", (idx_code,))
            existing_dates = set(str(r[0]) for r in cur.fetchall())

            df = call_api(
                pro.index_daily,
                ts_code=idx_code,
                start_date=start,
                end_date=end,
            )
            if df is None or df.empty:
                continue

            rows = []
            for _, row in df.iterrows():
                trade_dt = pd.Timestamp(row["trade_date"]).date()
                if trade_dt.isoformat() in existing_dates:
                    continue
                rows.append((
                    idx_code, trade_dt.isoformat(),
                    row.get("open"), row.get("high"), row.get("low"),
                    row.get("close"), row.get("vol"), row.get("amount"),
                    row.get("pct_chg"),
                ))

            if rows:
                cur.executemany(
                    "INSERT OR IGNORE INTO index_daily "
                    "(ts_code, trade_date, open, high, low, close, vol, amount, pct_chg) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows
                )
                conn.commit()
                total_new += len(rows)
                logger.info(f"  {idx_code}: 新增 {len(rows)} 条")

        logger.info(f"指数日线导入完成，累计新增 {total_new} 条")
    except Exception as e:
        conn.rollback()
        logger.error(f"指数日线导入失败: {e}")
    finally:
        cur.close()
        conn.close()


# ========== 主入口 ==========

def main():
    parser = argparse.ArgumentParser(description="批量导入 5 年历史数据")
    parser.add_argument("--only", choices=["stock", "daily", "basic", "fina", "index"],
                        help="只导入指定类型")
    parser.add_argument("--years", type=int, default=5, help="导入年数（默认5）")
    args = parser.parse_args()

    years = args.years
    logger.info(f"开始导入 {years} 年历史数据")
    logger.info(f"API: {API_URL or '官方'}")
    logger.info(f"限速: {REQUEST_INTERVAL}s/次（约 {int(60/REQUEST_INTERVAL)} 次/分钟）")
    start_time = time.time()

    if args.only:
        tasks = {args.only}
    else:
        tasks = {"stock", "daily", "basic", "fina", "index"}

    if "stock" in tasks:
        import_stock_list()
    if "daily" in tasks:
        import_daily_quotes(years)
    if "basic" in tasks:
        import_daily_basic(years)
    if "fina" in tasks:
        import_financial_indicators(years)
    if "index" in tasks:
        import_index_daily(years)

    elapsed = time.time() - start_time
    logger.info(f"全部完成，耗时 {elapsed/60:.1f} 分钟")


if __name__ == "__main__":
    main()
