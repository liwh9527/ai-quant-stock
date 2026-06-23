#!/usr/bin/env python3
"""主升浪优化版策略 - 实盘执行脚本

策略参数（优化后）：
- 持仓数量：4只
- 仓位比例：15%
- 动量阈值：30%
- 成交量比率：1.8倍
- 移动止损：5%
- 熔断阈值：8%
- 再平衡天数：5天
"""

import sys
import os
sys.path.insert(0, '/root/.hermes/skills/mx-skills/scripts')

import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import subprocess
import time

# 策略参数
STRATEGY_PARAMS = {
    'max_positions': 4,           # 最多持有4只
    'position_pct': 0.15,         # 单只仓位15%
    'momentum_threshold': 0.30,   # 动量阈值30%
    'volume_ratio': 1.8,          # 成交量放大1.8倍
    'trailing_stop': 0.05,        # 5%移动止损
    'circuit_breaker': 0.08,      # 8%熔断阈值
    'rebalance_days': 5,          # 5天再平衡
    'min_score': 0.7,             # 综合得分>70%
}

# 数据库路径
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'
TRADE_LOG = '/root/projects/ai-quant-stock/backend/data/main_uptrend_trades.json'

def run_moni_command(command):
    """执行模拟交易命令"""
    cmd = ['python', '/root/.hermes/skills/mx-skills/scripts/mx_moni.py', command]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def get_account_info():
    """获取账户信息"""
    output = run_moni_command("我的资金")
    # 解析输出
    lines = output.split('\n')
    info = {}
    for line in lines:
        if '总资产' in line:
            info['total_assets'] = float(line.split(':')[1].strip().replace('元', ''))
        elif '可用资金' in line:
            info['available_cash'] = float(line.split(':')[1].strip().replace('元', ''))
        elif '总持仓市值' in line:
            info['position_value'] = float(line.split(':')[1].strip().replace('元', ''))
    return info

def get_holdings():
    """获取当前持仓"""
    output = run_moni_command("我的持仓")
    holdings = []
    lines = output.split('\n')
    in_holdings = False
    
    for line in lines:
        if '持仓明细' in line:
            in_holdings = True
            continue
        if in_holdings and '---' in line:
            continue
        if in_holdings and line.strip():
            parts = line.split()
            if len(parts) >= 6 and parts[0] not in ['股票名称', '---']:
                try:
                    holding = {
                        'name': parts[0],
                        'code': parts[1],
                        'shares': int(parts[2]),
                        'available': int(parts[3]),
                        'price': float(parts[4]),
                        'value': float(parts[5]),
                        'pnl': float(parts[7]) if len(parts) > 7 else 0
                    }
                    if holding['shares'] > 0:
                        holdings.append(holding)
                except:
                    continue
    return holdings

def load_stock_data():
    """加载股票数据"""
    conn = sqlite3.connect(DB_PATH)
    start_date = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
    
    # 获取股票列表
    stocks = pd.read_sql_query(f'''
        SELECT ts_code, name FROM stocks 
        WHERE name NOT LIKE "%ST%" 
        AND name NOT LIKE "%退%"
        AND (ts_code LIKE "60%" OR ts_code LIKE "00%")
        AND ts_code NOT LIKE "30%"
        AND ts_code NOT LIKE "68%"
        LIMIT 200
    ''', conn)
    
    stock_data = {}
    
    for _, row in stocks.iterrows():
        ts_code = row['ts_code']
        name = row['name']
        
        df = pd.read_sql_query(f'''
            SELECT trade_date, open, high, low, close, vol as volume 
            FROM daily_quotes 
            WHERE ts_code="{ts_code}" 
            AND trade_date >= "{start_date}"
            ORDER BY trade_date
        ''', conn)
        
        if len(df) < 30:
            continue
            
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.set_index('trade_date')
        
        # 计算指标
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['momentum'] = df['close'].pct_change(20)
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        df['high_20'] = df['high'].rolling(20).max()
        df['breakout'] = (df['close'] > df['high_20'].shift(1)).astype(int)
        
        stock_data[name] = {
            'code': ts_code,
            'data': df,
            'latest': df.iloc[-1] if len(df) > 0 else None
        }
    
    conn.close()
    return stock_data

def identify_main_uptrend(stock_data):
    """识别主升浪股票"""
    candidates = []
    
    for name, info in stock_data.items():
        latest = info['latest']
        if latest is None:
            continue
        
        close = latest.get('close', 0)
        ma20 = latest.get('ma20', 0)
        ma60 = latest.get('ma60', 0)
        momentum = latest.get('momentum', 0)
        volume_ratio = latest.get('volume_ratio', 0)
        breakout = latest.get('breakout', 0)
        
        # 检查数据有效性
        if pd.isna(close) or pd.isna(ma20) or pd.isna(ma60):
            continue
        if pd.isna(momentum) or pd.isna(volume_ratio) or pd.isna(breakout):
            continue
        
        # 主升浪条件
        conditions = {
            'price_above_ma': close > ma20 and close > ma60,
            'ma_bullish': ma20 > ma60,
            'strong_momentum': momentum > STRATEGY_PARAMS['momentum_threshold'],
            'volume_surge': volume_ratio > STRATEGY_PARAMS['volume_ratio'],
            'breakout': breakout == 1,
        }
        
        score = sum(conditions.values()) / len(conditions)
        
        if score >= STRATEGY_PARAMS['min_score']:
            candidates.append({
                'name': name,
                'code': info['code'],
                'price': close,
                'momentum': momentum,
                'volume_ratio': volume_ratio,
                'score': score,
                'conditions': conditions,
            })
    
    # 按得分和动量排序
    candidates.sort(key=lambda x: (x['score'], x['momentum']), reverse=True)
    return candidates[:STRATEGY_PARAMS['max_positions']]

def execute_buy(stock_code, stock_name, price, account_info):
    """执行买入"""
    # 计算买入数量
    total_value = account_info['total_assets']
    position_value = total_value * STRATEGY_PARAMS['position_pct']
    shares = int(position_value / price / 100) * 100
    
    if shares <= 0:
        print(f"  ⚠️ 资金不足，无法买入 {stock_name}")
        return None
    
    # 检查可用资金
    cost = shares * price * 1.0003  # 手续费
    if cost > account_info['available_cash'] * 0.95:
        print(f"  ⚠️ 可用资金不足，无法买入 {stock_name}")
        return None
    
    # 执行买入
    command = f"买入 {stock_code} {price} {shares}"
    print(f"  📝 执行买入: {stock_name} ({stock_code})")
    print(f"     价格: {price:.2f}, 数量: {shares}, 金额: {cost:.2f}")
    
    output = run_moni_command(command)
    result_msg = output.split('✅')[1].split('\n')[0] if '✅' in output else '失败'
    print(f"     结果: {result_msg}")
    
    return {
        'action': 'buy',
        'stock': stock_name,
        'code': stock_code,
        'price': price,
        'shares': shares,
        'cost': cost,
        'time': datetime.now().isoformat()
    }

def execute_sell(stock_code, stock_name, price, shares, reason):
    """执行卖出"""
    command = f"卖出 {stock_code} {price} {shares}"
    print(f"  📝 执行卖出: {stock_name} ({stock_code})")
    print(f"     价格: {price:.2f}, 数量: {shares}, 原因: {reason}")
    
    output = run_moni_command(command)
    result_msg = output.split('✅')[1].split('\n')[0] if '✅' in output else '失败'
    print(f"     结果: {result_msg}")
    
    return {
        'action': 'sell',
        'stock': stock_name,
        'code': stock_code,
        'price': price,
        'shares': shares,
        'reason': reason,
        'time': datetime.now().isoformat()
    }

def check_stop_loss(holdings, stock_data):
    """检查止损"""
    sell_signals = []
    
    for holding in holdings:
        name = holding['name']
        code = holding['code']
        buy_price = holding['price']  # 这里需要记录买入价格
        
        if name not in stock_data:
            continue
        
        latest = stock_data[name]['latest']
        if latest is None:
            continue
        
        current_price = latest['close']
        ma20 = latest.get('ma20', 0)
        
        # 计算收益
        profit_pct = (current_price - buy_price) / buy_price
        
        # 止损条件
        sell = False
        reason = ""
        
        # 1. 跌破MA20止损
        if not pd.isna(ma20) and current_price < ma20:
            sell = True
            reason = "跌破MA20"
        
        # 2. 移动止损（从最高点回撤5%）
        # 这里需要记录最高价，简化处理
        if profit_pct < -STRATEGY_PARAMS['trailing_stop']:
            sell = True
            reason = f"亏损{profit_pct:.1%}超过止损线"
        
        # 3. 动量衰减止损
        momentum = latest.get('momentum', 0)
        if not pd.isna(momentum) and momentum < 0.10:
            sell = True
            reason = "动量衰减"
        
        if sell:
            sell_signals.append({
                'name': name,
                'code': code,
                'price': current_price,
                'shares': holding['shares'],
                'reason': reason
            })
    
    return sell_signals

def main():
    """主函数"""
    print("=" * 60)
    print("🚀 主升浪优化版策略 - 实盘执行")
    print("=" * 60)
    print(f"\n执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n策略参数:")
    for key, value in STRATEGY_PARAMS.items():
        print(f"  {key}: {value}")
    
    # 获取账户信息
    print("\n📊 账户状态:")
    account_info = get_account_info()
    print(f"  总资产: {account_info.get('total_assets', 0):.2f}元")
    print(f"  可用资金: {account_info.get('available_cash', 0):.2f}元")
    print(f"  持仓市值: {account_info.get('position_value', 0):.2f}元")
    
    # 获取当前持仓
    print("\n📈 当前持仓:")
    holdings = get_holdings()
    if holdings:
        for h in holdings:
            print(f"  {h['name']} ({h['code']}): {h['shares']}股, 现价{h['price']:.2f}元")
    else:
        print("  无持仓")
    
    # 加载股票数据
    print("\n📊 加载股票数据...")
    stock_data = load_stock_data()
    print(f"  已加载 {len(stock_data)} 只股票")
    
    # 检查止损
    print("\n🔍 检查止损信号...")
    sell_signals = check_stop_loss(holdings, stock_data)
    if sell_signals:
        print(f"  发现 {len(sell_signals)} 个止损信号")
        for signal in sell_signals:
            execute_sell(
                signal['code'],
                signal['name'],
                signal['price'],
                signal['shares'],
                signal['reason']
            )
    else:
        print("  无止损信号")
    
    # 识别主升浪股票
    print("\n🔍 识别主升浪股票...")
    candidates = identify_main_uptrend(stock_data)
    print(f"  发现 {len(candidates)} 只主升浪股票:")
    for i, c in enumerate(candidates, 1):
        print(f"  {i}. {c['name']} ({c['code']})")
        print(f"     价格: {c['price']:.2f}, 动量: {c['momentum']:.1%}, 得分: {c['score']:.0%}")
    
    # 执行买入
    if candidates:
        print("\n💰 执行买入操作:")
        for candidate in candidates:
            # 检查是否已持有
            already_held = any(h['code'] == candidate['code'] for h in holdings)
            if already_held:
                print(f"  ⏭️ 已持有 {candidate['name']}，跳过")
                continue
            
            # 检查持仓数量
            if len(holdings) >= STRATEGY_PARAMS['max_positions']:
                print(f"  ⚠️ 已达最大持仓数 {STRATEGY_PARAMS['max_positions']}，停止买入")
                break
            
            # 执行买入
            trade = execute_buy(
                candidate['code'],
                candidate['name'],
                candidate['price'],
                account_info
            )
            
            if trade:
                holdings.append({
                    'name': candidate['name'],
                    'code': candidate['code'],
                    'shares': trade['shares'],
                    'price': candidate['price']
                })
    
    # 保存交易记录
    print("\n💾 保存交易记录...")
    trades = []
    if os.path.exists(TRADE_LOG):
        with open(TRADE_LOG, 'r') as f:
            trades = json.load(f)
    
    trades.append({
        'time': datetime.now().isoformat(),
        'account': account_info,
        'holdings': holdings,
        'candidates': candidates[:5] if candidates else [],
    })
    
    with open(TRADE_LOG, 'w') as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)
    
    print(f"  交易记录已保存: {TRADE_LOG}")
    
    print("\n✅ 策略执行完成")

if __name__ == '__main__':
    main()
