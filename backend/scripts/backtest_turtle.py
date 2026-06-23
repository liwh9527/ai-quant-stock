#!/usr/bin/env python3
"""海龟交易策略（改良版）5年回测

核心规则：
1. 入场：价格突破20日高点买入
2. 出场：价格跌破10日低点卖出
3. 仓位：基于ATR的动态仓位管理
4. 风控：单笔亏损<2%，总仓位<60%
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
    'entry_period': 20,      # 20日高点突破入场
    'exit_period': 10,       # 10日低点跌破出场
    'atr_period': 20,
    'risk_per_trade': 0.02,  # 单笔风险2%
    'max_position_pct': 0.60, # 最大总仓位60%
    'stop_loss_atr': 2.0,    # 2倍ATR止损
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
    # 计算指标
    df['high_20'] = df['high'].rolling(20).max()
    df['low_10'] = df['low'].rolling(10).min()
    df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
    return df

class TurtleBacktest:
    def __init__(self, config, stock_data):
        self.config = config
        self.cash = config['initial_cash']
        self.positions = {}
        self.trade_log = []
        self.daily_values = []
        self.buy_prices = {}
        self.stock_data = stock_data
    
    def get_portfolio_value(self, prices):
        return self.cash + sum(self.positions[n]['shares'] * prices.get(n, 0) for n in self.positions if self.positions[n]['shares'] > 0)
    
    def get_position_count(self):
        return len([p for p in self.positions.values() if p['shares'] > 0])
    
    def calc_position_size(self, name, price, atr):
        """基于ATR计算仓位大小"""
        if pd.isna(atr) or atr <= 0: return 0
        
        # 风险金额 = 总资金 * 单笔风险比例
        risk_amount = self.get_portfolio_value({}) * self.config['risk_per_trade']
        
        # 每份仓位的风险 = ATR * 止损倍数
        risk_per_share = atr * self.config['stop_loss_atr']
        
        # 计算股数
        shares = int(risk_amount / risk_per_share / 100) * 100
        
        # 限制单只最大仓位
        max_amount = self.get_portfolio_value({}) * self.config['max_position_pct'] / self.config['max_positions']
        max_shares = int(max_amount / price / 100) * 100
        
        return min(shares, max_shares)
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for name, df in self.stock_data.items():
                if date in df.index:
                    row = df.loc[date]
                    prices[name] = row['close']
            
            # 检查出场信号
            for name in list(self.positions.keys()):
                if self.positions[name]['shares'] <= 0: continue
                if name not in self.stock_data or date not in self.stock_data[name].index: continue
                
                row = self.stock_data[name].loc[date]
                buy_price = self.buy_prices.get(name, 0)
                atr = row.get('atr', 0)
                
                # 海龟出场：跌破10日低点
                if row['close'] <= row['low_10']:
                    price = row['close']
                    revenue = self.positions[name]['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'])
                    self.cash += revenue
                    pnl = revenue - self.positions[name]['shares'] * buy_price
                    self.trade_log.append({'date': date.isoformat(), 'stock': name, 'buy_price': buy_price, 'sell_price': price, 'pnl': pnl, 'pnl_pct': (price-buy_price)/buy_price, 'reason': '跌破10日低点'})
                    self.positions[name] = {'shares': 0}
                    continue
                
                # ATR止损
                if not pd.isna(atr) and atr > 0:
                    stop_price = buy_price - self.config['stop_loss_atr'] * atr
                    if row['close'] <= stop_price:
                        price = row['close']
                        revenue = self.positions[name]['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'])
                        self.cash += revenue
                        pnl = revenue - self.positions[name]['shares'] * buy_price
                        self.trade_log.append({'date': date.isoformat(), 'stock': name, 'buy_price': buy_price, 'sell_price': price, 'pnl': pnl, 'pnl_pct': (price-buy_price)/buy_price, 'reason': 'ATR止损'})
                        self.positions[name] = {'shares': 0}
            
            # 检查入场信号
            for s in STOCK_POOL:
                name = s['name']
                if name in self.positions and self.positions[name]['shares'] > 0: continue
                if name not in self.stock_data or date not in self.stock_data[name].index: continue
                if self.get_position_count() >= self.config['max_positions']: break
                
                row = self.stock_data[name].loc[date]
                
                # 海龟入场：突破20日高点
                if row['close'] >= row['high_20']:
                    atr = row.get('atr', 0)
                    shares = self.calc_position_size(name, row['close'], atr)
                    
                    if shares > 0:
                        cost = shares * row['close'] * (1 + self.config['commission'])
                        if cost <= self.cash * 0.95:
                            self.cash -= cost
                            self.positions[name] = {'shares': shares, 'buy_price': row['close']}
                            self.buy_prices[name] = row['close']
            
            # 记录每日权益
            pv = self.get_portfolio_value(prices)
            self.daily_values.append({'date': date.isoformat(), 'value': pv})
            
            if (i+1) % 200 == 0: print(f"  [{i+1}/{len(dates)}] 权益: ¥{pv:,.0f}")
        
        return self.get_portfolio_value(prices)

def main():
    print("=" * 60)
    print("🐢 海龟交易策略（改良版）回测")
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
    
    dates = sorted(all_dates)
    bt = TurtleBacktest(CONFIG, stock_data)
    final = bt.run(dates)
    
    # 计算统计
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
    print(f"📊 海龟策略 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}, 胜率: {wr:.1%}, 盈亏比: {pr:.2f}, 交易: {tt}次")

if __name__ == '__main__':
    main()
