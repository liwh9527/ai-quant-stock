"""Agent 1: 日线行情 + 每日指标 + 复权因子 + 涨跌停价格"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'backend'))

import tinyshare as ts
import sqlite3
from datetime import datetime, timedelta

TOKEN = 'ovL7T12Mct8o5nWWRM1h9W8S2x6PhQf3uXci67G1mbWv34na646MTSLU6d37ddd7'
DB_PATH = 'data/quant.db'
START_DATE = '20230601'  # 3年数据
END_DATE = '20260608'

ts.set_token(TOKEN)
pro = ts.pro_api()

def get_trade_dates():
    """获取交易日列表"""
    # 从已有的daily_quotes表获取日期范围
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 生成日期范围
    dates = []
    current = datetime.strptime(START_DATE, '%Y%m%d')
    end = datetime.strptime(END_DATE, '%Y%m%d')
    while current <= end:
        if current.weekday() < 5:  # 跳过周末
            dates.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    conn.close()
    return dates

def import_daily():
    """导入日线行情"""
    print('[Agent1] 开始导入日线行情...')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    dates = get_trade_dates()
    total = 0
    errors = 0
    
    for i, date in enumerate(dates):
        try:
            df = pro.daily(trade_date=date)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        'INSERT OR REPLACE INTO daily_quotes (ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (row['ts_code'], row['trade_date'], row['open'], row['high'], row['low'], row['close'], row['pre_close'], row['change'], row['pct_chg'], row['vol'], row['amount'])
                    )
                total += len(df)
                conn.commit()
            if (i + 1) % 50 == 0:
                print(f'  [daily] {i+1}/{len(dates)} 日期, {total} 行')
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f'  [daily] 错误 {date}: {str(e)[:50]}')
            time.sleep(0.5)
    
    conn.close()
    print(f'[Agent1] 日线行情完成: {total} 行, {errors} 次错误')
    return total

def import_daily_basic():
    """导入每日指标"""
    print('[Agent1] 开始导入每日指标...')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    dates = get_trade_dates()
    total = 0
    errors = 0
    
    for i, date in enumerate(dates):
        try:
            df = pro.daily_basic(trade_date=date)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        'INSERT OR REPLACE INTO daily_basic (ts_code, trade_date, turnover_rate, turnover_rate_f, total_mv, circ_mv, pe, pb, ps) VALUES (?,?,?,?,?,?,?,?,?)',
                        (row['ts_code'], row['trade_date'], row.get('turnover_rate'), row.get('turnover_rate_f'), row.get('total_mv'), row.get('circ_mv'), row.get('pe'), row.get('pb'), row.get('ps'))
                    )
                total += len(df)
                conn.commit()
            if (i + 1) % 50 == 0:
                print(f'  [basic] {i+1}/{len(dates)} 日期, {total} 行')
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f'  [basic] 错误 {date}: {str(e)[:50]}')
            time.sleep(0.5)
    
    conn.close()
    print(f'[Agent1] 每日指标完成: {total} 行, {errors} 次错误')
    return total

def import_adj_factor():
    """导入复权因子"""
    print('[Agent1] 开始导入复权因子...')
    # 创建表
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS adj_factor (
        id INTEGER PRIMARY KEY,
        ts_code VARCHAR(20),
        trade_date DATE,
        adj_factor FLOAT
    )''')
    conn.commit()
    
    dates = get_trade_dates()
    total = 0
    errors = 0
    
    for i, date in enumerate(dates):
        try:
            df = pro.adj_factor(trade_date=date)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        'INSERT OR REPLACE INTO adj_factor (ts_code, trade_date, adj_factor) VALUES (?,?,?)',
                        (row['ts_code'], row['trade_date'], row['adj_factor'])
                    )
                total += len(df)
                conn.commit()
            if (i + 1) % 50 == 0:
                print(f'  [adj] {i+1}/{len(dates)} 日期, {total} 行')
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f'  [adj] 错误 {date}: {str(e)[:50]}')
            time.sleep(0.5)
    
    conn.close()
    print(f'[Agent1] 复权因子完成: {total} 行, {errors} 次错误')
    return total

def import_stk_limit():
    """导入涨跌停价格"""
    print('[Agent1] 开始导入涨跌停价格...')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS stk_limit (
        id INTEGER PRIMARY KEY,
        ts_code VARCHAR(20),
        trade_date DATE,
        up_limit FLOAT,
        down_limit FLOAT
    )''')
    conn.commit()
    
    dates = get_trade_dates()
    total = 0
    errors = 0
    
    for i, date in enumerate(dates):
        try:
            df = pro.stk_limit(trade_date=date)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        'INSERT OR REPLACE INTO stk_limit (ts_code, trade_date, up_limit, down_limit) VALUES (?,?,?,?)',
                        (row['ts_code'], row['trade_date'], row.get('up_limit'), row.get('down_limit'))
                    )
                total += len(df)
                conn.commit()
            if (i + 1) % 50 == 0:
                print(f'  [limit] {i+1}/{len(dates)} 日期, {total} 行')
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f'  [limit] 错误 {date}: {str(e)[:50]}')
            time.sleep(0.5)
    
    conn.close()
    print(f'[Agent1] 涨跌停完成: {total} 行, {errors} 次错误')
    return total

if __name__ == '__main__':
    start = time.time()
    print(f'[Agent1] 启动 - 日线/指标/复权/涨跌停')
    print(f'[Agent1] 日期范围: {START_DATE} ~ {END_DATE}')
    print()
    
    import_daily()
    import_daily_basic()
    import_adj_factor()
    import_stk_limit()
    
    elapsed = time.time() - start
    print(f'\n[Agent1] 全部完成! 总用时: {elapsed/60:.1f} 分钟')
