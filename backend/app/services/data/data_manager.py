"""统一数据管理器 — 数据库优先，API 补充"""
import sqlite3
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'quant.db')


def _fmt(d: str) -> str:
    """统一日期为 YYYY-MM-DD 格式（数据库主要格式）"""
    if d and '-' not in d and len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _raw(d: str) -> str:
    """统一日期为 YYYYMMDD 格式"""
    return d.replace('-', '') if d and '-' in d else d


class DataManager:
    """统一数据管理器，优先从 SQLite 读取"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()

    def get_trade_dates(self, start_date: str, end_date: str) -> List[str]:
        """获取交易日列表"""
        s, e = _fmt(start_date), _fmt(end_date)
        cur = self.conn.execute(
            "SELECT DISTINCT trade_date FROM daily_quotes "
            "WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date", (s, e))
        return [_raw(r[0]) for r in cur.fetchall()]

    def get_daily(self, ts_codes: List[str], start_date: str, end_date: str) -> List[Dict]:
        """获取日线行情"""
        s, e = _fmt(start_date), _fmt(end_date)
        ph = ','.join(['?'] * len(ts_codes))
        cur = self.conn.execute(
            f"SELECT * FROM daily_quotes WHERE ts_code IN ({ph}) "
            f"AND trade_date BETWEEN ? AND ? ORDER BY trade_date",
            ts_codes + [s, e])
        return [dict(r) for r in cur.fetchall()]

    def get_daily_for_date(self, ts_codes: List[str], date: str) -> Dict[str, Dict]:
        """获取某日日线数据"""
        d = _fmt(date)
        ph = ','.join(['?'] * len(ts_codes))
        cur = self.conn.execute(
            f"SELECT * FROM daily_quotes WHERE ts_code IN ({ph}) AND trade_date = ?",
            ts_codes + [d])
        return {r['ts_code']: dict(r) for r in cur.fetchall()}

    def get_daily_basic(self, ts_codes: List[str], date: str) -> Dict[str, Dict]:
        """获取每日指标"""
        d = _fmt(date)
        ph = ','.join(['?'] * len(ts_codes))
        cur = self.conn.execute(
            f"SELECT * FROM daily_basic WHERE ts_code IN ({ph}) AND trade_date = ?",
            ts_codes + [d])
        return {r['ts_code']: dict(r) for r in cur.fetchall()}

    def get_financial(self, ts_codes: List[str], date: str) -> Dict[str, Dict]:
        """获取最新一期财务指标"""
        d = _fmt(date)
        ph = ','.join(['?'] * len(ts_codes))
        cur = self.conn.execute(
            f"SELECT * FROM financial_indicators WHERE ts_code IN ({ph}) "
            f"AND ann_date <= ? ORDER BY ann_date DESC", ts_codes + [d])
        result = {}
        for row in cur.fetchall():
            r = dict(row)
            if r['ts_code'] not in result:
                result[r['ts_code']] = r
        return result

    def get_index_daily(self, index_code: str, start_date: str, end_date: str) -> List[Dict]:
        """获取指数日线"""
        s, e = _fmt(start_date), _fmt(end_date)
        cur = self.conn.execute(
            "SELECT * FROM index_daily WHERE ts_code = ? "
            "AND trade_date BETWEEN ? AND ? ORDER BY trade_date",
            (index_code, s, e))
        return [dict(r) for r in cur.fetchall()]

    def check_limit_up(self, ts_code: str, date: str) -> bool:
        """判断是否涨停"""
        d = _fmt(date)
        cur = self.conn.execute(
            "SELECT close, pct_chg FROM daily_quotes "
            "WHERE ts_code = ? AND trade_date = ?", (ts_code, d))
        row = cur.fetchone()
        if not row:
            return False
        if ts_code.startswith(('300', '301', '688')):
            return row['pct_chg'] >= 19.5
        return row['pct_chg'] >= 9.5

    def get_prev_limit_up_stocks(self, date: str) -> List[str]:
        """获取前一日涨停的股票"""
        d = _fmt(date)
        # 找前一个交易日
        cur = self.conn.execute(
            "SELECT DISTINCT trade_date FROM daily_quotes "
            "WHERE trade_date < ? ORDER BY trade_date DESC LIMIT 1", (d,))
        row = cur.fetchone()
        if not row:
            return []
        prev = row[0]

        cur = self.conn.execute(
            "SELECT ts_code FROM daily_quotes "
            "WHERE trade_date = ? AND pct_chg >= 9.5", (prev,))
        return [r[0] for r in cur.fetchall()]

    def get_moneyflow(self, ts_codes: List[str], date: str) -> Dict[str, Dict]:
        """获取资金流向"""
        d = _fmt(date)
        ph = ','.join(['?'] * len(ts_codes))
        cur = self.conn.execute(
            f"SELECT * FROM moneyflow WHERE ts_code IN ({ph}) AND trade_date = ?",
            ts_codes + [d])
        return {r['ts_code']: dict(r) for r in cur.fetchall()}

    def get_all_stocks(self, date: str = None) -> List[Dict]:
        """获取所有股票"""
        if date:
            d = _fmt(date)
            cur = self.conn.execute(
                "SELECT * FROM stocks WHERE list_date <= ? "
                "AND (delist_date = '' OR delist_date IS NULL OR delist_date > ?)",
                (d, d))
        else:
            cur = self.conn.execute("SELECT * FROM stocks")
        return [dict(r) for r in cur.fetchall()]

    def get_stock_price_on_date(self, ts_code: str, date: str) -> Optional[Dict]:
        """获取单只股票某日价格"""
        d = _fmt(date)
        cur = self.conn.execute(
            "SELECT * FROM daily_quotes WHERE ts_code = ? AND trade_date = ?",
            (ts_code, d))
        row = cur.fetchone()
        return dict(row) if row else None
