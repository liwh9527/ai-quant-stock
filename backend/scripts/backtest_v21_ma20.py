#!/usr/bin/env python3
"""v21策略 - MA20择时+动态仓位"""

import sys
import os
import json
import sqlite3
import numpy as np
import pandas as pd
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
    'initial_cash': 1_000_000,
    'max_positions': 5,
    'commission': 0.00025,
    'stamp_tax': 0.001,
    'slippage_pct': 0.001,
    'cooldown_days': 2,
    'take_profit_pct': 0.35,
    'trailing_stop_pct': 0.08,
    'score_threshold': 55,
    # MA20择时
    'timing_ma': 20,
    # 动态仓位
    'position_bull_low_vol': 0.62,
    'position_bull_high_vol': 0.51,
    'position_bear': 0.00,
    # 波动率分位
    'vol_low_quantile': 0.33,
    'vol_high_quantile': 0.67,
    # 动态止损
    'atr_mult_low_vol': 2.5,
    'atr_mult_mid_vol': 2.0,
    'atr_mult_high_vol': 1.5,
    'max_per_sector': 2,
    'portfolio_drawdown_stop': 0.10,
    'circuit_breaker_days': 3,
}

def load_data(ts_code, start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"""
        SELECT trade_date, open, high, low, close, vol as volume
        FROM daily_quotes WHERE ts_code='{ts_code}' AND trade_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY trade_date
    """, conn)
    conn.close()
    if df.empty: return None
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['atr'] = calculate_atr(df, 14)
    df['volatility'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
    df['vol_ma'] = df['volatility'].rolling(60).mean()
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['macd'], df['signal'] = calculate_macd(df['close'])
    return df

def calculate_atr(df, period):
    high, low, close = df['high'], df['low'], df['close'].shift(1)
    tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = prices.ewm(span=fast).mean()
    ema_slow = prices.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    return macd, signal_line

class V21Backtest:
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
        # 波动率阈值
        all_vols = []
        for name, df in stock_data.items():
            all_vols.extend(df['volatility'].dropna().tolist())
        self.vol_low = np.percentile(all_vols, config['vol_low_quantile'] * 100)
        self.vol_high = np.percentile(all_vols, config['vol_high_quantile'] * 100)
    
    def get_portfolio_value(self, prices):
        value = self.cash
        for name, pos in self.positions.items():
            if pos['shares'] > 0 and name in prices:
                value += pos['shares'] * prices[name]
        return value
    
    def get_position_count(self):
        return len([p for p in self.positions.values() if p['shares'] > 0])
    
    def get_position_pct(self, row):
        """根据MA20和波动率动态计算仓位"""
        close = row.get('close')
        ma20 = row.get('ma20')
        volatility = row.get('volatility')
        
        if pd.isna(close) or pd.isna(ma20):
            return 0
        
        # MA20择时
        if close < ma20:
            return self.config['position_bear']
        
        # 根据波动率调整仓位
        if pd.isna(volatility):
            return self.config['position_bull_high_vol']
        
        if volatility < self.vol_low:
            return self.config['position_bull_low_vol']
        elif volatility > self.vol_high:
            return self.config['position_bull_high_vol']
        else:
            return (self.config['position_bull_low_vol'] + self.config['position_bull_high_vol']) / 2
    
    def get_atr_mult(self, row):
        """根据波动率调整ATR倍数"""
        volatility = row.get('volatility')
        if pd.isna(volatility):
            return self.config['atr_mult_mid_vol']
        
        if volatility < self.vol_low:
            return self.config['atr_mult_low_vol']
        elif volatility > self.vol_high:
            return self.config['atr_mult_high_vol']
        else:
            return self.config['atr_mult_mid_vol']
    
    def calc_signal_score(self, row):
        score = 0
        ma20, close = row.get('ma20'), row.get('close')
        rsi, macd, signal = row.get('rsi'), row.get('macd'), row.get('signal')
        
        if any(pd.isna(x) for x in [ma20, close, rsi, macd, signal]):
            return 0
        
        if close < ma20:
            return 0
        
        score += 30
        if close > ma20 * 1.02: score += 15
        if 30 < rsi < 70: score += 15
        if macd > signal: score += 15
        
        return score
    
    def execute_buy(self, name, price, date, row):
        pct = self.get_position_pct(row)
        if pct <= 0:
            return False
        if self.get_position_count() >= self.config['max_positions']:
            return False
        if name in self.cooldown_until and date < self.cooldown_until[name]:
            return False
        sector = self.stock_sector.get(name, '未知')
        if self.sector_counts.get(sector, 0) >= self.config['max_per_sector']:
            return False
        
        total_value = self.get_portfolio_value({n: self.positions[n].get('current_price', 0) for n in self.positions})
        max_amount = total_value * pct / self.config['max_positions']
        shares = int(max_amount / price / 100) * 100
        if shares <= 0 or shares * price > self.cash * 0.95:
            return False
        
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
        if name not in self.positions or self.positions[name]['shares'] <= 0:
            return False
        pos = self.positions[name]
        shares, buy_price = pos['shares'], pos['buy_price']
        revenue = shares * price * (1 - self.config['commission'] - self.config['stamp_tax'] - self.config['slippage_pct'])
        self.cash += revenue
        pnl = revenue - shares * buy_price
        pnl_pct = (price - buy_price) / buy_price
        self.trade_log.append({'date': date.isoformat(), 'stock': name, 'buy_price': buy_price, 'sell_price': price, 'shares': shares, 'pnl': pnl, 'pnl_pct': pnl_pct, 'reason': reason})
        self.cooldown_until[name] = date + timedelta(days=self.config['cooldown_days'])
        sector = self.stock_sector.get(name, '未知')
        self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
        self.positions[name] = {'shares': 0, 'buy_price': 0, 'buy_date': None}
        return True
    
    def check_sell(self, name, row, date):
        if name not in self.positions or self.positions[name]['shares'] <= 0:
            return
        price = row['close']
        buy_price = self.buy_prices.get(name, 0)
        if buy_price <= 0: return
        
        profit_pct = (price - buy_price) / buy_price
        ma20, atr = row.get('ma20'), row.get('atr')
        highest = self.highest_prices.get(name, buy_price)
        self.highest_prices[name] = max(highest, price)
        self.max_profits[name] = max(self.max_profits.get(name, 0), profit_pct)
        
        # MA20跌破止损
        if not pd.isna(ma20) and price < ma20 * 0.98:
            self.execute_sell(name, price, date, f'MA20跌破({profit_pct:.1%})')
            return
        
        # 动态ATR止损
        if not pd.isna(atr):
            atr_mult = self.get_atr_mult(row)
            stop_price = buy_price - atr_mult * atr
            if price <= stop_price:
                self.execute_sell(name, price, date, f'ATR止损({profit_pct:.1%})')
                return
        
        # 移动止盈
        if self.max_profits[name] >= self.config['take_profit_pct']:
            if profit_pct <= self.max_profits[name] - self.config['trailing_stop_pct']:
                self.execute_sell(name, price, date, f'移动止盈({profit_pct:.1%})')
                return
    
    def run(self, dates):
        for i, date in enumerate(dates):
            prices = {}
            for name, df in self.stock_data.items():
                if date in df.index:
                    row = df.loc[date]
                    prices[name] = row['close']
                    if name in self.positions:
                        self.positions[name]['current_price'] = row['close']
            
            portfolio_value = self.get_portfolio_value(prices)
            self.daily_values.append({'date': date.isoformat(), 'value': portfolio_value})
            
            if portfolio_value > self.peak_value:
                self.peak_value = portfolio_value
            
            drawdown = (self.peak_value - portfolio_value) / self.peak_value
            if drawdown >= self.config['portfolio_drawdown_stop']:
                if not self.circuit_breaker:
                    self.circuit_breaker = True
                    self.circuit_breaker_until = date + timedelta(days=self.config['circuit_breaker_days'])
                    for name in list(self.positions.keys()):
                        if self.positions[name]['shares'] > 0 and name in prices:
                            self.execute_sell(name, prices[name], date, '熔断清仓')
                    continue
            else:
                if self.circuit_breaker and date >= self.circuit_breaker_until:
                    self.circuit_breaker = False
                    self.peak_value = portfolio_value
            if self.circuit_breaker: continue
            
            for name in list(self.positions.keys()):
                if self.positions[name]['shares'] > 0 and name in self.stock_data and date in self.stock_data[name].index:
                    self.check_sell(name, self.stock_data[name].loc[date], date)
            
            signals = []
            for s in STOCK_POOL:
                name = s['name']
                if name in self.positions and self.positions[name]['shares'] > 0: continue
                if name not in self.stock_data or date not in self.stock_data[name].index: continue
                row = self.stock_data[name].loc[date]
                score = self.calc_signal_score(row)
                if score >= self.config['score_threshold']:
                    signals.append((name, row['close'], score, row))
            signals.sort(key=lambda x: x[2], reverse=True)
            for name, price, score, row in signals:
                if self.get_position_count() >= self.config['max_positions']: break
                self.execute_buy(name, price, date, row)
            
            if (i + 1) % 200 == 0:
                print(f"  [{i+1}/{len(dates)}] 权益: ¥{portfolio_value:,.0f}")
        return portfolio_value

def generate_report(backtest, final_value, config):
    initial_cash = config['initial_cash']
    total_return = (final_value - initial_cash) / initial_cash
    days = len(backtest.daily_values)
    years = days / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    values = [d['value'] for d in backtest.daily_values]
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak: peak = v
        dd = (peak - v) / peak
        if dd > max_dd: max_dd = dd
    trades = backtest.trade_log
    total_trades = len(trades)
    winning = [t for t in trades if t['pnl'] > 0]
    losing = [t for t in trades if t['pnl'] <= 0]
    win_rate = len(winning) / max(total_trades, 1)
    avg_win = np.mean([t['pnl'] for t in winning]) if winning else 0
    avg_loss = abs(np.mean([t['pnl'] for t in losing])) if losing else 1
    profit_ratio = avg_win / max(avg_loss, 1)
    daily_returns = pd.Series(values).pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0
    dates = [d['date'] for d in backtest.daily_values]
    
    yearly_stats = {}
    for d in backtest.daily_values:
        year = d['date'][:4]
        if year not in yearly_stats: yearly_stats[year] = {'start': d['value'], 'end': d['value']}
        yearly_stats[year]['end'] = d['value']
    yearly_rows = ""
    for year, stats in sorted(yearly_stats.items()):
        ret = (stats['end'] - stats['start']) / stats['start']
        color = "#3fb950" if ret > 0 else "#f85149"
        yearly_rows += f'<tr><td>{year}</td><td style="color:{color}">{ret:+.1%}</td></tr>'
    
    trade_rows = ""
    for t in trades[-100:]:
        color = "#3fb950" if t['pnl'] > 0 else "#f85149"
        emoji = "🟢" if t['pnl'] > 0 else "🔴"
        trade_rows += f'<tr><td>{t["date"]}</td><td>{t["stock"]}</td><td>{t["pnl_pct"]:.1%}</td><td style="color:{color}">{emoji} {t["pnl"]:>+,.0f}</td><td>{t["reason"]}</td></tr>'
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>v21 MA20择时+动态仓位</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px}}.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;margin-bottom:20px}}h1{{text-align:center;color:#58a6ff}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}.metric{{background:#21262d;border-radius:8px;padding:16px;text-align:center}}.metric .label{{color:#8b949e;font-size:12px}}.metric .value{{font-size:20px;font-weight:bold}}.positive{{color:#3fb950}}.negative{{color:#f85149}}.neutral{{color:#58a6ff}}table{{width:100%;border-collapse:collapse}}th{{background:#21262d;padding:8px;text-align:left;color:#8b949e;font-size:12px}}td{{padding:6px 8px;border-bottom:1px solid #21262d;font-size:12px}}</style></head><body>
<h1>📊 v21 MA20择时+动态仓位</h1>
<p style="text-align:center;color:#8b949e">2021-01-01 ~ 2026-06-14</p>
<div class="grid">
<div class="metric"><div class="label">最终权益</div><div class="value {'positive' if total_return>0 else 'negative'}">¥{final_value:,.0f}</div></div>
<div class="metric"><div class="label">总收益率</div><div class="value {'positive' if total_return>0 else 'negative'}">{total_return:+.1%}</div></div>
<div class="metric"><div class="label">年化收益率</div><div class="value {'positive' if annual_return>0.1 else 'negative'}">{annual_return:+.1%}</div></div>
<div class="metric"><div class="label">最大回撤</div><div class="value {'positive' if max_dd<0.15 else 'negative'}">{max_dd:.1%}</div></div>
<div class="metric"><div class="label">夏普比率</div><div class="value neutral">{sharpe:.2f}</div></div>
<div class="metric"><div class="label">胜率</div><div class="value neutral">{win_rate:.1%}</div></div>
<div class="metric"><div class="label">盈亏比</div><div class="value neutral">{profit_ratio:.2f}</div></div>
<div class="metric"><div class="label">交易次数</div><div class="value neutral">{total_trades}</div></div>
</div>
<div class="card"><h2>📈 权益曲线</h2><div id="eq" style="height:400px"></div></div>
<div class="card"><h2>📅 年度收益</h2><table><tr><th>年份</th><th>收益率</th></tr>{yearly_rows}</table></div>
<div class="card"><h2>📝 交易明细</h2><div style="max-height:400px;overflow-y:auto"><table><tr><th>日期</th><th>股票</th><th>收益率</th><th>盈亏</th><th>原因</th></tr>{trade_rows}</table></div></div>
<script>var c=echarts.init(document.getElementById('eq'));c.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis'}},grid:{{left:80,right:30,top:30,bottom:40}},xAxis:{{type:'category',data:{json.dumps(dates)},axisLabel:{{color:'#8b949e',fontSize:10}}}},yAxis:{{type:'value',axisLabel:{{color:'#8b949e',formatter:'¥{{value}}'}}}},series:[{{type:'line',data:{json.dumps(values)},lineStyle:{{color:'#00e676',width:2}},itemStyle:{{color:'#00e676'}},areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(0,230,118,0.25)'}},{{offset:1,color:'rgba(0,230,118,0.02)'}}])}},showSymbol:false}}]}});window.addEventListener('resize',()=>c.resize());</script>
</body></html>"""
    
    with open('/usr/share/nginx/html/public/backtest_v21_ma20.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n{'='*60}")
    print(f"📊 v21 MA20择时+动态仓位 回测结果")
    print(f"{'='*60}")
    print(f"总收益: {total_return:+.1%}, 年化: {annual_return:+.1%}, 回撤: {max_dd:.1%}")
    print(f"夏普: {sharpe:.2f}, 胜率: {win_rate:.1%}, 盈亏比: {profit_ratio:.2f}, 交易: {total_trades}次")

def main():
    print("v21 MA20择时+动态仓位 回测")
    start_date, end_date = '2021-01-01', '2026-06-14'
    stock_data = {}
    all_dates = set()
    for s in STOCK_POOL:
        ts_code = f"{s['code']}.{'SH' if s['code'].startswith('6') else 'SZ'}"
        df = load_data(ts_code, start_date, end_date)
        if df is not None and len(df) > 100:
            stock_data[s['name']] = df
            all_dates.update(df.index)
            print(f"  ✅ {s['name']}: {len(df)}条")
    dates = sorted(all_dates)
    backtest = V21Backtest(CONFIG, stock_data)
    final_value = backtest.run(dates)
    generate_report(backtest, final_value, CONFIG)

if __name__ == '__main__':
    main()
