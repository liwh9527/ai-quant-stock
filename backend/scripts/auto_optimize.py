#!/usr/bin/env python3
"""自动化策略优化框架

功能：
1. 定义参数搜索空间
2. 自动测试不同参数组合
3. 记录结果到数据库
4. 筛选满足条件的策略
5. 生成优化报告

目标：找到总收益>200%且最大回撤<30%的策略
"""

import sqlite3
import pandas as pd
import numpy as np
from itertools import product
from datetime import datetime
import json
import os

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'
RESULTS_DB = '/root/projects/ai-quant-stock/backend/data/optimization_results.db'

# 参数搜索空间
PARAM_SPACE = {
    'max_positions': [2, 3, 4],
    'position_pct': [0.20, 0.25, 0.30, 0.35],
    'stop_loss_atr': [1.8, 2.0, 2.2, 2.5],
    'hard_stop': [0.06, 0.08, 0.10],
    'momentum_threshold': [0.12, 0.15, 0.18, 0.20],
    'rebalance_days': [5, 7, 10],
    'circuit_breaker_threshold': [0.05, 0.06, 0.08],
    'ma_period': [40, 50, 60],  # 大盘均线周期
}

# 目标条件
TARGET = {
    'min_total_return': 2.0,  # 总收益>200%
    'max_drawdown': 0.30,     # 最大回撤<30%
    'min_sharpe': 0.5,        # 夏普>0.5
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
    combined['ma20'] = combined['index'].rolling(20).mean()
    combined['ma40'] = combined['index'].rolling(40).mean()
    combined['ma50'] = combined['index'].rolling(50).mean()
    combined['ma60'] = combined['index'].rolling(60).mean()
    
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
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
        df['momentum'] = df['close'].pct_change(20)
        stock_data[name] = df
        all_dates.update(df.index)
    
    conn.close()
    return combined, stock_data, sorted(all_dates)

def run_backtest(combined, stock_data, all_dates, params):
    """运行单次回测"""
    initial_cash = 1000000
    cash = initial_cash
    positions = {}
    buy_prices = {}
    max_profits = {}
    daily_values = []
    
    market_state = 'bull'
    last_rebalance = None
    current_pool = []
    peak_value = initial_cash
    circuit_breaker = False
    circuit_breaker_until = None
    
    # 获取大盘均线
    ma_col = f"ma{params['ma_period']}"
    
    dates = all_dates
    
    for date in dates:
        prices = {}
        for name, df in stock_data.items():
            if date in df.index:
                prices[name] = df.loc[date]['close']
        
        # 判断市场状态
        if date in combined.index:
            idx_close = combined.loc[date, 'index']
            idx_ma = combined.loc[date, ma_col]
            if not pd.isna(idx_ma):
                if idx_close > idx_ma:
                    market_state = 'bull'
                else:
                    market_state = 'bear'
                    for name in list(positions.keys()):
                        if positions[name] > 0:
                            price = prices.get(name, 0)
                            if price > 0:
                                cash += positions[name] * price * 0.999
                                positions[name] = 0
        
        pv = cash + sum(positions[n] * prices.get(n, 0) for n in positions if positions[n] > 0)
        if pv > peak_value: peak_value = pv
        portfolio_drawdown = (peak_value - pv) / peak_value
        
        # 熔断
        if portfolio_drawdown > params['circuit_breaker_threshold'] and not circuit_breaker:
            circuit_breaker = True
            circuit_breaker_until = date + pd.Timedelta(days=5)
            for name in list(positions.keys()):
                if positions[name] > 0:
                    price = prices.get(name, 0)
                    if price > 0:
                        cash += positions[name] * price * 0.999
                        positions[name] = 0
        
        if circuit_breaker and date >= circuit_breaker_until:
            circuit_breaker = False
            peak_value = pv
        
        # 止损
        for name in list(positions.keys()):
            if positions[name] <= 0: continue
            if name not in stock_data or date not in stock_data[name].index: continue
            row = stock_data[name].loc[date]
            buy_price = buy_prices.get(name, 0)
            price = row['close']
            atr = row.get('atr', 0)
            if buy_price <= 0: continue
            profit_pct = (price - buy_price) / buy_price
            max_profits[name] = max(max_profits.get(name, 0), profit_pct)
            
            sell = False
            if name not in current_pool and profit_pct > 0.02:
                sell = True
            if not sell and not pd.isna(atr) and atr > 0:
                if price <= buy_price - params['stop_loss_atr'] * atr:
                    sell = True
            if not sell and profit_pct < -params['hard_stop']:
                sell = True
            
            if sell:
                cash += positions[name] * price * 0.999
                positions[name] = 0
        
        # 调仓
        if market_state == 'bull' and not circuit_breaker:
            if last_rebalance is None or (date - last_rebalance).days >= params['rebalance_days']:
                last_rebalance = date
                candidates = []
                for name, df in stock_data.items():
                    if date not in df.index: continue
                    row = df.loc[date]
                    close, ma20, momentum = row.get('close'), row.get('ma20'), row.get('momentum')
                    if pd.isna(close) or pd.isna(ma20) or pd.isna(momentum): continue
                    if close < ma20 or momentum < params['momentum_threshold']: continue
                    candidates.append({'name': name, 'score': momentum * 100})
                candidates.sort(key=lambda x: x['score'], reverse=True)
                current_pool = [c['name'] for c in candidates[:params['max_positions']]]
                for name in list(positions.keys()):
                    if positions[name] > 0 and name not in current_pool:
                        price = prices.get(name, 0)
                        if price > 0:
                            cash += positions[name] * price * 0.999
                            positions[name] = 0
        
        # 入场
        if market_state == 'bull' and not circuit_breaker:
            for name in current_pool:
                if name in positions and positions[name] > 0: continue
                if name not in stock_data or date not in stock_data[name].index: continue
                if len([p for p in positions.values() if p > 0]) >= params['max_positions']: break
                row = stock_data[name].loc[date]
                close, ma20 = row.get('close'), row.get('ma20')
                if pd.isna(close) or pd.isna(ma20) or close < ma20: continue
                total_value = cash + sum(positions[n] * prices.get(n, 0) for n in positions if positions[n] > 0)
                shares = int(total_value * params['position_pct'] / close / 100) * 100
                if shares > 0:
                    cost = shares * close * 1.0003
                    if cost <= cash * 0.95:
                        cash -= cost
                        positions[name] = shares
                        buy_prices[name] = close
                        max_profits[name] = 0
        
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
    
    # 年度收益
    yearly = {}
    for d in daily_values:
        y = d['date'].year
        if y not in yearly: yearly[y] = {'s': d['value'], 'e': d['value']}
        yearly[y]['e'] = d['value']
    
    return {
        'total_return': tr,
        'annual_return': ar,
        'max_drawdown': mdd,
        'sharpe': sh,
        'yearly': yearly,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.execute('''INSERT INTO results (params, total_return, annual_return, max_drawdown, sharpe)
        VALUES (?, ?, ?, ?, ?)''', (
        json.dumps(params),
        result['total_return'],
        result['annual_return'],
        result['max_drawdown'],
        result['sharpe']
    ))
    conn.commit()
    conn.close()

def main():
    print("=" * 60)
    print("📊 自动化策略优化框架")
    print("=" * 60)
    
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
    print(f"目标条件: 总收益>{TARGET['min_total_return']*100:.0f}%, 回撤<{TARGET['max_drawdown']*100:.0f}%, 夏普>{TARGET['min_sharpe']}")
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
            if (result['total_return'] >= TARGET['min_total_return'] and
                result['max_drawdown'] <= TARGET['max_drawdown'] and
                result['sharpe'] >= TARGET['min_sharpe']):
                valid_results.append((params, result))
                print(f"✅ [{i+1}/{total_combinations}] 满足条件! 收益:{result['total_return']:.1%}, 回撤:{result['max_drawdown']:.1%}, 夏普:{result['sharpe']:.2f}")
            
            # 更新最佳结果
            if best_result is None or result['total_return'] > best_result['total_return']:
                best_result = result
                best_params = params
            
            # 进度显示
            if (i+1) % 50 == 0:
                print(f"  [{i+1}/{total_combinations}] 当前最佳: 收益:{best_result['total_return']:.1%}, 回撤:{best_result['max_drawdown']:.1%}")
        
        except Exception as e:
            print(f"  [{i+1}/{total_combinations}] 错误: {e}")
    
    # 输出结果
    print("\n" + "=" * 60)
    print("📊 优化结果")
    print("=" * 60)
    
    print(f"\n满足条件的策略: {len(valid_results)} 个")
    
    if valid_results:
        # 按收益排序
        valid_results.sort(key=lambda x: x[1]['total_return'], reverse=True)
        
        print("\n前10个最优策略:")
        for i, (params, result) in enumerate(valid_results[:10]):
            print(f"\n#{i+1}:")
            print(f"  收益: {result['total_return']:.1%}, 回撤: {result['max_drawdown']:.1%}, 夏普: {result['sharpe']:.2f}")
            print(f"  参数: {json.dumps(params, indent=2)}")
    else:
        print("\n没有满足条件的策略")
        print(f"\n最佳策略:")
        print(f"  收益: {best_result['total_return']:.1%}, 回撤: {best_result['max_drawdown']:.1%}, 夏普: {best_result['sharpe']:.2f}")
        print(f"  参数: {json.dumps(best_params, indent=2)}")
    
    # 保存结果
    results_path = '/root/projects/ai-quant-stock/backend/data/optimization_summary.json'
    summary = {
        'total_combinations': total_combinations,
        'valid_count': len(valid_results),
        'best_result': best_result,
        'best_params': best_params,
        'valid_results': [(p, r) for p, r in valid_results[:10]]
    }
    with open(results_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"\n结果已保存: {results_path}")

if __name__ == '__main__':
    main()
