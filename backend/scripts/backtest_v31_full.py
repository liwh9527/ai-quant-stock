#!/usr/bin/env python3
"""v31策略 - 动态股票池（完整版）

核心优化：
1. 动态股票池：从100只流动性最好的股票中筛选最强的
2. 牛市集中仓位：3只，每只30%
3. 熊市分散仓位：4只，每只20%
4. 严格止损：ATR止损+MA60止损
5. 让利润奔跑：200%盈利后才启动移动止盈
"""

import sys, os, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# 牛市激进参数
CONFIG_BULL = {
    'max_positions': 3,
    'risk_per_trade': 0.04,
    'max_position_pct': 0.85,
    'stop_loss_atr': 2.5,
    'trailing_stop_pct': 0.25,
    'trailing_start': 1.50,  # 150%盈利后启动
    'position_pct': 0.30,
}

# 熊市保守参数
CONFIG_BEAR = {
    'max_positions': 4,
    'risk_per_trade': 0.02,
    'max_position_pct': 0.60,
    'stop_loss_atr': 2.0,
    'trailing_stop_pct': 0.15,
    'trailing_start': 0.50,
    'position_pct': 0.15,
}

COMMON = {
    'initial_cash': 1_000_000,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'rebalance_days': 5,
    'top_n': 3,
    'momentum_threshold': 0.08,
}

def load_stocks(start_date):
    conn = sqlite3.connect(DB_PATH)
    
    stocks = pd.read_sql_query(f'''
        SELECT d.ts_code, s.name, AVG(d.vol) as avg_vol
        FROM daily_quotes d
        JOIN stocks s ON d.ts_code = s.ts_code
        WHERE d.trade_date >= "{start_date}"
        AND s.name NOT LIKE "%ST%"
        AND s.name NOT LIKE "%退%"
        AND (d.ts_code LIKE "60%" OR d.ts_code LIKE "00%")
        AND d.ts_code NOT LIKE "30%"
        AND d.ts_code NOT LIKE "68%"
        GROUP BY d.ts_code
        HAVING COUNT(*) > 800
        ORDER BY avg_vol DESC
        LIMIT 100
    ''', conn)
    
    stock_data = {}
    all_dates = set()
    
    for _, row in stocks.iterrows():
        ts_code = row['ts_code']
        name = row['name']
        
        df = pd.read_sql_query(f'''
            SELECT trade_date, open, high, low, close, vol as volume 
            FROM daily_quotes WHERE ts_code="{ts_code}" 
            AND trade_date >= "{start_date}"
            ORDER BY trade_date
        ''', conn)
        
        if len(df) < 500:
            continue
        
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.set_index('trade_date')
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
        df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
        df['momentum'] = df['close'].pct_change(20)
        df['high_20'] = df['high'].rolling(20).max()
        
        stock_data[name] = df
        all_dates.update(df.index)
    
    conn.close()
    return stock_data, sorted(all_dates)

class V31FullBacktest:
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
        self.last_rebalance = None
        self.current_pool = []
    
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
    
    def select_top_stocks(self, date):
        candidates = []
        
        for name, df in self.stock_data.items():
            if date not in df.index:
                continue
            
            row = df.loc[date]
            close = row.get('close')
            ma20 = row.get('ma20')
            ma60 = row.get('ma60')
            momentum = row.get('momentum')
            
            if any(pd.isna(x) for x in [close, ma20, ma60, momentum]):
                continue
            
            # 基础条件
            if close < ma20:
                continue
            if momentum < COMMON['momentum_threshold']:
                continue
            
            # 计算得分
            score = momentum * 100
            if close > ma60: score += 15
            
            candidates.append({'name': name, 'score': score, 'momentum': momentum})
        
        candidates.sort(key=lambda x: x['score'], reverse=True)
        return [c['name'] for c in candidates[:COMMON['top_n']]]
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for name, df in self.stock_data.items():
                if date in df.index:
                    prices[name] = df.loc[date]['close']
            
            self.check_market_state(date)
            
            # 止损/出场检查
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
                
                # 不在股票池且盈利时清仓
                if name not in self.current_pool and profit_pct > 0.05:
                    sell, reason = True, f'不在池({profit_pct:.1%})'
                
                # ATR止损
                if not sell and not pd.isna(atr) and atr > 0:
                    stop_price = buy_price - self.current_config['stop_loss_atr'] * atr
                    if price <= stop_price:
                        sell, reason = True, f'ATR止损({profit_pct:.1%})'
                
                # MA60止损
                if not sell and not pd.isna(ma60) and price < ma60 * 0.95:
                    sell, reason = True, f'MA60止损({profit_pct:.1%})'
                
                # 移动止盈
                if not sell and self.max_profits[name] >= self.current_config['trailing_start']:
                    trailing_pct = self.current_config['trailing_stop_pct']
                    if self.max_profits[name] > 3.0:
                        trailing_pct = 0.35
                    elif self.max_profits[name] > 2.0:
                        trailing_pct = 0.30
                    
                    if profit_pct <= self.max_profits[name] - trailing_pct:
                        sell, reason = True, f'止盈({self.max_profits[name]:.1%}→{profit_pct:.1%})'
                
                if sell:
                    revenue = self.positions[name]['shares'] * price * (1 - COMMON['commission'] - COMMON['stamp_tax'])
                    self.cash += revenue
                    self.trade_log.append({'date': date.isoformat(), 'stock': name, 'pnl': revenue - self.positions[name]['shares'] * buy_price, 'pnl_pct': profit_pct, 'reason': reason, 'market': self.market_state})
                    self.positions[name] = {'shares': 0}
            
            # 每周调仓
            if self.last_rebalance is None or (date - self.last_rebalance).days >= COMMON['rebalance_days']:
                self.last_rebalance = date
                self.current_pool = self.select_top_stocks(date)
                
                # 清仓盈利但不在池中的股票
                for name in list(self.positions.keys()):
                    if self.positions[name]['shares'] > 0 and name not in self.current_pool:
                        price = prices.get(name, 0)
                        buy_price = self.buy_prices.get(name, 0)
                        if price > 0 and buy_price > 0:
                            profit_pct = (price - buy_price) / buy_price
                            if profit_pct > 0:
                                revenue = self.positions[name]['shares'] * price * (1 - COMMON['commission'] - COMMON['stamp_tax'])
                                self.cash += revenue
                                self.positions[name] = {'shares': 0}
            
            # 入场
            for name in self.current_pool:
                if name in self.positions and self.positions[name]['shares'] > 0: continue
                if name not in self.stock_data or date not in self.stock_data[name].index: continue
                if self.get_position_count() >= self.current_config['max_positions']: break
                
                row = self.stock_data[name].loc[date]
                close = row.get('close')
                ma20 = row.get('ma20')
                
                if pd.isna(close) or pd.isna(ma20) or close < ma20:
                    continue
                
                # 计算仓位
                total_value = self.get_portfolio_value(prices)
                target_amount = total_value * self.current_config['position_pct']
                shares = int(target_amount / close / 100) * 100
                
                if shares > 0:
                    cost = shares * close * (1 + COMMON['commission'])
                    if cost <= self.cash * 0.95:
                        self.cash -= cost
                        self.positions[name] = {'shares': shares}
                        self.buy_prices[name] = close
                        self.max_profits[name] = 0
                        self.highest_prices[name] = close
            
            pv = self.get_portfolio_value(prices)
            self.daily_values.append({'date': date.isoformat(), 'value': pv, 'market': self.market_state})
            
            if (i+1) % 200 == 0:
                print(f"  [{i+1}/{len(dates)}] 权益: ¥{pv:,.0f} 市场: {self.market_state}")
        
        return self.get_portfolio_value(prices)

def main():
    print("=" * 60)
    print("📊 v31策略 - 动态股票池（完整版）")
    print("=" * 60)
    
    start_date = '2021-01-01'
    
    print("加载股票数据...")
    stock_data, all_dates = load_stocks(start_date)
    print(f"成功加载 {len(stock_data)} 只股票")
    
    # 使用亨通光电作为大盘参考
    index_data = stock_data.get('亨通光电')
    
    bt = V31FullBacktest(stock_data, index_data)
    final = bt.run(all_dates)
    
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
    print(f"📊 v31策略 回测结果（动态股票池完整版）")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}, 胜率: {wr:.1%}, 盈亏比: {pr:.2f}, 交易: {tt}次")
    print(f"\n年度收益:")
    for y, st in sorted(yearly.items()):
        r = (st['e']-st['s'])/st['s']
        emoji = "🟢" if r > 0.5 else ("🟡" if r > 0 else "🔴")
        print(f"  {y}: {emoji} {r:+.1%}")

if __name__ == '__main__':
    main()
