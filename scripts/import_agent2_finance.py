"""Agent 2: 财务指标（全市场按股票拉）"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'backend'))

import tinyshare as ts
import sqlite3

TOKEN = 'ovL7T12Mct8o5nWWRM1h9W8S2x6PhQf3uXci67G1mbWv34na646MTSLU6d37ddd7'
DB_PATH = 'data/quant.db'

ts.set_token(TOKEN)
pro = ts.pro_api()

def get_stock_list():
    """获取所有股票代码"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT ts_code FROM stocks')
    stocks = [row[0] for row in cursor.fetchall()]
    conn.close()
    return stocks

def import_financial_indicators():
    """导入财务指标 - 按股票拉"""
    stocks = get_stock_list()
    print(f'[Agent2] 开始导入财务指标, 共 {len(stocks)} 只股票')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    total = 0
    errors = 0
    
    for i, ts_code in enumerate(stocks):
        try:
            df = pro.fina_indicator(ts_code=ts_code)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        '''INSERT OR REPLACE INTO financial_indicators 
                        (ts_code, ann_date, end_date, roe, roa, gross_margin, net_margin, 
                         revenue_yoy, net_profit_yoy, pe, pb, ps, debt_ratio, current_ratio, eps, bvps) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (row['ts_code'], row.get('ann_date'), row.get('end_date'),
                         row.get('roe', 0), row.get('roa', 0), row.get('grossmargin', 0), row.get('netmargin', 0),
                         row.get('revenue_yoy', 0), row.get('netprofit_yoy', 0),
                         row.get('pe', 0), row.get('pb', 0), row.get('ps', 0),
                         row.get('debt_ratio', 0), row.get('current_ratio', 0),
                         row.get('eps', 0), row.get('bvps', 0))
                    )
                total += len(df)
            if (i + 1) % 100 == 0:
                conn.commit()
                print(f'  [fina] {i+1}/{len(stocks)} 股票, {total} 行')
        except Exception as e:
            errors += 1
            if errors < 10:
                print(f'  [fina] 错误 {ts_code}: {str(e)[:50]}')
            time.sleep(0.3)
    
    conn.commit()
    conn.close()
    print(f'[Agent2] 财务指标完成: {total} 行, {errors} 次错误')
    return total

def import_income():
    """导入利润表"""
    stocks = get_stock_list()
    print(f'[Agent2] 开始导入利润表, 共 {len(stocks)} 只股票')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS income (
        id INTEGER PRIMARY KEY,
        ts_code VARCHAR(20),
        ann_date DATE,
        end_date DATE,
        revenue FLOAT,
        operate_profit FLOAT,
        total_profit FLOAT,
        n_income FLOAT,
        n_income_attr_p FLOAT,
        basic_eps FLOAT
    )''')
    conn.commit()
    
    total = 0
    errors = 0
    
    for i, ts_code in enumerate(stocks):
        try:
            df = pro.income(ts_code=ts_code)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        'INSERT OR REPLACE INTO income (ts_code, ann_date, end_date, revenue, operate_profit, total_profit, n_income, n_income_attr_p, basic_eps) VALUES (?,?,?,?,?,?,?,?,?)',
                        (row['ts_code'], row.get('ann_date'), row.get('end_date'),
                         row.get('revenue', 0), row.get('operate_profit', 0), row.get('total_profit', 0),
                         row.get('n_income', 0), row.get('n_income_attr_p', 0), row.get('basic_eps', 0))
                    )
                total += len(df)
            if (i + 1) % 100 == 0:
                conn.commit()
                print(f'  [income] {i+1}/{len(stocks)} 股票, {total} 行')
        except Exception as e:
            errors += 1
            time.sleep(0.3)
    
    conn.commit()
    conn.close()
    print(f'[Agent2] 利润表完成: {total} 行, {errors} 次错误')
    return total

def import_balancesheet():
    """导入资产负债表"""
    stocks = get_stock_list()
    print(f'[Agent2] 开始导入资产负债表, 共 {len(stocks)} 只股票')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS balancesheet (
        id INTEGER PRIMARY KEY,
        ts_code VARCHAR(20),
        ann_date DATE,
        end_date DATE,
        total_assets FLOAT,
        total_liab FLOAT,
        total_hldr_eqy_exc_min_int FLOAT,
        total_cur_assets FLOAT,
        total_cur_liab FLOAT,
        money_cap FLOAT
    )''')
    conn.commit()
    
    total = 0
    errors = 0
    
    for i, ts_code in enumerate(stocks):
        try:
            df = pro.balancesheet(ts_code=ts_code)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    cursor.execute(
                        'INSERT OR REPLACE INTO balancesheet (ts_code, ann_date, end_date, total_assets, total_liab, total_hldr_eqy_exc_min_int, total_cur_assets, total_cur_liab, money_cap) VALUES (?,?,?,?,?,?,?,?,?)',
                        (row['ts_code'], row.get('ann_date'), row.get('end_date'),
                         row.get('total_assets', 0), row.get('total_liab', 0), row.get('total_hldr_eqy_exc_min_int', 0),
                         row.get('total_cur_assets', 0), row.get('total_cur_liab', 0), row.get('money_cap', 0))
                    )
                total += len(df)
            if (i + 1) % 100 == 0:
                conn.commit()
                print(f'  [balance] {i+1}/{len(stocks)} 股票, {total} 行')
        except Exception as e:
            errors += 1
            time.sleep(0.3)
    
    conn.commit()
    conn.close()
    print(f'[Agent2] 资产负债表完成: {total} 行, {errors} 次错误')
    return total

if __name__ == '__main__':
    start = time.time()
    print(f'[Agent2] 启动 - 财务数据')
    print()
    
    import_financial_indicators()
    import_income()
    import_balancesheet()
    
    elapsed = time.time() - start
    print(f'\n[Agent2] 全部完成! 总用时: {elapsed/60:.1f} 分钟')
