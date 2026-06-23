#!/usr/bin/env python3
"""
智能量化交易系统 v14 - 模拟账户操作
基于v14回测策略：不对称波动率 + 动量加权 + 市场状态识别 + 问题股排除

功能：
1. 实时监控20只股票
2. v14策略信号计算
3. 妙想模拟账户自动交易
4. QQ消息推送
5. 每日报告
"""

import os
import sys
import json
import time
import math
import requests
import numpy as np
from data_source import fetch_realtime_quote as _fetch_realtime_quote, fetch_realtime_quotes_batch, fetch_historical_data as _fetch_historical_data
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# 配置
# ============================================================

MIXIANG_CONFIG = {
    "base_url": "https://mkapi2.dfcfs.com/finskillshub",
    "apikey": os.environ.get("MX_APIKEY", ""),
}

# v14策略配置 - 主升浪优化版#1381（总收益751.6%，年化50.7%，夏普1.01）
STRATEGY_CONFIG = {
    "ma_period": 20,
    "atr_period": 14,
    "volume_ratio": 1.5,          # 量比阈值（原1.2→1.5，更严格放量确认）
    "atr_threshold": 0.02,
    "max_deviation": 0.10,
    "take_profit_pct": 0.40,         # 40%止盈
    "trailing_stop_pct": 0.05,       # 移动止盈回撤（原8%→5%，更紧）
    "atr_stop_multiplier": 1.5,      # ATR止损
    "chandelier_atr_mult": 3,        # Chandelier Exit
    "max_positions": 4,              # 最多4只
    "position_pct_high": 0.25,       # 高分仓位25%
    "position_pct_low": 0.18,        # 低分仓位18%
    "target_volatility": 0.15,       # 目标波动率
    "cooldown_days": 3,              # 冷却3天
    "adx_threshold": 15,             # ADX阈值
    "max_per_sector": 1,             # 同行业最多1只
    "blacklist_days": 30,            # 问题股暂停30天
    "portfolio_drawdown_stop": 0.10, # 组合熔断10%（原7%→10%）
    "min_trade_amount": 10000,       # 最小交易金额
    "momentum_threshold": 0.4,       # 动量阈值（强动量确认）
    "rebalance_days": 5,             # 再平衡周期
}

# 股票池 - 沪深300典型成分股
STOCK_POOL = [
    # 半导体（高弹性）
    {'code': '600487', 'name': '亨通光电', 'sector': '半导体'},
    {'code': '002371', 'name': '北方华创', 'sector': '半导体'},
    {'code': '600584', 'name': '长电科技', 'sector': '半导体'},
    {'code': '002916', 'name': '深南电路', 'sector': '半导体'},
    {'code': '002185', 'name': '华天科技', 'sector': '半导体'},
    
    # 有色（周期股）
    {'code': '601899', 'name': '紫金矿业', 'sector': '有色'},
    {'code': '603993', 'name': '洛阳钼业', 'sector': '有色'},
    
    # 电力（防守型）
    {'code': '600025', 'name': '华能水电', 'sector': '电力'},
    {'code': '600900', 'name': '长江电力', 'sector': '电力'},
    
    # 消费（白马股）
    {'code': '600519', 'name': '贵州茅台', 'sector': '消费'},
    {'code': '000858', 'name': '五粮液', 'sector': '消费'},
    {'code': '000333', 'name': '美的集团', 'sector': '家电'},
    
    # 制造（周期股）
    {'code': '600309', 'name': '万华化学', 'sector': '化工'},
    {'code': '600031', 'name': '三一重工', 'sector': '机械'},
    
    # 科技（成长股）
    {'code': '002415', 'name': '海康威视', 'sector': '科技'},
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源'},
    {'code': '002475', 'name': '立讯精密', 'sector': '科技'},
    
    # 金融（大盘股）
    {'code': '600036', 'name': '招商银行', 'sector': '金融'},
    {'code': '601318', 'name': '中国平安', 'sector': '金融'},
    
    # 军工
    {'code': '600760', 'name': '中航沈飞', 'sector': '军工'},
]

SECTORS = list(set(s["sector"] for s in STOCK_POOL))
STOCK_MAP = {s["code"]: s for s in STOCK_POOL}


# ============================================================
# QQ消息推送
# ============================================================

class QQNotifier:
    def send(self, message: str):
        try:
            queue_dir = os.path.expanduser("~/.hermes/message_queue")
            os.makedirs(queue_dir, exist_ok=True)
            msg_file = os.path.join(queue_dir, f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(msg_file, 'w', encoding='utf-8') as f:
                json.dump({"platform": "qqbot", "message": message, "timestamp": datetime.now().isoformat()}, f, ensure_ascii=False)
        except Exception as e:
            print(f"📤 消息异常: {e}")

    def format_signal(self, signal_type, code, name, price, quantity, reason, indicators=None):
        emoji = "🟢" if signal_type == "buy" else "🔴"
        action = "买入" if signal_type == "buy" else "卖出"
        msg = f"""{emoji} **{action}信号**

📊 **股票**: {name} ({code})
💰 **价格**: {price:.2f}
📦 **数量**: {quantity} 股
💵 **金额**: ¥{price * quantity:,.0f}

💡 **原因**: {reason}"""
        if indicators:
            msg += f"\n📈 MA20={indicators.get('ma20',0):.2f} ATR={indicators.get('atr',0):.4f}"
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return msg


# ============================================================
# 妙想API客户端
# ============================================================

class MixiangClient:
    def __init__(self, base_url, apikey):
        self.base_url = base_url
        self.apikey = apikey
        self.headers = {"Content-Type": "application/json", "apikey": apikey}

    def _request(self, endpoint, data=None):
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.post(url, headers=self.headers, json=data or {}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"code": "-1", "message": str(e)}

    def get_balance(self):
        result = self._request("/api/claw/mockTrading/balance", {"moneyUnit": 1})
        return result.get("data") if result.get("code") == "200" else None

    def get_positions(self):
        result = self._request("/api/claw/mockTrading/positions", {"moneyUnit": 1})
        if result.get("code") == "200":
            return result.get("data", {}).get("posList", []) or []
        return []

    def buy(self, code, price, quantity, use_market_price=False):
        return self._request("/api/claw/mockTrading/trade", {
            "type": "buy", "stockCode": code, "price": price,
            "quantity": quantity, "useMarketPrice": use_market_price,
        })

    def sell(self, code, price, quantity, use_market_price=False):
        return self._request("/api/claw/mockTrading/trade", {
            "type": "sell", "stockCode": code, "price": price,
            "quantity": quantity, "useMarketPrice": use_market_price,
        })


# ============================================================
# v14策略分析器
# ============================================================

class StrategyV14:
    def __init__(self, config):
        self.config = config
        self.stock_sector = {s["code"]: s["sector"] for s in STOCK_POOL}
        self.consecutive_losses = {}
        self.total_pnl = {}
        self.blacklist_until = {}
        self.cooldown_until = {}
        self.highest_prices = {}
        self.max_profits = {}
        self.buy_prices = {}
        self.peak_value = 0
        self.circuit_breaker_until = None

    def calculate_indicators(self, df):
        """计算技术指标"""
        df = df.copy()
        df['ma20'] = df['close'].rolling(self.config['ma_period']).mean()
        df['ma5'] = df['close'].rolling(5).mean()
        df['atr'] = (df['high'] - df['low']).rolling(self.config['atr_period']).mean()
        df['vol_ma'] = df['volume'].rolling(5).mean()
        df['volatility'] = df['close'].rolling(20).std() / df['close'] * math.sqrt(252)
        df['atr_ma'] = df['atr'].rolling(20).mean()

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema12 - ema26
        df['signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['signal']

        # ADX (简化版)
        tr = pd.concat([
            df['high'] - df['low'],
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        ], axis=1).max(axis=1)
        df['atr14'] = tr.rolling(14).mean()
        plus_dm = (df['high'] - df['high'].shift(1)).where(lambda x: x > 0, 0)
        minus_dm = (df['low'].shift(1) - df['low']).where(lambda x: x > 0, 0)
        plus_di = (plus_dm.rolling(14).mean() / df['atr14'] * 100)
        minus_di = (minus_dm.rolling(14).mean() / df['atr14'] * 100)
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
        df['adx'] = dx.rolling(14).mean()

        return df

    def get_market_state(self, idx_df):
        """市场状态识别"""
        if len(idx_df) < 25:
            return 'unknown'
        row = idx_df.iloc[-1]
        ma5 = row.get('ma5', 0)
        ma20 = row.get('ma20', 0)
        atr = row.get('atr', 0)
        atr_avg = row.get('atr_ma', 0)

        if pd.isna(ma5) or pd.isna(ma20) or pd.isna(atr) or pd.isna(atr_avg) or atr_avg == 0:
            return 'unknown'

        vol_high = atr > atr_avg * 1.3
        trend_up = ma5 > ma20

        if trend_up and not vol_high:
            return 'bull'
        elif trend_up and vol_high:
            return 'volatile_up'
        elif not trend_up and vol_high:
            return 'bear'
        else:
            return 'sideways'

    def calc_signal_score(self, row, prev_rows=None):
        """计算买入信号评分"""
        score = 0
        price = row['close']
        ma = row['ma20']
        atr = row['atr']
        vol = row['volume']
        vol_ma = row['vol_ma']
        rsi = row['rsi']
        macd_hist = row['macd_hist']

        if any(pd.isna(x) for x in [ma, atr, vol_ma, rsi, macd_hist]):
            return 0

        deviation = abs(price - ma) / ma
        if deviation > self.config['max_deviation']:
            return 0
        score += 30

        if price >= ma:
            score += 20
        else:
            return 0

        # 动量阈值检查（20日价格变化率）
        if prev_rows is not None and len(prev_rows) >= 20:
            price_20d_ago = prev_rows[-20]['close'] if len(prev_rows) >= 20 else None
            if price_20d_ago and price_20d_ago > 0:
                momentum = (price - price_20d_ago) / price_20d_ago
                if momentum < self.config.get('momentum_threshold', 0):
                    return 0  # 动量不足，直接拒绝
                score += 10  # 动量达标加分

        if vol_ma > 0 and vol > vol_ma * self.config['volume_ratio']:
            score += 15

        if price > 0 and atr / price > self.config['atr_threshold']:
            score += 10

        if 40 <= rsi <= 70:
            score += 10
        elif rsi > 70:
            return 0

        if macd_hist > 0:
            score += 5

        return score

    def check_sell(self, code, current_price, buy_price, highest, max_profit, row):
        """检查卖出条件"""
        profit_pct = (current_price - buy_price) / buy_price
        atr = row['atr']
        ma = row['ma20']

        # Chandelier Exit
        if not pd.isna(atr):
            chandelier_stop = highest - self.config['chandelier_atr_mult'] * atr
            if current_price <= chandelier_stop and profit_pct > 0:
                return f"Chandelier止盈({profit_pct:.1%})"

        # ATR止损
        if not pd.isna(atr):
            stop_price = buy_price - self.config['atr_stop_multiplier'] * atr
            if current_price <= stop_price:
                return f"ATR止损({profit_pct:.1%})"

        # 移动止盈
        if max_profit >= self.config['take_profit_pct']:
            trailing_pct = self.config['trailing_stop_pct']
            if not pd.isna(atr) and current_price > 0 and atr / current_price > 0.04:
                trailing_pct = 0.10
            if profit_pct <= max_profit - trailing_pct:
                return f"移动止盈({max_profit:.1%}→{profit_pct:.1%})"

        # 跌破MA20
        if not pd.isna(ma):
            if current_price < ma * 0.98:
                return f"跌破MA20({profit_pct:.1%})"

        return None

    def update_trade_result(self, code, pnl):
        """更新交易结果，管理黑名单"""
        self.total_pnl[code] = self.total_pnl.get(code, 0) + pnl
        if pnl < 0:
            self.consecutive_losses[code] = self.consecutive_losses.get(code, 0) + 1
        else:
            self.consecutive_losses[code] = 0

        if self.consecutive_losses.get(code, 0) >= 2 and self.total_pnl.get(code, 0) < 0:
            self.blacklist_until[code] = datetime.now() + timedelta(days=self.config['blacklist_days'])
            return True  # 被加入黑名单
        return False


# ============================================================
# 主监控系统
# ============================================================

class TradingSystem:
    def __init__(self):
        self.client = MixiangClient(MIXIANG_CONFIG["base_url"], MIXIANG_CONFIG["apikey"])
        self.notifier = QQNotifier()
        self.strategy = StrategyV14(STRATEGY_CONFIG)
        self.price_history = {s["code"]: [] for s in STOCK_POOL}
        self.volume_history = {s["code"]: [] for s in STOCK_POOL}
        self.running = True
        self.last_buy_time = {}  # 记录每只股票上次买入时间，防止重复买入

    def fetch_historical_data(self, code, days=60):
        """获取历史数据（baostock）"""
        for attempt in range(3):
            try:
                df = _fetch_historical_data(code, days=days)
                if df is None or df.empty:
                    return None
                return df
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                    continue
                print(f"  ❌ {code} 历史数据获取失败: {e}")
                return None

    def fetch_realtime_quote(self, code):
        """获取实时行情（腾讯接口）"""
        try:
            result = _fetch_realtime_quote(code)
            if result is None:
                return None
            return result
        except Exception as e:
            print(f"  ❌ {code} 实时行情获取失败: {e}")
            return None

    def is_trading_time(self):
        """判断是否在交易时间（避开开盘前15分钟和收盘前15分钟）"""
        now = datetime.now()
        if now.weekday() >= 5:  # 周末
            return False
        t = now.time()
        from datetime import time as dt_time
        # 避开9:30-9:45（开盘波动大）和14:45-15:00（收盘前）
        morning = dt_time(9, 45) <= t <= dt_time(11, 30)
        afternoon = dt_time(13, 0) <= t <= dt_time(14, 45)
        return morning or afternoon

    def get_current_positions(self):
        """获取当前持仓"""
        positions = self.client.get_positions()
        result = {}
        for pos in positions:
            code = pos.get('secCode', '')
            if code in STOCK_MAP:
                cost_price = pos.get('costPrice', 0)
                cost_dec = pos.get('costPriceDec', 3)
                if cost_price > 0:
                    cost_price = cost_price / (10 ** cost_dec)
                quantity = pos.get('count', 0)  # 字段是count
                avail_count = pos.get('availCount', 0)  # 可卖数量
                market_price = pos.get('price', 0)
                price_dec = pos.get('priceDec', 2)
                if market_price > 0:
                    market_price = market_price / (10 ** price_dec)
                if quantity > 0:
                    result[code] = {
                        'code': code,
                        'name': STOCK_MAP[code]['name'],
                        'quantity': int(quantity),
                        'avail_count': int(avail_count),
                        'cost_price': cost_price,
                        'current_price': market_price,
                    }
        return result

    def run_scan(self):
        """执行一次扫描"""
        print(f"\n{'='*60}")
        print(f"🔍 扫描开始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        # 获取账户信息
        balance = self.client.get_balance()
        if not balance:
            print("❌ 获取账户信息失败")
            return

        total_assets = balance.get('totalAssets', 0)
        avail_balance = balance.get('availBalance', 0)
        print(f"💰 总资产: ¥{total_assets:,.0f}  可用: ¥{avail_balance:,.0f}")

        # 更新峰值
        if total_assets > self.strategy.peak_value:
            self.strategy.peak_value = total_assets

        # 组合熔断检查
        if self.strategy.peak_value > 0:
            dd = (self.strategy.peak_value - total_assets) / self.strategy.peak_value
            if dd >= STRATEGY_CONFIG['portfolio_drawdown_stop']:
                print(f"🚨 组合回撤 {dd:.1%} 触发熔断！暂停交易")
                return

        # 获取当前持仓
        positions = self.get_current_positions()
        print(f"📊 当前持仓: {len(positions)} 只")

        # 获取指数数据（用于市场状态判断）
        idx_df = self.fetch_historical_data("000001")  # 上证指数
        if idx_df is not None:
            idx_df = self.strategy.calculate_indicators(idx_df)
            market_state = self.strategy.get_market_state(idx_df)
            print(f"🌍 市场状态: {market_state}")
        else:
            market_state = 'unknown'

        # 遍历股票池
        for stock in STOCK_POOL:
            code = stock['code']
            name = stock['name']
            sector = stock['sector']

            # 获取历史数据
            df = self.fetch_historical_data(code)
            if df is None or len(df) < 25:
                continue

            df = self.strategy.calculate_indicators(df)
            latest = df.iloc[-1]
            current_price = latest['close']

            # 已持仓 → 检查卖出
            if code in positions:
                pos = positions[code]
                buy_price = self.strategy.buy_prices.get(code, pos['cost_price'])
                highest = self.strategy.highest_prices.get(code, current_price)
                max_profit = self.strategy.max_profits.get(code, 0)

                # 更新最高价和最大盈利
                if buy_price <= 0:
                    buy_price = current_price  # 兜底
                if current_price > highest:
                    highest = current_price
                    self.strategy.highest_prices[code] = highest
                profit_pct = (current_price - buy_price) / buy_price if buy_price > 0 else 0
                if profit_pct > max_profit:
                    max_profit = profit_pct
                    self.strategy.max_profits[code] = max_profit

                sell_reason = self.strategy.check_sell(code, current_price, buy_price, highest, max_profit, latest)
                if sell_reason:
                    print(f"  🔴 卖出信号: {name} {sell_reason}")
                    quantity = pos.get('avail_count', pos['quantity'])
                    if quantity <= 0:
                        print(f"  ⏸️ 无可卖数量(T+1)")
                        continue
                    result = self.client.sell(code, current_price, quantity, use_market_price=True)
                    success = result.get('code') == '200'
                    if success:
                        pnl = (current_price - buy_price) * quantity
                        blacklisted = self.strategy.update_trade_result(code, pnl)
                        self.strategy.cooldown_until[code] = datetime.now() + timedelta(days=STRATEGY_CONFIG['cooldown_days'])
                        msg = self.notifier.format_signal('sell', code, name, current_price, quantity, sell_reason)
                        self.notifier.send(msg)
                        print(f"  ✅ 卖出成功: {name} 盈亏 ¥{pnl:+,.0f}")
                        if blacklisted:
                            print(f"  ⚠️ {name} 加入黑名单30天")
                    else:
                        print(f"  ❌ 卖出失败: {result.get('message', '')}")
                else:
                    print(f"  📊 持仓: {name} 盈亏 {profit_pct:+.1%}")
                continue

            # 未持仓 → 检查买入
            if len(positions) >= STRATEGY_CONFIG['max_positions']:
                continue

            # 冷却期检查
            if code in self.strategy.cooldown_until:
                if datetime.now() < self.strategy.cooldown_until[code]:
                    continue

            # 黑名单检查
            if code in self.strategy.blacklist_until:
                if datetime.now() < self.strategy.blacklist_until[code]:
                    continue

            # 防止24小时内重复买入同一只股票
            if code in self.last_buy_time:
                if datetime.now() - self.last_buy_time[code] < timedelta(hours=24):
                    continue

            # 市场状态过滤
            if market_state == 'bear':
                continue

            # 同行业限制（更严格：已持有的行业不能再买）
            held_sectors = [STOCK_MAP[c]['sector'] for c in positions if c in STOCK_MAP]
            if sector in held_sectors:
                continue

            # 行业动量检查
            sector_momentum = self._calc_sector_momentum()
            if sector_momentum:
                sorted_sectors = sorted(sector_momentum.items(), key=lambda x: x[1], reverse=True)
                top_sectors = [s[0] for s in sorted_sectors[:3]]
                if sector not in top_sectors:
                    continue

            # ADX检查
            adx = latest.get('adx', 0)
            if not pd.isna(adx) and adx < STRATEGY_CONFIG['adx_threshold']:
                continue

            # 评分（传入历史数据用于动量计算）
            score = self.strategy.calc_signal_score(latest, df.to_dict('records'))
            if score < 70:
                continue

            # 不对称波动率仓位
            base_pct = STRATEGY_CONFIG['position_pct_high'] if score >= 90 else STRATEGY_CONFIG['position_pct_low']
            try:
                cur_vol = latest.get('volatility', 0)
                if not pd.isna(cur_vol) and cur_vol > 0:
                    vol_ratio = STRATEGY_CONFIG['target_volatility'] / cur_vol
                    trend_up = latest.get('ma5', 0) > latest.get('ma20', 0)
                    if trend_up:
                        ratio = max(0.8, min(1.2, vol_ratio))
                    else:
                        ratio = max(0.4, min(1.0, vol_ratio))
                    pct = base_pct * ratio
                else:
                    pct = base_pct
            except:
                pct = base_pct

            max_amount = total_assets * pct
            quantity = int(max_amount / current_price / 100) * 100

            if quantity <= 0 or quantity * current_price < STRATEGY_CONFIG['min_trade_amount']:
                continue
            if quantity * current_price > avail_balance * 0.95:
                quantity = int(avail_balance / current_price / 100) * 100
                if quantity <= 0:
                    continue

            # 买入
            print(f"  🟢 买入信号: {name} 评分{score} 仓位{pct:.0%}")
            result = self.client.buy(code, current_price, quantity, use_market_price=True)
            success = result.get('code') == '200'
            if success:
                self.strategy.buy_prices[code] = current_price
                self.strategy.highest_prices[code] = current_price
                self.strategy.max_profits[code] = 0
                self.last_buy_time[code] = datetime.now()  # 记录买入时间
                avail_balance -= quantity * current_price
                msg = self.notifier.format_signal('buy', code, name, current_price, quantity,
                                                   f"评分{score} 仓位{pct:.0%}",
                                                   {'ma20': latest.get('ma20', 0), 'atr': latest.get('atr', 0)})
                self.notifier.send(msg)
                print(f"  ✅ 买入成功: {name} ×{quantity}股 @¥{current_price:.2f}")
            else:
                print(f"  ❌ 买入失败: {result.get('message', '')}")

        print(f"\n✅ 扫描完成")

    def _calc_sector_momentum(self):
        """计算行业动量"""
        sector_returns = {}
        for sector in SECTORS:
            returns = []
            for stock in STOCK_POOL:
                if stock['sector'] != sector:
                    continue
                df = self.fetch_historical_data(stock['code'], days=30)
                if df is not None and len(df) >= 20:
                    cur = df.iloc[-1]['close']
                    prev = df.iloc[-20]['close']
                    if prev > 0:
                        returns.append((cur - prev) / prev)
            if returns:
                sector_returns[sector] = np.mean(returns)
        return sector_returns

    def run(self, interval=300):
        """主循环"""
        print(f"""
{'='*60}
🚀 智能量化交易系统 v14 启动
{'='*60}
策略: 不对称波动率 + 动量加权 + 市场状态识别
股票池: {len(STOCK_POOL)} 只
最大持仓: {STRATEGY_CONFIG['max_positions']} 只
扫描间隔: {interval} 秒
{'='*60}
""")

        while self.running:
            try:
                if self.is_trading_time():
                    self.run_scan()
                else:
                    now = datetime.now()
                    print(f"⏸️ 非交易时间 {now.strftime('%H:%M')}")
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n🛑 系统停止")
                break
            except Exception as e:
                print(f"❌ 异常: {e}")
                time.sleep(60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=int, default=300, help='扫描间隔(秒)')
    parser.add_argument('--once', action='store_true', help='只执行一次')
    args = parser.parse_args()

    system = TradingSystem()
    if args.once:
        system.run_scan()
    else:
        system.run(interval=args.interval)
