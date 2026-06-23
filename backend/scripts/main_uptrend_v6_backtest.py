#!/usr/bin/env python3
"""主升浪策略V6 - 简化版（学习财通成长基金核心优化）

核心优化点：
1. 移动止损4%（从5%降低）
2. 熔断阈值6%（从8%降低）
3. 再平衡3天（从5天缩短）
4. 动量确认（多周期一致性）
5. 行业筛选（降低权重）
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
import time

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# 简化版策略参数
PARAMS = {
    # 基本参数
    'max_positions': 5,
    'position_pct': 0.15,
    'momentum_threshold': 0.40,
    'volume_ratio': 1.5,
    'trailing_stop': 0.04,        # 4%移动止损
    'circuit_breaker': 0.06,      # 6%熔断阈值
    'rebalance_days': 3,          # 3天再平衡
    'min_score': 0.60,
    
    # 动量确认
    'momentum_consistency': 0.6,
    
    # 风险控制
    'max_volatility': 0.40,
}

def load_data():
    """加载股票数据"""
    conn = sqlite3.connect(DB_PATH)
    start_date = '2021-01-01'
    
    big_cap_stocks = [
        '600036.SH', '601318.SH', '600519.SH', '600030.SH', '601166.SH',
        '600276.SH', '600309.SH', '600031.SH', '601899.SH', '600900.SH',
    ]
    
    all_data = []
    for ts_code in big_cap_stocks:
        df = pd.read_sql_query(f'''
            SELECT trade_date, close FROM daily_quotes 
            WHERE ts_code="{ts_code}" AND trade_date >= "{start_date}"
            ORDER BY trade_date
        ''', conn)
        if len(df) > 500:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.set_index('trade_date')
            df = df.rename(columns={'close': ts_code})
            all_data.append(df)
    
    combined = pd.concat(all_data, axis=1).dropna()
    returns = combined.pct_change()
    returns['avg_return'] = returns.mean(axis=1)
    combined['index'] = 1000 * (1 + returns['avg_return']).cumprod()
    
    for period in [20, 60]:
        combined[f'ma{period}'] = combined['index'].rolling(period).mean()
    
    stocks = pd.read_sql_query(f'''
        SELECT d.ts_code, s.name, AVG(d.vol) as avg_vol
        FROM daily_quotes d
        JOIN stocks s ON d.ts_code = s.ts_code
        WHERE d.trade_date >= "{start_date}"
        AND s.name NOT LIKE "%ST%"
        AND s.name NOT LIKE "%退%"
        AND (d.ts_code LIKE "60%" OR d.ts_code LIKE "00%")
        AND d.ts_code NOT LIKE "30%"
        AND d.ts_code NOT LIKE "68%"
        GROUP BY d.ts_code
        HAVING COUNT(*) > 800
        ORDER BY avg_vol DESC
        LIMIT 200
    ''', conn)
    
    stock_data = {}
    all_dates = set()
    
    for _, row in stocks.iterrows():
        ts_code = row['ts_code']
        name = row['name']
        df = pd.read_sql_query(f'''
            SELECT trade_date, open, high, low, close, vol as volume 
            FROM daily_quotes WHERE ts_code="{ts_code}" 
            AND trade_date >= "{start_date}"
            ORDER BY trade_date
        ''', conn)
        if len(df) < 500: continue
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.set_index('trade_date')
        
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
        
        df['momentum'] = df['close'].pct_change(20)
        df['momentum_5d'] = df['close'].pct_change(5)
        df['momentum_10d'] = df['close'].pct_change(10)
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        df['high_20'] = df['high'].rolling(20).max()
        df['breakout'] = (df['close'] > df['high_20'].shift(1)).astype(int)
        df['relative_strength'] = df['close'].pct_change(20) - combined['index'].pct_change(20)
        df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
        
        df['close_np'] = df['close'].values
        df['ma20_np'] = df['ma20'].values
        df['ma60_np'] = df['ma60'].values
        df['atr_np'] = df['atr'].values
        df['momentum_np'] = df['momentum'].values
        df['momentum_5d_np'] = df['momentum_5d'].values
        df['momentum_10d_np'] = df['momentum_10d'].values
        df['volume_ratio_np'] = df['volume_ratio'].values
        df['breakout_np'] = df['breakout'].values
        df['relative_strength_np'] = df['relative_strength'].values
        df['volatility_np'] = df['volatility'].values
        
        stock_data[name] = {
            'code': ts_code,
            'data': df,
        }
        all_dates.update(df.index)
    
    conn.close()
    return combined, stock_data, sorted(all_dates)

def check_momentum_consistency(row, params):
    """检查动量一致性"""
    momentum_5d = row.get('momentum_5d_np', 0)
    momentum_10d = row.get('momentum_10d_np', 0)
    momentum_20d = row.get('momentum_np', 0)
    
    if pd.isna(momentum_5d) or pd.isna(momentum_10d) or pd.isna(momentum_20d):
        return False, 0
    
    positive_count = 0
    if momentum_5d > 0:
        positive_count += 1
    if momentum_10d > 0:
        positive_count += 1
    if momentum_20d > params['momentum_threshold']:
        positive_count += 1
    
    consistency = positive_count / 3
    passed = consistency >= params['momentum_consistency']
    
    return passed, consistency

def identify_main_uptrend(stock_data, date, params):
    """识别主升浪股票（简化版）"""
    main_uptrend_stocks = []
    
    for name, info in stock_data.items():
        df = info['data']
        
        if date not in df.index:
            continue
        
        row = df.loc[date]
        
        close = row.get('close_np', 0)
        ma20 = row.get('ma20_np', 0)
        ma60 = row.get('ma60_np', 0)
        momentum = row.get('momentum_np', 0)
        volume_ratio = row.get('volume_ratio_np', 0)
        breakout = row.get('breakout_np', 0)
        relative_strength = row.get('relative_strength_np', 0)
        volatility = row.get('volatility_np', 0)
        
        if pd.isna(close) or pd.isna(ma20) or pd.isna(ma60):
            continue
        if pd.isna(momentum) or pd.isna(volume_ratio) or pd.isna(breakout):
            continue
        
        # 波动率限制
        if not pd.isna(volatility) and volatility > params['max_volatility']:
            continue
        
        # 动量一致性
        momentum_consistent, momentum_score = check_momentum_consistency(row, params)
        if not momentum_consistent:
            continue
        
        # 主升浪条件
        conditions = {
            'price_above_ma': close > ma20 and close > ma60,
            'ma_bullish': ma20 > ma60,
            'strong_momentum': momentum > params['momentum_threshold'],
            'volume_surge': volume_ratio > params['volume_ratio'],
            'breakout': breakout == 1,
            'relative_strength': relative_strength > 0.1,
            'momentum_consistent': momentum_consistent,
        }
        
        score = sum(conditions.values()) / len(conditions)
        
        if score >= params['min_score']:
            main_uptrend_stocks.append({
                'name': name,
                'code': info['code'],
                'score': score,
                'momentum': momentum,
                'volume_ratio': volume_ratio,
                'breakout': breakout,
                'volatility': volatility,
            })
    
    main_uptrend_stocks.sort(key=lambda x: x['score'], reverse=True)
    return main_uptrend_stocks[:params['max_positions']]

def run_backtest(combined, stock_data, all_dates, params):
    """运行回测"""
    initial_cash = 1000000
    cash = initial_cash
    positions = {}
    buy_prices = {}
    max_prices = {}
    daily_values = []
    
    last_rebalance = None
    peak_value = initial_cash
    circuit_breaker = False
    circuit_breaker_until = None
    
    for date in all_dates:
        prices = {}
        for name, info in stock_data.items():
            if date in info['data'].index:
                prices[name] = info['data'].loc[date, 'close_np']
        
        pv = cash + sum(positions[n] * prices.get(n, 0) for n in positions if positions[n] > 0)
        if pv > peak_value: peak_value = pv
        portfolio_drawdown = (peak_value - pv) / peak_value
        
        # 熔断检查（优化：6%熔断）
        if portfolio_drawdown > params['circuit_breaker'] and not circuit_breaker:
            circuit_breaker = True
            circuit_breaker_until = date + pd.Timedelta(days=10)
            for name in list(positions.keys()):
                if positions[name] > 0:
                    price = prices.get(name, 0)
                    if price > 0:
                        cash += positions[name] * price * 0.999
                        positions[name] = 0
        
        if circuit_breaker and date >= circuit_breaker_until:
            circuit_breaker = False
            peak_value = pv
        
        # 止损检查（优化：4%止损）
        for name in list(positions.keys()):
            if positions[name] <= 0: continue
            if name not in stock_data or date not in stock_data[name]['data'].index: continue
            
            row = stock_data[name]['data'].loc[date]
            price = row['close_np']
            buy_price = buy_prices.get(name, 0)
            max_price = max_prices.get(name, buy_price)
            
            if buy_price <= 0: continue
            
            if price > max_price:
                max_prices[name] = price
                max_price = price
            
            sell = False
            
            # 跌破MA20止损
            if 'ma20_np' in row and not pd.isna(row['ma20_np']):
                if price < row['ma20_np']:
                    sell = True
            
            # 移动止损（优化：4%）
            if not sell:
                trailing_stop_price = max_price * (1 - params['trailing_stop'])
                if price < trailing_stop_price:
                    sell = True
            
            # 动量衰减止损
            if not sell and 'momentum_np' in row and not pd.isna(row['momentum_np']):
                if row['momentum_np'] < 0.10:
                    sell = True
            
            if sell:
                cash += positions[name] * price * 0.999
                positions[name] = 0
                if name in buy_prices: del buy_prices[name]
                if name in max_prices: del max_prices[name]
        
        # 识别主升浪股票（优化：3天再平衡）
        if not circuit_breaker:
            if last_rebalance is None or (date - last_rebalance).days >= params['rebalance_days']:
                last_rebalance = date
                main_uptrend_stocks = identify_main_uptrend(stock_data, date, params)
                
                current_holdings = [name for name, shares in positions.items() if shares > 0]
                new_pool = [stock['name'] for stock in main_uptrend_stocks]
                
                # 卖出不在池中的股票
                for name in current_holdings:
                    if name not in new_pool:
                        price = prices.get(name, 0)
                        if price > 0:
                            cash += positions[name] * price * 0.999
                            positions[name] = 0
                            if name in buy_prices: del buy_prices[name]
                            if name in max_prices: del max_prices[name]
                
                # 买入新股票
                for stock in main_uptrend_stocks:
                    name = stock['name']
                    if name in positions and positions[name] > 0:
                        continue
                    
                    if len([p for p in positions.values() if p > 0]) >= params['max_positions']:
                        break
                    
                    if name not in stock_data or date not in stock_data[name]['data'].index:
                        continue
                    
                    row = stock_data[name]['data'].loc[date]
                    price = row['close_np']
                    
                    if pd.isna(price) or price <= 0:
                        continue
                    
                    total_value = cash + sum(positions[n] * prices.get(n, 0) for n in positions if positions[n] > 0)
                    position_value = total_value * params['position_pct']
                    shares = int(position_value / price / 100) * 100
                    
                    if shares > 0:
                        cost = shares * price * 1.0003
                        if cost <= cash * 0.95:
                            cash -= cost
                            positions[name] = shares
                            buy_prices[name] = price
                            max_prices[name] = price
        
        pv = cash + sum(positions[n] * prices.get(n, 0) for n in positions if positions[n] > 0)
        daily_values.append({'date': date, 'value': pv})
    
    final = daily_values[-1]['value']
    tr = (final - initial_cash) / initial_cash
    years = len(daily_values) / 252
    ar = (1+tr)**(1/years)-1 if years > 0 else 0
    vals = [d['value'] for d in daily_values]
    pk, mdd = vals[0], 0
    for v in vals:
        if v > pk: pk = v
        dd = (pk-v)/pk
        if dd > mdd: mdd = dd
    dr = pd.Series(vals).pct_change().dropna()
    sh = (dr.mean()/dr.std())*np.sqrt(252) if dr.std()>0 else 0
    
    return {
        'total_return': tr,
        'annual_return': ar,
        'max_drawdown': mdd,
        'sharpe': sh,
        'final_value': final,
    }

def main():
    print("=" * 60)
    print("📊 主升浪策略V6 - 简化版（学习财通成长基金核心优化）")
    print("=" * 60)
    
    start_time = time.time()
    
    print("加载数据...")
    combined, stock_data, all_dates = load_data()
    print(f"数据加载完成: {len(stock_data)} 只股票, {len(all_dates)} 个交易日")
    
    print(f"\n核心优化点:")
    print(f"  移动止损: {PARAMS['trailing_stop']*100}%（从5%降低）")
    print(f"  熔断阈值: {PARAMS['circuit_breaker']*100}%（从8%降低）")
    print(f"  再平衡周期: {PARAMS['rebalance_days']}天（从5天缩短）")
    print(f"  动量一致性: >{PARAMS['momentum_consistency']*100}%")
    print(f"  最大波动率: {PARAMS['max_volatility']*100}%")
    
    print(f"\n运行回测...")
    result = run_backtest(combined, stock_data, all_dates, PARAMS)
    
    total_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("📊 回测结果")
    print("=" * 60)
    
    print(f"\n总耗时: {total_time:.1f}秒")
    
    print(f"\n📈 绩效指标:")
    print(f"  总收益: {result['total_return']:.1%}")
    print(f"  年化收益: {result['annual_return']:.1%}")
    print(f"  最大回撤: {result['max_drawdown']:.1%}")
    print(f"  夏普比率: {result['sharpe']:.2f}")
    print(f"  最终净值: {result['final_value']:,.0f}元")
    
    # 与之前版本对比
    print(f"\n📊 版本对比:")
    print(f"  V3（优化基本面）: 收益574.9%, 回撤44.0%, 夏普1.09")
    print(f"  V6（简化版）: 收益{result['total_return']:.1%}, 回撤{result['max_drawdown']:.1%}, 夏普{result['sharpe']:.2f}")
    
    results_path = '/root/projects/ai-quant-stock/backend/data/main_uptrend_v6_summary.json'
    summary = {
        'strategy': 'main_uptrend_v6_simplified',
        'params': PARAMS,
        'result': result,
        'total_time': total_time,
    }
    with open(results_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"\n结果已保存: {results_path}")

if __name__ == '__main__':
    main()
