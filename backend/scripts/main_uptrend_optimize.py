#!/usr/bin/env python3
"""主升浪策略参数优化 - 降低回撤

优化目标：
1. 最大回撤 < 25%
2. 总收益 > 400%
3. 夏普比率 > 0.8
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
import time
from itertools import product

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'
RESULTS_DB = '/root/projects/ai-quant-stock/backend/data/main_uptrend_optimization.db'

# 优化参数空间
PARAM_SPACE = {
    'max_positions': [3, 4, 5],           # 持仓数量
    'position_pct': [0.15, 0.20, 0.25],   # 仓位比例
    'momentum_threshold': [0.30, 0.35, 0.40],  # 动量阈值
    'volume_ratio': [1.5, 1.8, 2.0],      # 成交量比率
    'trailing_stop': [0.05, 0.06, 0.07],  # 移动止损
    'circuit_breaker': [0.08, 0.10, 0.12], # 熔断阈值
    'rebalance_days': [5, 7, 10],          # 再平衡天数
}

# 目标条件
TARGET = {
    'max_drawdown': 0.25,     # 最大回撤<25%
    'min_total_return': 4.0,  # 总收益>400%
    'min_sharpe': 0.8,        # 夏普>0.8
}

def load_data():
    """加载股票数据"""
    conn = sqlite3.connect(DB_PATH)
    start_date = '2021-01-01'
    
    # 构建综合大盘指标
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
    
    # 预计算大盘均线
    for period in [20, 60]:
        combined[f'ma{period}'] = combined['index'].rolling(period).mean()
    
    # 加载股票
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
        LIMIT 100
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
        
        # 计算技术指标
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
        
        # 主升浪特征指标
        df['momentum'] = df['close'].pct_change(20)
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        df['high_20'] = df['high'].rolling(20).max()
        df['breakout'] = (df['close'] > df['high_20'].shift(1)).astype(int)
        df['relative_strength'] = df['close'].pct_change(20) - combined['index'].pct_change(20)
        
        # 预计算为numpy数组
        df['close_np'] = df['close'].values
        df['ma20_np'] = df['ma20'].values
        df['ma60_np'] = df['ma60'].values
        df['atr_np'] = df['atr'].values
        df['momentum_np'] = df['momentum'].values
        df['volume_ratio_np'] = df['volume_ratio'].values
        df['breakout_np'] = df['breakout'].values
        df['relative_strength_np'] = df['relative_strength'].values
        
        stock_data[name] = df
        all_dates.update(df.index)
    
    conn.close()
    return combined, stock_data, sorted(all_dates)

def identify_main_uptrend(stock_data, date, params):
    """识别主升浪股票"""
    main_uptrend_stocks = []
    
    for name, df in stock_data.items():
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
        
        if pd.isna(close) or pd.isna(ma20) or pd.isna(ma60):
            continue
        if pd.isna(momentum) or pd.isna(volume_ratio) or pd.isna(breakout):
            continue
        
        # 主升浪条件
        conditions = {
            'price_above_ma': close > ma20 and close > ma60,
            'ma_bullish': ma20 > ma60,
            'strong_momentum': momentum > params['momentum_threshold'],
            'volume_surge': volume_ratio > params['volume_ratio'],
            'breakout': breakout == 1,
            'relative_strength': relative_strength > 0.1,
        }
        
        score = sum(conditions.values()) / len(conditions)
        
        if score >= 0.7:
            main_uptrend_stocks.append({
                'name': name,
                'score': score,
                'momentum': momentum,
                'volume_ratio': volume_ratio,
                'breakout': breakout,
            })
    
    main_uptrend_stocks.sort(key=lambda x: (x['score'], x['momentum']), reverse=True)
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
    current_pool = []
    peak_value = initial_cash
    circuit_breaker = False
    circuit_breaker_until = None
    
    for date in all_dates:
        prices = {}
        for name, df in stock_data.items():
            if date in df.index:
                prices[name] = df.loc[date, 'close_np']
        
        pv = cash + sum(positions[n] * prices.get(n, 0) for n in positions if positions[n] > 0)
        if pv > peak_value: peak_value = pv
        portfolio_drawdown = (peak_value - pv) / peak_value
        
        # 熔断检查
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
        
        # 止损检查
        for name in list(positions.keys()):
            if positions[name] <= 0: continue
            if name not in stock_data or date not in stock_data[name].index: continue
            
            row = stock_data[name].loc[date]
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
            
            # 移动止损
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
        
        # 识别主升浪股票
        if not circuit_breaker:
            main_uptrend_stocks = identify_main_uptrend(stock_data, date, params)
            
            current_holdings = [name for name, shares in positions.items() if shares > 0]
            new_pool = [stock['name'] for stock in main_uptrend_stocks]
            
            # 卖出不在主升浪池中的股票
            for name in current_holdings:
                if name not in new_pool:
                    price = prices.get(name, 0)
                    if price > 0:
                        cash += positions[name] * price * 0.999
                        positions[name] = 0
                        if name in buy_prices: del buy_prices[name]
                        if name in max_prices: del max_prices[name]
            
            # 买入新的主升浪股票
            for stock in main_uptrend_stocks:
                name = stock['name']
                if name in positions and positions[name] > 0:
                    continue
                
                if len([p for p in positions.values() if p > 0]) >= params['max_positions']:
                    break
                
                if name not in stock_data or date not in stock_data[name].index:
                    continue
                
                row = stock_data[name].loc[date]
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
    
    # 计算统计
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

def save_result(params, result):
    """保存结果到数据库"""
    conn = sqlite3.connect(RESULTS_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        params TEXT,
        total_return REAL,
        annual_return REAL,
        max_drawdown REAL,
        sharpe REAL,
        final_value REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.execute('''INSERT INTO results (params, total_return, annual_return, max_drawdown, sharpe, final_value)
        VALUES (?, ?, ?, ?, ?, ?)''', (
        json.dumps(params),
        result['total_return'],
        result['annual_return'],
        result['max_drawdown'],
        result['sharpe'],
        result['final_value']
    ))
    conn.commit()
    conn.close()

def main():
    print("=" * 60)
    print("🔧 主升浪策略参数优化 - 降低回撤")
    print("=" * 60)
    
    start_time = time.time()
    
    # 加载数据
    print("加载数据...")
    combined, stock_data, all_dates = load_data()
    print(f"数据加载完成: {len(stock_data)} 只股票, {len(all_dates)} 个交易日")
    
    # 生成参数组合
    param_names = list(PARAM_SPACE.keys())
    param_values = list(PARAM_SPACE.values())
    param_combinations = list(product(*param_values))
    total_combinations = len(param_combinations)
    
    print(f"参数组合总数: {total_combinations}")
    print(f"目标条件:")
    print(f"  最大回撤: <{TARGET['max_drawdown']*100:.0f}%")
    print(f"  总收益: >{TARGET['min_total_return']*100:.0f}%")
    print(f"  夏普比率: >{TARGET['min_sharpe']}")
    print()
    
    # 初始化结果数据库
    if os.path.exists(RESULTS_DB):
        os.remove(RESULTS_DB)
    
    # 遍历参数组合
    best_result = None
    best_params = None
    valid_results = []
    
    for i, values in enumerate(param_combinations):
        params = dict(zip(param_names, values))
        
        try:
            result = run_backtest(combined, stock_data, all_dates, params)
            save_result(params, result)
            
            # 检查是否满足目标条件
            if (result['max_drawdown'] <= TARGET['max_drawdown'] and
                result['total_return'] >= TARGET['min_total_return'] and
                result['sharpe'] >= TARGET['min_sharpe']):
                valid_results.append((params, result))
                print(f"✅ [{i+1}/{total_combinations}] 满足条件! 收益:{result['total_return']:.1%}, 回撤:{result['max_drawdown']:.1%}, 夏普:{result['sharpe']:.2f}")
            
            # 更新最佳结果（优先低回撤）
            if best_result is None or (result['max_drawdown'] <= TARGET['max_drawdown'] and result['total_return'] > best_result['total_return']):
                best_result = result
                best_params = params
            
            # 进度显示
            if (i+1) % 50 == 0:
                print(f"  [{i+1}/{total_combinations}] 当前最佳: 收益:{best_result['total_return']:.1%}, 回撤:{best_result['max_drawdown']:.1%}")
        
        except Exception as e:
            print(f"  [{i+1}/{total_combinations}] 错误: {e}")
    
    # 输出结果
    total_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("📊 优化结果")
    print("=" * 60)
    
    print(f"\n总耗时: {total_time/60:.1f}分钟")
    print(f"测试组合数: {total_combinations}")
    print(f"满足条件的策略: {len(valid_results)} 个")
    
    if valid_results:
        # 按收益排序
        valid_results.sort(key=lambda x: x[1]['total_return'], reverse=True)
        
        print("\n🏆 最优策略 (前5名):")
        for i, (params, result) in enumerate(valid_results[:5]):
            print(f"\n#{i+1}:")
            print(f"  收益: {result['total_return']:.1%}")
            print(f"  回撤: {result['max_drawdown']:.1%}")
            print(f"  夏普: {result['sharpe']:.2f}")
            print(f"  年化: {result['annual_return']:.1%}")
            print(f"  最终净值: {result['final_value']:,.0f}元")
            print(f"  参数: {json.dumps(params, indent=2)}")
    else:
        print("\n⚠️ 没有满足所有条件的策略")
        if best_result:
            print(f"\n最佳策略 (未完全达标):")
            print(f"  收益: {best_result['total_return']:.1%}")
            print(f"  回撤: {best_result['max_drawdown']:.1%}")
            print(f"  夏普: {best_result['sharpe']:.2f}")
            print(f"  参数: {json.dumps(best_params, indent=2)}")
    
    # 保存结果
    results_path = '/root/projects/ai-quant-stock/backend/data/main_uptrend_optimization_summary.json'
    summary = {
        'total_combinations': total_combinations,
        'valid_count': len(valid_results),
        'target': TARGET,
        'best_results': [(p, r) for p, r in valid_results[:10]] if valid_results else [],
        'total_time': total_time,
    }
    with open(results_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"\n结果已保存: {results_path}")

if __name__ == '__main__':
    main()
