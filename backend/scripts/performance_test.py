#!/usr/bin/env python3
"""性能对比测试：原版 vs 优化版"""

import time
import sqlite3
import pandas as pd
import numpy as np
from itertools import product
from multiprocessing import Pool, cpu_count

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# 简化的参数空间用于测试
PARAM_SPACE_SMALL = {
    'max_positions': [2, 3],
    'position_pct': [0.20, 0.25],
    'stop_loss_atr': [1.8, 2.0],
    'hard_stop': [0.06, 0.08],
    'momentum_threshold': [0.12, 0.15],
    'rebalance_days': [5, 7],
    'circuit_breaker_threshold': [0.05, 0.06],
    'ma_period': [40, 50],
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
    
    # 预计算所有均线
    for period in [20, 40, 50, 60]:
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
        LIMIT 50
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
        
        # 预计算所有指标
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
        df['momentum'] = df['close'].pct_change(20)
        
        # 预计算为numpy数组 (更快)
        df['close_np'] = df['close'].values
        df['ma20_np'] = df['ma20'].values
        df['atr_np'] = df['atr'].values
        df['momentum_np'] = df['momentum'].values
        
        stock_data[name] = df
        all_dates.update(df.index)
    
    conn.close()
    return combined, stock_data, sorted(all_dates)

def run_backtest_original(combined, stock_data, all_dates, params):
    """原版回测函数"""
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
    
    return {
        'total_return': tr,
        'annual_return': ar,
        'max_drawdown': mdd,
        'sharpe': sh,
    }

def run_backtest_optimized(combined, stock_data, all_dates, params):
    """优化版回测函数"""
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
    
    ma_col = f"ma{params['ma_period']}"
    dates = all_dates
    
    # 预提取大盘数据
    combined_np = combined[['index', ma_col]].values
    combined_dates = combined.index
    
    for i, date in enumerate(dates):
        # 快速获取价格
        prices = {}
        for name, df in stock_data.items():
            if date in df.index:
                prices[name] = df.loc[date, 'close_np']
        
        # 判断市场状态
        if date in combined_dates:
            idx = combined_dates.get_loc(date)
            idx_close = combined_np[idx, 0]
            idx_ma = combined_np[idx, 1]
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
            price = row['close_np']
            atr = row.get('atr_np', 0)
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
                    close, ma20, momentum = row.get('close_np'), row.get('ma20_np'), row.get('momentum_np')
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
                close, ma20 = row.get('close_np'), row.get('ma20_np')
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
    
    return {
        'total_return': tr,
        'annual_return': ar,
        'max_drawdown': mdd,
        'sharpe': sh,
    }

def test_single_backtest(backtest_func, combined, stock_data, all_dates, params):
    """测试单次回测性能"""
    start = time.time()
    result = backtest_func(combined, stock_data, all_dates, params)
    end = time.time()
    return end - start, result

def main():
    print("=" * 60)
    print("📊 性能对比测试：原版 vs 优化版")
    print("=" * 60)
    
    # 加载数据
    print("加载数据...")
    combined, stock_data, all_dates = load_data()
    print(f"数据加载完成: {len(stock_data)} 只股票, {len(all_dates)} 个交易日")
    
    # 生成测试参数组合
    param_names = list(PARAM_SPACE_SMALL.keys())
    param_values = list(PARAM_SPACE_SMALL.values())
    param_combinations = list(product(*param_values))
    total_combinations = len(param_combinations)
    
    print(f"测试参数组合数: {total_combinations}")
    print(f"CPU核心数: {cpu_count()}")
    print()
    
    # 测试原版性能
    print("测试原版性能...")
    original_times = []
    for i, values in enumerate(param_combinations[:10]):  # 只测试前10个
        params = dict(zip(param_names, values))
        time_taken, result = test_single_backtest(run_backtest_original, combined, stock_data, all_dates, params)
        original_times.append(time_taken)
        print(f"  [{i+1}/10] 耗时: {time_taken:.3f}秒")
    
    original_avg = np.mean(original_times)
    print(f"原版平均耗时: {original_avg:.3f}秒/个")
    print()
    
    # 测试优化版性能
    print("测试优化版性能...")
    optimized_times = []
    for i, values in enumerate(param_combinations[:10]):  # 只测试前10个
        params = dict(zip(param_names, values))
        time_taken, result = test_single_backtest(run_backtest_optimized, combined, stock_data, all_dates, params)
        optimized_times.append(time_taken)
        print(f"  [{i+1}/10] 耗时: {time_taken:.3f}秒")
    
    optimized_avg = np.mean(optimized_times)
    print(f"优化版平均耗时: {optimized_avg:.3f}秒/个")
    print()
    
    # 计算加速比
    speedup = original_avg / optimized_avg
    print(f"加速比: {speedup:.2f}倍")
    
    # 预测总时间
    original_total = original_avg * 15552 / 3600
    optimized_total = optimized_avg * 15552 / 3600
    
    print(f"\n预测总时间:")
    print(f"  原版: {original_total:.1f}小时")
    print(f"  优化版: {optimized_total:.1f}小时")
    print(f"  节省时间: {original_total - optimized_total:.1f}小时")
    
    # 测试多进程性能
    print(f"\n测试多进程性能 ({cpu_count()}核心)...")
    
    def worker(args):
        params, idx = args
        time_taken, result = test_single_backtest(run_backtest_optimized, combined, stock_data, all_dates, params)
        return time_taken
    
    args_list = [(dict(zip(param_names, values)), i) for i, values in enumerate(param_combinations[:20])]
    
    start = time.time()
    with Pool(processes=cpu_count()) as pool:
        times = pool.map(worker, args_list)
    end = time.time()
    
    multiprocess_total = end - start
    multiprocess_avg = multiprocess_total / len(args_list)
    
    print(f"多进程总耗时: {multiprocess_total:.3f}秒")
    print(f"多进程平均耗时: {multiprocess_avg:.3f}秒/个")
    print(f"多进程加速比: {original_avg / multiprocess_avg:.2f}倍")
    
    multiprocess_total_hours = multiprocess_avg * 15552 / 3600
    print(f"多进程预测总时间: {multiprocess_total_hours:.1f}小时")

if __name__ == '__main__':
    main()
