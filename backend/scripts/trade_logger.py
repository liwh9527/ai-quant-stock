#!/usr/bin/env python3
"""
量化交易日志数据库
SQLite存储所有交易记录、信号、每日快照
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
DB_PATH = os.path.join(DB_DIR, 'trades.db')


def get_conn():
    """获取数据库连接"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        action TEXT NOT NULL,
        price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        amount REAL NOT NULL,
        reason TEXT,
        score INTEGER,
        pnl REAL,
        pnlcomm REAL
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS daily_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        total_assets REAL,
        cash REAL,
        positions_value REAL,
        daily_pnl REAL,
        total_pnl REAL,
        positions_json TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        score INTEGER,
        indicators_json TEXT,
        executed INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()


def log_trade(code, name, action, price, quantity, amount, reason="", score=0, pnl=0, pnlcomm=0):
    """记录交易"""
    init_db()
    conn = get_conn()
    conn.execute(
        'INSERT INTO trades (timestamp, code, name, action, price, quantity, amount, reason, score, pnl, pnlcomm) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (datetime.now().isoformat(), code, name, action, price, quantity, amount, reason, score, pnl, pnlcomm)
    )
    conn.commit()
    conn.close()


def log_snapshot(total_assets, cash, positions_value, daily_pnl, total_pnl, positions):
    """记录每日快照"""
    init_db()
    conn = get_conn()
    today = datetime.now().strftime('%Y-%m-%d')
    conn.execute(
        'INSERT OR REPLACE INTO daily_snapshots (date, total_assets, cash, positions_value, daily_pnl, total_pnl, positions_json) VALUES (?,?,?,?,?,?,?)',
        (today, total_assets, cash, positions_value, daily_pnl, total_pnl, json.dumps(positions, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def log_signal(code, name, signal_type, score, indicators=None, executed=False):
    """记录信号"""
    init_db()
    conn = get_conn()
    conn.execute(
        'INSERT INTO signals (timestamp, code, name, signal_type, score, indicators_json, executed) VALUES (?,?,?,?,?,?,?)',
        (datetime.now().isoformat(), code, name, signal_type, score,
         json.dumps(indicators or {}, ensure_ascii=False), 1 if executed else 0)
    )
    conn.commit()
    conn.close()


def get_trades(days=30):
    """获取最近交易"""
    init_db()
    conn = get_conn()
    since = (datetime.now() - timedelta(days=days)).isoformat()
    rows = conn.execute('SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp DESC', (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_snapshots(days=30):
    """获取每日快照"""
    init_db()
    conn = get_conn()
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = conn.execute('SELECT * FROM daily_snapshots WHERE date >= ? ORDER BY date', (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signals(days=7):
    """获取最近信号"""
    init_db()
    conn = get_conn()
    since = (datetime.now() - timedelta(days=days)).isoformat()
    rows = conn.execute('SELECT * FROM signals WHERE timestamp >= ? ORDER BY timestamp DESC', (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trade_summary():
    """获取交易统计"""
    init_db()
    conn = get_conn()
    
    total = conn.execute('SELECT COUNT(*) as cnt FROM trades WHERE action="sell"').fetchone()['cnt']
    wins = conn.execute('SELECT COUNT(*) as cnt FROM trades WHERE action="sell" AND pnlcomm > 0').fetchone()['cnt']
    losses = conn.execute('SELECT COUNT(*) as cnt FROM trades WHERE action="sell" AND pnlcomm <= 0').fetchone()['cnt']
    total_pnl = conn.execute('SELECT COALESCE(SUM(pnlcomm), 0) as s FROM trades WHERE action="sell"').fetchone()['s']
    avg_win = conn.execute('SELECT COALESCE(AVG(pnlcomm), 0) as a FROM trades WHERE action="sell" AND pnlcomm > 0').fetchone()['a']
    avg_loss = conn.execute('SELECT COALESCE(AVG(pnlcomm), 0) as a FROM trades WHERE action="sell" AND pnlcomm <= 0').fetchone()['a']
    
    conn.close()
    
    return {
        'total_trades': total,
        'wins': wins,
        'losses': losses,
        'win_rate': wins / max(total, 1),
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_ratio': abs(avg_win / avg_loss) if avg_loss != 0 else 0,
    }


if __name__ == '__main__':
    init_db()
    print(f"✅ 数据库已初始化: {DB_PATH}")
    
    summary = get_trade_summary()
    print(f"📊 交易统计: {summary}")
    
    trades = get_trades(7)
    print(f"📝 最近7天交易: {len(trades)} 笔")
