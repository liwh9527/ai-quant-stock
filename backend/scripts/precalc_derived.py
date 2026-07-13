"""预计算派生字段（单条SQL，极速）

在数据库中创建 daily_derived 表，存储：
- pct_chg_5d, pct_chg_10d, pct_chg_20d: 近N日涨幅
- consecutive_up_days: 连续上涨天数

运行一次即可，之后回测直接查表。
"""

import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'quant.db')


def precalc(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("创建 daily_derived 表...")
    cur.execute("DROP TABLE IF EXISTS daily_derived")
    conn.commit()

    t0 = time.time()

    # 单条 SQL 完成全部计算
    print("计算派生字段（单条SQL窗口函数）...")
    cur.execute("""
        CREATE TABLE daily_derived AS
        WITH base AS (
            SELECT
                ts_code,
                trade_date,
                close,
                LAG(close, 1) OVER w as close_1d,
                LAG(close, 5) OVER w as close_5d,
                LAG(close, 10) OVER w as close_10d,
                LAG(close, 20) OVER w as close_20d
            FROM daily_quotes
            WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
        ),
        with_pct AS (
            SELECT
                ts_code,
                trade_date,
                CASE WHEN close_5d > 0 THEN ROUND((close - close_5d) / close_5d * 100, 2) END as pct_chg_5d,
                CASE WHEN close_10d > 0 THEN ROUND((close - close_10d) / close_10d * 100, 2) END as pct_chg_10d,
                CASE WHEN close_20d > 0 THEN ROUND((close - close_20d) / close_20d * 100, 2) END as pct_chg_20d,
                CASE WHEN close > close_1d THEN 1 ELSE 0 END as is_up
            FROM base
        ),
        with_grp AS (
            SELECT
                *,
                SUM(CASE WHEN is_up = 0 THEN 1 ELSE 0 END) OVER (PARTITION BY ts_code ORDER BY trade_date) as grp
            FROM with_pct
        )
        SELECT
            ts_code,
            trade_date,
            pct_chg_5d,
            pct_chg_10d,
            pct_chg_20d,
            CASE WHEN is_up = 1 THEN
                ROW_NUMBER() OVER (PARTITION BY ts_code, grp ORDER BY trade_date)
            ELSE 0 END as consecutive_up_days
        FROM with_grp
    """)
    conn.commit()

    # 添加索引
    print("创建索引...")
    cur.execute("CREATE INDEX idx_derived_date ON daily_derived(trade_date)")
    cur.execute("CREATE INDEX idx_derived_code ON daily_derived(ts_code)")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM daily_derived")
    total = cur.fetchone()[0]
    elapsed = time.time() - t0
    print(f"完成! 共 {total:,} 条, 耗时 {elapsed:.0f} 秒")

    conn.close()


if __name__ == "__main__":
    precalc()
