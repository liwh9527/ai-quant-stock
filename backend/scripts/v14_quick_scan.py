#!/usr/bin/env python3
"""
v14 Quick Scan — 轻量级策略扫描（~30-45秒）
用于 cron 报告推送，不执行交易。

用法:
  cd /root/projects/ai-quant-stock/backend
  MX_APIKEY=mkt_xxx python3 scripts/v14_quick_scan.py

输出: 格式化的扫描报告（持仓、买入/卖出信号、关注列表）
"""

import os
import sys
import json
import math
import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ========== CONFIG ==========
MX_APIKEY = os.environ.get("MX_APIKEY", "")
BASE_URL = "https://mkapi2.dfcfs.com/finskillshub"
HEADERS = {"Content-Type": "application/json", "apikey": MX_APIKEY}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

STRATEGY_CONFIG = {
    "ma_period": 20, "atr_period": 14, "volume_ratio": 1.5,
    "atr_threshold": 0.02, "max_deviation": 0.10,
    "take_profit_pct": 0.40, "trailing_stop_pct": 0.05,
    "atr_stop_multiplier": 1.5, "chandelier_atr_mult": 3,
    "max_positions": 4, "position_pct_high": 0.25, "position_pct_low": 0.18,
    "momentum_threshold": 0.4, "adx_threshold": 15,
    "max_per_sector": 1, "blacklist_days": 30, "cooldown_days": 3,
    "portfolio_drawdown_stop": 0.10, "min_trade_amount": 10000,
}

STOCK_POOL = [
    {'code': '600487', 'name': '亨通光电', 'sector': '半导体'},
    {'code': '002371', 'name': '北方华创', 'sector': '半导体'},
    {'code': '600584', 'name': '长电科技', 'sector': '半导体'},
    {'code': '002916', 'name': '深南电路', 'sector': '半导体'},
    {'code': '002185', 'name': '华天科技', 'sector': '半导体'},
    {'code': '601899', 'name': '紫金矿业', 'sector': '有色'},
    {'code': '603993', 'name': '洛阳钼业', 'sector': '有色'},
    {'code': '600025', 'name': '华能水电', 'sector': '电力'},
    {'code': '600900', 'name': '长江电力', 'sector': '电力'},
    {'code': '600519', 'name': '贵州茅台', 'sector': '消费'},
    {'code': '000858', 'name': '五粮液', 'sector': '消费'},
    {'code': '000333', 'name': '美的集团', 'sector': '家电'},
    {'code': '600309', 'name': '万华化学', 'sector': '化工'},
    {'code': '600031', 'name': '三一重工', 'sector': '机械'},
    {'code': '002415', 'name': '海康威视', 'sector': '科技'},
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源'},
    {'code': '002475', 'name': '立讯精密', 'sector': '科技'},
    {'code': '600036', 'name': '招商银行', 'sector': '金融'},
    {'code': '601318', 'name': '中国平安', 'sector': '金融'},
    {'code': '600760', 'name': '中航沈飞', 'sector': '军工'},
]
STOCK_MAP = {s['code']: s for s in STOCK_POOL}

# ========== DATA SOURCE ==========
sys.path.insert(0, SCRIPT_DIR)
from data_source import fetch_historical_data, fetch_realtime_quote


def resolve_stock_name(code, db_path=None):
    """从 SQLite 数据库查询股票名称（当 STOCK_MAP 和 realtime 都无名称时）"""
    if db_path is None:
        db_path = os.path.join(SCRIPT_DIR, '..', 'data', 'quant.db')
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM stocks WHERE ts_code LIKE ?", (f"{code}%",))
        row = c.fetchone()
        conn.close()
        return row[0] if row else f'未知({code})'
    except Exception:
        return f'未知({code})'


def calculate_indicators(df, config):
    df = df.copy()
    df['ma20'] = df['close'].rolling(config['ma_period']).mean()
    df['ma5'] = df['close'].rolling(5).mean()
    df['atr'] = (df['high'] - df['low']).rolling(config['atr_period']).mean()
    df['vol_ma'] = df['volume'].rolling(5).mean()
    df['atr_ma'] = df['atr'].rolling(20).mean()

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['signal']
    return df


def get_market_state(idx_df):
    if len(idx_df) < 25:
        return 'unknown'
    row = idx_df.iloc[-1]
    ma5, ma20, atr, atr_avg = row.get('ma5',0), row.get('ma20',0), row.get('atr',0), row.get('atr_ma',0)
    if pd.isna(ma5) or pd.isna(ma20) or pd.isna(atr) or pd.isna(atr_avg) or atr_avg == 0:
        return 'unknown'
    vol_high = atr > atr_avg * 1.3
    trend_up = ma5 > ma20
    if trend_up and not vol_high: return 'bull'
    elif trend_up and vol_high: return 'volatile_up'
    elif not trend_up and vol_high: return 'bear'
    else: return 'sideways'


def calc_signal_score(row, config, prev_rows=None):
    score = 0
    price, ma, atr, vol, vol_ma = row['close'], row['ma20'], row['atr'], row['volume'], row['vol_ma']
    rsi, macd_hist = row['rsi'], row['macd_hist']
    if any(pd.isna(x) for x in [ma, atr, vol_ma, rsi, macd_hist]):
        return 0
    deviation = abs(price - ma) / ma
    if deviation > config['max_deviation']:
        return 0
    score += 30
    if price >= ma:
        score += 20
    else:
        return 0
    if prev_rows is not None and len(prev_rows) >= 20:
        price_20d_ago = prev_rows[-20]['close']
        if price_20d_ago > 0:
            momentum = (price - price_20d_ago) / price_20d_ago
            if momentum < config.get('momentum_threshold', 0):
                return 0
            score += 10
    if vol_ma > 0 and vol > vol_ma * config['volume_ratio']:
        score += 15
    if price > 0 and atr / price > config['atr_threshold']:
        score += 10
    if 40 <= rsi <= 70:
        score += 10
    elif rsi > 70:
        return 0
    if macd_hist > 0:
        score += 5
    return score


def check_sell(code, current_price, buy_price, highest, max_profit, row, config):
    profit_pct = (current_price - buy_price) / buy_price
    atr, ma = row['atr'], row['ma20']
    if not pd.isna(atr):
        chandelier_stop = highest - config['chandelier_atr_mult'] * atr
        if current_price <= chandelier_stop and profit_pct > 0:
            return f"Chandelier止盈({profit_pct:.1%})"
    if not pd.isna(atr):
        stop_price = buy_price - config['atr_stop_multiplier'] * atr
        if current_price <= stop_price:
            return f"ATR止损({profit_pct:.1%})"
    if max_profit >= config['take_profit_pct']:
        trailing_pct = config['trailing_stop_pct']
        if not pd.isna(atr) and current_price > 0 and atr / current_price > 0.04:
            trailing_pct = 0.10
        if profit_pct <= max_profit - trailing_pct:
            return f"移动止盈({max_profit:.1%}→{profit_pct:.1%})"
    if not pd.isna(ma):
        if current_price < ma * 0.98:
            return f"跌破MA20({profit_pct:.1%})"
    return None


# ========== MAIN SCAN ==========
def main():
    print(f"🔍 v14 Quick Scan — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not MX_APIKEY:
        print("❌ MX_APIKEY 环境变量未设置，无法获取账户信息")
        return

    # 1. Account info
    try:
        resp = requests.post(f"{BASE_URL}/api/claw/mockTrading/balance", headers=HEADERS, json={"moneyUnit": 1}, timeout=10)
        balance = resp.json().get("data", {})
        total_assets = balance.get('totalAssets', 0)
        avail_balance = balance.get('availBalance', 0)
        pos_value = balance.get('totalPosValue', 0)
        print(f"💰 总资产: ¥{total_assets:,.0f}  可用: ¥{avail_balance:,.0f}  持仓市值: ¥{pos_value:,.0f}")
    except Exception as e:
        print(f"❌ 获取账户信息失败: {e}")
        total_assets, avail_balance, pos_value = 0, 0, 0

    # 2. Current positions
    positions = {}
    try:
        resp = requests.post(f"{BASE_URL}/api/claw/mockTrading/positions", headers=HEADERS, json={"moneyUnit": 1}, timeout=10)
        pos_list = resp.json().get("data", {}).get("posList", []) or []
        for pos in pos_list:
            code = pos.get('secCode', '')
            cost_price = pos.get('costPrice', 0) / (10 ** pos.get('costPriceDec', 3))
            market_price = pos.get('price', 0) / (10 ** pos.get('priceDec', 2))
            quantity = int(pos.get('count', 0))
            avail = int(pos.get('availCount', 0))
            if quantity > 0:
                if code in STOCK_MAP:
                    name = STOCK_MAP[code]['name']
                    sector = STOCK_MAP[code]['sector']
                else:
                    name = resolve_stock_name(code)
                    sector = '非策略池'
                pnl = (market_price - cost_price) * quantity
                pnl_pct = (market_price - cost_price) / cost_price * 100 if cost_price > 0 else 0
                positions[code] = {
                    'name': name, 'sector': sector, 'quantity': quantity, 'avail': avail,
                    'cost_price': cost_price, 'market_price': market_price,
                    'pnl': pnl, 'pnl_pct': pnl_pct,
                }
        print(f"📊 当前持仓: {len(positions)} 只")
    except Exception as e:
        print(f"❌ 获取持仓失败: {e}")

    # 3. Market state
    try:
        idx_df = fetch_historical_data("000001", days=60)
        if idx_df is not None and len(idx_df) >= 25:
            idx_df = calculate_indicators(idx_df, STRATEGY_CONFIG)
            market_state = get_market_state(idx_df)
        else:
            market_state = 'unknown'
        print(f"🌍 市场状态: {market_state}")
    except Exception as e:
        market_state = 'unknown'
        print(f"❌ 市场状态判断失败: {e}")

    # 4. Signal scanning
    buy_signals = []
    sell_signals = []
    watch_list = []

    for stock in STOCK_POOL:
        code = stock['code']
        name = stock['name']
        sector = stock['sector']

        try:
            df = fetch_historical_data(code, days=60)
            if df is None or len(df) < 25:
                continue
            df = calculate_indicators(df, STRATEGY_CONFIG)
            latest = df.iloc[-1]
            current_price = latest['close']

            # Check sell signals for held positions
            if code in positions:
                pos = positions[code]
                buy_price = pos['cost_price']
                highest = current_price
                max_profit = max(0, (current_price - buy_price) / buy_price)
                sell_reason = check_sell(code, current_price, buy_price, highest, max_profit, latest, STRATEGY_CONFIG)
                if sell_reason:
                    sell_signals.append({
                        'code': code, 'name': name, 'sector': sector,
                        'price': current_price, 'buy_price': buy_price,
                        'pnl_pct': (current_price - buy_price) / buy_price * 100,
                        'reason': sell_reason, 'quantity': pos['quantity'],
                    })

            # Check buy signals for non-held stocks
            if code not in positions and market_state not in ('bear', 'unknown'):
                prev_rows = [df.iloc[i] for i in range(len(df))]
                score = calc_signal_score(latest, STRATEGY_CONFIG, prev_rows)
                indicators = {
                    'ma20': latest.get('ma20', 0),
                    'rsi': latest.get('rsi', 0),
                    'macd_hist': latest.get('macd_hist', 0),
                    'atr': latest.get('atr', 0),
                    'vol_ratio': latest['volume'] / latest['vol_ma'] if latest.get('vol_ma', 0) > 0 else 0,
                }
                if score >= 70:
                    buy_signals.append({
                        'code': code, 'name': name, 'sector': sector,
                        'price': current_price, 'score': score, 'indicators': indicators,
                    })
                elif score >= 50:
                    watch_list.append({
                        'code': code, 'name': name, 'sector': sector,
                        'price': current_price, 'score': score, 'indicators': indicators,
                    })
        except Exception as e:
            print(f"  ⚠️ {name}({code}) 分析失败: {e}")

    # ========== OUTPUT ==========
    print("\n" + "=" * 60)
    print("📋 扫描结果汇总")
    print("=" * 60)

    # Positions
    if positions:
        print(f"\n📈 **当前持仓 ({len(positions)}只)**")
        total_pnl = 0
        for code, pos in positions.items():
            emoji = "🟢" if pos['pnl'] >= 0 else "🔴"
            pool_tag = "" if code in STOCK_MAP else " ⚠️非策略池"
            print(f"  {emoji} {pos['name']}({code}){pool_tag}")
            print(f"     持仓: {pos['quantity']}股 (可卖:{pos['avail']})  成本: ¥{pos['cost_price']:.2f}  现价: ¥{pos['market_price']:.2f}")
            print(f"     盈亏: ¥{pos['pnl']:+,.0f} ({pos['pnl_pct']:+.2f}%)")
            total_pnl += pos['pnl']
        print(f"  ────────────────────────")
        print(f"  持仓总盈亏: ¥{total_pnl:+,.0f}")
    else:
        print("\n📈 **当前持仓**: 空仓")

    # Buy signals
    if buy_signals:
        print(f"\n🟢 **买入信号 ({len(buy_signals)}只)** — 评分≥70")
        for sig in buy_signals:
            ind = sig['indicators']
            print(f"  🟢 {sig['name']}({sig['code']}) [{sig['sector']}]")
            print(f"     价格: ¥{sig['price']:.2f}  评分: {sig['score']}")
            print(f"     MA20: ¥{ind['ma20']:.2f}  RSI: {ind['rsi']:.1f}  MACD柱: {ind['macd_hist']:.3f}  量比: {ind['vol_ratio']:.2f}")
    else:
        print(f"\n🟢 **买入信号**: 无")

    # Sell signals
    if sell_signals:
        print(f"\n🔴 **卖出信号 ({len(sell_signals)}只)**")
        for sig in sell_signals:
            emoji = "🟢" if sig['pnl_pct'] >= 0 else "🔴"
            print(f"  🔴 {sig['name']}({sig['code']}) [{sig['sector']}]")
            print(f"     现价: ¥{sig['price']:.2f}  {emoji} {sig['pnl_pct']:+.2f}%")
            print(f"     触发: {sig['reason']}")
    else:
        print(f"\n🔴 **卖出信号**: 无")

    # Watch list
    if watch_list:
        print(f"\n👀 **关注列表 ({len(watch_list)}只)** — 评分50-69")
        for sig in watch_list:
            ind = sig['indicators']
            print(f"  👀 {sig['name']}({sig['code']}) [{sig['sector']}] 评分:{sig['score']}  ¥{sig['price']:.2f}")

    # Non-pool positions
    non_pool = {c: p for c, p in positions.items() if c not in STOCK_MAP}
    if non_pool:
        print(f"\n⚠️ **非策略池持仓 ({len(non_pool)}只)** — 不受v14策略管理")
        for code, pos in non_pool.items():
            emoji = "🟢" if pos['pnl'] >= 0 else "🔴"
            print(f"  {emoji} {pos['name']}({code}) {pos['quantity']}股 成本:¥{pos['cost_price']:.2f} 现价:¥{pos['market_price']:.2f} {pos['pnl_pct']:+.2f}%")

    print(f"\n{'='*60}")
    print(f"⏰ 扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📌 策略: v14主升浪优化版 | 动量阈值: {STRATEGY_CONFIG['momentum_threshold']} | 量比: {STRATEGY_CONFIG['volume_ratio']}")


if __name__ == '__main__':
    main()
