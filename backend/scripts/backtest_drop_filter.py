#!/usr/bin/env python3
"""
策略回测：对比有无跌幅过滤的MA20策略
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Tushare配置
TUSHARE_TOKEN = "29479ac41a3b85cd62b519f1d32a14e343ea99b6def6ce61a646395d"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def get_stock_data(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取股票日线数据"""
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


def calculate_ma(prices: pd.Series, period: int = 20) -> pd.Series:
    """计算移动平均线"""
    return prices.rolling(window=period).mean()


def calculate_atr(prices: pd.Series, period: int = 14) -> pd.Series:
    """计算ATR"""
    changes = prices.diff().abs()
    return changes.rolling(window=period).mean()


def backtest_strategy(stock_df: pd.DataFrame, drop_filter: float = None) -> dict:
    """
    回测MA20策略
    
    Args:
        stock_df: 股票数据
        drop_filter: 跌幅过滤阈值（如-0.03表示跌幅>3%时不买入）
    
    Returns:
        回测结果
    """
    if stock_df.empty:
        return {}
    
    # 计算技术指标
    stock_df['ma20'] = calculate_ma(stock_df['close'], 20)
    stock_df['atr'] = calculate_atr(stock_df['close'], 14)
    stock_df['avg_vol'] = stock_df['vol'].rolling(window=5).mean()
    stock_df['pct_change'] = stock_df['close'].pct_change()
    
    # 初始化交易记录
    trades = []
    position = None
    
    # 遍历数据
    for i in range(20, len(stock_df)):
        row = stock_df.iloc[i]
        prev_row = stock_df.iloc[i-1]
        
        # 跳过NaN
        if pd.isna(row['ma20']) or pd.isna(row['atr']):
            continue
        
        # 计算偏离度
        deviation = abs(row['close'] - row['ma20']) / row['ma20']
        
        # 成交量条件
        volume_condition = row['vol'] > row['avg_vol'] * 1.5 if not pd.isna(row['avg_vol']) else False
        
        # ATR条件
        atr_condition = row['atr'] / row['close'] > 0.02 if row['close'] > 0 else False
        
        # 跌幅过滤条件
        drop_condition = True
        if drop_filter is not None and not pd.isna(row['pct_change']):
            # 当日跌幅超过阈值时不买入
            drop_condition = row['pct_change'] > drop_filter
        
        # 买入逻辑
        if position is None:
            buy_condition = (
                deviation < 0.10 and
                volume_condition and
                atr_condition and
                prev_row['close'] < prev_row['ma20'] and
                row['close'] >= row['ma20'] and
                drop_condition  # 跌幅过滤
            )
            
            if buy_condition:
                position = {
                    'buy_price': row['close'],
                    'buy_date': row['trade_date'],
                    'quantity': 10000 // row['close']
                }
                trades.append({
                    'type': 'buy',
                    'date': row['trade_date'],
                    'price': row['close'],
                    'quantity': position['quantity'],
                    'pct_change': row['pct_change'],
                    'reason': 'MA20突破买入'
                })
        
        # 卖出逻辑
        else:
            profit_pct = (row['close'] - position['buy_price']) / position['buy_price']
            
            sell_condition = (
                profit_pct <= -0.05 or
                profit_pct >= 0.15 or
                row['close'] < row['ma20'] * 0.98
            )
            
            if sell_condition:
                reason = '止损' if profit_pct <= -0.05 else '止盈' if profit_pct >= 0.15 else '跌破MA20'
                trades.append({
                    'type': 'sell',
                    'date': row['trade_date'],
                    'price': row['close'],
                    'quantity': position['quantity'],
                    'profit_pct': profit_pct,
                    'profit_amount': (row['close'] - position['buy_price']) * position['quantity'],
                    'reason': reason
                })
                position = None
    
    # 计算收益
    total_profit = sum(t.get('profit_amount', 0) for t in trades if t['type'] == 'sell')
    win_trades = [t for t in trades if t['type'] == 'sell' and t.get('profit_amount', 0) > 0]
    lose_trades = [t for t in trades if t['type'] == 'sell' and t.get('profit_amount', 0) <= 0]
    
    return {
        'trades': trades,
        'total_trades': len([t for t in trades if t['type'] == 'sell']),
        'win_trades': len(win_trades),
        'lose_trades': len(lose_trades),
        'win_rate': len(win_trades) / max(len(win_trades) + len(lose_trades), 1),
        'total_profit': total_profit,
        'avg_profit': total_profit / max(len(win_trades) + len(lose_trades), 1),
    }


def run_backtest():
    """运行回测"""
    start_date = '20250101'
    end_date = '20260610'
    
    stocks = [
        {'code': '600487', 'name': '亨通光电'},
        {'code': '601208', 'name': '东材科技'},
        {'code': '601138', 'name': '工业富联'},
    ]
    
    # 跌幅过滤阈值
    drop_filters = [
        {'name': '无过滤', 'value': None},
        {'name': '跌幅>1%', 'value': -0.01},
        {'name': '跌幅>2%', 'value': -0.02},
        {'name': '跌幅>3%', 'value': -0.03},
        {'name': '跌幅>5%', 'value': -0.05},
    ]
    
    print("="*80)
    print("策略回测对比: 跌幅过滤效果分析")
    print("="*80)
    print(f"回测期间: {start_date} ~ {end_date}")
    print(f"股票池: {', '.join(s['name'] for s in stocks)}")
    print("="*80)
    
    all_results = {}
    
    for stock in stocks:
        print(f"\n{'='*60}")
        print(f"回测: {stock['name']} ({stock['code']})")
        print('='*60)
        
        stock_df = get_stock_data(stock['code'], start_date, end_date)
        if stock_df.empty:
            print(f"获取{stock['name']}数据失败")
            continue
        
        print(f"数据条数: {len(stock_df)}")
        
        stock_results = []
        
        for df in drop_filters:
            result = backtest_strategy(stock_df.copy(), df['value'])
            stock_results.append({
                'filter_name': df['name'],
                'result': result
            })
        
        all_results[stock['name']] = stock_results
        
        # 打印对比表
        print(f"\n{'过滤方式':<12} {'交易次数':>8} {'盈利':>6} {'亏损':>6} {'胜率':>8} {'总收益':>10} {'平均收益':>10}")
        print("-"*70)
        
        for sr in stock_results:
            r = sr['result']
            trades = r.get('total_trades', 0)
            win = r.get('win_trades', 0)
            lose = r.get('lose_trades', 0)
            wr = r.get('win_rate', 0) * 100
            total = r.get('total_profit', 0)
            avg = r.get('avg_profit', 0)
            
            emoji = '🟢' if total > 0 else '🔴'
            print(f"{sr['filter_name']:<12} {trades:>8} {win:>6} {lose:>6} {wr:>7.1f}% {emoji}{total:>+9.2f} {avg:>+9.2f}")
        
        # 打印交易详情
        print(f"\n交易详情:")
        for sr in stock_results:
            r = sr['result']
            if r.get('trades'):
                print(f"\n  {sr['filter_name']}:")
                for t in r['trades']:
                    if t['type'] == 'buy':
                        pct = t.get('pct_change', 0) * 100
                        print(f"    {t['date']} 买入 {t['price']:.2f} (当日涨跌: {pct:+.1f}%)")
                    else:
                        emoji = '🟢' if t.get('profit_amount', 0) > 0 else '🔴'
                        print(f"    {t['date']} 卖出 {t['price']:.2f} {emoji} {t.get('profit_pct', 0):.1%} ({t['reason']})")
    
    # 汇总对比
    print("\n" + "="*80)
    print("汇总对比")
    print("="*80)
    
    print(f"\n{'过滤方式':<12} {'总交易':>8} {'总收益':>12} {'平均收益':>12} {'收益变化':>12}")
    print("-"*60)
    
    base_profit = None
    for df in drop_filters:
        total_trades = 0
        total_profit = 0
        
        for stock_name, results in all_results.items():
            for sr in results:
                if sr['filter_name'] == df['name']:
                    total_trades += sr['result'].get('total_trades', 0)
                    total_profit += sr['result'].get('total_profit', 0)
        
        avg_profit = total_profit / max(total_trades, 1)
        
        if base_profit is None:
            base_profit = total_profit
            change = 0
        else:
            change = total_profit - base_profit
        
        emoji = '🟢' if total_profit > 0 else '🔴'
        change_emoji = '🟢' if change > 0 else '🔴' if change < 0 else '⚪'
        
        print(f"{df['name']:<12} {total_trades:>8} {emoji}{total_profit:>+11.2f} {avg_profit:>+11.2f} {change_emoji}{change:>+11.2f}")
    
    # 结论
    print("\n" + "="*80)
    print("结论")
    print("="*80)
    
    # 找出最优过滤阈值
    best_filter = None
    best_profit = float('-inf')
    
    for df in drop_filters:
        total_profit = 0
        for stock_name, results in all_results.items():
            for sr in results:
                if sr['filter_name'] == df['name']:
                    total_profit += sr['result'].get('total_profit', 0)
        
        if total_profit > best_profit:
            best_profit = total_profit
            best_filter = df['name']
    
    print(f"\n最优跌幅过滤: {best_filter}")
    print(f"最优总收益: {best_profit:+.2f}")
    
    # 计算各过滤方式的平均收益
    print(f"\n各过滤方式平均收益:")
    for df in drop_filters:
        total_trades = 0
        total_profit = 0
        for stock_name, results in all_results.items():
            for sr in results:
                if sr['filter_name'] == df['name']:
                    total_trades += sr['result'].get('total_trades', 0)
                    total_profit += sr['result'].get('total_profit', 0)
        
        avg = total_profit / max(total_trades, 1)
        print(f"  {df['name']}: {avg:+.2f}/笔 (共{total_trades}笔)")


if __name__ == "__main__":
    run_backtest()
