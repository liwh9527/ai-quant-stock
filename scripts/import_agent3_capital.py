"""Agent 3: 资金流向 + 融资融券 + 大宗交易"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'backend'))

import tinyshare as ts
import sqlite3
from datetime import datetime, timedelta

TOKEN = 'ovL7T12Mct8o5nWWRM1h9W8S2x6PhQf3uXci67G1mbWv34na646MTSLU6d37ddd7'
DB_PATH = 'data/quant.db'
START_DATE = '20230601'
END_DATE = '20260608'

ts.set_token(TOKEN)
pro = ts.pro_api()

def get_trade_dates():
    dates = []
    current = datetime.strptime(START_DATE, '%Y%m%d')
    end = datetime.strptime(END_DATE, '%Y%m%d')
    while current <= end:
        if current.weekday() < 5:
            dates.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return dates

def import_moneyflow():
    """导入个股资金流向"""
    print('[Agent3] 开始导入资金流向...')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS moneyflow (
        id INTEGER PRIMARY KEY,
        ts_code VARCHAR(20),
        trade_date DATE,
        buy_sm_vol FLOAT,
        sell_sm_vol FLOAT,
        buy_md_vol FLOAT,
        sell_md_vol FLOAT,
        buy_lg_vol FLOAT,
        sell_lg_vol FLOAT,
        buy_elg_vol FLOAT,
        sell_elg_vol FLOAT,
        net_mf_vol FLOAT
    )''')
    conn.commit()
    
    dates = get_trade_dates()
    total = 0
    errors = 0
    
    for i, date in enumerate(dates):
        try:
            df = pro.moneyflow(trade_date=date)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        '''INSERT OR REPLACE INTO moneyflow 
                        (ts_code, trade_date, buy_sm_vol, sell_sm_vol, buy_md_vol, sell_md_vol,
                         buy_lg_vol, sell_lg_vol, buy_elg_vol, sell_elg_vol, net_mf_vol) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                        (row['ts_code'], row['trade_date'],
                         row.get('buy_sm_vol', 0), row.get('sell_sm_vol', 0),
                         row.get('buy_md_vol', 0), row.get('sell_md_vol', 0),
                         row.get('buy_lg_vol', 0), row.get('sell_lg_vol', 0),
                         row.get('buy_elg_vol', 0), row.get('sell_elg_vol', 0),
                         row.get('net_mf_vol', 0))
                    )
                total += len(df)
                conn.commit()
            if (i + 1) % 50 == 0:
                print(f'  [moneyflow] {i+1}/{len(dates)} 日期, {total} 行')
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f'  [moneyflow] 错误 {date}: {str(e)[:50]}')
            time.sleep(0.5)
    
    conn.close()
    print(f'[Agent3] 资金流向完成: {total} 行, {errors} 次错误')
    return total

def import_margin():
    """导入融资融券"""
    print('[Agent3] 开始导入融资融券...')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS margin (
        id INTEGER PRIMARY KEY,
        trade_date DATE,
        ts_code VARCHAR(20),
        rzye FLOAT,
        rzmre FLOAT,
        rzche FLOAT,
        rqye FLOAT,
        rqmce FLOAT,
        rqchl FLOAT
    )''')
    conn.commit()
    
    dates = get_trade_dates()
    total = 0
    errors = 0
    
    for i, date in enumerate(dates):
        try:
            df = pro.margin(trade_date=date)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        'INSERT OR REPLACE INTO margin (trade_date, ts_code, rzye, rzmre, rzche, rqye, rqmce, rqchl) VALUES (?,?,?,?,?,?,?,?)',
                        (row['trade_date'], row.get('ts_code'),
                         row.get('rzye', 0), row.get('rzmre', 0), row.get('rzche', 0),
                         row.get('rqye', 0), row.get('rqmce', 0), row.get('rqchl', 0))
                    )
                total += len(df)
                conn.commit()
            if (i + 1) % 50 == 0:
                print(f'  [margin] {i+1}/{len(dates)} 日期, {total} 行')
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f'  [margin] 错误 {date}: {str(e)[:50]}')
            time.sleep(0.5)
    
    conn.close()
    print(f'[Agent3] 融资融券完成: {total} 行, {errors} 次错误')
    return total

def import_block_trade():
    """导入大宗交易"""
    print('[Agent3] 开始导入大宗交易...')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS block_trade (
        id INTEGER PRIMARY KEY,
        ts_code VARCHAR(20),
        trade_date DATE,
        price FLOAT,
        vol FLOAT,
        amount FLOAT,
        buyer VARCHAR(100),
        seller VARCHAR(100)
    )''')
    conn.commit()
    
    dates = get_trade_dates()
    total = 0
    errors = 0
    
    for i, date in enumerate(dates):
        try:
            df = pro.block_trade(trade_date=date)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        'INSERT OR REPLACE INTO block_trade (ts_code, trade_date, price, vol, amount, buyer, seller) VALUES (?,?,?,?,?,?,?)',
                        (row['ts_code'], row['trade_date'],
                         row.get('price', 0), row.get('vol', 0), row.get('amount', 0),
                         row.get('buyer', ''), row.get('seller', ''))
                    )
                total += len(df)
                conn.commit()
            if (i + 1) % 50 == 0:
                print(f'  [block] {i+1}/{len(dates)} 日期, {total} 行')
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f'  [block] 错误 {date}: {str(e)[:50]}')
            time.sleep(0.5)
    
    conn.close()
    print(f'[Agent3] 大宗交易完成: {total} 行, {errors} 次错误')
    return total

if __name__ == '__main__':
    start = time.time()
    print(f'[Agent3] 启动 - 资金流向/融资融券/大宗交易')
    print(f'[Agent3] 日期范围: {START_DATE} ~ {END_DATE}')
    print()
    
    import_moneyflow()
    import_margin()
    import_block_trade()
    
    elapsed = time.time() - start
    print(f'\n[Agent3] 全部完成! 总用时: {elapsed/60:.1f} 分钟')
