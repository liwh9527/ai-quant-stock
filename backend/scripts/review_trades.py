#!/usr/bin/env python3
"""交易复盘分析"""

import tushare as ts
import pandas as pd

TUSHARE_TOKEN = '29479ac41a3b85cd62b519f1d32a14e343ea99b6def6ce61a646395d'
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# 获取上证指数
index_df = pro.index_daily(ts_code='000001.SH', start_date='20260601', end_date='20260611')
index_df = index_df.sort_values('trade_date')

print('='*60)
print('大盘走势 (上证指数)')
print('='*60)
for _, row in index_df.iterrows():
    emoji = '🟢' if row['pct_chg'] > 0 else '🔴'
    print(f"{row['trade_date']} | {emoji} {row['pct_chg']:+.2f}% | 收盘 {row['close']:.2f}")

# 获取个股数据
stocks = [
    {'code': '600487', 'name': '亨通光电', 'buy_date': '20260610', 'buy_price': 105.85, 'sell_date': None, 'sell_price': None},
    {'code': '601208', 'name': '东材科技', 'buy_date': '20260610', 'buy_price': 62.09, 'sell_date': '20260611', 'sell_price': 58.93},
    {'code': '601138', 'name': '工业富联', 'buy_date': '20260610', 'buy_price': 71.36, 'sell_date': None, 'sell_price': None},
]

print()
print('='*60)
print('个股走势分析')
print('='*60)

for s in stocks:
    ts_code = f"{s['code']}.SH" if s['code'].startswith('6') else f"{s['code']}.SZ"
    df = pro.daily(ts_code=ts_code, start_date='20260605', end_date='20260611')
    df = df.sort_values('trade_date').reset_index(drop=True)
    df['ma20'] = df['close'].rolling(20).mean()
    
    print(f"\n{s['name']} ({s['code']}):")
    print(f"  买入: {s['buy_date']} @ {s['buy_price']}")
    if s['sell_date']:
        profit = (s['sell_price'] - s['buy_price']) / s['buy_price'] * 100
        print(f"  卖出: {s['sell_date']} @ {s['sell_price']} ({profit:+.1f}%)")
    
    print(f"  {'日期':<12} {'收盘':>8} {'涨跌%':>8} {'MA20':>8} {'vs MA20':>10}")
    print(f"  {'-'*50}")
    
    for _, row in df.iterrows():
        emoji = '🟢' if row['pct_chg'] > 0 else '🔴'
        vs_ma20 = (row['close'] - row['ma20']) / row['ma20'] * 100 if pd.notna(row['ma20']) and row['ma20'] > 0 else 0
        marker = ''
        if row['trade_date'] == s['buy_date']:
            marker = ' ← 买入'
        elif s['sell_date'] and row['trade_date'] == s['sell_date']:
            marker = ' ← 卖出'
        print(f"  {row['trade_date']} {emoji}{row['pct_chg']:>+7.2f}% {row['close']:>8.2f} {row['ma20']:>8.2f} {vs_ma20:>+9.1f}%{marker}")

# 总结
print()
print('='*60)
print('交易总结')
print('='*60)

total_profit = 0
for s in stocks:
    if s['sell_date']:
        profit = (s['sell_price'] - s['buy_price']) / s['buy_price'] * 100
        total_profit += profit
        print(f"{s['name']}: {profit:+.1f}%")
    else:
        print(f"{s['name']}: 持仓中")
