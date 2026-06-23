#!/usr/bin/env python3
"""v30策略 - 沪深300股票池 + 动态切换组合

使用沪深300典型成分股作为股票池
结合v29的动态切换逻辑
"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# 沪深300典型成分股
STOCK_POOL = [
    # 半导体（高弹性）
    {'code': '600487', 'name': '亨通光电'},
    {'code': '002371', 'name': '北方华创'},
    {'code': '600584', 'name': '长电科技'},
    
    # 有色（周期股）
    {'code': '601899', 'name': '紫金矿业'},
    {'code': '603993', 'name': '洛阳钼业'},
    
    # 电力（防守型）
    {'code': '600025', 'name': '华能水电'},
    {'code': '600900', 'name': '长江电力'},
    
    # 消费（白马股）
    {'code': '600519', 'name': '贵州茅台'},
    {'code': '000858', 'name': '五粮液'},
    {'code': '000333', 'name': '美的集团'},
    
    # 制造（周期股）
    {'code': '600309', 'name': '万华化学'},
    {'code': '600031', 'name': '三一重工'},
    
    # 科技（成长股）
    {'code': '002415', 'name': '海康威视'},
    {'code': '002594', 'name': '比亚迪'},
    
    # 金融（大盘股）
    {'code': '600036', 'name': '招商银行'},
    {'code': '601318', 'name': '中国平安'},
]

# v28参数（牛市激进）
CONFIG_BULL = {
    'max_positions': 3,
    'risk_per_trade': 0.04,
    'max_position_pct': 0.85,
    'stop_loss_atr': 3.0,
    'trailing_stop_pct': 0.30,
    'trailing_start': 2.00,
    'position_low_vol': 0.75,
    'position_high_vol': 0.55,
}

# v26参数（熊市保守）
CONFIG_BEAR = {
    'max_positions': 4,
    'risk_per_trade': 0.025,
    'max_position_pct': 0.70,
    'stop_loss_atr': 2.5,
    'trailing_stop_pct': 0.15,
    'trailing_start': 0.50,
    'position_low_vol': 0.60,
    'position_high_vol': 0.40,
}

COMMON = {
    'initial_cash': 1_000_000,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'vol_threshold': 0.35,
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
    df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
    df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
    df['momentum'] = df['close'].pct_change(20)
    df['high_20'] = df['high'].rolling(20).max()
    return df

class V30Backtest:
    def __init__(self, stock_data, index_data):
        self.cash = COMMON['initial_cash']
        self.positions = {}
        self.buy_prices = {}
        self.max_profits = {}
        self.highest_prices = {}
        self.trade_log = []
        self.daily_values = []
        self.stock_data = stock_data
        self.index_data = index_data
        self.market_state = 'unknown'
        self.current_config = CONFIG_BULL
    
    def get_portfolio_value(self, prices):
        return self.cash + sum(self.positions[n]['shares'] * prices.get(n, 0) for n in self.positions if self.positions[n]['shares'] > 0)
    
    def get_position_count(self):
        return len([p for p in self.positions.values() if p['shares'] > 0])
    
    def check_market_state(self, date):
        if date not in self.index_data.index: return self.market_state
        row = self.index_data.loc[date]
        ma60 = row.get('ma60', 0)
        
        if pd.isna(ma60):
            return self.market_state
        
        if row['close'] > ma60:
            self.market_state = 'bull'
            self.current_config = CONFIG_BULL
        else:
            self.market_state = 'bear'
            self.current_config = CONFIG_BEAR
        
        return self.market_state
    
    def calc_entry_score(self, name, row):
        score = 0
        close = row.get('close')
        ma20 = row.get('ma20')
        ma60 = row.get('ma60')
        momentum = row.get('momentum')
        
        if any(pd.isna(x) for x in [close, ma20, ma60]): return 0
        
        if close > ma20 and close > ma60:
            score += 50
        elif close > ma20:
            score += 30
        else:
            return 0
        
        momentum_threshold = 0.10 if self.market_state == 'bull' else 0.05
        if not pd.isna(momentum) and momentum > momentum_threshold:
            score += 25
        elif not pd.isna(momentum) and momentum > 0:
            score += 10
        
        high_20 = row.get('high_20')
        if not pd.isna(high_20) and close >= high_20:
            score += 15
        
        return score
    
    def get_position_size(self, name, price, atr, row):
        if pd.isna(atr) or atr <= 0: return 0
        
        volatility = row.get('volatility')
        if pd.isna(volatility):
            pct = 0.60
        elif volatility < COMMON['vol_threshold']:
            pct = self.current_config['position_low_vol']
        else:
            pct = self.current_config['position_high_vol']
        
        max_pct = min(pct, 0.35 if self.market_state == 'bull' else 0.25)
        
        risk_amount = self.get_portfolio_value({}) * self.current_config['risk_per_trade']
        risk_per_share = atr * self.current_config['stop_loss_atr']
        shares = int(risk_amount / risk_per_share / 100) * 100
        
        max_amount = self.get_portfolio_value({}) * max_pct
        max_shares = int(max_amount / price / 100) * 100
        
        return min(shares, max_shares)
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for name, df in self.stock_data.items():
                if date in df.index:
                    prices[name] = df.loc[date]['close']
            
            self.check_market_state(date)
            
            for name in list(self.positions.keys()):
                if self.positions[name]['shares'] <= 0: continue
                if name not in self.stock_data or date not in self.stock_data[name].index: continue
                
                row = self.stock_data[name].loc[date]
                buy_price = self.buy_prices.get(name, 0)
                price = row['close']
                atr = row.get('atr', 0)
                ma60 = row.get('ma60', 0)
                
                if buy_price <= 0: continue
                profit_pct = (price - buy_price) / buy_price
                self.max_profits[name] = max(self.max_profits.get(name, 0), profit_pct)
                self.highest_prices[name] = max(self.highest_prices.get(name, buy_price), price)
                
                sell = False
                reason = ''
                
                if not pd.isna(atr) and atr > 0:
                    stop_price = buy_price - self.current_config['stop_loss_atr'] * atr
                    if price <= stop_price:
                        sell, reason = True, f'ATR止损({profit_pct:.1%})'
                
                ma60_threshold = 0.93 if self.market_state == 'bull' else 0.95
                if not sell and not pd.isna(ma60) and price < ma60 * ma60_threshold:
                    sell, reason = True, f'跌破MA60({profit_pct:.1%})'
                
                if not sell and self.max_profits[name] >= self.current_config['trailing_start']:
                    trailing_pct = self.current_config['trailing_stop_pct']
                    if self.max_profits[name] > 3.0:
                        trailing_pct = 0.40
                    elif self.max_profits[name] > 2.0:
                        trailing_pct = 0.35
                    elif self.max_profits[name] > 1.0:
                        trailing_pct = 0.25
                    
                    if profit_pct <= self.max_profits[name] - trailing_pct:
                        sell, reason = True, f'移动止盈({self.max_profits[name]:.1%}→{profit_pct:.1%})'
                
                if not sell and self.market_state == 'bull' and profit_pct < 0:
                    if not pd.isna(ma60) and price > ma60 and profit_pct < -0.05:
                        sell, reason = True, f'牛市换股({profit_pct:.1%})'
                
                if sell:
                    revenue = self.positions[name]['shares'] * price * (1 - COMMON['commission'] - COMMON['stamp_tax'])
                    self.cash += revenue
                    self.trade_log.append({'date': date.isoformat(), 'stock': name, 'buy_price': buy_price, 'sell_price': price, 'pnl': revenue - self.positions[name]['shares'] * buy_price, 'pnl_pct': profit_pct, 'reason': reason, 'market': self.market_state})
                    self.positions[name] = {'shares': 0}
            
            for s in STOCK_POOL:
                name = s['name']
                if name in self.positions and self.positions[name]['shares'] > 0: continue
                if name not in self.stock_data or date not in self.stock_data[name].index: continue
                if self.get_position_count() >= self.current_config['max_positions']: break
                
                row = self.stock_data[name].loc[date]
                score = self.calc_entry_score(name, row)
                
                score_threshold = 70 if self.market_state == 'bull' else 50
                
                if score >= score_threshold:
                    atr = row.get('atr', 0)
                    shares = self.get_position_size(name, row['close'], atr, row)
                    
                    if shares > 0:
                        cost = shares * row['close'] * (1 + COMMON['commission'])
                        if cost <= self.cash * 0.95:
                            self.cash -= cost
                            self.positions[name] = {'shares': shares}
                            self.buy_prices[name] = row['close']
                            self.max_profits[name] = 0
                            self.highest_prices[name] = row['close']
            
            pv = self.get_portfolio_value(prices)
            self.daily_values.append({'date': date.isoformat(), 'value': pv, 'market': self.market_state})
            
            if (i+1) % 200 == 0: print(f"  [{i+1}/{len(dates)}] 权益: ¥{pv:,.0f} 市场: {self.market_state}")
        
        return self.get_portfolio_value(prices)

def main():
    print("=" * 60)
    print("📊 v30策略 - 沪深300股票池")
    print("=" * 60)
    
    start_date, end_date = '2021-01-01', '2026-06-14'
    stock_data = {}
    all_dates = set()
    
    for s in STOCK_POOL:
        ts = f"{s['code']}.{'SH' if s['code'].startswith('6') else 'SZ'}"
        df = load_data(ts, start_date, end_date)
        if df is not None and len(df) > 100:
            stock_data[s['name']] = df
            all_dates.update(df.index)
            print(f"  ✅ {s['name']}: {len(df)}条")
    
    # 使用沪深300指数作为大盘参考
    conn = sqlite3.connect(DB_PATH)
    index_df = pd.read_sql_query("""
        SELECT trade_date, close FROM index_daily 
        WHERE ts_code='000300.SH' AND trade_date BETWEEN '2021-01-01' AND '2026-06-14'
        ORDER BY trade_date
    """, conn)
    conn.close()
    
    if len(index_df) > 100:
        index_df['trade_date'] = pd.to_datetime(index_df['trade_date'])
        index_df = index_df.set_index('trade_date')
        index_df['ma20'] = index_df['close'].rolling(20).mean()
        index_df['ma60'] = index_df['close'].rolling(60).mean()
        index_data = index_df
        print(f"\n  ✅ 沪深300指数: {len(index_df)}条")
    else:
        index_data = stock_data.get('亨通光电')
    
    dates = sorted(all_dates)
    bt = V30Backtest(stock_data, index_data)
    final = bt.run(dates)
    
    initial = COMMON['initial_cash']
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
    
    yearly = {}
    for d in bt.daily_values:
        y = d['date'][:4]
        if y not in yearly: yearly[y] = {'s': d['value'], 'e': d['value']}
        yearly[y]['e'] = d['value']
    
    print(f"\n{'='*60}")
    print(f"📊 v30策略 回测结果（沪深300股票池）")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}, 胜率: {wr:.1%}, 盈亏比: {pr:.2f}, 交易: {tt}次")
    print(f"\n年度收益:")
    for y, st in sorted(yearly.items()):
        r = (st['e']-st['s'])/st['s']
        emoji = "🟢" if r > 0.5 else ("🟡" if r > 0 else "🔴")
        print(f"  {y}: {emoji} {r:+.1%}")
    
    # 对比沪深300指数
    print(f"\n对比沪深300指数:")
    if len(index_data) > 100:
        index_ret = (index_data.iloc[-1]['close'] - index_data.iloc[0]['close']) / index_data.iloc[0]['close']
        print(f"  沪深300指数: {index_ret:+.1%}")
        print(f"  v30策略超额: {tr - index_ret:+.1%}")

if __name__ == '__main__':
    main()
