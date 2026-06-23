#!/usr/bin/env python3
"""
策略回测：不同仓位比例对比
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


def calculate_atr(prices, period=14):
    changes = prices.diff().abs()
    return changes.rolling(window=period).mean()


def backtest_with_position(stock_df, initial_capital=200000, position_pct=0.15, 
                           max_positions=5, trailing_stop=True):
    """
    回测策略 - 支持仓位比例和移动止盈
    """
    if stock_df.empty:
        return {}
    
    # 计算技术指标
    stock_df['ma20'] = calculate_ma(stock_df['close'], 20)
    stock_df['atr'] = calculate_atr(stock_df['close'], 14)
    stock_df['avg_vol'] = stock_df['vol'].rolling(window=5).mean()
    
    # 资金和持仓
    capital = initial_capital
    available = initial_capital
    positions = {}  # code -> {'quantity': int, 'buy_price': float, 'buy_idx': int, 'max_profit': float}
    trades = []
    equity_curve = []
    
    for i in range(20, len(stock_df)):
        row = stock_df.iloc[i]
        prev_row = stock_df.iloc[i-1]
        
        if pd.isna(row['ma20']) or pd.isna(row['atr']):
            continue
        
        # 计算当前持仓市值
        pos_value = 0
        for code, pos in positions.items():
            pos_value += pos['quantity'] * row['close']
        
        total_equity = available + pos_value
        equity_curve.append({'date': row['trade_date'], 'equity': total_equity})
        
        # 检查卖出
        codes_to_sell = []
        for code, pos in positions.items():
            profit_pct = (row['close'] - pos['buy_price']) / pos['buy_price']
            
            # 更新最高收益
            pos['max_profit'] = max(pos['max_profit'], profit_pct)
            
            sell_reason = None
            
            # 止损5%
            if profit_pct <= -0.05:
                sell_reason = '止损'
            
            # 移动止盈
            elif trailing_stop and pos['max_profit'] >= 0.15:
                trailing_stop_line = pos['max_profit'] - 0.05
                if profit_pct <= trailing_stop_line:
                    sell_reason = '移动止盈'
            
            # 固定止盈15%
            elif not trailing_stop and profit_pct >= 0.15:
                sell_reason = '固定止盈'
            
            # 跌破MA20
            elif row['close'] < row['ma20'] * 0.98:
                sell_reason = '跌破MA20'
            
            if sell_reason:
                sell_amount = pos['quantity'] * row['close']
                available += sell_amount
                trades.append({
                    'type': 'sell',
                    'date': row['trade_date'],
                    'price': row['close'],
                    'quantity': pos['quantity'],
                    'amount': sell_amount,
                    'profit_pct': profit_pct,
                    'profit_amount': (row['close'] - pos['buy_price']) * pos['quantity'],
                    'max_profit': pos['max_profit'],
                    'reason': sell_reason,
                })
                codes_to_sell.append(code)
        
        for code in codes_to_sell:
            del positions[code]
        
        # 检查买入
        if len(positions) < max_positions:
            deviation = abs(row['close'] - row['ma20']) / row['ma20'] if row['ma20'] > 0 else 1
            volume_ok = row['vol'] > row['avg_vol'] * 1.5 if not pd.isna(row['avg_vol']) else False
            atr_ok = row['atr'] / row['close'] > 0.02 if row['close'] > 0 else False
            
            if (deviation < 0.10 and volume_ok and atr_ok and
                prev_row['close'] < prev_row['ma20'] and row['close'] >= row['ma20']):
                
                # 计算买入数量
                max_amount = total_equity * position_pct
                quantity = int(max_amount / row['close'] / 100) * 100
                
                if quantity > 0 and quantity * row['close'] <= available:
                    buy_amount = quantity * row['close']
                    available -= buy_amount
                    positions['STOCK'] = {
                        'quantity': quantity,
                        'buy_price': row['close'],
                        'buy_idx': i,
                        'max_profit': 0,
                    }
                    trades.append({
                        'type': 'buy',
                        'date': row['trade_date'],
                        'price': row['close'],
                        'quantity': quantity,
                        'amount': buy_amount,
                    })
    
    # 计算统计
    sell_trades = [t for t in trades if t['type'] == 'sell']
    win_trades = [t for t in sell_trades if t.get('profit_amount', 0) > 0]
    lose_trades = [t for t in sell_trades if t.get('profit_amount', 0) <= 0]
    
    total_profit = sum(t.get('profit_amount', 0) for t in sell_trades)
    max_equity = max(e['equity'] for e in equity_curve) if equity_curve else initial_capital
    min_equity = min(e['equity'] for e in equity_curve) if equity_curve else initial_capital
    max_drawdown = (max_equity - min_equity) / max_equity if max_equity > 0 else 0
    
    return {
        'trades': trades,
        'total_trades': len(sell_trades),
        'win_trades': len(win_trades),
        'lose_trades': len(lose_trades),
        'win_rate': len(win_trades) / max(len(sell_trades), 1),
        'total_profit': total_profit,
        'total_return': total_profit / initial_capital,
        'avg_profit': total_profit / max(len(sell_trades), 1),
        'max_drawdown': max_drawdown,
        'final_equity': equity_curve[-1]['equity'] if equity_curve else initial_capital,
        'equity_curve': equity_curve,
    }


def run_backtest():
    start_date = '20250101'
    end_date = '20260610'
    initial_capital = 200000
    
    stocks = [
        {'code': '600487', 'name': '亨通光电'},
        {'code': '601208', 'name': '东材科技'},
        {'code': '601138', 'name': '工业富联'},
    ]
    
    # 不同仓位比例
    position_pcts = [0.10, 0.15, 0.20, 0.25, 0.30]
    
    print("="*80)
    print("仓位比例回测对比")
    print("="*80)
    print(f"初始资金: {initial_capital:,} 元")
    print(f"回测期间: {start_date} ~ {end_date}")
    print(f"股票池: {', '.join(s['name'] for s in stocks)}")
    print(f"止盈模式: 移动止盈 (15%启动, 5%回撤)")
    print("="*80)
    
    # 获取数据
    stock_data = {}
    for stock in stocks:
        df = get_stock_data(stock['code'], start_date, end_date)
        if not df.empty:
            stock_data[stock['name']] = df
    
    # 测试不同仓位比例
    results = []
    
    for pct in position_pcts:
        total_profit = 0
        total_trades = 0
        total_win = 0
        total_lose = 0
        max_drawdown = 0
        final_equity = 0
        
        for stock_name, df in stock_data.items():
            result = backtest_with_position(df.copy(), initial_capital, pct, max_positions=5, trailing_stop=True)
            total_profit += result.get('total_profit', 0)
            total_trades += result.get('total_trades', 0)
            total_win += result.get('win_trades', 0)
            total_lose += result.get('lose_trades', 0)
            max_drawdown = max(max_drawdown, result.get('max_drawdown', 0))
            final_equity += result.get('final_equity', initial_capital)
        
        win_rate = total_win / max(total_trades, 1)
        avg_profit = total_profit / max(total_trades, 1)
        total_return = total_profit / initial_capital
        
        results.append({
            'pct': pct,
            'total_trades': total_trades,
            'win_trades': total_win,
            'lose_trades': total_lose,
            'win_rate': win_rate,
            'total_profit': total_profit,
            'total_return': total_return,
            'avg_profit': avg_profit,
            'max_drawdown': max_drawdown,
            'final_equity': final_equity,
        })
    
    # 打印对比表
    print(f"\n{'仓位':>6} {'交易':>6} {'盈利':>6} {'亏损':>6} {'胜率':>8} {'总收益':>12} {'收益率':>8} {'平均收益':>10} {'最大回撤':>8}")
    print("-"*85)
    
    for r in results:
        emoji = '🟢' if r['total_profit'] > 0 else '🔴'
        print(f"{r['pct']*100:>5.0f}% {r['total_trades']:>6} {r['win_trades']:>6} {r['lose_trades']:>6} "
              f"{r['win_rate']*100:>7.1f}% {emoji}{r['total_profit']:>+11.2f} {r['total_return']*100:>+7.1f}% "
              f"{r['avg_profit']:>+9.2f} {r['max_drawdown']*100:>7.1f}%")
    
    # 找出最优仓位
    best_profit = max(results, key=lambda x: x['total_profit'])
    best_return = max(results, key=lambda x: x['total_return'])
    best_drawdown = min(results, key=lambda x: x['max_drawdown'])
    
    print("\n" + "="*80)
    print("结论")
    print("="*80)
    
    print(f"\n最高总收益: {best_profit['pct']*100:.0f}% 仓位 (收益: {best_profit['total_profit']:+.2f})")
    print(f"最高收益率: {best_return['pct']*100:.0f}% 仓位 (收益率: {best_return['total_return']*100:+.1f}%)")
    print(f"最小回撤: {best_drawdown['pct']*100:.0f}% 仓位 (回撤: {best_drawdown['max_drawdown']*100:.1f}%)")
    
    # 风险收益比
    print(f"\n风险收益比:")
    for r in results:
        risk_return = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] > 0 else 0
        print(f"  {r['pct']*100:.0f}% 仓位: 收益{r['total_return']*100:+.1f}% / 回撤{r['max_drawdown']*100:.1f}% = {risk_return:.2f}")
    
    # 推荐
    print(f"\n推荐仓位:")
    print(f"  保守型: 10-15% (低回撤, 稳健收益)")
    print(f"  平衡型: 15-20% (适中回撤, 适中收益)")
    print(f"  激进型: 20-30% (高回撤, 高收益)")


if __name__ == "__main__":
    run_backtest()
