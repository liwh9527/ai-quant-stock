#!/usr/bin/env python3
"""多因子选股策略5年回测

因子权重：
- 动量因子 30%：20日涨幅
- 波动因子 20%：低波动优先
- 均线因子 25%：价格相对MA20位置
- 成交量因子 15%：放量优先
- RSI因子 10%：适中RSI优先

调仓：每周调仓，选综合得分前5
"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

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
    'rebalance_days': 5,
    'index_ma_period': 20,
    # 因子权重
    'w_momentum': 0.30,
    'w_volatility': 0.20,
    'w_ma': 0.25,
    'w_volume': 0.15,
    'w_rsi': 0.10,
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
    # 计算因子
    df['momentum'] = df['close'].pct_change(20)
    df['volatility'] = df['close'].pct_change().rolling(20).std()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma_ratio'] = df['close'] / df['ma20']
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma']
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def calc_factor_score(row, config):
    """计算综合因子得分"""
    score = 0
    
    # 动量因子：20日涨幅，越高越好
    momentum = row.get('momentum', 0)
    if not pd.isna(momentum):
        score += momentum * config['w_momentum'] * 100
    
    # 波动因子：波动率越低越好
    volatility = row.get('volatility', 0)
    if not pd.isna(volatility) and volatility > 0:
        score += (1 / volatility) * config['w_volatility'] * 10
    
    # 均线因子：价格在MA20上方越高越好
    ma_ratio = row.get('ma_ratio', 1)
    if not pd.isna(ma_ratio):
        score += (ma_ratio - 1) * config['w_ma'] * 100
    
    # 成交量因子：放量优先
    vol_ratio = row.get('vol_ratio', 1)
    if not pd.isna(vol_ratio):
        score += (vol_ratio - 1) * config['w_volume'] * 50
    
    # RSI因子：40-60最佳
    rsi = row.get('rsi', 50)
    if not pd.isna(rsi):
        rsi_score = 1 - abs(rsi - 50) / 50  # 越接近50越好
        score += rsi_score * config['w_rsi'] * 100
    
    return score

class MultiFactorBacktest:
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
        if date not in self.index_data.index: return False
        row = self.index_data.loc[date]
        return row['close'] > row.get('ma20', 0)
    
    def get_top_stocks(self, date, n=5):
        scores = []
        for ts_code, df in self.stock_data.items():
            if date not in df.index: continue
            row = df.loc[date]
            score = calc_factor_score(row, self.config)
            scores.append((ts_code, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scores[:n]]
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for ts_code, df in self.stock_data.items():
                if date in df.index:
                    prices[ts_code] = df.loc[date]['close']
            
            # 每周调仓
            if self.last_rebalance is None or (date - self.last_rebalance).days >= self.config['rebalance_days']:
                self.last_rebalance = date
                market_ok = self.get_market_ok(date)
                
                if market_ok:
                    top_stocks = self.get_top_stocks(date, self.config['max_positions'])
                    
                    # 清仓不在列表的
                    for name in list(self.positions.keys()):
                        if self.positions[name]['shares'] > 0 and name not in top_stocks:
                            price = prices.get(name, 0)
                            if price > 0:
                                revenue = self.positions[name]['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'])
                                self.cash += revenue
                                self.positions[name] = {'shares': 0}
                    
                    # 买入
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
                    # 清仓
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
    print("📊 多因子选股策略 回测")
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
    bt = MultiFactorBacktest(CONFIG, stock_data, index_data)
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
    
    dr = pd.Series(vals).pct_change().dropna()
    sh = (dr.mean()/dr.std())*np.sqrt(252) if dr.std()>0 else 0
    
    print(f"\n{'='*60}")
    print(f"📊 多因子选股策略 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}")

if __name__ == '__main__':
    main()
