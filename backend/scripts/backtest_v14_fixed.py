#!/usr/bin/env python3
"""v14策略回测 - 修复未来函数版本

修复内容：
1. 信号在t日收盘后计算
2. 买入在t+1日用开盘价执行
3. 卖出在t+1日用开盘价执行
"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# v14策略配置
CONFIG = {
    'initial_cash': 1_000_000,
    'max_positions': 4,
    'position_pct_high': 0.25,
    'position_pct_low': 0.18,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'cooldown_days': 3,
    'ma_period': 20,
    'atr_period': 14,
    'volume_ratio': 1.2,
    'atr_threshold': 0.02,
    'max_deviation': 0.10,
    'take_profit_pct': 0.40,
    'trailing_stop_pct': 0.08,
    'atr_stop_multiplier': 1.5,
    'chandelier_atr_mult': 3,
    'adx_threshold': 15,
    'max_per_sector': 1,
    'blacklist_days': 30,
    'portfolio_drawdown_stop': 0.07,
}

# 股票池
STOCK_POOL = [
    {'code': '600584', 'name': '长电科技', 'sector': '半导体'},
    {'code': '601138', 'name': '工业富联', 'sector': '半导体'},
    {'code': '002185', 'name': '华天科技', 'sector': '半导体'},
    {'code': '002049', 'name': '紫光国微', 'sector': '半导体'},
    {'code': '600487', 'name': '亨通光电', 'sector': '半导体'},
    {'code': '002916', 'name': '深南电路', 'sector': '半导体'},
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源'},
    {'code': '000333', 'name': '美的集团', 'sector': '家电'},
    {'code': '601899', 'name': '紫金矿业', 'sector': '有色'},
    {'code': '603993', 'name': '洛阳钼业', 'sector': '有色'},
    {'code': '002475', 'name': '立讯精密', 'sector': '科技'},
    {'code': '002371', 'name': '北方华创', 'sector': '半导体'},
    {'code': '600760', 'name': '中航沈飞', 'sector': '军工'},
    {'code': '600893', 'name': '航发动力', 'sector': '军工'},
    {'code': '600309', 'name': '万华化学', 'sector': '化工'},
    {'code': '600176', 'name': '中国巨石', 'sector': '化工'},
    {'code': '600900', 'name': '长江电力', 'sector': '电力'},
    {'code': '600025', 'name': '华能水电', 'sector': '电力'},
    {'code': '600031', 'name': '三一重工', 'sector': '机械'},
    {'code': '000425', 'name': '徐工机械', 'sector': '机械'},
]

def load_stock_data(ts_code, start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT trade_date, open, high, low, close, vol as volume
    FROM daily_quotes
    WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
    ORDER BY trade_date
    """
    df = pd.read_sql_query(query, conn, params=(ts_code, start_date, end_date))
    conn.close()
    if df.empty:
        return None
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    return df

def calculate_indicators(df):
    df = df.copy()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma5'] = df['close'].rolling(5).mean()
    df['atr'] = (df['high'] - df['low']).rolling(14).mean()
    df['vol_ma'] = df['volume'].rolling(5).mean()
    df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
    df['momentum'] = df['close'].pct_change(20)
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['signal']
    
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift(1)),
        abs(df['low'] - df['close'].shift(1))
    ], axis=1).max(axis=1)
    df['atr14'] = tr.rolling(14).mean()
    plus_dm = (df['high'] - df['high'].shift(1)).where(lambda x: x > 0, 0)
    minus_dm = (df['low'].shift(1) - df['low']).where(lambda x: x > 0, 0)
    plus_di = (plus_dm.rolling(14).mean() / df['atr14'] * 100)
    minus_di = (minus_dm.rolling(14).mean() / df['atr14'] * 100)
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    df['adx'] = dx.rolling(14).mean()
    
    return df

def calc_signal_score(row, config):
    """计算信号分数 - 使用t日收盘数据"""
    score = 0
    price = row['close']
    ma20 = row['ma20']
    atr = row['atr']
    vol_ma = row['vol_ma']
    rsi = row['rsi']
    macd = row['macd']
    signal = row['signal']
    adx = row['adx']
    
    if any(pd.isna(x) for x in [ma20, atr, vol_ma, rsi, macd, signal, adx]):
        return 0
    
    if adx < config['adx_threshold']:
        return 0
    
    deviation = abs(price - ma20) / ma20
    if deviation > config['max_deviation']:
        return 0
    score += 30
    
    if price >= ma20:
        score += 20
    else:
        return 0
    
    if vol_ma > 0 and row['volume'] > vol_ma * config['volume_ratio']:
        score += 15
    
    if price > 0 and atr / price > config['atr_threshold']:
        score += 10
    
    if 40 <= rsi <= 70:
        score += 10
    elif rsi > 70:
        return 0
    
    if macd > signal:
        score += 5
    
    return score

def check_sell_conditions(row, buy_price, highest, config):
    """检查卖出条件"""
    price = row['close']
    profit_pct = (price - buy_price) / buy_price
    ma20 = row['ma20']
    atr = row['atr']
    
    if pd.isna(atr):
        return None
    
    # Chandelier Exit
    chandelier_stop = highest - config['chandelier_atr_mult'] * atr
    if price <= chandelier_stop and profit_pct > 0:
        return 'Chandelier止盈'
    
    # ATR止损
    stop_price = buy_price - config['atr_stop_multiplier'] * atr
    if price <= stop_price:
        return 'ATR止损'
    
    # 移动止盈
    if profit_pct >= config['take_profit_pct']:
        trailing_stop = highest * (1 - config['trailing_stop_pct'])
        if price <= trailing_stop:
            return '移动止盈'
    
    # 跌破MA20
    if not pd.isna(ma20) and price < ma20 * 0.98:
        return '跌破MA20'
    
    return None

def run_backtest():
    """运行回测 - 修复未来函数版本"""
    print("📊 加载数据...")
    start_date = '2021-01-01'
    end_date = '2026-06-14'
    
    # 加载所有股票数据
    stocks_data = {}
    for stock in STOCK_POOL:
        code = stock['code']
        ts_code = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
        df = load_stock_data(ts_code, start_date, end_date)
        if df is not None and len(df) >= 25:
            df = calculate_indicators(df)
            stocks_data[code] = df
            print(f"  ✅ {stock['name']}: {len(df)}条")
    
    # 获取所有交易日
    all_dates = sorted(set().union(*[set(df.index) for df in stocks_data.values()]))
    
    # 初始化
    cash = CONFIG['initial_cash']
    positions = {}  # {code: {'shares': N, 'buy_price': P, 'highest': H, 'buy_date': D}}
    cooldown_until = {}
    daily_values = []
    trades = []
    
    print(f"\n📊 开始回测（修复未来函数版本）")
    print(f"   时间范围: {all_dates[0].strftime('%Y-%m-%d')} ~ {all_dates[-1].strftime('%Y-%m-%d')}")
    print(f"   股票池: {len(STOCK_POOL)}只")
    print(f"   关键修复: t日信号 → t+1日开盘价执行")
    print()
    
    # 遍历交易日
    for i in range(len(all_dates) - 1):  # 最后一天无法执行
        date = all_dates[i]
        next_date = all_dates[i + 1]
        
        # 计算当前持仓市值（用t日收盘价计算）
        portfolio_value = cash
        for code, pos in positions.items():
            if code in stocks_data and date in stocks_data[code].index:
                portfolio_value += stocks_data[code].loc[date, 'close'] * pos['shares']
        
        daily_values.append({'date': date, 'value': portfolio_value})
        
        # 组合熔断检查
        peak_value = max(d['value'] for d in daily_values) if daily_values else CONFIG['initial_cash']
        drawdown = (peak_value - portfolio_value) / peak_value
        if drawdown >= CONFIG['portfolio_drawdown_stop']:
            # 熔断：次日开盘清仓
            for code in list(positions.keys()):
                if code in stocks_data and next_date in stocks_data[code].index:
                    next_row = stocks_data[code].loc[next_date]
                    sell_price = next_row['open']  # 用次日开盘价卖出
                    pos = positions[code]
                    revenue = sell_price * pos['shares'] * (1 - CONFIG['commission'] - CONFIG['stamp_tax'] - CONFIG['slippage_pct'])
                    cash += revenue
                    pnl = (sell_price - pos['buy_price']) * pos['shares']
                    trades.append({
                        'date': next_date,
                        'code': code,
                        'action': 'SELL',
                        'reason': '组合熔断',
                        'price': sell_price,
                        'pnl': pnl
                    })
                    del positions[code]
            continue
        
        # t日收盘后：检查持仓股票的卖出条件
        sell_signals = []
        for code in list(positions.keys()):
            if code not in stocks_data or date not in stocks_data[code].index:
                continue
            
            row = stocks_data[code].loc[date]
            pos = positions[code]
            buy_price = pos['buy_price']
            highest = max(pos['highest'], row['close'])
            pos['highest'] = highest
            
            sell_reason = check_sell_conditions(row, buy_price, highest, CONFIG)
            if sell_reason:
                sell_signals.append((code, sell_reason))
        
        # t+1日开盘：执行卖出
        for code, reason in sell_signals:
            if code in stocks_data and next_date in stocks_data[code].index:
                next_row = stocks_data[code].loc[next_date]
                sell_price = next_row['open']  # 用次日开盘价卖出
                pos = positions[code]
                revenue = sell_price * pos['shares'] * (1 - CONFIG['commission'] - CONFIG['stamp_tax'] - CONFIG['slippage_pct'])
                cash += revenue
                pnl = (sell_price - pos['buy_price']) * pos['shares']
                trades.append({
                    'date': next_date,
                    'code': code,
                    'action': 'SELL',
                    'reason': reason,
                    'price': sell_price,
                    'pnl': pnl
                })
                cooldown_until[code] = next_date + timedelta(days=CONFIG['cooldown_days'])
                del positions[code]
        
        # t日收盘后：扫描买入信号
        buy_signals = []
        for stock in STOCK_POOL:
            code = stock['code']
            if code in positions:
                continue
            if code in cooldown_until and date < cooldown_until[code]:
                continue
            if code not in stocks_data or date not in stocks_data[code].index:
                continue
            
            row = stocks_data[code].loc[date]
            score = calc_signal_score(row, CONFIG)
            if score >= 70:
                buy_signals.append((code, stock['name'], stock['sector'], score))
        
        # 按分数排序
        buy_signals.sort(key=lambda x: x[3], reverse=True)
        
        # t+1日开盘：执行买入
        for code, name, sector, score in buy_signals:
            if len(positions) >= CONFIG['max_positions']:
                break
            
            # 同行业限制
            held_sectors = [s['sector'] for s in STOCK_POOL if s['code'] in positions]
            if sector in held_sectors:
                continue
            
            if code in stocks_data and next_date in stocks_data[code].index:
                next_row = stocks_data[code].loc[next_date]
                buy_price = next_row['open']  # 用次日开盘价买入
                
                # 计算仓位
                base_pct = CONFIG['position_pct_high'] if score >= 90 else CONFIG['position_pct_low']
                buy_amount = portfolio_value * base_pct
                shares = int(buy_amount / buy_price / 100) * 100
                if shares < 100:
                    continue
                
                cost = buy_price * shares * (1 + CONFIG['commission'] + CONFIG['slippage_pct'])
                if cost > cash:
                    continue
                
                cash -= cost
                positions[code] = {
                    'shares': shares,
                    'buy_price': buy_price,
                    'highest': buy_price,
                    'buy_date': next_date
                }
                trades.append({
                    'date': next_date,
                    'code': code,
                    'name': name,
                    'action': 'BUY',
                    'score': score,
                    'price': buy_price,
                    'pnl': 0
                })
        
        # 进度显示
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(all_dates)}] 权益: ¥{portfolio_value:,.0f}")
    
    # 最后一天也加入
    last_date = all_dates[-1]
    portfolio_value = cash
    for code, pos in positions.items():
        if code in stocks_data and last_date in stocks_data[code].index:
            portfolio_value += stocks_data[code].loc[last_date, 'close'] * pos['shares']
    daily_values.append({'date': last_date, 'value': portfolio_value})
    
    # 计算结果
    final_value = daily_values[-1]['value']
    total_return = (final_value - CONFIG['initial_cash']) / CONFIG['initial_cash']
    days = len(daily_values)
    years = days / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    
    values = [d['value'] for d in daily_values]
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    
    daily_returns = pd.Series(values).pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0
    
    # 统计交易
    sell_trades = [t for t in trades if t['action'] == 'SELL']
    win_trades = [t for t in sell_trades if t['pnl'] > 0]
    lose_trades = [t for t in sell_trades if t['pnl'] < 0]
    win_rate = len(win_trades) / len(sell_trades) if sell_trades else 0
    
    # 输出结果
    print()
    print("=" * 70)
    print("📊 v14策略回测结果（修复未来函数版本）")
    print("=" * 70)
    print(f"  初始资金:     ¥{CONFIG['initial_cash']:,.0f}")
    print(f"  最终权益:     ¥{final_value:,.0f}")
    print(f"  总收益:       {total_return:.1%}")
    print(f"  年化收益:     {annual_return:.1%}")
    print(f"  最大回撤:     {max_dd:.1%}")
    print(f"  夏普比率:     {sharpe:.2f}")
    print(f"  交易次数:     {len(trades)}笔")
    print(f"  胜率:         {win_rate:.1%}")
    print(f"  盈利交易:     {len(win_trades)}笔")
    print(f"  亏损交易:     {len(lose_trades)}笔")
    print()
    print("📌 关键修复：")
    print("  - 信号在t日收盘后计算")
    print("  - 买入在t+1日用开盘价执行")
    print("  - 卖出在t+1日用开盘价执行")
    print("=" * 70)
    
    # 保存结果
    result = {
        'strategy': 'v14 修复未来函数',
        'initial_cash': CONFIG['initial_cash'],
        'final_value': final_value,
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_dd,
        'sharpe': sharpe,
        'trade_count': len(trades),
        'win_rate': win_rate,
        'days': days,
    }
    
    result_file = '/root/projects/ai-quant-stock/backend/data/backtest_v14_fixed_result.json'
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  结果已保存: {result_file}")
    
    return result

if __name__ == '__main__':
    run_backtest()
