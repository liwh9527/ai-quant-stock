#!/usr/bin/env python3
"""贝叶斯优化版本 - 智能搜索最优参数"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
import time
from skopt import gp_minimize
from skopt.space import Integer, Real
from skopt.utils import use_named_args

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'
RESULTS_DB = '/root/projects/ai-quant-stock/backend/data/optimization_results.db'

# 定义搜索空间
SPACE = [
    Integer(2, 4, name='max_positions'),
    Real(0.20, 0.35, name='position_pct'),
    Real(1.8, 2.5, name='stop_loss_atr'),
    Real(0.06, 0.10, name='hard_stop'),
    Real(0.12, 0.20, name='momentum_threshold'),
    Integer(5, 10, name='rebalance_days'),
    Real(0.05, 0.08, name='circuit_breaker_threshold'),
    Integer(40, 60, name='ma_period'),
]

# 目标条件
TARGET = {
    'min_total_return': 2.0,
    'max_drawdown': 0.30,
    'min_sharpe': 0.5,
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
    
    # 预计算所有均线 (40-60)
    for period in range(40, 61):
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
        
        # 预计算所有指标
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
        df['momentum'] = df['close'].pct_change(20)
        
        # 预计算为numpy数组
        df['close_np'] = df['close'].values
        df['ma20_np'] = df['ma20'].values
        df['atr_np'] = df['atr'].values
        df['momentum_np'] = df['momentum'].values
        
        stock_data[name] = df
        all_dates.update(df.index)
    
    conn.close()
    return combined, stock_data, sorted(all_dates)

def run_backtest(combined, stock_data, all_dates, params):
    """运行回测"""
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
    print("🚀 贝叶斯优化版本 - 智能搜索最优参数")
    print("=" * 60)
    
    start_time = time.time()
    
    # 加载数据
    print("加载数据...")
    combined, stock_data, all_dates = load_data()
    print(f"数据加载完成: {len(stock_data)} 只股票, {len(all_dates)} 个交易日")
    
    # 初始化结果数据库
    if os.path.exists(RESULTS_DB):
        os.remove(RESULTS_DB)
    
    # 定义目标函数
    @use_named_args(SPACE)
    def objective(**params):
        # 转换参数类型
        params['max_positions'] = int(params['max_positions'])
        params['rebalance_days'] = int(params['rebalance_days'])
        params['ma_period'] = int(params['ma_period'])
        
        # 运行回测
        result = run_backtest(combined, stock_data, all_dates, params)
        
        # 保存结果
        save_result(params, result)
        
        # 计算目标值（最小化负收益 + 回撤惩罚）
        # 目标：最大化收益，同时控制回撤
        if result['max_drawdown'] > 0.30:
            # 回撤超过30%，严重惩罚
            penalty = (result['max_drawdown'] - 0.30) * 100
        else:
            penalty = 0
        
        # 目标值 = -收益 + 惩罚（最小化）
        objective_value = -result['total_return'] + penalty
        
        print(f"  测试: 收益={result['total_return']:.1%}, 回撤={result['max_drawdown']:.1%}, 夏普={result['sharpe']:.2f}")
        
        return objective_value
    
    # 运行贝叶斯优化
    print(f"\n开始贝叶斯优化 (目标: 测试100个组合)...")
    print(f"目标条件: 总收益>200%, 回撤<30%, 夏普>0.5")
    print()
    
    result = gp_minimize(
        objective,
        SPACE,
        n_calls=100,  # 只测试100个组合
        random_state=42,
        verbose=False
    )
    
    # 输出结果
    total_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("📊 优化结果")
    print("=" * 60)
    
    print(f"\n总耗时: {total_time/60:.1f} 分钟")
    print(f"测试组合数: 100")
    print(f"平均速度: {100/total_time:.1f} 个/秒")
    
    # 获取最优参数
    best_params = {
        'max_positions': int(result.x[0]),
        'position_pct': result.x[1],
        'stop_loss_atr': result.x[2],
        'hard_stop': result.x[3],
        'momentum_threshold': result.x[4],
        'rebalance_days': int(result.x[5]),
        'circuit_breaker_threshold': result.x[6],
        'ma_period': int(result.x[7]),
    }
    
    # 运行最优参数的回测
    best_result = run_backtest(combined, stock_data, all_dates, best_params)
    
    print(f"\n最优策略:")
    print(f"  收益: {best_result['total_return']:.1%}")
    print(f"  回撤: {best_result['max_drawdown']:.1%}")
    print(f"  夏普: {best_result['sharpe']:.2f}")
    print(f"\n最优参数:")
    print(json.dumps(best_params, indent=2))
    
    # 检查是否满足目标条件
    if (best_result['total_return'] >= TARGET['min_total_return'] and
        best_result['max_drawdown'] <= TARGET['max_drawdown'] and
        best_result['sharpe'] >= TARGET['min_sharpe']):
        print(f"\n✅ 满足所有目标条件!")
    else:
        print(f"\n⚠️ 未完全满足目标条件")
        if best_result['total_return'] < TARGET['min_total_return']:
            print(f"  - 收益不足: {best_result['total_return']:.1%} < {TARGET['min_total_return']*100:.0f}%")
        if best_result['max_drawdown'] > TARGET['max_drawdown']:
            print(f"  - 回撤过大: {best_result['max_drawdown']:.1%} > {TARGET['max_drawdown']*100:.0f}%")
        if best_result['sharpe'] < TARGET['min_sharpe']:
            print(f"  - 夏普不足: {best_result['sharpe']:.2f} < {TARGET['min_sharpe']}")
    
    # 保存结果
    results_path = '/root/projects/ai-quant-stock/backend/data/optimization_summary.json'
    summary = {
        'method': 'bayesian_optimization',
        'total_calls': 100,
        'total_time': total_time,
        'best_params': best_params,
        'best_result': best_result,
        'target_met': (best_result['total_return'] >= TARGET['min_total_return'] and
                      best_result['max_drawdown'] <= TARGET['max_drawdown'] and
                      best_result['sharpe'] >= TARGET['min_sharpe'])
    }
    with open(results_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"\n结果已保存: {results_path}")

if __name__ == '__main__':
    main()
