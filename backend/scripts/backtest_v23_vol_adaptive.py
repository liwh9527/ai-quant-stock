#!/usr/bin/env python3
"""v23策略 - 波动率自适应"""

import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
DB_PATH = '/root/projects/ai-quant-stock/backend/data/quant.db'

STOCK_POOL = [
    {'code': '600487', 'name': '亨通光电', 'sector': '半导体'},
    {'code': '601138', 'name': '工业富联', 'sector': '半导体'},
    {'code': '002371', 'name': '北方华创', 'sector': '半导体'},
    {'code': '002916', 'name': '深南电路', 'sector': '半导体'},
    {'code': '600584', 'name': '长电科技', 'sector': '半导体'},
    {'code': '002185', 'name': '华天科技', 'sector': '半导体'},
    {'code': '601899', 'name': '紫金矿业', 'sector': '有色'},
    {'code': '603993', 'name': '洛阳钼业', 'sector': '有色'},
    {'code': '600176', 'name': '中国巨石', 'sector': '有色'},
    {'code': '600025', 'name': '华能水电', 'sector': '电力'},
    {'code': '600900', 'name': '长江电力', 'sector': '电力'},
    {'code': '600309', 'name': '万华化学', 'sector': '化工'},
    {'code': '000425', 'name': '徐工机械', 'sector': '机械'},
    {'code': '600031', 'name': '三一重工', 'sector': '机械'},
    {'code': '002475', 'name': '立讯精密', 'sector': '科技'},
]

CONFIG = {
    'initial_cash': 1_000_000, 'max_positions': 5, 'commission': 0.00025,
    'stamp_tax': 0.001, 'slippage_pct': 0.001, 'cooldown_days': 2,
    'take_profit_pct': 0.35, 'trailing_stop_pct': 0.08, 'score_threshold': 55,
    'position_low_vol': 0.70, 'position_mid_vol': 0.50, 'position_high_vol': 0.20,
    'vol_low': 0.25, 'vol_high': 0.40,
    'atr_mult_low_vol': 2.5, 'atr_mult_mid_vol': 2.0, 'atr_mult_high_vol': 1.5,
    'max_per_sector': 2, 'portfolio_drawdown_stop': 0.10, 'circuit_breaker_days': 3,
}

def load_data(ts_code, start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT trade_date, open, high, low, close, vol as volume FROM daily_quotes WHERE ts_code='{ts_code}' AND trade_date BETWEEN '{start_date}' AND '{end_date}' ORDER BY trade_date", conn)
    conn.close()
    if df.empty: return None
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['atr'] = (pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(14).mean()
    df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
    df['rsi'] = 100 - (100 / (1 + ((df['close'].diff().where(lambda x: x>0, 0)).rolling(14).mean() / (-df['close'].diff().where(lambda x: x<0, 0)).rolling(14).mean())))
    df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    df['signal'] = df['macd'].ewm(span=9).mean()
    return df

class V23Backtest:
    def __init__(self, config, stock_data):
        self.config = config
        self.cash = config['initial_cash']
        self.positions = {}
        self.trade_log = []
        self.daily_values = []
        self.buy_prices = {}
        self.max_profits = {}
        self.highest_prices = {}
        self.cooldown_until = {}
        self.sector_counts = {}
        self.peak_value = config['initial_cash']
        self.circuit_breaker = False
        self.circuit_breaker_until = None
        self.stock_sector = {s['name']: s['sector'] for s in STOCK_POOL}
        self.stock_data = stock_data
    
    def get_portfolio_value(self, prices):
        return self.cash + sum(self.positions[n]['shares'] * prices[n] for n in self.positions if self.positions[n]['shares'] > 0 and n in prices)
    
    def get_position_count(self):
        return len([p for p in self.positions.values() if p['shares'] > 0])
    
    def get_position_pct(self, row):
        """根据波动率动态计算仓位"""
        close, ma20 = row.get('close'), row.get('ma20')
        volatility = row.get('volatility')
        
        if pd.isna(close) or pd.isna(ma20) or close < ma20:
            return 0
        
        if pd.isna(volatility):
            return self.config['position_mid_vol']
        
        if volatility < self.config['vol_low']:
            return self.config['position_low_vol']
        elif volatility > self.config['vol_high']:
            return self.config['position_high_vol']
        else:
            return self.config['position_mid_vol']
    
    def get_atr_mult(self, row):
        volatility = row.get('volatility')
        if pd.isna(volatility): return self.config['atr_mult_mid_vol']
        if volatility < self.config['vol_low']: return self.config['atr_mult_low_vol']
        if volatility > self.config['vol_high']: return self.config['atr_mult_high_vol']
        return self.config['atr_mult_mid_vol']
    
    def calc_score(self, row):
        score = 0
        close, ma20 = row.get('close'), row.get('ma20')
        rsi, macd, signal = row.get('rsi'), row.get('macd'), row.get('signal')
        if any(pd.isna(x) for x in [close, ma20, rsi, macd, signal]): return 0
        if close < ma20: return 0
        score += 30
        if close > ma20 * 1.02: score += 15
        if 30 < rsi < 70: score += 15
        if macd > signal: score += 15
        return score
    
    def execute_buy(self, name, price, date, row):
        pct = self.get_position_pct(row)
        if pct <= 0: return False
        if self.get_position_count() >= self.config['max_positions']: return False
        if name in self.cooldown_until and date < self.cooldown_until[name]: return False
        sector = self.stock_sector.get(name, '未知')
        if self.sector_counts.get(sector, 0) >= self.config['max_per_sector']: return False
        
        total_value = self.get_portfolio_value({n: self.positions[n].get('current_price', 0) for n in self.positions})
        max_amount = total_value * pct / self.config['max_positions']
        shares = int(max_amount / price / 100) * 100
        if shares <= 0 or shares * price > self.cash * 0.95: return False
        cost = shares * price * (1 + self.config['commission'] + self.config['slippage_pct'])
        if cost > self.cash: return False
        
        self.cash -= cost
        self.positions[name] = {'shares': shares, 'buy_price': price, 'buy_date': date, 'current_price': price}
        self.buy_prices[name] = price
        self.max_profits[name] = 0
        self.highest_prices[name] = price
        self.sector_counts[sector] = self.sector_counts.get(sector, 0) + 1
        return True
    
    def execute_sell(self, name, price, date, reason=''):
        if name not in self.positions or self.positions[name]['shares'] <= 0: return False
        pos = self.positions[name]
        revenue = pos['shares'] * price * (1 - self.config['commission'] - self.config['stamp_tax'] - self.config['slippage_pct'])
        self.cash += revenue
        pnl = revenue - pos['shares'] * pos['buy_price']
        self.trade_log.append({'date': date.isoformat(), 'stock': name, 'buy_price': pos['buy_price'], 'sell_price': price, 'shares': pos['shares'], 'pnl': pnl, 'pnl_pct': (price-pos['buy_price'])/pos['buy_price'], 'reason': reason})
        self.cooldown_until[name] = date + timedelta(days=self.config['cooldown_days'])
        sector = self.stock_sector.get(name, '未知')
        self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
        self.positions[name] = {'shares': 0, 'buy_price': 0, 'buy_date': None}
        return True
    
    def check_sell(self, name, row, date):
        if name not in self.positions or self.positions[name]['shares'] <= 0: return
        price = row['close']
        buy_price = self.buy_prices.get(name, 0)
        if buy_price <= 0: return
        
        profit_pct = (price - buy_price) / buy_price
        ma20, atr = row.get('ma20'), row.get('atr')
        self.highest_prices[name] = max(self.highest_prices.get(name, buy_price), price)
        self.max_profits[name] = max(self.max_profits.get(name, 0), profit_pct)
        
        # MA20跌破
        if not pd.isna(ma20) and price < ma20 * 0.98:
            self.execute_sell(name, price, date, f'MA20跌破({profit_pct:.1%})')
            return
        
        # 动态ATR止损
        if not pd.isna(atr):
            mult = self.get_atr_mult(row)
            stop = buy_price - mult * atr
            if price <= stop:
                self.execute_sell(name, price, date, f'ATR止损({profit_pct:.1%})')
                return
        
        # 移动止盈
        if self.max_profits[name] >= self.config['take_profit_pct']:
            if profit_pct <= self.max_profits[name] - self.config['trailing_stop_pct']:
                self.execute_sell(name, price, date, f'止盈({profit_pct:.1%})')
                return
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for name, df in self.stock_data.items():
                if date in df.index:
                    row = df.loc[date]
                    prices[name] = row['close']
                    if name in self.positions: self.positions[name]['current_price'] = row['close']
            
            pv = self.get_portfolio_value(prices)
            self.daily_values.append({'date': date.isoformat(), 'value': pv})
            if pv > self.peak_value: self.peak_value = pv
            
            dd = (self.peak_value - pv) / self.peak_value
            if dd >= self.config['portfolio_drawdown_stop']:
                if not self.circuit_breaker:
                    self.circuit_breaker = True
                    self.circuit_breaker_until = date + timedelta(days=self.config['circuit_breaker_days'])
                    for n in list(self.positions.keys()):
                        if self.positions[n]['shares'] > 0 and n in prices:
                            self.execute_sell(n, prices[n], date, '熔断清仓')
                    continue
            else:
                if self.circuit_breaker and date >= self.circuit_breaker_until:
                    self.circuit_breaker = False
                    self.peak_value = pv
            if self.circuit_breaker: continue
            
            for n in list(self.positions.keys()):
                if self.positions[n]['shares'] > 0 and n in self.stock_data and date in self.stock_data[n].index:
                    self.check_sell(n, self.stock_data[n].loc[date], date)
            
            signals = []
            for s in STOCK_POOL:
                n = s['name']
                if n in self.positions and self.positions[n]['shares'] > 0: continue
                if n not in self.stock_data or date not in self.stock_data[n].index: continue
                row = self.stock_data[n].loc[date]
                score = self.calc_score(row)
                if score >= self.config['score_threshold']:
                    signals.append((n, row['close'], score, row))
            signals.sort(key=lambda x: x[2], reverse=True)
            for n, p, sc, r in signals:
                if self.get_position_count() >= self.config['max_positions']: break
                self.execute_buy(n, p, date, r)
            
            if (i+1) % 200 == 0: print(f"  [{i+1}/{len(dates)}] 权益: ¥{pv:,.0f}")
        return pv

def main():
    print("v23 波动率自适应 回测")
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
    bt = V23Backtest(CONFIG, stock_data)
    final = bt.run(dates)
    
    initial = CONFIG['initial_cash']
    tr = (final - initial) / initial
    years = len(bt.daily_values) / 252
    ar = (1+tr)**(1/years)-1 if years > 0 else 0
    vals = [d['value'] for d in bt.daily_values]
    pk = vals[0]
    mdd = 0
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
    yr = ""
    for y, st in sorted(yearly.items()):
        r = (st['e']-st['s'])/st['s']
        c = "#3fb950" if r>0 else "#f85149"
        yr += f'<tr><td>{y}</td><td style="color:{c}">{r:+.1%}</td></tr>'
    
    tr_rows = ""
    for t in trades[-100:]:
        c = "#3fb950" if t['pnl']>0 else "#f85149"
        e = "🟢" if t['pnl']>0 else "🔴"
        tr_rows += f'<tr><td>{t["date"]}</td><td>{t["stock"]}</td><td>{t["pnl_pct"]:.1%}</td><td style="color:{c}">{e} {t["pnl"]:>+,.0f}</td><td>{t["reason"]}</td></tr>'
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>v23 波动率自适应</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px}}.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;margin-bottom:20px}}h1{{text-align:center;color:#58a6ff}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}.metric{{background:#21262d;border-radius:8px;padding:16px;text-align:center}}.metric .label{{color:#8b949e;font-size:12px}}.metric .value{{font-size:20px;font-weight:bold}}.positive{{color:#3fb950}}.negative{{color:#f85149}}.neutral{{color:#58a6ff}}table{{width:100%;border-collapse:collapse}}th{{background:#21262d;padding:8px;text-align:left;color:#8b949e;font-size:12px}}td{{padding:6px 8px;border-bottom:1px solid #21262d;font-size:12px}}</style></head><body>
<h1>📊 v23 波动率自适应</h1>
<p style="text-align:center;color:#8b949e">2021-01-01 ~ 2026-06-14</p>
<div class="grid">
<div class="metric"><div class="label">最终权益</div><div class="value {'positive' if tr>0 else 'negative'}">¥{final:,.0f}</div></div>
<div class="metric"><div class="label">总收益率</div><div class="value {'positive' if tr>0 else 'negative'}">{tr:+.1%}</div></div>
<div class="metric"><div class="label">年化收益率</div><div class="value {'positive' if ar>0.1 else 'negative'}">{ar:+.1%}</div></div>
<div class="metric"><div class="label">最大回撤</div><div class="value {'positive' if mdd<0.15 else 'negative'}">{mdd:.1%}</div></div>
<div class="metric"><div class="label">夏普比率</div><div class="value neutral">{sh:.2f}</div></div>
<div class="metric"><div class="label">胜率</div><div class="value neutral">{wr:.1%}</div></div>
<div class="metric"><div class="label">盈亏比</div><div class="value neutral">{pr:.2f}</div></div>
<div class="metric"><div class="label">交易次数</div><div class="value neutral">{tt}</div></div>
</div>
<div class="card"><h2>📈 权益曲线</h2><div id="eq" style="height:400px"></div></div>
<div class="card"><h2>📅 年度收益</h2><table><tr><th>年份</th><th>收益率</th></tr>{yr}</table></div>
<div class="card"><h2>📝 交易明细</h2><div style="max-height:400px;overflow-y:auto"><table><tr><th>日期</th><th>股票</th><th>收益率</th><th>盈亏</th><th>原因</th></tr>{tr_rows}</table></div></div>
<script>var c=echarts.init(document.getElementById('eq'));c.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis'}},grid:{{left:80,right:30,top:30,bottom:40}},xAxis:{{type:'category',data:{json.dumps([d['date'] for d in bt.daily_values])},axisLabel:{{color:'#8b949e',fontSize:10}}}},yAxis:{{type:'value',axisLabel:{{color:'#8b949e',formatter:'¥{{value}}'}}}},series:[{{type:'line',data:{json.dumps(vals)},lineStyle:{{color:'#00e676',width:2}},itemStyle:{{color:'#00e676'}},areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(0,230,118,0.25)'}},{{offset:1,color:'rgba(0,230,118,0.02)'}}])}},showSymbol:false}}]}});window.addEventListener('resize',()=>c.resize());</script>
</body></html>"""
    
    with open('/usr/share/nginx/html/public/backtest_v23_vol_adaptive.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n{'='*60}")
    print(f"📊 v23 波动率自适应 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {tr:+.1%}, 年化: {ar:+.1%}, 回撤: {mdd:.1%}")
    print(f"夏普: {sh:.2f}, 胜率: {wr:.1%}, 盈亏比: {pr:.2f}, 交易: {tt}次")

if __name__ == '__main__':
    main()
