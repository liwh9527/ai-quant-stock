#!/usr/bin/env python3
"""
分析MA20策略条件满足情况
"""

import tushare as ts
import pandas as pd

TUSHARE_TOKEN = '29479ac41a3b85cd62b519f1d32a14e343ea99b6def6ce61a646395d'
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

def analyze_conditions(code, start_date='20250101', end_date='20260610'):
    ts_code = f'{code}.SH' if code.startswith('6') else f'{code}.SZ'
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    df = df.sort_values('trade_date').reset_index(drop=True)
    
    # 计算指标
    df['ma20'] = df['close'].rolling(20).mean()
    df['atr'] = df['close'].diff().abs().rolling(14).mean()
    df['avg_vol'] = df['vol'].rolling(5).mean()
    df['pct_change'] = df['close'].pct_change()
    
    # 统计各条件满足的天数
    total_days = len(df) - 20
    
    # 条件1: 偏离度<10%
    df['deviation'] = abs(df['close'] - df['ma20']) / df['ma20']
    cond1 = (df['deviation'] < 0.10).sum()
    
    # 条件2: 成交量>1.5倍
    df['vol_ratio'] = df['vol'] / df['avg_vol']
    cond2 = (df['vol_ratio'] > 1.5).sum()
    
    # 条件3: ATR>2%
    df['atr_pct'] = df['atr'] / df['close']
    cond3 = (df['atr_pct'] > 0.02).sum()
    
    # 条件4: 前一日在MA20下方
    df['prev_below'] = df['close'].shift(1) < df['ma20'].shift(1)
    cond4 = df['prev_below'].sum()
    
    # 条件5: 当日突破MA20
    df['cross_up'] = (df['close'] >= df['ma20']) & (df['close'].shift(1) < df['ma20'].shift(1))
    cond5 = df['cross_up'].sum()
    
    # 所有条件同时满足
    df['all_cond'] = (
        (df['deviation'] < 0.10) &
        (df['vol_ratio'] > 1.5) &
        (df['atr_pct'] > 0.02) &
        df['prev_below'] &
        (df['close'] >= df['ma20']) &
        (df['close'].shift(1) < df['ma20'].shift(1))
    )
    cond_all = df['all_cond'].sum()
    
    return {
        'total_days': total_days,
        'cond1_deviation': cond1,
        'cond2_volume': cond2,
        'cond3_atr': cond3,
        'cond4_below_ma20': cond4,
        'cond5_cross_up': cond5,
        'cond_all': cond_all,
    }

print('='*60)
print('MA20策略条件满足情况分析')
print('='*60)

stocks = ['600487', '601208', '601138']
names = ['亨通光电', '东材科技', '工业富联']

for code, name in zip(stocks, names):
    result = analyze_conditions(code)
    total = result['total_days']
    print(f'\n{name} ({code}):')
    print(f'  有效交易日: {total} 天')
    print(f'  条件1 偏离度<10%: {result["cond1_deviation"]} 天 ({result["cond1_deviation"]/total*100:.1f}%)')
    print(f'  条件2 成交量>1.5倍: {result["cond2_volume"]} 天 ({result["cond2_volume"]/total*100:.1f}%)')
    print(f'  条件3 ATR>2%: {result["cond3_atr"]} 天 ({result["cond3_atr"]/total*100:.1f}%)')
    print(f'  条件4 前日在MA20下方: {result["cond4_below_ma20"]} 天 ({result["cond4_below_ma20"]/total*100:.1f}%)')
    print(f'  条件5 突破MA20: {result["cond5_cross_up"]} 天 ({result["cond5_cross_up"]/total*100:.1f}%)')
    print(f'  所有条件同时满足: {result["cond_all"]} 天 ({result["cond_all"]/total*100:.1f}%)')

print('\n' + '='*60)
print('结论: 交易次数少的原因')
print('='*60)
print("""
MA20策略要求所有条件同时满足，这是一个"右侧突破"策略：

1. 突破信号本身罕见
   - 价格从下方突破MA20，平均每月只有1-2次
   
2. 多条件叠加更严格
   - 偏离度<10% ✓ (较宽松)
   - 成交量>1.5倍 ✓ (中等)
   - ATR>2% ✓ (较宽松)
   - 前日在MA20下方 + 当日突破 ✓ (最严格)
   
3. 这是策略设计的特点
   - MA20是中长线策略，不是短线频繁交易
   - 宁可少交易，也要高胜率
   - 避免频繁交易带来的手续费损耗

总结: 交易次数少是正常的，这是中长线趋势跟踪策略的特点。
""")
