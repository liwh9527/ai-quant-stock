#!/usr/bin/env python3
"""
策略回测：固定止损 vs ATR止损
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TUSHARE_TOKEN = "29479ac41a3b85cd62b519f1d32a14e343ea99b6def6ce61a646395d"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def get_stock_data(code, start_date, end_date):
    try:
        ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df.empty:
            return pd.DataFrame()
        df = df.sort_values('trade_date').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"获取{code}数据失败: {e}")
        return pd.DataFrame()


def calculate_ma(prices, period=20):
    return prices.rolling(window=period).mean()


def calculate_atr(high, low, close, period=14):
    """计算ATR"""
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def backtest_strategy(stock_df, stop_loss_mode="fixed", stop_loss_pct=0.05, atr_multiplier=2):
    """
    回测策略
    
    stop_loss_mode: "fixed" 或 "atr"
    stop_loss_pct: 固定止损百分比
    atr_multiplier: ATR止损倍数
    """
    if stock_df.empty:
        return {}
    
    # 计算技术指标
    stock_df['ma20'] = calculate_ma(stock_df['close'], 20)
    stock_df['atr'] = calculate_atr(stock_df['high'], stock_df['low'], stock_df['close'], 14)
    stock_df['avg_vol'] = stock_df['vol'].rolling(window=5).mean()
    
    # 交易记录
    trades = []
    position = None
    max_profit = 0
    
    for i in range(20, len(stock_df)):
        row = stock_df.iloc[i]
        prev_row = stock_df.iloc[i-1]
        
        if pd.isna(row['ma20']) or pd.isna(row['atr']):
            continue
        
        # 基础条件
        deviation = abs(row['close'] - row['ma20']) / row['ma20']
        volume_ok = row['vol'] > row['avg_vol'] * 1.5 if not pd.isna(row['avg_vol']) else False
        atr_ok = row['atr'] / row['close'] > 0.02
        
        # 买入逻辑
        if position is None:
            if (deviation < 0.10 and volume_ok and atr_ok and
                prev_row['close'] < prev_row['ma20'] and row['close'] >= row['ma20']):
                
                # 计算止损价
                if stop_loss_mode == "atr":
                    stop_loss_price = row['close'] - atr_multiplier * row['atr']
                else:
                    stop_loss_price = row['close'] * (1 - stop_loss_pct)
                
                position = {
                    'buy_price': row['close'],
                    'buy_date': row['trade_date'],
                    'buy_idx': i,
                    'stop_loss_price': stop_loss_price,
                    'atr_at_buy': row['atr'],
                }
                trades.append({
                    'type': 'buy',
                    'date': row['trade_date'],
                    'price': row['close'],
                    'stop_loss_price': stop_loss_price,
                    'atr': row['atr'],
                })
                max_profit = 0
        
        # 卖出逻辑
        else:
            profit_pct = (row['close'] - position['buy_price']) / position['buy_price']
            max_profit = max(max_profit, profit_pct)
            
            sell_reason = None
            
            # 止损检查
            if stop_loss_mode == "atr":
                # ATR止损
                if row['close'] <= position['stop_loss_price']:
                    sell_reason = f"ATR止损(止损价{position['stop_loss_price']:.2f})"
            else:
                # 固定止损
                if profit_pct <= -stop_loss_pct:
                    sell_reason = f"固定止损({profit_pct:.1%})"
            
            # 移动止盈
            if sell_reason is None and max_profit >= 0.15:
                trailing_stop_line = max_profit - 0.05
                if profit_pct <= trailing_stop_line:
                    sell_reason = f"移动止盈(最高{max_profit:.1%})"
            
            # 跌破MA20
            if sell_reason is None and row['close'] < row['ma20'] * 0.98:
                sell_reason = "跌破MA20"
            
            if sell_reason:
                trades.append({
                    'type': 'sell',
                    'date': row['trade_date'],
                    'price': row['close'],
                    'profit_pct': profit_pct,
                    'profit_amount': (row['close'] - position['buy_price']) * 10000 / position['buy_price'],
                    'max_profit': max_profit,
                    'reason': sell_reason,
                })
                position = None
    
    # 统计
    sell_trades = [t for t in trades if t['type'] == 'sell']
    win_trades = [t for t in sell_trades if t.get('profit_amount', 0) > 0]
    lose_trades = [t for t in sell_trades if t.get('profit_amount', 0) <= 0]
    
    total_profit = sum(t.get('profit_amount', 0) for t in sell_trades)
    
    return {
        'trades': trades,
        'total_trades': len(sell_trades),
        'win_trades': len(win_trades),
        'lose_trades': len(lose_trades),
        'win_rate': len(win_trades) / max(len(sell_trades), 1),
        'total_profit': total_profit,
        'avg_profit': total_profit / max(len(sell_trades), 1),
    }


def run_backtest():
    start_date = '20250101'
    end_date = '20260611'
    
    stocks = [
        {'code': '600584', 'name': '长电科技'},
        {'code': '601138', 'name': '工业富联'},
        {'code': '002185', 'name': '华天科技'},
        {'code': '002049', 'name': '紫光国微'},
        {'code': '600487', 'name': '亨通光电'},
        {'code': '002916', 'name': '深南电路'},
    ]
    
    print("="*80)
    print("策略回测对比: 固定止损 vs ATR止损")
    print("="*80)
    print(f"回测期间: {start_date} ~ {end_date}")
    print(f"股票池: {', '.join(s['name'] for s in stocks)}")
    print("="*80)
    
    # 获取数据
    print("\n获取数据中...")
    stock_data = {}
    for stock in stocks:
        df = get_stock_data(stock['code'], start_date, end_date)
        if not df.empty:
            stock_data[stock['name']] = df
            print(f"  ✅ {stock['name']}: {len(df)} 条")
    
    # 不同止损策略
    strategies = [
        {'name': '固定5%', 'mode': 'fixed', 'pct': 0.05, 'atr_mult': 2},
        {'name': '固定7%', 'mode': 'fixed', 'pct': 0.07, 'atr_mult': 2},
        {'name': 'ATR 1.5倍', 'mode': 'atr', 'pct': 0.05, 'atr_mult': 1.5},
        {'name': 'ATR 2倍', 'mode': 'atr', 'pct': 0.05, 'atr_mult': 2},
        {'name': 'ATR 2.5倍', 'mode': 'atr', 'pct': 0.05, 'atr_mult': 2.5},
        {'name': 'ATR 3倍', 'mode': 'atr', 'pct': 0.05, 'atr_mult': 3},
    ]
    
    print("\n" + "="*80)
    print("回测结果对比")
    print("="*80)
    
    results = []
    
    for strategy in strategies:
        total_trades = 0
        total_profit = 0
        total_win = 0
        total_lose = 0
        
        for stock_name, df in stock_data.items():
            result = backtest_strategy(df.copy(), strategy['mode'], strategy['pct'], strategy['atr_mult'])
            total_trades += result.get('total_trades', 0)
            total_profit += result.get('total_profit', 0)
            total_win += result.get('win_trades', 0)
            total_lose += result.get('lose_trades', 0)
        
        win_rate = total_win / max(total_trades, 1)
        avg_profit = total_profit / max(total_trades, 1)
        
        results.append({
            'name': strategy['name'],
            'total_trades': total_trades,
            'win_trades': total_win,
            'lose_trades': total_lose,
            'win_rate': win_rate,
            'total_profit': total_profit,
            'avg_profit': avg_profit,
        })
    
    # 打印对比表
    print(f"\n{'策略':<12} {'交易':>6} {'盈利':>6} {'亏损':>6} {'胜率':>8} {'总收益':>12} {'平均收益':>12}")
    print("-"*70)
    
    for r in results:
        emoji = '🟢' if r['total_profit'] > 0 else '🔴'
        print(f"{r['name']:<12} {r['total_trades']:>6} {r['win_trades']:>6} {r['lose_trades']:>6} "
              f"{r['win_rate']*100:>7.1f}% {emoji}{r['total_profit']:>+11.2f} {r['avg_profit']:>+11.2f}")
    
    # 打印各股票详情
    print("\n" + "="*80)
    print("各股票详情 (ATR 2倍)")
    print("="*80)
    
    for stock_name, df in stock_data.items():
        result = backtest_strategy(df.copy(), 'atr', 0.05, 2)
        
        print(f"\n{stock_name}:")
        if result.get('trades'):
            for t in result['trades']:
                if t['type'] == 'buy':
                    print(f"  {t['date']} 买入 {t['price']:.2f} (ATR: {t['atr']:.2f}, 止损价: {t['stop_loss_price']:.2f})")
                else:
                    emoji = '🟢' if t.get('profit_amount', 0) > 0 else '🔴'
                    print(f"  {t['date']} 卖出 {t['price']:.2f} {emoji} {t.get('profit_pct', 0):.1%} ({t['reason']})")
    
    # 结论
    print("\n" + "="*80)
    print("结论")
    print("="*80)
    
    best = max(results, key=lambda x: x['total_profit'])
    print(f"\n最优策略: {best['name']}")
    print(f"总收益: {best['total_profit']:+.2f}")
    print(f"胜率: {best['win_rate']*100:.1f}%")
    
    print("\nATR止损优势:")
    print("  ✅ 根据股票波动性动态调整止损点")
    print("  ✅ 高波动股票给更多空间，避免洗盘")
    print("  ✅ 低波动股票止损更紧，保护利润")


if __name__ == "__main__":
    run_backtest()
