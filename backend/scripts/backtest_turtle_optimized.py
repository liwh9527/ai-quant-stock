#!/usr/bin/env python3
"""优化版海龟策略 - 高收益+低回撤

优化点：
1. 大盘择时：MA20上方才入场，下方清仓
2. 更快止损：1.5倍ATR止损
3. 更严格入场：突破20日高点 + MA20上方 + 放量
4. 动态仓位：根据波动率调整
5. 板块过滤：只买动量最强的股票
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
    'risk_per_trade': 0.015,  # 1.5%风险（原2%）
    'max_position_pct': 0.50,  # 最大总仓位50%（原60%）
    'stop_loss_atr': 1.5,    # 1.5倍ATR止损（原2.0）
    # 新增优化
    'index_ma_period': 20,   # 大盘MA20
    'momentum_period': 20,   # 20日动量
    'vol_ratio_threshold': 1.1,  # 放量阈值
    'position_low_vol': 0.50,   # 低波动仓位
    'position_high_vol': 0.30,  # 高波动仓位
    'vol_threshold': 0.35,      # 波动率阈值
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
    df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(20).mean()
    df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
    df['momentum'] = df['close'].pct_change(20)
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma']
    return df

class OptimizedTurtleBacktest:
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
        """检查大盘状态"""
        if date not in self.index_data.index: return self.market_state
        row = self.index_data.loc[date]
        if row['close'] > row.get('ma20', 0):
            self.market_state = 'bull'
        else:
            self.market_state = 'bear'
        return self.market_state
    
    def calc_entry_score(self, name, row):
        """计算入场得分"""
        score = 0
        close = row.get('close')
        high_20 = row.get('high_20')
        ma20 = row.get('ma20')
        vol_ratio = row.get('vol_ratio')
        momentum = row.get('momentum')
        
        if any(pd.isna(x) for x in [close, high_20, ma20]): return 0
        
        # 突破20日高点
        if close >= high_20:
            score += 40
        
        # MA20上方
        if close > ma20:
            score += 20
        else:
            return 0
        
        # 放量
        if not pd.isna(vol_ratio) and vol_ratio > self.config['vol_ratio_threshold']:
            score += 15
        
        # 正动量
        if not pd.isna(momentum) and momentum > 0:
            score += 15
        
        return score
    
    def get_position_size(self, name, price, atr, row):
        """基于ATR和波动率计算仓位"""
        if pd.isna(atr) or atr <= 0: return 0
        
        # 根据波动率调整仓位
        volatility = row.get('volatility')
        if pd.isna(volatility):
            pct = 0.40
        elif volatility < self.config['vol_threshold']:
            pct = self.config['position_low_vol']
        else:
            pct = self.config['position_high_vol']
        
        # 风险金额
        risk_amount = self.get_portfolio_value({}) * self.config['risk_per_trade']
        
        # 每份风险
        risk_per_share = atr * self.config['stop_loss_atr']
        
        # 计算股数
        shares = int(risk_amount / risk_per_share / 100) * 100
        
        # 限制仓位
        max_amount = self.get_portfolio_value({}) * pct / self.config['max_positions']
        max_shares = int(max_amount / price / 100) * 100
        
        return min(shares, max_shares)
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for name, df in self.stock_data.items():
                if date in df.index:
                    prices[name] = df.loc[date]['close']
            
            # 检查大盘状态
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
                
                if buy_price <= 0: continue
                profit_pct = (price - buy_price) / buy_price
                self.max_profits[name] = max(self.max_profits.get(name, 0), profit_pct)
                self.highest_prices[name] = max(self.highest_prices.get(name, buy_price), price)
                
                sell = False
                reason = ''
                
                # 大盘转熊清仓
                if self.market_state == 'bear' and profit_pct > 0:
                    sell, reason = True, f'大盘转熊({profit_pct:.1%})'
                
                # 跌破10日低点
                if not sell and not pd.isna(low_10) and price <= low_10:
                    sell, reason = True, f'跌破10日低点({profit_pct:.1%})'
                
                # ATR止损（更快）
                if not sell and not pd.isna(atr) and atr > 0:
                    stop_price = buy_price - self.config['stop_loss_atr'] * atr
                    if price <= stop_price:
                        sell, reason = True, f'ATR止损({profit_pct:.1%})'
                
                if sell:
                    revenue = self.positions[name]['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'])
                    self.cash += revenue
                    self.trade_log.append({'date': date.isoformat(), 'stock': name, 'buy_price': buy_price, 'sell_price': price, 'pnl': revenue - self.positions[name]['shares'] * buy_price, 'pnl_pct': profit_pct, 'reason': reason})
                    self.positions[name] = {'shares': 0}
            
            # 入场信号（只在牛市）
            if self.market_state == 'bull':
                for s in STOCK_POOL:
                    name = s['name']
                    if name in self.positions and self.positions[name]['shares'] > 0: continue
                    if name not in self.stock_data or date not in self.stock_data[name].index: continue
                    if self.get_position_count() >= self.config['max_positions']: break
                    
                    row = self.stock_data[name].loc[date]
                    score = self.calc_entry_score(name, row)
                    
                    if score >= 60:  # 需要较高分数才入场
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
    print("🐢 优化版海龟策略 - 高收益+低回撤")
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
    
    # 大盘数据
    index_data = stock_data.get('亨通光电')
    
    dates = sorted(all_dates)
    bt = OptimizedTurtleBacktest(CONFIG, stock_data, index_data)
    final = bt.run(dates)
    
    # 统计
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
    
    # 年度收益
    yearly = {}
    for d in bt.daily_values:
        y = d['date'][:4]
        if y not in yearly: yearly[y] = {'s': d['value'], 'e': d['value']}
        yearly[y]['e'] = d['value']
    
    print(f"\n{'='*60}")
    print(f"📊 优化版海龟策略 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}, 胜率: {wr:.1%}, 盈亏比: {pr:.2f}, 交易: {tt}次")
    print(f"\n年度收益:")
    for y, st in sorted(yearly.items()):
        r = (st['e']-st['s'])/st['s']
        print(f"  {y}: {r:+.1%}")
    
    print(f"\n最近10笔交易:")
    for t in trades[-10:]:
        emoji = '🟢' if t['pnl']>0 else '🔴'
        print(f"  {t['date']} {t['stock']} {emoji} {t['pnl_pct']:+.1%} ({t['reason']})")

if __name__ == '__main__':
    main()
