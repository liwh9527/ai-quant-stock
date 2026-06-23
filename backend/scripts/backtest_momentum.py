#!/usr/bin/env python3
"""动量轮动策略5年回测

核心规则：
1. 选股：按20日涨幅排名，选前5强
2. 轮动：每周调仓
3. 仓位：等权分配
4. 风控：大盘跌破MA20清仓
"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

# 扩大股票池用于动量筛选
STOCK_POOL = [
    '600487.SH', '601138.SH', '002371.SZ', '002916.SZ', '600584.SH',
    '002185.SZ', '002049.SZ', '601899.SH', '603993.SH', '600176.SH',
    '600025.SH', '600900.SH', '600309.SH', '000425.SZ', '600031.SH',
    '002475.SZ', '000333.SZ', '600760.SH', '600893.SH', '002594.SZ',
]

NAMES = {
    '600487.SH': '亨通光电', '601138.SH': '工业富联', '002371.SZ': '北方华创',
    '002916.SZ': '深南电路', '600584.SH': '长电科技', '002185.SZ': '华天科技',
    '002049.SZ': '紫光国微', '601899.SH': '紫金矿业', '603993.SH': '洛阳钼业',
    '600176.SH': '中国巨石', '600025.SH': '华能水电', '600900.SH': '长江电力',
    '600309.SH': '万华化学', '000425.SZ': '徐工机械', '600031.SH': '三一重工',
    '002475.SZ': '立讯精密', '000333.SZ': '美的集团', '600760.SH': '中航沈飞',
    '600893.SH': '航发动力', '002594.SZ': '比亚迪',
}

CONFIG = {
    'initial_cash': 1_000_000,
    'max_positions': 5,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'momentum_period': 20,   # 20日动量
    'rebalance_days': 5,     # 每周调仓
    'index_ma_period': 20,   # 大盘MA20
}

def load_data(ts_code, start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"""
        SELECT trade_date, close FROM daily_quotes 
        WHERE ts_code='{ts_code}' AND trade_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY trade_date
    """, conn)
    conn.close()
    if df.empty: return None
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    df['momentum'] = df['close'].pct_change(CONFIG['momentum_period'])
    df['ma20'] = df['close'].rolling(20).mean()
    return df

class MomentumBacktest:
    def __init__(self, config, stock_data, index_data):
        self.config = config
        self.cash = config['initial_cash']
        self.positions = {}
        self.trade_log = []
        self.daily_values = []
        self.stock_data = stock_data
        self.index_data = index_data
        self.last_rebalance = None
    
    def get_portfolio_value(self, prices):
        return self.cash + sum(self.positions[n]['shares'] * prices.get(n, 0) for n in self.positions if self.positions[n]['shares'] > 0)
    
    def get_market_ok(self, date):
        """检查大盘是否在MA20上方"""
        if date not in self.index_data.index: return False
        row = self.index_data.loc[date]
        return row['close'] > row['ma20']
    
    def get_top_momentum(self, date, n=5):
        """获取动量最强的n只股票"""
        scores = []
        for ts_code, df in self.stock_data.items():
            if date not in df.index: continue
            row = df.loc[date]
            if pd.isna(row.get('momentum')): continue
            scores.append((ts_code, row['momentum']))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scores[:n] if s[1] > 0]  # 只选正动量
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for ts_code, df in self.stock_data.items():
                if date in df.index:
                    prices[ts_code] = df.loc[date]['close']
            
            # 每周调仓
            if self.last_rebalance is None or (date - self.last_rebalance).days >= self.config['rebalance_days']:
                self.last_rebalance = date
                
                # 检查大盘
                market_ok = self.get_market_ok(date)
                
                if market_ok:
                    # 获取动量最强股票
                    top_stocks = self.get_top_momentum(date, self.config['max_positions'])
                    
                    # 清仓不在top列表的股票
                    for name in list(self.positions.keys()):
                        if self.positions[name]['shares'] > 0 and name not in top_stocks:
                            price = prices.get(name, 0)
                            if price > 0:
                                revenue = self.positions[name]['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'])
                                self.cash += revenue
                                self.positions[name] = {'shares': 0}
                    
                    # 买入新的top股票
                    target_pct = 1.0 / len(top_stocks) if top_stocks else 0
                    for name in top_stocks:
                        if name in self.positions and self.positions[name]['shares'] > 0: continue
                        
                        price = prices.get(name, 0)
                        if price <= 0: continue
                        
                        total_value = self.get_portfolio_value(prices)
                        target_amount = total_value * target_pct
                        shares = int(target_amount / price / 100) * 100
                        
                        if shares > 0:
                            cost = shares * price * (1 + self.config['commission'])
                            if cost <= self.cash:
                                self.cash -= cost
                                self.positions[name] = {'shares': shares}
                else:
                    # 大盘在MA20下方，清仓
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
    print("🔄 动量轮动策略 回测")
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
    
    # 加载大盘数据（用亨通光电作为代理）
    index_data = stock_data.get('600487.SH')
    
    dates = sorted(all_dates)
    bt = MomentumBacktest(CONFIG, stock_data, index_data)
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
    
    dr = pd.Series(vals).pct_change().dropna()
    sh = (dr.mean()/dr.std())*np.sqrt(252) if dr.std()>0 else 0
    
    print(f"\n{'='*60}")
    print(f"📊 动量轮动策略 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}")

if __name__ == '__main__':
    main()
