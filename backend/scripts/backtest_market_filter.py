#!/usr/bin/env python3
"""
策略回测：对比有无大盘过滤的MA20策略
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


def get_index_data(index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取指数日线数据"""
    try:
        df = pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
        if df.empty:
            return pd.DataFrame()
        df = df.sort_values('trade_date').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"获取{index_code}数据失败: {e}")
        return pd.DataFrame()


def calculate_ma(prices: pd.Series, period: int = 20) -> pd.Series:
    """计算移动平均线"""
    return prices.rolling(window=period).mean()


def calculate_atr(prices: pd.Series, period: int = 14) -> pd.Series:
    """计算ATR"""
    changes = prices.diff().abs()
    return changes.rolling(window=period).mean()


def backtest_strategy(stock_df: pd.DataFrame, index_df: pd.DataFrame = None, 
                      use_market_filter: bool = False) -> dict:
    """
    回测MA20策略
    
    Args:
        stock_df: 股票数据
        index_df: 指数数据（大盘）
        use_market_filter: 是否使用大盘过滤
    
    Returns:
        回测结果
    """
    if stock_df.empty:
        return {}
    
    # 计算技术指标
    stock_df['ma20'] = calculate_ma(stock_df['close'], 20)
    stock_df['atr'] = calculate_atr(stock_df['close'], 14)
    stock_df['avg_vol'] = stock_df['vol'].rolling(window=5).mean()
    
    # 如果使用大盘过滤，计算大盘MA20
    if use_market_filter and index_df is not None and not index_df.empty:
        index_df['ma20'] = calculate_ma(index_df['close'], 20)
        # 合并数据
        stock_df = stock_df.merge(
            index_df[['trade_date', 'close', 'ma20']].rename(
                columns={'close': 'index_close', 'ma20': 'index_ma20'}
            ),
            on='trade_date',
            how='left'
        )
    
    # 初始化交易记录
    trades = []
    position = None  # {'buy_price': float, 'buy_date': str, 'quantity': int}
    
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
        
        # 大盘过滤条件
        market_condition = True
        if use_market_filter and 'index_close' in row and 'index_ma20' in row:
            if not pd.isna(row['index_close']) and not pd.isna(row['index_ma20']):
                # 大盘在MA20之上
                market_condition = row['index_close'] > row['index_ma20']
        
        # 买入逻辑
        if position is None:
            # 买入条件
            buy_condition = (
                deviation < 0.10 and  # 偏离度<10%
                volume_condition and  # 成交量放大
                atr_condition and  # ATR足够
                prev_row['close'] < prev_row['ma20'] and  # 前一日在MA20下方
                row['close'] >= row['ma20'] and  # 当日突破MA20
                market_condition  # 大盘条件
            )
            
            if buy_condition:
                position = {
                    'buy_price': row['close'],
                    'buy_date': row['trade_date'],
                    'quantity': 10000 // row['close']  # 假设1万元
                }
                trades.append({
                    'type': 'buy',
                    'date': row['trade_date'],
                    'price': row['close'],
                    'quantity': position['quantity'],
                    'reason': 'MA20突破买入'
                })
        
        # 卖出逻辑
        else:
            profit_pct = (row['close'] - position['buy_price']) / position['buy_price']
            
            # 卖出条件
            sell_condition = (
                profit_pct <= -0.05 or  # 止损5%
                profit_pct >= 0.15 or   # 止盈15%
                row['close'] < row['ma20'] * 0.98  # 跌破MA20
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
    # 回测参数
    start_date = '20250101'
    end_date = '20260610'
    
    # 监控股票
    stocks = [
        {'code': '600487', 'name': '亨通光电'},
        {'code': '601208', 'name': '东材科技'},
        {'code': '601138', 'name': '工业富联'},
    ]
    
    # 获取大盘数据（上证指数）
    print("获取大盘数据...")
    index_df = get_index_data('000001.SH', start_date, end_date)
    
    if not index_df.empty:
        print(f"大盘数据: {len(index_df)} 条")
        # 计算大盘MA20
        index_df['ma20'] = calculate_ma(index_df['close'], 20)
        # 统计大盘在MA20上方的比例
        above_ma20 = (index_df['close'] > index_df['ma20']).sum()
        print(f"大盘在MA20上方: {above_ma20}/{len(index_df)} ({above_ma20/len(index_df)*100:.1f}%)")
    else:
        print("获取大盘数据失败")
    
    print("\n" + "="*70)
    print("策略回测对比: 有无大盘过滤")
    print("="*70)
    
    results = []
    
    for stock in stocks:
        print(f"\n{'='*50}")
        print(f"回测: {stock['name']} ({stock['code']})")
        print('='*50)
        
        # 获取股票数据
        stock_df = get_stock_data(stock['code'], start_date, end_date)
        if stock_df.empty:
            print(f"获取{stock['name']}数据失败")
            continue
        
        print(f"数据范围: {stock_df.iloc[0]['trade_date']} ~ {stock_df.iloc[-1]['trade_date']}")
        print(f"数据条数: {len(stock_df)}")
        
        # 回测1: 无大盘过滤
        result1 = backtest_strategy(stock_df.copy(), index_df, use_market_filter=False)
        
        # 回测2: 有大盘过滤
        result2 = backtest_strategy(stock_df.copy(), index_df, use_market_filter=True)
        
        results.append({
            'stock': stock['name'],
            'no_filter': result1,
            'with_filter': result2,
        })
        
        # 打印对比
        print(f"\n{'指标':<15} {'无大盘过滤':>12} {'有大盘过滤':>12} {'差异':>12}")
        print("-"*55)
        
        trades1 = result1.get('total_trades', 0)
        trades2 = result2.get('total_trades', 0)
        print(f"{'交易次数':<15} {trades1:>12} {trades2:>12} {trades2-trades1:>+12}")
        
        win1 = result1.get('win_trades', 0)
        win2 = result2.get('win_trades', 0)
        print(f"{'盈利次数':<15} {win1:>12} {win2:>12} {win2-win1:>+12}")
        
        lose1 = result1.get('lose_trades', 0)
        lose2 = result2.get('lose_trades', 0)
        print(f"{'亏损次数':<15} {lose1:>12} {lose2:>12} {lose2-lose1:>+12}")
        
        wr1 = result1.get('win_rate', 0) * 100
        wr2 = result2.get('win_rate', 0) * 100
        print(f"{'胜率%':<15} {wr1:>11.1f}% {wr2:>11.1f}% {wr2-wr1:>+11.1f}%")
        
        profit1 = result1.get('total_profit', 0)
        profit2 = result2.get('total_profit', 0)
        print(f"{'总收益':<15} {profit1:>12.2f} {profit2:>12.2f} {profit2-profit1:>+12.2f}")
        
        avg1 = result1.get('avg_profit', 0)
        avg2 = result2.get('avg_profit', 0)
        print(f"{'平均收益':<15} {avg1:>12.2f} {avg2:>12.2f} {avg2-avg1:>+12.2f}")
    
    # 打印交易详情
    print("\n" + "="*70)
    print("交易详情对比")
    print("="*70)
    
    for r in results:
        print(f"\n{r['stock']}:")
        
        print("\n  无大盘过滤:")
        for t in r['no_filter'].get('trades', []):
            if t['type'] == 'buy':
                print(f"    {t['date']} 买入 {t['price']:.2f}")
            else:
                emoji = '🟢' if t.get('profit_amount', 0) > 0 else '🔴'
                print(f"    {t['date']} 卖出 {t['price']:.2f} {emoji} {t.get('profit_pct', 0):.1%} ({t['reason']})")
        
        print("\n  有大盘过滤:")
        for t in r['with_filter'].get('trades', []):
            if t['type'] == 'buy':
                print(f"    {t['date']} 买入 {t['price']:.2f}")
            else:
                emoji = '🟢' if t.get('profit_amount', 0) > 0 else '🔴'
                print(f"    {t['date']} 卖出 {t['price']:.2f} {emoji} {t.get('profit_pct', 0):.1%} ({t['reason']})")
    
    # 总结
    print("\n" + "="*70)
    print("回测总结")
    print("="*70)
    
    total_profit_no_filter = sum(r['no_filter'].get('total_profit', 0) for r in results)
    total_profit_with_filter = sum(r['with_filter'].get('total_profit', 0) for r in results)
    
    total_trades_no_filter = sum(r['no_filter'].get('total_trades', 0) for r in results)
    total_trades_with_filter = sum(r['with_filter'].get('total_trades', 0) for r in results)
    
    print(f"\n总收益对比:")
    print(f"  无大盘过滤: {total_profit_no_filter:.2f}")
    print(f"  有大盘过滤: {total_profit_with_filter:.2f}")
    print(f"  差异: {total_profit_with_filter - total_profit_no_filter:+.2f}")
    
    print(f"\n交易次数对比:")
    print(f"  无大盘过滤: {total_trades_no_filter}")
    print(f"  有大盘过滤: {total_trades_with_filter}")
    print(f"  减少: {total_trades_no_filter - total_trades_with_filter} 次")
    
    if total_trades_no_filter > 0 and total_trades_with_filter > 0:
        avg_no = total_profit_no_filter / total_trades_no_filter
        avg_with = total_profit_with_filter / total_trades_with_filter
        print(f"\n平均收益对比:")
        print(f"  无大盘过滤: {avg_no:.2f}/笔")
        print(f"  有大盘过滤: {avg_with:.2f}/笔")
        print(f"  差异: {avg_with - avg_no:+.2f}/笔")


if __name__ == "__main__":
    run_backtest()
