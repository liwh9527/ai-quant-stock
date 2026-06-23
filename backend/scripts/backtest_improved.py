#!/usr/bin/env python3
"""
策略回测：对比当前策略 vs 改进策略
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


def get_index_data(start_date, end_date):
    try:
        df = pro.index_daily(ts_code='000001.SH', start_date=start_date, end_date=end_date)
        if df.empty:
            return pd.DataFrame()
        df = df.sort_values('trade_date').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"获取指数数据失败: {e}")
        return pd.DataFrame()


def calculate_ma(prices, period=20):
    return prices.rolling(window=period).mean()


def calculate_atr(prices, period=14):
    changes = prices.diff().abs()
    return changes.rolling(window=period).mean()


def backtest_strategy(stock_df, index_df=None, strategy_type="current"):
    """
    回测策略
    
    strategy_type:
    - "current": 当前策略
    - "improved": 改进策略
    """
    if stock_df.empty:
        return {}
    
    # 计算技术指标
    stock_df['ma20'] = calculate_ma(stock_df['close'], 20)
    stock_df['atr'] = calculate_atr(stock_df['close'], 14)
    stock_df['avg_vol'] = stock_df['vol'].rolling(window=5).mean()
    
    # 如果有指数数据，计算大盘MA20
    if index_df is not None and not index_df.empty:
        index_df['ma20'] = calculate_ma(index_df['close'], 20)
        stock_df = stock_df.merge(
            index_df[['trade_date', 'close', 'ma20']].rename(
                columns={'close': 'index_close', 'ma20': 'index_ma20'}
            ),
            on='trade_date',
            how='left'
        )
    
    # 策略参数
    if strategy_type == "current":
        stop_loss_pct = 0.05
        take_profit_pct = 0.15
        trailing_stop = True
        trailing_pct = 0.05
        require_confirmation = False
        check_market = False
    else:  # improved
        stop_loss_pct = 0.07
        take_profit_pct = 0.15
        trailing_stop = True
        trailing_pct = 0.05
        require_confirmation = True
        check_market = True
    
    # 交易记录
    trades = []
    position = None
    confirmation_count = 0
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
        
        # 大盘条件
        market_ok = True
        if check_market and 'index_close' in row and 'index_ma20' in row:
            if not pd.isna(row['index_close']) and not pd.isna(row['index_ma20']):
                market_ok = row['index_close'] > row['index_ma20']
        
        # 突破条件
        cross_up = prev_row['close'] < prev_row['ma20'] and row['close'] >= row['ma20']
        above_ma20 = row['close'] >= row['ma20']
        
        # 买入逻辑
        if position is None:
            if require_confirmation:
                # 改进策略：需要确认
                if cross_up:
                    confirmation_count = 1
                elif confirmation_count > 0 and above_ma20:
                    confirmation_count += 1
                else:
                    confirmation_count = 0
                
                # 连续2天站稳MA20
                if confirmation_count >= 2:
                    if deviation < 0.10 and volume_ok and atr_ok and market_ok:
                        position = {
                            'buy_price': row['close'],
                            'buy_date': row['trade_date'],
                            'buy_idx': i
                        }
                        trades.append({
                            'type': 'buy',
                            'date': row['trade_date'],
                            'price': row['close'],
                            'reason': '确认突破买入'
                        })
                        confirmation_count = 0
                        max_profit = 0
            else:
                # 当前策略：直接突破买入
                if cross_up and deviation < 0.10 and volume_ok and atr_ok and market_ok:
                    position = {
                        'buy_price': row['close'],
                        'buy_date': row['trade_date'],
                        'buy_idx': i
                    }
                    trades.append({
                        'type': 'buy',
                        'date': row['trade_date'],
                        'price': row['close'],
                        'reason': 'MA20突破买入'
                    })
                    max_profit = 0
        
        # 卖出逻辑
        else:
            profit_pct = (row['close'] - position['buy_price']) / position['buy_price']
            max_profit = max(max_profit, profit_pct)
            
            sell_reason = None
            
            # 止损
            if profit_pct <= -stop_loss_pct:
                sell_reason = f'止损({profit_pct:.1%})'
            
            # 移动止盈
            elif trailing_stop and max_profit >= take_profit_pct:
                trailing_stop_line = max_profit - trailing_pct
                if profit_pct <= trailing_stop_line:
                    sell_reason = f'移动止盈(最高{max_profit:.1%})'
            
            # 跌破MA20
            elif row['close'] < row['ma20'] * 0.98:
                sell_reason = '跌破MA20'
            
            if sell_reason:
                trades.append({
                    'type': 'sell',
                    'date': row['trade_date'],
                    'price': row['close'],
                    'profit_pct': profit_pct,
                    'profit_amount': (row['close'] - position['buy_price']) * 10000 / position['buy_price'],
                    'max_profit': max_profit,
                    'reason': sell_reason
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
        {'code': '600487', 'name': '亨通光电'},
        {'code': '601208', 'name': '东材科技'},
        {'code': '601138', 'name': '工业富联'},
    ]
    
    print("="*80)
    print("策略回测对比: 当前策略 vs 改进策略")
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
    
    # 获取大盘数据
    print("获取大盘数据...")
    index_df = get_index_data(start_date, end_date)
    if not index_df.empty:
        print(f"  ✅ 上证指数: {len(index_df)} 条")
    
    print("\n" + "="*80)
    print("回测结果对比")
    print("="*80)
    
    # 回测两种策略
    results = {}
    
    for strategy in ["current", "improved"]:
        strategy_name = "当前策略" if strategy == "current" else "改进策略"
        
        total_trades = 0
        total_profit = 0
        total_win = 0
        total_lose = 0
        stock_details = {}
        
        for stock_name, df in stock_data.items():
            result = backtest_strategy(df.copy(), index_df, strategy)
            total_trades += result.get('total_trades', 0)
            total_profit += result.get('total_profit', 0)
            total_win += result.get('win_trades', 0)
            total_lose += result.get('lose_trades', 0)
            stock_details[stock_name] = result
        
        win_rate = total_win / max(total_trades, 1)
        avg_profit = total_profit / max(total_trades, 1)
        
        results[strategy] = {
            'name': strategy_name,
            'total_trades': total_trades,
            'win_trades': total_win,
            'lose_trades': total_lose,
            'win_rate': win_rate,
            'total_profit': total_profit,
            'avg_profit': avg_profit,
            'details': stock_details,
        }
    
    # 打印对比表
    print(f"\n{'策略':<12} {'交易':>6} {'盈利':>6} {'亏损':>6} {'胜率':>8} {'总收益':>12} {'平均收益':>12}")
    print("-"*70)
    
    for strategy in ["current", "improved"]:
        r = results[strategy]
        emoji = '🟢' if r['total_profit'] > 0 else '🔴'
        print(f"{r['name']:<12} {r['total_trades']:>6} {r['win_trades']:>6} {r['lose_trades']:>6} "
              f"{r['win_rate']*100:>7.1f}% {emoji}{r['total_profit']:>+11.2f} {r['avg_profit']:>+11.2f}")
    
    # 打印各股票详情
    print("\n" + "="*80)
    print("各股票详情")
    print("="*80)
    
    for stock_name in stock_data.keys():
        print(f"\n{stock_name}:")
        print(f"  {'策略':<12} {'交易':>6} {'胜率':>8} {'总收益':>12}")
        print(f"  {'-'*40}")
        
        for strategy in ["current", "improved"]:
            r = results[strategy]
            detail = r['details'].get(stock_name, {})
            trades = detail.get('total_trades', 0)
            win_rate = detail.get('win_rate', 0) * 100
            total = detail.get('total_profit', 0)
            
            emoji = '🟢' if total > 0 else '🔴'
            print(f"  {r['name']:<12} {trades:>6} {win_rate:>7.1f}% {emoji}{total:>+11.2f}")
        
        # 打印改进策略的交易详情
        improved_detail = results['improved']['details'].get(stock_name, {})
        if improved_detail.get('trades'):
            print(f"\n  改进策略交易详情:")
            for t in improved_detail['trades']:
                if t['type'] == 'buy':
                    print(f"    {t['date']} 买入 {t['price']:.2f} ({t['reason']})")
                else:
                    emoji = '🟢' if t.get('profit_amount', 0) > 0 else '🔴'
                    print(f"    {t['date']} 卖出 {t['price']:.2f} {emoji} {t.get('profit_pct', 0):.1%} ({t['reason']})")
    
    # 总结
    print("\n" + "="*80)
    print("结论")
    print("="*80)
    
    current = results['current']
    improved = results['improved']
    
    print(f"\n收益对比:")
    print(f"  当前策略: {current['total_profit']:+.2f}")
    print(f"  改进策略: {improved['total_profit']:+.2f}")
    print(f"  差异: {improved['total_profit'] - current['total_profit']:+.2f}")
    
    print(f"\n胜率对比:")
    print(f"  当前策略: {current['win_rate']*100:.1f}%")
    print(f"  改进策略: {improved['win_rate']*100:.1f}%")
    
    print(f"\n交易次数:")
    print(f"  当前策略: {current['total_trades']} 次")
    print(f"  改进策略: {improved['total_trades']} 次")
    
    print(f"\n改进策略优势:")
    print(f"  ✅ 止损更宽松 (7% vs 5%)，减少被洗盘出局")
    print(f"  ✅ 需要确认突破，减少假突破")
    print(f"  ✅ 大盘过滤，避免逆势操作")


if __name__ == "__main__":
    run_backtest()
