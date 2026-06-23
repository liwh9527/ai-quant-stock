#!/usr/bin/env python3
"""沪深300 + 主升浪优化版#1381 回测

参数：
- 股票池：沪深300典型成分股（20只）
- 动量阈值：20%
- 量比阈值：1.5x
- 移动止盈：5%
- 组合熔断：10%
- 时间范围：2021-01-01 ~ 2026-06-17
"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
import math

DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# 沪深300股票池
STOCK_POOL = [
    {'code': '600487.SH', 'name': '亨通光电', 'sector': '半导体'},
    {'code': '002371.SZ', 'name': '北方华创', 'sector': '半导体'},
    {'code': '600584.SH', 'name': '长电科技', 'sector': '半导体'},
    {'code': '002916.SZ', 'name': '深南电路', 'sector': '半导体'},
    {'code': '002185.SZ', 'name': '华天科技', 'sector': '半导体'},
    {'code': '601899.SH', 'name': '紫金矿业', 'sector': '有色'},
    {'code': '603993.SH', 'name': '洛阳钼业', 'sector': '有色'},
    {'code': '600025.SH', 'name': '华能水电', 'sector': '电力'},
    {'code': '600900.SH', 'name': '长江电力', 'sector': '电力'},
    {'code': '600519.SH', 'name': '贵州茅台', 'sector': '消费'},
    {'code': '000858.SZ', 'name': '五粮液', 'sector': '消费'},
    {'code': '000333.SZ', 'name': '美的集团', 'sector': '家电'},
    {'code': '600309.SH', 'name': '万华化学', 'sector': '化工'},
    {'code': '600031.SH', 'name': '三一重工', 'sector': '机械'},
    {'code': '002415.SZ', 'name': '海康威视', 'sector': '科技'},
    {'code': '002594.SZ', 'name': '比亚迪', 'sector': '新能源'},
    {'code': '002475.SZ', 'name': '立讯精密', 'sector': '科技'},
    {'code': '600036.SH', 'name': '招商银行', 'sector': '金融'},
    {'code': '601318.SH', 'name': '中国平安', 'sector': '金融'},
    {'code': '600760.SH', 'name': '中航沈飞', 'sector': '军工'},
]

# 策略配置 - 主升浪优化版#1381（动量20%）
CONFIG = {
    'ma_period': 20,
    'atr_period': 14,
    'volume_ratio': 1.5,
    'atr_threshold': 0.02,
    'max_deviation': 0.10,
    'take_profit_pct': 0.40,
    'trailing_stop_pct': 0.05,
    'atr_stop_multiplier': 1.5,
    'chandelier_atr_mult': 3,
    'max_positions': 4,
    'position_pct_high': 0.25,
    'position_pct_low': 0.18,
    'adx_threshold': 15,
    'momentum_threshold': 0.20,
    'cooldown_days': 3,
    'portfolio_drawdown_stop': 0.10,
}

def load_data():
    """从数据库加载股票数据"""
    conn = sqlite3.connect(DB_PATH)
    
    # 获取股票代码映射
    stock_codes = [s['code'] for s in STOCK_POOL]
    placeholders = ','.join(['?' for _ in stock_codes])
    
    query = f"""
        SELECT ts_code, trade_date, open, high, low, close, vol as volume
        FROM daily_quotes
        WHERE ts_code IN ({placeholders})
        AND trade_date >= '2021-01-01'
        ORDER BY ts_code, trade_date
    """
    
    df = pd.read_sql_query(query, conn, params=stock_codes)
    conn.close()
    
    # 转换日期
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    
    return df

def calculate_indicators(df):
    """计算技术指标"""
    df = df.copy()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma5'] = df['close'].rolling(5).mean()
    df['atr'] = (df['high'] - df['low']).rolling(14).mean()
    df['vol_ma'] = df['volume'].rolling(5).mean()
    df['volatility'] = df['close'].rolling(20).std() / df['close'] * math.sqrt(252)
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['signal']
    
    # ADX
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
    
    # 20日动量
    df['momentum'] = df['close'].pct_change(20)
    
    return df

def calc_signal_score(row, config):
    """计算买入信号评分"""
    score = 0
    price = row['close']
    ma = row['ma20']
    atr = row['atr']
    vol = row['volume']
    vol_ma = row['vol_ma']
    rsi = row['rsi']
    macd_hist = row['macd_hist']
    momentum = row['momentum']
    adx = row['adx']
    
    if any(pd.isna(x) for x in [ma, atr, vol_ma, rsi, macd_hist, momentum, adx]):
        return 0
    
    # ADX检查
    if adx < config['adx_threshold']:
        return 0
    
    deviation = abs(price - ma) / ma
    if deviation > config['max_deviation']:
        return 0
    score += 30
    
    if price >= ma:
        score += 20
    else:
        return 0
    
    # 动量检查
    if momentum < config['momentum_threshold']:
        return 0
    score += 10
    
    if vol_ma > 0 and vol > vol_ma * config['volume_ratio']:
        score += 15
    
    if price > 0 and atr / price > config['atr_threshold']:
        score += 10
    
    if 40 <= rsi <= 70:
        score += 10
    elif rsi > 70:
        return 0
    
    if macd_hist > 0:
        score += 5
    
    return score

def check_sell(current_price, buy_price, highest, max_profit, row, config):
    """检查卖出条件"""
    profit_pct = (current_price - buy_price) / buy_price
    atr = row['atr']
    ma = row['ma20']
    
    if pd.isna(atr):
        return None
    
    # Chandelier Exit
    chandelier_stop = highest - config['chandelier_atr_mult'] * atr
    if current_price <= chandelier_stop and profit_pct > 0:
        return f"Chandelier止盈({profit_pct:.1%})"
    
    # ATR止损
    stop_price = buy_price - config['atr_stop_multiplier'] * atr
    if current_price <= stop_price:
        return f"ATR止损({profit_pct:.1%})"
    
    # 移动止盈
    if max_profit >= config['take_profit_pct']:
        trailing_pct = config['trailing_stop_pct']
        if profit_pct <= max_profit - trailing_pct:
            return f"移动止盈({max_profit:.1%}→{profit_pct:.1%})"
    
    # 跌破MA20
    if not pd.isna(ma):
        if current_price < ma * 0.98:
            return f"跌破MA20({profit_pct:.1%})"
    
    return None

def run_backtest():
    """运行回测"""
    print("📊 加载数据...")
    df = load_data()
    
    # 按股票分组
    stocks_data = {}
    for _, row in df.iterrows():
        code = row['ts_code']
        if code not in stocks_data:
            stocks_data[code] = []
        stocks_data[code].append(row)
    
    # 转换为DataFrame并计算指标
    print("📊 计算指标...")
    for code in stocks_data:
        stock_df = pd.DataFrame(stocks_data[code])
        stock_df = stock_df.set_index('trade_date').sort_index()
        stock_df = calculate_indicators(stock_df)
        stocks_data[code] = stock_df
    
    # 获取所有交易日
    all_dates = sorted(df['trade_date'].unique())
    
    # 回测参数
    initial_cash = 1000000  # 初始资金100万
    cash = initial_cash
    positions = {}  # {code: {'shares': N, 'buy_price': P, 'highest': H, 'max_profit': M, 'buy_date': D}}
    cooldown_until = {}  # 冷却期
    
    daily_values = []
    trades = []
    
    print(f"📊 开始回测: {all_dates[0].strftime('%Y-%m-%d')} ~ {all_dates[-1].strftime('%Y-%m-%d')}")
    print(f"   初始资金: ¥{initial_cash:,.0f}")
    print(f"   股票池: {len(STOCK_POOL)}只")
    print()
    
    for date in all_dates:
        # 计算当前持仓市值
        portfolio_value = cash
        for code, pos in positions.items():
            if code in stocks_data and date in stocks_data[code].index:
                current_price = stocks_data[code].loc[date, 'close']
                portfolio_value += current_price * pos['shares']
        
        daily_values.append({
            'date': date.strftime('%Y-%m-%d'),
            'value': portfolio_value
        })
        
        # 组合熔断检查
        peak_value = max(d['value'] for d in daily_values)
        drawdown = (peak_value - portfolio_value) / peak_value
        if drawdown >= CONFIG['portfolio_drawdown_stop']:
            # 熔断：清仓
            for code in list(positions.keys()):
                if code in stocks_data and date in stocks_data[code].index:
                    current_price = stocks_data[code].loc[date, 'close']
                    pos = positions[code]
                    cash += current_price * pos['shares']
                    pnl = (current_price - pos['buy_price']) * pos['shares']
                    trades.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'code': code,
                        'action': 'SELL',
                        'reason': '组合熔断',
                        'price': current_price,
                        'shares': pos['shares'],
                        'pnl': pnl
                    })
                    del positions[code]
            continue
        
        # 遍历股票池
        for stock in STOCK_POOL:
            code = stock['code']
            name = stock['name']
            
            if code not in stocks_data or date not in stocks_data[code].index:
                continue
            
            row = stocks_data[code].loc[date]
            current_price = row['close']
            
            # 已持仓 → 检查卖出
            if code in positions:
                pos = positions[code]
                buy_price = pos['buy_price']
                highest = max(pos['highest'], current_price)
                max_profit = max(pos['max_profit'], (current_price - buy_price) / buy_price)
                
                pos['highest'] = highest
                pos['max_profit'] = max_profit
                
                sell_reason = check_sell(current_price, buy_price, highest, max_profit, row, CONFIG)
                if sell_reason:
                    cash += current_price * pos['shares']
                    pnl = (current_price - buy_price) * pos['shares']
                    trades.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'code': code,
                        'name': name,
                        'action': 'SELL',
                        'reason': sell_reason,
                        'price': current_price,
                        'shares': pos['shares'],
                        'pnl': pnl
                    })
                    cooldown_until[code] = date + timedelta(days=CONFIG['cooldown_days'])
                    del positions[code]
            
            # 未持仓 → 检查买入
            else:
                # 冷却期检查
                if code in cooldown_until and date < cooldown_until[code]:
                    continue
                
                # 持仓数量检查
                if len(positions) >= CONFIG['max_positions']:
                    continue
                
                # 同行业限制
                held_sectors = [s['sector'] for s in STOCK_POOL if s['code'] in positions]
                if stock['sector'] in held_sectors:
                    continue
                
                # 计算信号评分
                score = calc_signal_score(row, CONFIG)
                if score < 70:
                    continue
                
                # 计算仓位
                base_pct = CONFIG['position_pct_high'] if score >= 90 else CONFIG['position_pct_low']
                cur_vol = row.get('volatility', 0)
                if not pd.isna(cur_vol) and cur_vol > 0:
                    vol_ratio = 0.15 / cur_vol
                    ratio = max(0.8, min(1.2, vol_ratio))
                    pct = base_pct * ratio
                else:
                    pct = base_pct
                
                # 计算买入数量
                buy_amount = portfolio_value * pct
                shares = int(buy_amount / current_price / 100) * 100  # 取整到100股
                if shares < 100:
                    continue
                
                cost = current_price * shares
                if cost > cash:
                    continue
                
                cash -= cost
                positions[code] = {
                    'shares': shares,
                    'buy_price': current_price,
                    'highest': current_price,
                    'max_profit': 0,
                    'buy_date': date
                }
                trades.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'code': code,
                    'name': name,
                    'action': 'BUY',
                    'reason': f'评分{score}',
                    'price': current_price,
                    'shares': shares,
                    'pnl': 0
                })
    
    # 计算结果
    final_value = daily_values[-1]['value']
    total_return = (final_value - initial_cash) / initial_cash
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
    
    # 输出结果
    print()
    print("=" * 70)
    print("📊 回测结果")
    print("=" * 70)
    print(f"  初始资金:     ¥{initial_cash:,.0f}")
    print(f"  最终权益:     ¥{final_value:,.0f}")
    print(f"  总收益:       {total_return:.1%}")
    print(f"  年化收益:     {annual_return:.1%}")
    print(f"  最大回撤:     {max_dd:.1%}")
    print(f"  夏普比率:     {sharpe:.2f}")
    print(f"  交易次数:     {len(trades)}")
    print(f"  回测天数:     {days}天 ({years:.1f}年)")
    print()
    
    # 统计交易
    buy_trades = [t for t in trades if t['action'] == 'BUY']
    sell_trades = [t for t in trades if t['action'] == 'SELL']
    win_trades = [t for t in sell_trades if t['pnl'] > 0]
    lose_trades = [t for t in sell_trades if t['pnl'] < 0]
    
    if sell_trades:
        win_rate = len(win_trades) / len(sell_trades)
        avg_win = np.mean([t['pnl'] for t in win_trades]) if win_trades else 0
        avg_loss = np.mean([t['pnl'] for t in lose_trades]) if lose_trades else 0
        
        print(f"  胜率:         {win_rate:.1%}")
        print(f"  盈利交易:     {len(win_trades)}笔 (平均 ¥{avg_win:,.0f})")
        print(f"  亏损交易:     {len(lose_trades)}笔 (平均 ¥{avg_loss:,.0f})")
    
    print()
    
    # 保存结果
    result = {
        'strategy': '主升浪优化版#1381 (沪深300, 动量20%)',
        'initial_cash': initial_cash,
        'final_value': final_value,
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_dd,
        'sharpe': sharpe,
        'trade_count': len(trades),
        'days': days,
        'config': CONFIG,
        'stock_pool': '沪深300 (20只)',
    }
    
    result_file = '/root/projects/ai-quant-stock/backend/data/backtest_hs300_v1381_result.json'
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  结果已保存: {result_file}")
    
    return result

if __name__ == '__main__':
    run_backtest()
