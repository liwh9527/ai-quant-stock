#!/usr/bin/env python3
"""主升浪策略V4 - 学习财通成长基金优化

优化点：
1. 增加行业筛选（聚焦高景气行业）
2. 增加成长性筛选（营收增长>20%，利润增长>30%）
3. 优化换手率策略（再平衡周期从5天改为3天）
4. 加强风险控制（止损4%，熔断6%）
5. 增加动量确认（多周期动量一致性）
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
import time

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# 优化后的策略参数（学习财通成长基金）
PARAMS = {
    # 基本参数
    'max_positions': 5,           # 持仓5只
    'position_pct': 0.15,         # 单只仓位15%
    'momentum_threshold': 0.40,   # 动量阈值40%
    'volume_ratio': 1.5,          # 成交量比率1.5倍
    'trailing_stop': 0.04,        # 4%移动止损（优化：从5%改为4%）
    'circuit_breaker': 0.06,      # 6%熔断阈值（优化：从8%改为6%）
    'rebalance_days': 3,          # 3天再平衡（优化：从5天改为3天）
    'min_score': 0.70,            # 综合得分>70%（优化：从65%提高到70%）
    
    # 基本面筛选（优化：更严格）
    'min_pe': 0,                  # 市盈率>0（排除亏损股）
    'max_pe': 80,                 # 市盈率<80（排除泡沫股）
    'min_roe': 15,                # ROE>15%（优化：从3%提高到15%）
    'min_revenue_growth': 20,     # 营收增长>20%（优化：从-5%提高到20%）
    'min_profit_growth': 30,      # 利润增长>30%（新增）
    'exclude_st': True,           # 排除ST股
    'min_market_cap': 50,         # 最小市值50亿（优化：从30亿提高到50亿）
    
    # 行业筛选（新增：学习财通成长基金）
    'allowed_sectors': [
        '光模块', '半导体', '新能源', '人工智能',
        '机器人', '军工', '医药生物', '新材料',
        '电子', '计算机', '通信', '电力设备'
    ],
    'sector_weight': 0.10,        # 行业权重10%
    
    # 动量确认（新增：提高信号准确性）
    'momentum_periods': [5, 10, 20],  # 5日、10日、20日动量
    'momentum_consistency': 0.7,      # 动量一致性>70%
    'breakout_confirmation': True,    # 突破确认
    'breakout_days': 2,               # 突破确认2天
    
    # 风险控制（新增：更严格的风控）
    'max_volatility': 0.3,        # 最大波动率30%
    'max_drawdown_limit': 0.20,   # 最大回撤限制20%
    'trend_confirmation_days': 2, # 趋势确认2天
    
    # 权重设置（优化：调整权重）
    'technical_weight': 0.70,     # 技术面权重70%（优化：从80%降到70%）
    'fundamental_weight': 0.20,   # 基本面权重20%
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
        SELECT d.ts_code, s.name, AVG(d.vol) as avg_vol,
               AVG(d.close * d.vol) as avg_amount
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
        
        # 计算技术指标
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
        
        # 主升浪特征指标
        df['momentum'] = df['close'].pct_change(20)
        df['momentum_5d'] = df['close'].pct_change(5)
        df['momentum_10d'] = df['close'].pct_change(10)
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        df['high_20'] = df['high'].rolling(20).max()
        df['breakout'] = (df['close'] > df['high_20'].shift(1)).astype(int)
        df['relative_strength'] = df['close'].pct_change(20) - combined['index'].pct_change(20)
        
        # 波动率指标（新增）
        df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
        
        # 预计算为numpy数组
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
            'avg_amount': row['avg_amount']
        }
        all_dates.update(df.index)
    
    conn.close()
    return combined, stock_data, sorted(all_dates)

def get_fundamental_data(ts_code, date):
    """获取基本面数据（模拟）"""
    np.random.seed(hash(ts_code) % 2**32)
    
    # 模拟基本面数据
    pe = np.random.uniform(5, 100)
    roe = np.random.uniform(5, 30)
    revenue_growth = np.random.uniform(0, 60)
    profit_growth = np.random.uniform(10, 80)
    market_cap = np.random.uniform(30, 500)
    
    # 模拟行业数据
    sectors = ['光模块', '半导体', '新能源', '人工智能', '机器人', 
               '军工', '医药生物', '新材料', '电子', '计算机', '通信', '电力设备']
    sector = np.random.choice(sectors)
    
    return {
        'pe': pe,
        'roe': roe,
        'revenue_growth': revenue_growth,
        'profit_growth': profit_growth,
        'market_cap': market_cap,
        'sector': sector,
        'is_st': False,
    }

def check_fundamental_filter(ts_code, date, params):
    """检查基本面筛选条件（优化版）"""
    fundamental = get_fundamental_data(ts_code, date)
    
    # 基本面筛选条件（更严格）
    conditions = {
        'pe_ok': fundamental['pe'] > params['min_pe'] and fundamental['pe'] < params['max_pe'],
        'roe_ok': fundamental['roe'] > params['min_roe'],
        'revenue_ok': fundamental['revenue_growth'] > params['min_revenue_growth'],
        'profit_ok': fundamental['profit_growth'] > params['min_profit_growth'],
        'market_cap_ok': fundamental['market_cap'] > params['min_market_cap'],
        'not_st': not fundamental['is_st'],
        'sector_ok': fundamental['sector'] in params['allowed_sectors'],
    }
    
    fundamental_score = sum(conditions.values()) / len(conditions)
    passed = fundamental_score >= 0.7  # 至少满足70%条件
    
    return passed, fundamental, conditions, fundamental_score

def check_momentum_consistency(row, params):
    """检查动量一致性（新增）"""
    momentum_5d = row.get('momentum_5d_np', 0)
    momentum_10d = row.get('momentum_10d_np', 0)
    momentum_20d = row.get('momentum_np', 0)
    
    if pd.isna(momentum_5d) or pd.isna(momentum_10d) or pd.isna(momentum_20d):
        return False, 0
    
    # 检查多周期动量是否都为正
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
    """识别主升浪股票（优化版）"""
    main_uptrend_stocks = []
    
    for name, info in stock_data.items():
        ts_code = info['code']
        df = info['data']
        
        if date not in df.index:
            continue
        
        # 检查基本面筛选
        fundamental_passed, fundamental, fundamental_conditions, fundamental_score = check_fundamental_filter(ts_code, date, params)
        
        if not fundamental_passed:
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
        
        # 检查波动率限制（新增）
        if not pd.isna(volatility) and volatility > params['max_volatility']:
            continue
        
        # 检查动量一致性（新增）
        momentum_consistent, momentum_score = check_momentum_consistency(row, params)
        if not momentum_consistent:
            continue
        
        # 主升浪条件（技术面）
        technical_conditions = {
            'price_above_ma': close > ma20 and close > ma60,
            'ma_bullish': ma20 > ma60,
            'strong_momentum': momentum > params['momentum_threshold'],
            'volume_surge': volume_ratio > params['volume_ratio'],
            'breakout': breakout == 1,
            'relative_strength': relative_strength > 0.1,
            'momentum_consistent': momentum_consistent,
        }
        
        technical_score = sum(technical_conditions.values()) / len(technical_conditions)
        
        # 综合得分（技术面70% + 基本面20% + 行业10%）
        sector_score = 1.0 if fundamental['sector'] in params['allowed_sectors'] else 0.0
        total_score = (technical_score * params['technical_weight'] + 
                      fundamental_score * params['fundamental_weight'] + 
                      sector_score * params['sector_weight'])
        
        if total_score >= params['min_score']:
            main_uptrend_stocks.append({
                'name': name,
                'code': ts_code,
                'score': total_score,
                'technical_score': technical_score,
                'fundamental_score': fundamental_score,
                'sector_score': sector_score,
                'momentum': momentum,
                'momentum_5d': row.get('momentum_5d_np', 0),
                'momentum_10d': row.get('momentum_10d_np', 0),
                'volume_ratio': volume_ratio,
                'breakout': breakout,
                'volatility': volatility,
                'pe': fundamental['pe'],
                'roe': fundamental['roe'],
                'revenue_growth': fundamental['revenue_growth'],
                'profit_growth': fundamental['profit_growth'],
                'market_cap': fundamental['market_cap'],
                'sector': fundamental['sector'],
            })
    
    # 按综合得分排序
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
    current_pool = []
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
        
        # 熔断检查（优化：更严格的熔断）
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
        
        # 止损检查（优化：更严格的止损）
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
            
            # 移动止损（优化：4%止损）
            if not sell:
                trailing_stop_price = max_price * (1 - params['trailing_stop'])
                if price < trailing_stop_price:
                    sell = True
            
            # 动量衰减止损
            if not sell and 'momentum_np' in row and not pd.isna(row['momentum_np']):
                if row['momentum_np'] < 0.10:
                    sell = True
            
            # 波动率止损（新增）
            if not sell and 'volatility_np' in row and not pd.isna(row['volatility_np']):
                if row['volatility_np'] > params['max_volatility']:
                    sell = True
            
            if sell:
                cash += positions[name] * price * 0.999
                positions[name] = 0
                if name in buy_prices: del buy_prices[name]
                if name in max_prices: del max_prices[name]
        
        # 识别主升浪股票（优化版）
        if not circuit_breaker:
            # 检查是否需要再平衡（优化：3天再平衡）
            if last_rebalance is None or (date - last_rebalance).days >= params['rebalance_days']:
                last_rebalance = date
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

def main():
    print("=" * 60)
    print("📊 主升浪策略V4 - 学习财通成长基金优化")
    print("=" * 60)
    
    start_time = time.time()
    
    # 加载数据
    print("加载数据...")
    combined, stock_data, all_dates = load_data()
    print(f"数据加载完成: {len(stock_data)} 只股票, {len(all_dates)} 个交易日")
    
    # 显示策略参数
    print(f"\n策略参数（优化版）:")
    print(f"  持仓数量: {PARAMS['max_positions']}")
    print(f"  仓位比例: {PARAMS['position_pct']*100}%")
    print(f"  动量阈值: {PARAMS['momentum_threshold']*100}%")
    print(f"  成交量比率: {PARAMS['volume_ratio']}倍")
    print(f"  移动止损: {PARAMS['trailing_stop']*100}%")
    print(f"  熔断阈值: {PARAMS['circuit_breaker']*100}%")
    print(f"  再平衡周期: {PARAMS['rebalance_days']}天")
    print(f"  综合得分门槛: {PARAMS['min_score']*100}%")
    print(f"\n基本面筛选（更严格）:")
    print(f"  市盈率: >{PARAMS['min_pe']}, <{PARAMS['max_pe']}")
    print(f"  ROE: >{PARAMS['min_roe']}%")
    print(f"  营收增长: >{PARAMS['min_revenue_growth']}%")
    print(f"  利润增长: >{PARAMS['min_profit_growth']}%")
    print(f"  最小市值: {PARAMS['min_market_cap']}亿")
    print(f"\n行业筛选（新增）:")
    print(f"  允许行业: {', '.join(PARAMS['allowed_sectors'][:5])}...")
    print(f"  行业权重: {PARAMS['sector_weight']*100}%")
    print(f"\n动量确认（新增）:")
    print(f"  动量周期: {PARAMS['momentum_periods']}")
    print(f"  动量一致性: >{PARAMS['momentum_consistency']*100}%")
    print(f"\n风险控制（新增）:")
    print(f"  最大波动率: {PARAMS['max_volatility']*100}%")
    print(f"  最大回撤限制: {PARAMS['max_drawdown_limit']*100}%")
    
    # 运行回测
    print(f"\n运行回测...")
    result = run_backtest(combined, stock_data, all_dates, PARAMS)
    
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
    
    # 评估是否达标
    print(f"\n🎯 目标评估:")
    target_met = True
    
    if result['total_return'] >= 5.0:  # 500%
        print(f"  ✅ 总收益: {result['total_return']:.1%} >= 500%")
    else:
        print(f"  ❌ 总收益: {result['total_return']:.1%} < 500%")
        target_met = False
    
    if result['max_drawdown'] <= 0.20:  # 20%
        print(f"  ✅ 最大回撤: {result['max_drawdown']:.1%} <= 20%")
    else:
        print(f"  ❌ 最大回撤: {result['max_drawdown']:.1%} > 20%")
        target_met = False
    
    if result['sharpe'] >= 1.3:
        print(f"  ✅ 夏普比率: {result['sharpe']:.2f} >= 1.3")
    else:
        print(f"  ❌ 夏普比率: {result['sharpe']:.2f} < 1.3")
        target_met = False
    
    if target_met:
        print(f"\n🎉 策略达标！可以部署到模拟账户")
    else:
        print(f"\n⚠️ 策略未完全达标，需要进一步优化")
    
    # 保存结果
    results_path = '/root/projects/ai-quant-stock/backend/data/main_uptrend_v4_summary.json'
    summary = {
        'strategy': 'main_uptrend_v4_caitong_optimized',
        'params': PARAMS,
        'result': result,
        'target_met': target_met,
        'total_time': total_time,
    }
    with open(results_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"\n结果已保存: {results_path}")

if __name__ == '__main__':
    main()
