#!/usr/bin/env python3
"""v29策略 - 动态切换组合策略

核心逻辑：
1. 牛市（MA60上方）：用v28策略（集中仓位+让利润跑）
2. 熊市（MA60下方）：用v26策略（分散仓位+严格止损）

目标：牛市收益50%+，熊市亏损<10%，整体回撤<20%
"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

STOCK_POOL = [
    {'code': '600487', 'name': '亨通光电'},
    {'code': '002916', 'name': '深南电路'},
    {'code': '601138', 'name': '工业富联'},
    {'code': '603993', 'name': '洛阳钼业'},
    {'code': '002371', 'name': '北方华创'},
    {'code': '601899', 'name': '紫金矿业'},
    {'code': '600025', 'name': '华能水电'},
    {'code': '600900', 'name': '长江电力'},
    {'code': '600309', 'name': '万华化学'},
    {'code': '000425', 'name': '徐工机械'},
    {'code': '002475', 'name': '立讯精密'},
    {'code': '000333', 'name': '美的集团'},
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

class V29Backtest:
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
        self.current_config = CONFIG_BULL  # 默认牛市
    
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
        
        # 牛市要求更强动量
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
        
        # 牛市集中仓位，熊市分散仓位
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
            
            # 检查止损/出场
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
                
                # ATR止损
                if not pd.isna(atr) and atr > 0:
                    stop_price = buy_price - self.current_config['stop_loss_atr'] * atr
                    if price <= stop_price:
                        sell, reason = True, f'ATR止损({profit_pct:.1%})'
                
                # 跌破MA60止损
                ma60_threshold = 0.93 if self.market_state == 'bull' else 0.95
                if not sell and not pd.isna(ma60) and price < ma60 * ma60_threshold:
                    sell, reason = True, f'跌破MA60({profit_pct:.1%})'
                
                # 移动止盈
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
                
                # 熊市转牛市时，清理弱势股票
                if not sell and self.market_state == 'bull' and profit_pct < 0:
                    # 如果持仓亏损且牛市来了，止损换股
                    if not pd.isna(ma60) and price > ma60 and profit_pct < -0.05:
                        sell, reason = True, f'牛市换股({profit_pct:.1%})'
                
                if sell:
                    revenue = self.positions[name]['shares'] * price * (1 - COMMON['commission'] - COMMON['stamp_tax'])
                    self.cash += revenue
                    self.trade_log.append({'date': date.isoformat(), 'stock': name, 'buy_price': buy_price, 'sell_price': price, 'pnl': revenue - self.positions[name]['shares'] * buy_price, 'pnl_pct': profit_pct, 'reason': reason, 'market': self.market_state})
                    self.positions[name] = {'shares': 0}
            
            # 入场信号
            for s in STOCK_POOL:
                name = s['name']
                if name in self.positions and self.positions[name]['shares'] > 0: continue
                if name not in self.stock_data or date not in self.stock_data[name].index: continue
                if self.get_position_count() >= self.current_config['max_positions']: break
                
                row = self.stock_data[name].loc[date]
                score = self.calc_entry_score(name, row)
                
                # 牛市要求更高分数
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
    print("🔄 v29策略 - 动态切换组合策略")
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
    
    index_data = stock_data.get('亨通光电')
    
    dates = sorted(all_dates)
    bt = V29Backtest(stock_data, index_data)
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
    
    # 统计牛市/熊市交易
    bull_trades = [t for t in trades if t.get('market') == 'bull']
    bear_trades = [t for t in trades if t.get('market') == 'bear']
    
    print(f"\n{'='*60}")
    print(f"📊 v29策略 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}, 胜率: {wr:.1%}, 盈亏比: {pr:.2f}, 交易: {tt}次")
    print(f"\n年度收益:")
    for y, st in sorted(yearly.items()):
        r = (st['e']-st['s'])/st['s']
        emoji = "🟢" if r > 0.5 else ("🟡" if r > 0 else "🔴")
        print(f"  {y}: {emoji} {r:+.1%}")
    
    print(f"\n市场状态统计:")
    print(f"  牛市交易: {len(bull_trades)}次")
    print(f"  熊市交易: {len(bear_trades)}次")

if __name__ == '__main__':
    main()
