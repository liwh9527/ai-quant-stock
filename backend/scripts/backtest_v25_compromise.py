#!/usr/bin/env python3
"""v25策略 - v14+海龟折中版

目标：在v14收益和优化版海龟回撤之间找平衡

优化点：
1. 大盘择时放宽：MA60替代MA20
2. 入场条件放宽：MA20上方即可，去掉放量要求
3. 保留海龟的ATR仓位管理
4. 更灵活的止损
"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

STOCK_POOL = [
    {'code': '600487', 'name': '亨通光电'},
    {'code': '601138', 'name': '工业富联'},
    {'code': '002371', 'name': '北方华创'},
    {'code': '002916', 'name': '深南电路'},
    {'code': '601899', 'name': '紫金矿业'},
    {'code': '603993', 'name': '洛阳钼业'},
    {'code': '600025', 'name': '华能水电'},
    {'code': '600900', 'name': '长江电力'},
    {'code': '600309', 'name': '万华化学'},
    {'code': '000425', 'name': '徐工机械'},
    {'code': '002475', 'name': '立讯精密'},
    {'code': '000333', 'name': '美的集团'},
]

CONFIG = {
    'initial_cash': 1_000_000,
    'max_positions': 4,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'entry_period': 20,
    'exit_period': 10,
    'atr_period': 20,
    'risk_per_trade': 0.02,    # 2%风险
    'max_position_pct': 0.60,  # 最大总仓位60%
    'stop_loss_atr': 1.8,      # 1.8倍ATR止损
    'take_profit_pct': 0.30,   # 30%止盈
    'trailing_stop_pct': 0.08, # 8%移动止损
    # 折中优化
    'index_ma_period': 60,     # MA60择时（更宽松）
    'position_low_vol': 0.55,  # 低波动仓位
    'position_high_vol': 0.35, # 高波动仓位
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
    df['high_20'] = df['high'].rolling(20).max()
    df['low_10'] = df['low'].rolling(10).min()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
    df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
    df['momentum'] = df['close'].pct_change(20)
    return df

class V25Backtest:
    def __init__(self, config, stock_data, index_data):
        self.config = config
        self.cash = config['initial_cash']
        self.positions = {}
        self.buy_prices = {}
        self.max_profits = {}
        self.highest_prices = {}
        self.trade_log = []
        self.daily_values = []
        self.stock_data = stock_data
        self.index_data = index_data
        self.market_state = 'unknown'
    
    def get_portfolio_value(self, prices):
        return self.cash + sum(self.positions[n]['shares'] * prices.get(n, 0) for n in self.positions if self.positions[n]['shares'] > 0)
    
    def get_position_count(self):
        return len([p for p in self.positions.values() if p['shares'] > 0])
    
    def check_market_state(self, date):
        """检查大盘状态 - 使用MA60"""
        if date not in self.index_data.index: return self.market_state
        row = self.index_data.loc[date]
        if row['close'] > row.get('ma60', 0):
            self.market_state = 'bull'
        else:
            self.market_state = 'bear'
        return self.market_state
    
    def calc_entry_score(self, name, row):
        """入场评分 - 放宽条件"""
        score = 0
        close = row.get('close')
        ma20 = row.get('ma20')
        momentum = row.get('momentum')
        
        if any(pd.isna(x) for x in [close, ma20]): return 0
        
        # MA20上方（核心条件）
        if close > ma20:
            score += 40
        else:
            return 0
        
        # 突破20日高点加分
        high_20 = row.get('high_20')
        if not pd.isna(high_20) and close >= high_20:
            score += 20
        
        # 正动量
        if not pd.isna(momentum) and momentum > 0:
            score += 20
        
        return score
    
    def get_position_size(self, name, price, atr, row):
        """基于ATR计算仓位"""
        if pd.isna(atr) or atr <= 0: return 0
        
        volatility = row.get('volatility')
        if pd.isna(volatility):
            pct = 0.45
        elif volatility < self.config['vol_threshold']:
            pct = self.config['position_low_vol']
        else:
            pct = self.config['position_high_vol']
        
        risk_amount = self.get_portfolio_value({}) * self.config['risk_per_trade']
        risk_per_share = atr * self.config['stop_loss_atr']
        shares = int(risk_amount / risk_per_share / 100) * 100
        
        max_amount = self.get_portfolio_value({}) * pct / self.config['max_positions']
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
                low_10 = row.get('low_10', 0)
                ma20 = row.get('ma20', 0)
                
                if buy_price <= 0: continue
                profit_pct = (price - buy_price) / buy_price
                self.max_profits[name] = max(self.max_profits.get(name, 0), profit_pct)
                self.highest_prices[name] = max(self.highest_prices.get(name, buy_price), price)
                
                sell = False
                reason = ''
                
                # 跌破MA20止损（v14风格）
                if not sell and not pd.isna(ma20) and price < ma20 * 0.98:
                    sell, reason = True, f'跌破MA20({profit_pct:.1%})'
                
                # 跌破10日低点（海龟风格）
                if not sell and not pd.isna(low_10) and price <= low_10 and profit_pct < 0:
                    sell, reason = True, f'跌破10日低点({profit_pct:.1%})'
                
                # ATR止损
                if not sell and not pd.isna(atr) and atr > 0:
                    stop_price = buy_price - self.config['stop_loss_atr'] * atr
                    if price <= stop_price:
                        sell, reason = True, f'ATR止损({profit_pct:.1%})'
                
                # 移动止盈
                if not sell and self.max_profits[name] >= self.config['take_profit_pct']:
                    if profit_pct <= self.max_profits[name] - self.config['trailing_stop_pct']:
                        sell, reason = True, f'移动止盈({profit_pct:.1%})'
                
                # 大盘转熊（MA60下方）且盈利时清仓
                if not sell and self.market_state == 'bear' and profit_pct > 0.10:
                    sell, reason = True, f'大盘转熊({profit_pct:.1%})'
                
                if sell:
                    revenue = self.positions[name]['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'])
                    self.cash += revenue
                    self.trade_log.append({'date': date.isoformat(), 'stock': name, 'buy_price': buy_price, 'sell_price': price, 'pnl': revenue - self.positions[name]['shares'] * buy_price, 'pnl_pct': profit_pct, 'reason': reason})
                    self.positions[name] = {'shares': 0}
            
            # 入场（牛市或震荡市）
            if self.market_state in ['bull', 'unknown']:
                for s in STOCK_POOL:
                    name = s['name']
                    if name in self.positions and self.positions[name]['shares'] > 0: continue
                    if name not in self.stock_data or date not in self.stock_data[name].index: continue
                    if self.get_position_count() >= self.config['max_positions']: break
                    
                    row = self.stock_data[name].loc[date]
                    score = self.calc_entry_score(name, row)
                    
                    if score >= 40:  # 只需要MA20上方
                        atr = row.get('atr', 0)
                        shares = self.get_position_size(name, row['close'], atr, row)
                        
                        if shares > 0:
                            cost = shares * row['close'] * (1 + self.config['commission'])
                            if cost <= self.cash * 0.95:
                                self.cash -= cost
                                self.positions[name] = {'shares': shares}
                                self.buy_prices[name] = row['close']
                                self.max_profits[name] = 0
                                self.highest_prices[name] = row['close']
            
            pv = self.get_portfolio_value(prices)
            self.daily_values.append({'date': date.isoformat(), 'value': pv})
            
            if (i+1) % 200 == 0: print(f"  [{i+1}/{len(dates)}] 权益: ¥{pv:,.0f} 大盘: {self.market_state}")
        
        return self.get_portfolio_value(prices)

def main():
    print("=" * 60)
    print("📊 v25策略 - v14+海龟折中版")
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
    bt = V25Backtest(CONFIG, stock_data, index_data)
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
    
    yearly = {}
    for d in bt.daily_values:
        y = d['date'][:4]
        if y not in yearly: yearly[y] = {'s': d['value'], 'e': d['value']}
        yearly[y]['e'] = d['value']
    
    print(f"\n{'='*60}")
    print(f"📊 v25策略 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}, 胜率: {wr:.1%}, 盈亏比: {pr:.2f}, 交易: {tt}次")
    print(f"\n年度收益:")
    for y, st in sorted(yearly.items()):
        r = (st['e']-st['s'])/st['s']
        print(f"  {y}: {r:+.1%}")

if __name__ == '__main__':
    main()
