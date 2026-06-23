#!/usr/bin/env python3
"""
策略回测：对比多种优化方案
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
    return prices.rolling(window=period).mean()


def calculate_atr(prices: pd.Series, period: int = 14) -> pd.Series:
    changes = prices.diff().abs()
    return changes.rolling(window=period).mean()


def backtest_strategy(stock_df: pd.DataFrame, filters: dict = None) -> dict:
    """
    回测MA20策略
    
    Args:
        stock_df: 股票数据
        filters: 过滤条件字典
    """
    if stock_df.empty:
        return {}
    
    if filters is None:
        filters = {}
    
    # 计算技术指标
    stock_df['ma20'] = calculate_ma(stock_df['close'], 20)
    stock_df['atr'] = calculate_atr(stock_df['close'], 14)
    stock_df['avg_vol'] = stock_df['vol'].rolling(window=5).mean()
    stock_df['pct_change'] = stock_df['close'].pct_change()
    
    # 计算连涨天数
    stock_df['is_up'] = stock_df['pct_change'] > 0
    stock_df['consecutive_up'] = 0
    for i in range(1, len(stock_df)):
        if stock_df.iloc[i]['is_up']:
            stock_df.loc[stock_df.index[i], 'consecutive_up'] = stock_df.iloc[i-1]['consecutive_up'] + 1
    
    # 初始化
    trades = []
    position = None
    
    for i in range(20, len(stock_df)):
        row = stock_df.iloc[i]
        prev_row = stock_df.iloc[i-1]
        
        if pd.isna(row['ma20']) or pd.isna(row['atr']):
            continue
        
        # 基础条件
        deviation = abs(row['close'] - row['ma20']) / row['ma20']
        volume_condition = row['vol'] > row['avg_vol'] * 1.5 if not pd.isna(row['avg_vol']) else False
        atr_condition = row['atr'] / row['close'] > 0.02 if row['close'] > 0 else False
        
        # 过滤条件
        filter_pass = True
        filter_reason = ""
        
        # 1. 涨幅过滤：当日涨幅>阈值时不买入
        if 'max_rise' in filters and not pd.isna(row['pct_change']):
            if row['pct_change'] > filters['max_rise']:
                filter_pass = False
                filter_reason = f"涨幅{row['pct_change']*100:.1f}%>{filters['max_rise']*100}%"
        
        # 2. 换手率过滤：换手率>阈值时不买入
        if 'max_turnover' in filters and 'turnover_rate' in row and not pd.isna(row.get('turnover_rate')):
            if row['turnover_rate'] > filters['max_turnover']:
                filter_pass = False
                filter_reason = f"换手率{row['turnover_rate']:.1f}%>{filters['max_turnover']}%"
        
        # 3. 连涨过滤：连涨>阈值天时不买入
        if 'max_consecutive' in filters:
            if row['consecutive_up'] > filters['max_consecutive']:
                filter_pass = False
                filter_reason = f"连涨{row['consecutive_up']}天>{filters['max_consecutive']}天"
        
        # 4. 成交量确认：成交量需>阈值倍均量
        if 'volume_ratio' in filters and not pd.isna(row['avg_vol']):
            if row['vol'] < row['avg_vol'] * filters['volume_ratio']:
                filter_pass = False
                filter_reason = f"成交量{row['vol']/row['avg_vol']:.1f}倍<{filters['volume_ratio']}倍"
        
        # 买入逻辑
        if position is None:
            buy_condition = (
                deviation < 0.10 and
                volume_condition and
                atr_condition and
                prev_row['close'] < prev_row['ma20'] and
                row['close'] >= row['ma20'] and
                filter_pass
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
    
    # 统计
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
    
    # 优化方案
    strategies = [
        {'name': '基准(无过滤)', 'filters': {}},
        {'name': '涨幅>5%过滤', 'filters': {'max_rise': 0.05}},
        {'name': '涨幅>8%过滤', 'filters': {'max_rise': 0.08}},
        {'name': '涨幅>10%过滤', 'filters': {'max_rise': 0.10}},
        {'name': '连涨>2天过滤', 'filters': {'max_consecutive': 2}},
        {'name': '连涨>3天过滤', 'filters': {'max_consecutive': 3}},
        {'name': '成交量>2倍', 'filters': {'volume_ratio': 2.0}},
        {'name': '成交量>2.5倍', 'filters': {'volume_ratio': 2.5}},
        {'name': '成交量>3倍', 'filters': {'volume_ratio': 3.0}},
    ]
    
    print("="*90)
    print("策略回测对比: 多种优化方案")
    print("="*90)
    print(f"回测期间: {start_date} ~ {end_date}")
    print(f"股票池: {', '.join(s['name'] for s in stocks)}")
    print("="*90)
    
    # 获取所有股票数据
    stock_data = {}
    for stock in stocks:
        df = get_stock_data(stock['code'], start_date, end_date)
        if not df.empty:
            stock_data[stock['name']] = df
            print(f"✅ {stock['name']}: {len(df)} 条数据")
    
    print("\n" + "="*90)
    print("各方案回测结果")
    print("="*90)
    
    # 按方案汇总
    strategy_results = []
    
    for strategy in strategies:
        total_trades = 0
        total_profit = 0
        total_win = 0
        total_lose = 0
        stock_details = {}
        
        for stock_name, df in stock_data.items():
            result = backtest_strategy(df.copy(), strategy['filters'])
            total_trades += result.get('total_trades', 0)
            total_profit += result.get('total_profit', 0)
            total_win += result.get('win_trades', 0)
            total_lose += result.get('lose_trades', 0)
            stock_details[stock_name] = result
        
        win_rate = total_win / max(total_win + total_lose, 1)
        avg_profit = total_profit / max(total_trades, 1)
        
        strategy_results.append({
            'name': strategy['name'],
            'total_trades': total_trades,
            'total_profit': total_profit,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'win': total_win,
            'lose': total_lose,
            'details': stock_details,
        })
    
    # 打印汇总表
    print(f"\n{'方案':<18} {'交易':>6} {'盈利':>6} {'亏损':>6} {'胜率':>8} {'总收益':>12} {'平均收益':>12}")
    print("-"*80)
    
    base_profit = strategy_results[0]['total_profit']
    
    for sr in strategy_results:
        change = sr['total_profit'] - base_profit
        emoji = '🟢' if sr['total_profit'] > 0 else '🔴'
        change_emoji = '🟢' if change > 0 else '🔴' if change < 0 else '⚪'
        
        print(f"{sr['name']:<18} {sr['total_trades']:>6} {sr['win']:>6} {sr['lose']:>6} "
              f"{sr['win_rate']*100:>7.1f}% {emoji}{sr['total_profit']:>+11.2f} "
              f"{sr['avg_profit']:>+11.2f}")
    
    # 打印各股票详情
    print("\n" + "="*90)
    print("各股票详情")
    print("="*90)
    
    for stock_name in stock_data.keys():
        print(f"\n{'='*60}")
        print(f"{stock_name}")
        print('='*60)
        
        print(f"{'方案':<18} {'交易':>6} {'胜率':>8} {'总收益':>12} {'平均收益':>12}")
        print("-"*60)
        
        for sr in strategy_results:
            detail = sr['details'].get(stock_name, {})
            trades = detail.get('total_trades', 0)
            win_rate = detail.get('win_rate', 0) * 100
            total = detail.get('total_profit', 0)
            avg = detail.get('avg_profit', 0)
            
            emoji = '🟢' if total > 0 else '🔴'
            print(f"{sr['name']:<18} {trades:>6} {win_rate:>7.1f}% {emoji}{total:>+11.2f} {avg:>+11.2f}")
        
        # 打印基准方案的交易详情
        base_result = strategy_results[0]['details'].get(stock_name, {})
        if base_result.get('trades'):
            print(f"\n基准交易详情:")
            for t in base_result['trades']:
                if t['type'] == 'buy':
                    pct = t.get('pct_change', 0) * 100
                    print(f"  {t['date']} 买入 {t['price']:.2f} (当日涨跌: {pct:+.1f}%)")
                else:
                    emoji = '🟢' if t.get('profit_amount', 0) > 0 else '🔴'
                    print(f"  {t['date']} 卖出 {t['price']:.2f} {emoji} {t.get('profit_pct', 0):.1%} ({t['reason']})")
    
    # 结论
    print("\n" + "="*90)
    print("结论")
    print("="*90)
    
    # 找出最优方案
    best_strategy = max(strategy_results, key=lambda x: x['total_profit'])
    best_avg = max(strategy_results, key=lambda x: x['avg_profit'])
    best_wr = max(strategy_results, key=lambda x: x['win_rate'])
    
    print(f"\n最高总收益: {best_strategy['name']} ({best_strategy['total_profit']:+.2f})")
    print(f"最高平均收益: {best_avg['name']} ({best_avg['avg_profit']:+.2f}/笔)")
    print(f"最高胜率: {best_wr['name']} ({best_wr['win_rate']*100:.1f}%)")
    
    # 对比基准
    print(f"\n各方案相对基准收益变化:")
    for sr in strategy_results[1:]:
        change = sr['total_profit'] - base_profit
        change_pct = change / abs(base_profit) * 100 if base_profit != 0 else 0
        emoji = '🟢' if change > 0 else '🔴' if change < 0 else '⚪'
        print(f"  {sr['name']}: {emoji}{change:+.2f} ({change_pct:+.1f}%)")


if __name__ == "__main__":
    run_backtest()
