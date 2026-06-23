#!/usr/bin/env python3
"""趋势跟踪+大盘择时组合策略5年回测

核心规则：
1. 择时：大盘MA20上方才入场
2. 选股：MA20上方 + 放量 + RSI适中
3. 仓位：根据波动率动态调整
4. 止损：ATR动态止损
5. 轮动：每周检查，换强势股
"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

STOCK_POOL = [
    '600487.SH', '601138.SH', '002371.SZ', '002916.SZ', '600584.SH',
    '002185.SZ', '601899.SH', '603993.SH', '600176.SH',
    '600025.SH', '600900.SH', '600309.SH', '000425.SZ', '600031.SH',
    '002475.SZ', '000333.SZ',
]

NAMES = {
    '600487.SH': '亨通光电', '601138.SH': '工业富联', '002371.SZ': '北方华创',
    '002916.SZ': '深南电路', '600584.SH': '长电科技', '002185.SZ': '华天科技',
    '601899.SH': '紫金矿业', '603993.SH': '洛阳钼业', '600176.SH': '中国巨石',
    '600025.SH': '华能水电', '600900.SH': '长江电力', '600309.SH': '万华化学',
    '000425.SZ': '徐工机械', '600031.SH': '三一重工', '002475.SZ': '立讯精密',
    '000333.SZ': '美的集团',
}

CONFIG = {
    'initial_cash': 1_000_000,
    'max_positions': 4,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'rebalance_days': 5,
    'position_low_vol': 0.60,
    'position_high_vol': 0.40,
    'vol_threshold': 0.35,
    'stop_loss_atr': 2.0,
    'take_profit_pct': 0.30,
    'trailing_stop_pct': 0.08,
}

def load_data(ts_code, start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"""
        SELECT trade_date, open, high, low, close, vol as volume 
        FROM daily_quotes WHERE ts_code='{ts_code}' 
        AND trade_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY trade_date
    """, conn)
    conn.close()
    if df.empty: return None
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(14).mean()
    df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
    df['momentum'] = df['close'].pct_change(20)
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma']
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain/loss))
    return df

class TrendTimingBacktest:
    def __init__(self, config, stock_data, index_data):
        self.config = config
        self.cash = config['initial_cash']
        self.positions = {}
        self.buy_prices = {}
        self.max_profits = {}
        self.trade_log = []
        self.daily_values = []
        self.stock_data = stock_data
        self.index_data = index_data
        self.last_rebalance = None
    
    def get_portfolio_value(self, prices):
        return self.cash + sum(self.positions[n]['shares'] * prices.get(n, 0) for n in self.positions if self.positions[n]['shares'] > 0)
    
    def get_market_ok(self, date):
        if date not in self.index_data.index: return False
        row = self.index_data.loc[date]
        return row['close'] > row.get('ma20', 0)
    
    def calc_score(self, row):
        score = 0
        close, ma20 = row.get('close'), row.get('ma20')
        rsi, vol_ratio, momentum = row.get('rsi'), row.get('vol_ratio'), row.get('momentum')
        
        if any(pd.isna(x) for x in [close, ma20]): return 0
        if close < ma20: return 0
        score += 30
        
        if not pd.isna(momentum) and momentum > 0: score += 20
        if not pd.isna(vol_ratio) and vol_ratio > 1.1: score += 15
        if not pd.isna(rsi) and 30 < rsi < 70: score += 15
        if close > ma20 * 1.02: score += 10
        
        return score
    
    def get_position_pct(self, row):
        volatility = row.get('volatility')
        if pd.isna(volatility): return 0.50
        if volatility < self.config['vol_threshold']:
            return self.config['position_low_vol']
        else:
            return self.config['position_high_vol']
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for ts_code, df in self.stock_data.items():
                if date in df.index:
                    prices[ts_code] = df.loc[date]['close']
            
            # 检查止损/止盈
            for name in list(self.positions.keys()):
                if self.positions[name]['shares'] <= 0: continue
                if name not in self.stock_data or date not in self.stock_data[name].index: continue
                
                row = self.stock_data[name].loc[date]
                buy_price = self.buy_prices.get(name, 0)
                price = row['close']
                atr = row.get('atr', 0)
                
                if buy_price <= 0: continue
                profit_pct = (price - buy_price) / buy_price
                self.max_profits[name] = max(self.max_profits.get(name, 0), profit_pct)
                
                sell = False
                reason = ''
                
                # ATR止损
                if not pd.isna(atr) and atr > 0:
                    if price <= buy_price - self.config['stop_loss_atr'] * atr:
                        sell, reason = True, f'ATR止损({profit_pct:.1%})'
                
                # 移动止盈
                if not sell and self.max_profits[name] >= self.config['take_profit_pct']:
                    if profit_pct <= self.max_profits[name] - self.config['trailing_stop_pct']:
                        sell, reason = True, f'止盈({profit_pct:.1%})'
                
                # MA20跌破
                if not sell and not pd.isna(row.get('ma20')):
                    if price < row['ma20'] * 0.98:
                        sell, reason = True, f'MA20跌破({profit_pct:.1%})'
                
                if sell:
                    revenue = self.positions[name]['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'])
                    self.cash += revenue
                    self.trade_log.append({'date': date.isoformat(), 'stock': name, 'pnl': revenue - self.positions[name]['shares'] * buy_price, 'pnl_pct': profit_pct, 'reason': reason})
                    self.positions[name] = {'shares': 0}
            
            # 每周调仓
            if self.last_rebalance is None or (date - self.last_rebalance).days >= self.config['rebalance_days']:
                self.last_rebalance = date
                market_ok = self.get_market_ok(date)
                
                if market_ok:
                    # 评分选股
                    scores = []
                    for ts_code, df in self.stock_data.items():
                        if ts_code in self.positions and self.positions[ts_code]['shares'] > 0: continue
                        if date not in df.index: continue
                        row = df.loc[date]
                        score = self.calc_score(row)
                        if score >= 60:
                            scores.append((ts_code, score, row))
                    
                    scores.sort(key=lambda x: x[1], reverse=True)
                    
                    # 买入
                    for ts_code, score, row in scores:
                        if len([p for p in self.positions.values() if p['shares'] > 0]) >= self.config['max_positions']: break
                        
                        pct = self.get_position_pct(row)
                        total_value = self.get_portfolio_value(prices)
                        target = total_value * pct / self.config['max_positions']
                        shares = int(target / row['close'] / 100) * 100
                        
                        if shares > 0:
                            cost = shares * row['close'] * (1 + self.config['commission'])
                            if cost <= self.cash:
                                self.cash -= cost
                                self.positions[ts_code] = {'shares': shares}
                                self.buy_prices[ts_code] = row['close']
                                self.max_profits[ts_code] = 0
                else:
                    # 熊市清仓
                    for name in list(self.positions.keys()):
                        if self.positions[name]['shares'] > 0:
                            price = prices.get(name, 0)
                            if price > 0:
                                revenue = self.positions[name]['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'])
                                self.cash += revenue
                                self.positions[name] = {'shares': 0}
            
            pv = self.get_portfolio_value(prices)
            self.daily_values.append({'date': date.isoformat(), 'value': pv})
            
            if (i+1) % 200 == 0: print(f"  [{i+1}/{len(dates)}] 权益: ¥{pv:,.0f}")
        
        return self.get_portfolio_value(prices)

def main():
    print("=" * 60)
    print("📈 趋势跟踪+大盘择时组合策略 回测")
    print("=" * 60)
    
    start_date, end_date = '2021-01-01', '2026-06-14'
    stock_data = {}
    all_dates = set()
    
    for ts_code in STOCK_POOL:
        df = load_data(ts_code, start_date, end_date)
        if df is not None and len(df) > 100:
            stock_data[ts_code] = df
            all_dates.update(df.index)
            print(f"  ✅ {NAMES.get(ts_code, ts_code)}: {len(df)}条")
    
    index_data = stock_data.get('600487.SH')
    
    dates = sorted(all_dates)
    bt = TrendTimingBacktest(CONFIG, stock_data, index_data)
    final = bt.run(dates)
    
    initial = CONFIG['initial_cash']
    tr = (final - initial) / initial
    years = len(bt.daily_values) / 252
    ar = (1+tr)**(1/years)-1 if years > 0 else 0
    vals = [d['value'] for d in bt.daily_values]
    pk, mdd = vals[0], 0
    for v in vals:
        if v > pk: pk = v
        dd = (pk-v)/pk
        if dd > mdd: mdd = dd
    
    trades = bt.trade_log
    tt = len(trades)
    w = len([t for t in trades if t['pnl']>0])
    wr = w/max(tt,1)
    aw = np.mean([t['pnl'] for t in trades if t['pnl']>0]) if w>0 else 0
    al = abs(np.mean([t['pnl'] for t in trades if t['pnl']<=0])) if tt-w>0 else 1
    pr = aw/max(al,1)
    dr = pd.Series(vals).pct_change().dropna()
    sh = (dr.mean()/dr.std())*np.sqrt(252) if dr.std()>0 else 0
    
    print(f"\n{'='*60}")
    print(f"📊 趋势跟踪+大盘择时 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}, 胜率: {wr:.1%}, 盈亏比: {pr:.2f}, 交易: {tt}次")

if __name__ == '__main__':
    main()
