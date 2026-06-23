#!/usr/bin/env python3
"""主升浪集中策略 - 快速验证版本

核心思路：
1. 识别主升浪股票（突破+强动量+放量）
2. 集中持仓1-3只
3. 主升浪结束后退出
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
import time

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'
RESULTS_DB = '/root/projects/ai-quant-stock/backend/data/main_uptrend_results.db'

# 主升浪策略参数
MAIN_UPTREND_PARAMS = {
    'max_positions': 3,           # 最多持有3只
    'position_pct': 0.30,         # 单只股票最大仓位30%
    'momentum_threshold': 0.30,   # 30%动量阈值（主升浪特征）
    'volume_ratio': 1.5,          # 成交量放大1.5倍
    'trailing_stop': 0.08,        # 8%移动止损
    'ma_stop': True,              # 跌破MA20止损
    'rebalance_days': 5,          # 5天检查一次
    'circuit_breaker': 0.15,      # 15%组合回撤熔断
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
        df['momentum'] = df['close'].pct_change(20)  # 20日动量
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()  # 成交量比率
        df['high_20'] = df['high'].rolling(20).max()  # 20日最高价
        df['breakout'] = (df['close'] > df['high_20'].shift(1)).astype(int)  # 突破信号
        
        # 相对强度（相对于大盘）
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
        
        # 获取指标
        close = row.get('close_np', 0)
        ma20 = row.get('ma20_np', 0)
        ma60 = row.get('ma60_np', 0)
        momentum = row.get('momentum_np', 0)
        volume_ratio = row.get('volume_ratio_np', 0)
        breakout = row.get('breakout_np', 0)
        relative_strength = row.get('relative_strength_np', 0)
        
        # 检查数据有效性
        if pd.isna(close) or pd.isna(ma20) or pd.isna(ma60):
            continue
        if pd.isna(momentum) or pd.isna(volume_ratio) or pd.isna(breakout):
            continue
        
        # 主升浪条件
        conditions = {
            'price_above_ma': close > ma20 and close > ma60,  # 价格在均线之上
            'ma_bullish': ma20 > ma60,  # 均线多头排列
            'strong_momentum': momentum > params['momentum_threshold'],  # 强动量
            'volume_surge': volume_ratio > params['volume_ratio'],  # 放量
            'breakout': breakout == 1,  # 突破20日新高
            'relative_strength': relative_strength > 0.1,  # 相对强度>10%
        }
        
        # 计算综合得分
        score = sum(conditions.values()) / len(conditions)
        
        # 只选择得分>70%的股票
        if score >= 0.7:
            main_uptrend_stocks.append({
                'name': name,
                'score': score,
                'momentum': momentum,
                'volume_ratio': volume_ratio,
                'breakout': breakout,
            })
    
    # 按得分和动量排序
    main_uptrend_stocks.sort(key=lambda x: (x['score'], x['momentum']), reverse=True)
    
    return main_uptrend_stocks[:params['max_positions']]

def run_main_uptrend_backtest(combined, stock_data, all_dates, params):
    """运行主升浪策略回测"""
    initial_cash = 1000000
    cash = initial_cash
    positions = {}
    buy_prices = {}
    max_prices = {}  # 记录最高价，用于移动止损
    daily_values = []
    
    last_rebalance = None
    current_pool = []
    peak_value = initial_cash
    circuit_breaker = False
    circuit_breaker_until = None
    
    for date in all_dates:
        # 获取当前价格
        prices = {}
        for name, df in stock_data.items():
            if date in df.index:
                prices[name] = df.loc[date, 'close_np']
        
        # 计算组合价值
        pv = cash + sum(positions[n] * prices.get(n, 0) for n in positions if positions[n] > 0)
        if pv > peak_value: peak_value = pv
        portfolio_drawdown = (peak_value - pv) / peak_value
        
        # 熔断检查
        if portfolio_drawdown > params['circuit_breaker'] and not circuit_breaker:
            circuit_breaker = True
            circuit_breaker_until = date + pd.Timedelta(days=10)
            print(f"  熔断触发: {date.strftime('%Y-%m-%d')}, 回撤: {portfolio_drawdown:.1%}")
            # 清仓
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
            
            # 更新最高价
            if price > max_price:
                max_prices[name] = price
                max_price = price
            
            # 计算收益
            profit_pct = (price - buy_price) / buy_price
            
            # 止损条件
            sell = False
            
            # 1. 跌破MA20止损
            if params['ma_stop'] and 'ma20_np' in row and not pd.isna(row['ma20_np']):
                if price < row['ma20_np']:
                    sell = True
                    print(f"  跌破MA20止损: {name}, 价格: {price:.2f}, MA20: {row['ma20_np']:.2f}")
            
            # 2. 移动止损：从最高点回撤8%
            if not sell:
                trailing_stop_price = max_price * (1 - params['trailing_stop'])
                if price < trailing_stop_price:
                    sell = True
                    print(f"  移动止损: {name}, 价格: {price:.2f}, 最高点: {max_price:.2f}, 止损价: {trailing_stop_price:.2f}")
            
            # 3. 动量衰减止损
            if not sell and 'momentum_np' in row and not pd.isna(row['momentum_np']):
                if row['momentum_np'] < 0.10:  # 动量<10%
                    sell = True
                    print(f"  动量衰减止损: {name}, 动量: {row['momentum_np']:.1%}")
            
            if sell:
                cash += positions[name] * price * 0.999
                positions[name] = 0
                if name in buy_prices: del buy_prices[name]
                if name in max_prices: del max_prices[name]
        
        # 识别主升浪股票
        if not circuit_breaker:
            main_uptrend_stocks = identify_main_uptrend(stock_data, date, params)
            
            # 检查是否需要调仓
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
                        print(f"  卖出非主升浪: {name}, 价格: {price:.2f}")
            
            # 买入新的主升浪股票
            for stock in main_uptrend_stocks:
                name = stock['name']
                if name in positions and positions[name] > 0:
                    continue  # 已持有
                
                if len([p for p in positions.values() if p > 0]) >= params['max_positions']:
                    break  # 已满仓
                
                if name not in stock_data or date not in stock_data[name].index:
                    continue
                
                row = stock_data[name].loc[date]
                price = row['close_np']
                
                if pd.isna(price) or price <= 0:
                    continue
                
                # 计算仓位
                total_value = cash + sum(positions[n] * prices.get(n, 0) for n in positions if positions[n] > 0)
                position_value = total_value * params['position_pct']
                shares = int(position_value / price / 100) * 100
                
                if shares > 0:
                    cost = shares * price * 1.0003  # 手续费
                    if cost <= cash * 0.95:  # 保留5%现金
                        cash -= cost
                        positions[name] = shares
                        buy_prices[name] = price
                        max_prices[name] = price
                        print(f"  买入主升浪: {name}, 价格: {price:.2f}, 数量: {shares}, 得分: {stock['score']:.1%}, 动量: {stock['momentum']:.1%}")
        
        # 记录每日净值
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
    
    # 计算交易统计
    trades = []
    for i in range(1, len(daily_values)):
        if daily_values[i]['value'] != daily_values[i-1]['value']:
            trades.append({
                'date': daily_values[i]['date'],
                'value': daily_values[i]['value'],
                'change': daily_values[i]['value'] / daily_values[i-1]['value'] - 1
            })
    
    return {
        'total_return': tr,
        'annual_return': ar,
        'max_drawdown': mdd,
        'sharpe': sh,
        'final_value': final,
        'total_trades': len(trades),
        'win_rate': len([t for t in trades if t['change'] > 0]) / len(trades) if trades else 0,
    }

def main():
    print("=" * 60)
    print("🚀 主升浪集中策略 - 快速验证")
    print("=" * 60)
    
    start_time = time.time()
    
    # 加载数据
    print("加载数据...")
    combined, stock_data, all_dates = load_data()
    print(f"数据加载完成: {len(stock_data)} 只股票, {len(all_dates)} 个交易日")
    
    # 显示策略参数
    print(f"\n策略参数:")
    for key, value in MAIN_UPTREND_PARAMS.items():
        print(f"  {key}: {value}")
    
    # 运行回测
    print(f"\n运行回测...")
    result = run_main_uptrend_backtest(combined, stock_data, all_dates, MAIN_UPTREND_PARAMS)
    
    # 计算时间
    total_time = time.time() - start_time
    
    # 输出结果
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
    
    print(f"\n📊 交易统计:")
    print(f"  交易次数: {result['total_trades']}")
    print(f"  胜率: {result['win_rate']:.1%}")
    
    # 评估是否达标
    print(f"\n🎯 目标评估:")
    target_met = True
    
    if result['total_return'] >= 3.0:  # 300%
        print(f"  ✅ 总收益: {result['total_return']:.1%} >= 300%")
    else:
        print(f"  ❌ 总收益: {result['total_return']:.1%} < 300%")
        target_met = False
    
    if result['max_drawdown'] <= 0.25:  # 25%
        print(f"  ✅ 最大回撤: {result['max_drawdown']:.1%} <= 25%")
    else:
        print(f"  ❌ 最大回撤: {result['max_drawdown']:.1%} > 25%")
        target_met = False
    
    if result['sharpe'] >= 0.8:
        print(f"  ✅ 夏普比率: {result['sharpe']:.2f} >= 0.8")
    else:
        print(f"  ❌ 夏普比率: {result['sharpe']:.2f} < 0.8")
        target_met = False
    
    if target_met:
        print(f"\n🎉 策略达标！可以部署到模拟账户")
    else:
        print(f"\n⚠️ 策略未完全达标，需要优化")
    
    # 保存结果
    results_path = '/root/projects/ai-quant-stock/backend/data/main_uptrend_summary.json'
    summary = {
        'strategy': 'main_uptrend_concentrated',
        'params': MAIN_UPTREND_PARAMS,
        'result': result,
        'target_met': target_met,
        'total_time': total_time,
    }
    with open(results_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"\n结果已保存: {results_path}")

if __name__ == '__main__':
    main()
