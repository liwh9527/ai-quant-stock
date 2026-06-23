#!/usr/bin/env python3
"""
智能量化交易系统 v6.0
新增：移动止盈策略
"""

import os
import sys
import json
import time
import threading
import requests
import subprocess
from datetime import datetime
from typing import List, Dict, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.multi_source import fetch_realtime_quote, RealtimeQuote


# ============================================================
# 配置
# ============================================================

MIXIANG_CONFIG = {
    "base_url": "https://mkapi2.dfcfs.com/finskillshub",
    "apikey": os.environ.get("MX_APIKEY", ""),
}

# 策略配置 - 移动止盈 + ATR止损
STRATEGY_CONFIG = {
    "ma_period": 20,
    "volume_ratio": 1.5,
    "atr_threshold": 0.02,
    "max_deviation_pct": 0.10,
    
    # 止损配置
    "stop_loss_mode": "atr",  # "fixed" 或 "atr"
    "stop_loss_pct": 0.07,    # 固定止损7%（备选）
    "atr_stop_multiplier": 2, # ATR止损倍数
    
    # 移动止盈配置
    "take_profit_mode": "trailing",
    "take_profit_pct": 0.15,
    "trailing_stop_pct": 0.05,
    
    # 仓位管理
    "max_position_pct": 0.25,
    "max_positions": 5,
    "min_trade_amount": 10000,
}

MONITOR_CONFIG = {
    "interval": 60,
    "fast_interval": 30,
    "slow_interval": 120,
    "fast_threshold": 2.0,
    "slow_threshold": 0.5,
    "alert_cooldown": 300,
    "price_history_size": 120,
}

STOCK_POOL = [
    {"code": "600584", "name": "长电科技"},  # 封装龙头
    {"code": "601138", "name": "工业富联"},  # AI服务器
    {"code": "002185", "name": "华天科技"},  # 封装
    {"code": "002049", "name": "紫光国微"},  # 芯片设计
    {"code": "600487", "name": "亨通光电"},  # 光纤光缆
    {"code": "002916", "name": "深南电路"},  # PCB
]


# ============================================================
# QQ消息推送
# ============================================================

class QQNotifier:
    def __init__(self):
        self.hermes_bin = "/usr/local/lib/hermes-agent/venv/bin/hermes"
    
    def send(self, message: str):
        try:
            queue_dir = os.path.expanduser("~/.hermes/message_queue")
            os.makedirs(queue_dir, exist_ok=True)
            msg_file = os.path.join(queue_dir, f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(msg_file, 'w', encoding='utf-8') as f:
                json.dump({"platform": "qqbot", "message": message, "timestamp": datetime.now().isoformat()}, f, ensure_ascii=False)
        except Exception as e:
            print(f"📤 消息发送异常: {e}")
    
    def format_buy_signal(self, code, name, price, quantity, reason, indicators):
        return f"""🟢 **买入信号触发**

📊 **股票信息**
• 名称：{name} ({code})
• 价格：{price:.2f}
• 数量：{quantity} 股
• 金额：{price * quantity:,.2f}

📈 **技术指标**
• MA20：{indicators.get('ma20', 0):.2f}
• ATR：{indicators.get('atr', 0):.4f}

💡 **触发原因**
{reason}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    def format_sell_signal(self, code, name, price, quantity, reason, profit_pct, max_profit=None):
        emoji = "🟢" if profit_pct > 0 else "🔴"
        msg = f"""🔴 **卖出信号触发**

📊 **股票信息**
• 名称：{name} ({code})
• 价格：{price:.2f}
• 数量：{quantity} 股
• 盈亏：{emoji} {profit_pct:.1%}"""
        
        if max_profit is not None:
            msg += f"\n• 最高盈利：{max_profit:.1%}"
        
        msg += f"""

💡 **触发原因**
{reason}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return msg
    
    def format_trade_result(self, type, code, name, price, quantity, success, msg=""):
        emoji = "✅" if success else "❌"
        action = "买入" if type == "buy" else "卖出"
        return f"""{emoji} **{action}委托{'成功' if success else '失败'}**

📊 **委托信息**
• 股票：{name} ({code})
• 价格：{price:.2f}
• 数量：{quantity} 股
• 金额：{price * quantity:,.2f}

{f'💬 {msg}' if msg else ''}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""


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
# 策略分析器 - 移动止盈版本
# ============================================================

class StrategyAnalyzer:
    """MA20策略分析器 - 支持移动止盈"""
    
    def __init__(self, config):
        self.config = config
        # 记录每只股票的最高收益
        self.max_profit_tracker = {}
        # 记录买入时的ATR值（用于ATR止损）
        self.atr_at_buy = {}
    
    def calculate_ma(self, prices, period=20):
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        return sum(prices[-period:]) / period
    
    def calculate_atr(self, prices, period=14):
        if len(prices) < 2:
            return 0
        changes = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
        if len(changes) < period:
            return sum(changes) / len(changes) if changes else 0
        return sum(changes[-period:]) / period
    
    def analyze(self, code, name, price, volume, price_history, volume_history, position=None):
        result = {"signal": False, "type": None, "reason": "", "score": 0, "indicators": {}}
        
        if len(price_history) < 5:
            result["reason"] = "历史数据不足"
            return result
        
        ma20 = self.calculate_ma(price_history, self.config["ma_period"])
        atr = self.calculate_atr(price_history, 14)
        avg_vol = sum(volume_history[-5:]) / min(5, len(volume_history))
        
        result["indicators"] = {"ma20": round(ma20, 2), "atr": round(atr, 4), "avg_volume": int(avg_vol)}
        
        if position:
            return self._check_sell(code, price, position, ma20, result)
        
        # 检查买入信号
        buy_result = self._check_buy(price, volume, ma20, atr, avg_vol, price_history, result)
        
        # 如果买入信号触发，记录ATR值
        if buy_result.get("signal") and buy_result.get("type") == "buy":
            self.atr_at_buy[code] = atr
        
        return buy_result
    
    def _check_buy(self, price, volume, ma20, atr, avg_vol, price_history, result):
        deviation = abs(price - ma20) / ma20 if ma20 > 0 else 1
        if deviation > self.config["max_deviation_pct"]:
            result["reason"] = f"偏离MA20过远: {deviation:.1%}"
            return result
        result["score"] += 30
        
        # MA20斜率检查 - 新增
        if len(price_history) >= 25:
            # 计算5日前的MA20
            ma20_5d_ago = sum(price_history[-25:-5]) / 20
            ma20_slope = (ma20 - ma20_5d_ago) / ma20_5d_ago * 100 if ma20_5d_ago > 0 else 0
            
            # 如果MA20斜率为负，跳过买入
            if ma20_slope < 0:
                result["reason"] = f"MA20下降趋势 (斜率: {ma20_slope:+.1f}%)"
                return result
            
            # MA20斜率为正，加分
            if ma20_slope > 1:
                result["score"] += 10  # 强势上升
            elif ma20_slope > 0:
                result["score"] += 5   # 温和上升
        
        if len(price_history) >= 2:
            prev_price = price_history[-2]
            if prev_price < ma20 and price >= ma20:
                result["score"] += 30
            elif price < ma20 and price > ma20 * 0.97:
                result["score"] += 15
            else:
                result["score"] += 10
        
        if avg_vol > 0 and volume > avg_vol * self.config["volume_ratio"]:
            result["score"] += 20
        elif avg_vol > 0 and volume > avg_vol:
            result["score"] += 10
        
        if atr > 0 and price > 0 and atr / price >= self.config["atr_threshold"]:
            result["score"] += 20
        elif atr > 0 and price > 0 and atr / price >= self.config["atr_threshold"] * 0.5:
            result["score"] += 10
        
        if result["score"] >= 70:
            result["signal"] = True
            result["type"] = "buy"
            result["reason"] = f"MA20买入信号 (评分: {result['score']}/100)"
        
        return result
    
    def _check_sell(self, code, price, position, ma20, result):
        """检查卖出信号 - 支持移动止盈"""
        cost_price = position.get("costPrice", 0)
        cost_price_dec = position.get("costPriceDec", 2)
        if cost_price > 0:
            cost_price = cost_price / (10 ** cost_price_dec)
        else:
            return result
        
        profit_pct = (price - cost_price) / cost_price
        
        # 更新最高收益
        if code not in self.max_profit_tracker:
            self.max_profit_tracker[code] = profit_pct
        else:
            self.max_profit_tracker[code] = max(self.max_profit_tracker[code], profit_pct)
        
        max_profit = self.max_profit_tracker[code]
        
        # 1. 止损检查
        if self.config.get("stop_loss_mode") == "atr":
            # ATR止损：需要在买入时记录止损价
            # 这里使用当前ATR计算止损价
            if hasattr(self, 'atr_at_buy') and code in self.atr_at_buy:
                atr = self.atr_at_buy[code]
                stop_loss_price = position.get('costPrice', 0) / (10 ** position.get('costPriceDec', 2)) - self.config['atr_stop_multiplier'] * atr
                if price <= stop_loss_price:
                    result["signal"] = True
                    result["type"] = "sell"
                    result["reason"] = f"ATR止损: 价格{price:.2f} <= 止损价{stop_loss_price:.2f}"
                    result["score"] = 100
                    result["profit_pct"] = profit_pct
                    result["max_profit"] = max_profit
                    if code in self.max_profit_tracker:
                        del self.max_profit_tracker[code]
                    if code in self.atr_at_buy:
                        del self.atr_at_buy[code]
                    return result
            else:
                # 如果没有ATR数据，使用固定止损
                if profit_pct <= -self.config["stop_loss_pct"]:
                    result["signal"] = True
                    result["type"] = "sell"
                    result["reason"] = f"止损: 亏损 {profit_pct:.1%}"
                    result["score"] = 100
                    result["profit_pct"] = profit_pct
                    result["max_profit"] = max_profit
                    if code in self.max_profit_tracker:
                        del self.max_profit_tracker[code]
                    return result
        else:
            # 固定止损
            if profit_pct <= -self.config["stop_loss_pct"]:
                result["signal"] = True
                result["type"] = "sell"
                result["reason"] = f"止损: 亏损 {profit_pct:.1%}"
                result["score"] = 100
                result["profit_pct"] = profit_pct
                result["max_profit"] = max_profit
                if code in self.max_profit_tracker:
                    del self.max_profit_tracker[code]
                return result
        
        # 2. 移动止盈
        if self.config["take_profit_mode"] == "trailing":
            # 当收益超过初始止盈点后，启动移动止盈
            if max_profit >= self.config["take_profit_pct"]:
                # 移动止盈线 = 最高收益 - 回撤比例
                trailing_stop = max_profit - self.config["trailing_stop_pct"]
                
                if profit_pct <= trailing_stop:
                    result["signal"] = True
                    result["type"] = "sell"
                    result["reason"] = f"移动止盈: 当前{profit_pct:.1%} <= 止盈线{trailing_stop:.1%} (最高{max_profit:.1%})"
                    result["score"] = 100
                    result["profit_pct"] = profit_pct
                    result["max_profit"] = max_profit
                    # 清理追踪器
                    if code in self.max_profit_tracker:
                        del self.max_profit_tracker[code]
                    return result
        
        # 3. 固定止盈（备选）
        elif self.config["take_profit_mode"] == "fixed":
            if profit_pct >= self.config["take_profit_pct"]:
                result["signal"] = True
                result["type"] = "sell"
                result["reason"] = f"止盈: 盈利 {profit_pct:.1%}"
                result["score"] = 100
                result["profit_pct"] = profit_pct
                result["max_profit"] = max_profit
                if code in self.max_profit_tracker:
                    del self.max_profit_tracker[code]
                return result
        
        # 4. 跌破MA20
        if price < ma20 * 0.98:
            result["signal"] = True
            result["type"] = "sell"
            result["reason"] = f"跌破MA20: {price:.2f} < {ma20:.2f}"
            result["score"] = 80
            result["profit_pct"] = profit_pct
            result["max_profit"] = max_profit
            if code in self.max_profit_tracker:
                del self.max_profit_tracker[code]
            return result
        
        return result


# ============================================================
# 交易执行器
# ============================================================

class TradeExecutor:
    def __init__(self, client, notifier, config):
        self.client = client
        self.notifier = notifier
        self.config = config
        self.trade_log = []
        self.today_signals = 0
        self.today_trades = 0
    
    def calculate_quantity(self, price, total_assets):
        max_amount = total_assets * self.config["max_position_pct"]
        quantity = int(max_amount / price / 100) * 100
        if quantity * price < self.config["min_trade_amount"]:
            return 0
        return quantity
    
    def execute_buy(self, code, name, price, reason, indicators):
        self.today_signals += 1
        
        balance = self.client.get_balance()
        if not balance:
            return False
        
        total_assets = balance.get("totalAssets", 0)
        avail_balance = balance.get("availBalance", 0)
        
        positions = self.client.get_positions()
        if len(positions) >= self.config["max_positions"]:
            return False
        
        for pos in positions:
            if pos.get("secCode") == code:
                return False
        
        quantity = self.calculate_quantity(price, total_assets)
        if quantity == 0:
            return False
        
        if quantity * price > avail_balance:
            quantity = int(avail_balance / price / 100) * 100
            if quantity == 0:
                return False
        
        msg = self.notifier.format_buy_signal(code, name, price, quantity, reason, indicators)
        self.notifier.send(msg)
        
        result = self.client.buy(code, price, quantity)
        success = result.get("code") == "200"
        
        trade_msg = self.notifier.format_trade_result("buy", code, name, price, quantity, success, result.get("message", ""))
        self.notifier.send(trade_msg)
        
        if success:
            self.today_trades += 1
            self._log_trade(code, name, "buy", price, quantity, "成功")
        else:
            self._log_trade(code, name, "buy", price, quantity, f"失败: {result.get('message')}")
        
        return success
    
    def execute_sell(self, code, name, price, quantity, reason, profit_pct, max_profit=None):
        self.today_signals += 1
        
        msg = self.notifier.format_sell_signal(code, name, price, quantity, reason, profit_pct, max_profit)
        self.notifier.send(msg)
        
        result = self.client.sell(code, price, quantity)
        success = result.get("code") == "200"
        
        trade_msg = self.notifier.format_trade_result("sell", code, name, price, quantity, success, result.get("message", ""))
        self.notifier.send(trade_msg)
        
        if success:
            self.today_trades += 1
            self._log_trade(code, name, "sell", price, quantity, f"成功 ({reason})")
        else:
            self._log_trade(code, name, "sell", price, quantity, f"失败: {result.get('message')}")
        
        return success
    
    def _log_trade(self, code, name, type, price, quantity, status):
        self.trade_log.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "code": code, "name": name, "type": type,
            "price": price, "quantity": quantity, "status": status,
        })


# ============================================================
# 主监控系统
# ============================================================

class QuantTradingSystem:
    def __init__(self):
        self.client = MixiangClient(MIXIANG_CONFIG["base_url"], MIXIANG_CONFIG["apikey"])
        self.notifier = QQNotifier()
        self.strategy = StrategyAnalyzer(STRATEGY_CONFIG)
        self.executor = TradeExecutor(self.client, self.notifier, STRATEGY_CONFIG)
        
        self.stocks = {}
        self.running = False
        self.thread = None
        
        self.log_file = os.path.join(os.path.dirname(__file__), "trade_log.json")
        self._load_trade_log()
    
    def _load_trade_log(self):
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r") as f:
                    self.executor.trade_log = json.load(f)
            except:
                self.executor.trade_log = []
    
    def _save_trade_log(self):
        try:
            with open(self.log_file, "w") as f:
                json.dump(self.executor.trade_log, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def add_stock(self, code, name):
        self.stocks[code] = {"name": name, "price_history": [], "volume_history": [], "last_alert_time": None}
        print(f"✅ 添加监控: {name} ({code})")
    
    def update_stock(self, code, positions):
        if code not in self.stocks:
            return None
        
        stock = self.stocks[code]
        quote = fetch_realtime_quote(code)
        if not quote:
            return None
        
        stock["price_history"].append(quote.price)
        stock["volume_history"].append(quote.volume)
        
        max_size = MONITOR_CONFIG["price_history_size"]
        if len(stock["price_history"]) > max_size:
            stock["price_history"] = stock["price_history"][-max_size:]
            stock["volume_history"] = stock["volume_history"][-max_size:]
        
        position = None
        for pos in positions:
            if pos.get("secCode") == code:
                position = pos
                break
        
        analysis = self.strategy.analyze(
            code=code, name=stock["name"], price=quote.price,
            volume=quote.volume, price_history=stock["price_history"],
            volume_history=stock["volume_history"], position=position,
        )
        
        return {
            "code": code, "name": stock["name"], "price": quote.price,
            "change_pct": quote.change_pct, "volume": quote.volume,
            "source": quote.source, "position": position, "analysis": analysis,
        }
    
    def check_and_trade(self):
        results = []
        positions = self.client.get_positions()
        
        for code in list(self.stocks.keys()):
            result = self.update_stock(code, positions)
            if not result:
                continue
            
            analysis = result["analysis"]
            
            if analysis["signal"]:
                stock = self.stocks[code]
                now = datetime.now()
                
                if stock["last_alert_time"]:
                    last_alert = datetime.strptime(stock["last_alert_time"], "%Y-%m-%d %H:%M:%S")
                    if (now - last_alert).total_seconds() < MONITOR_CONFIG["alert_cooldown"]:
                        continue
                
                stock["last_alert_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
                
                if analysis["type"] == "buy":
                    self.executor.execute_buy(
                        code=code, name=stock["name"],
                        price=result["price"], reason=analysis["reason"],
                        indicators=analysis.get("indicators", {}),
                    )
                elif analysis["type"] == "sell" and result["position"]:
                    pos = result["position"]
                    quantity = pos.get("availCount", pos.get("count", 0))
                    if quantity > 0:
                        self.executor.execute_sell(
                            code=code, name=stock["name"],
                            price=result["price"], quantity=quantity,
                            reason=analysis["reason"],
                            profit_pct=analysis.get("profit_pct", 0),
                            max_profit=analysis.get("max_profit"),
                        )
                
                self._save_trade_log()
            
            results.append(result)
        
        return results
    
    def display_status(self, results):
        print(f"\n{'='*70}")
        print(f"📊 监控状态 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        print(f"{'股票':<12} {'价格':>8} {'涨跌幅':>8} {'成交量':>10} {'MA20':>8} {'信号':<15}")
        print(f"{'-'*70}")
        
        for r in results:
            analysis = r["analysis"]
            indicators = analysis.get("indicators", {})
            
            signal_str = "无"
            if analysis["signal"]:
                signal_str = f"{'买入' if analysis['type'] == 'buy' else '卖出'} ({analysis['score']})"
            
            pos_mark = "📌" if r.get("position") else "  "
            print(f"{pos_mark}{r['name']:<9} {r['price']:>8.2f} {r['change_pct']:>+7.2f}% {r['volume']:>10} "
                  f"{indicators.get('ma20', 0):>8.2f} {signal_str:<15}")
        
        print(f"{'='*70}")
        
        balance = self.client.get_balance()
        if balance:
            print(f"💰 总资产: {balance.get('totalAssets', 0):,.2f} | "
                  f"可用: {balance.get('availBalance', 0):,.2f} | "
                  f"持仓: {balance.get('totalPosPct', 0):.1f}%")
        print(f"📈 今日信号: {self.executor.today_signals} | 交易: {self.executor.today_trades}")
        print(f"{'='*70}\n")
    
    def _calculate_interval(self, results):
        if not results:
            return MONITOR_CONFIG["interval"]
        max_change = max(abs(r.get("change_pct", 0)) for r in results)
        if max_change > MONITOR_CONFIG["fast_threshold"]:
            return MONITOR_CONFIG["fast_interval"]
        elif max_change < MONITOR_CONFIG["slow_threshold"]:
            return MONITOR_CONFIG["slow_interval"]
        return MONITOR_CONFIG["interval"]
    
    def start(self):
        if self.running:
            print("监控已在运行")
            return
        
        self.running = True
        
        def monitor_loop():
            print(f"\n{'='*60}")
            print(f"🚀 智能量化交易系统 v6.0 启动")
            print(f"{'='*60}")
            print(f"监控股票: {len(self.stocks)} 只")
            print(f"止盈模式: {STRATEGY_CONFIG['take_profit_mode']}")
            if STRATEGY_CONFIG['take_profit_mode'] == 'trailing':
                print(f"初始止盈: {STRATEGY_CONFIG['take_profit_pct']*100}%")
                print(f"移动回撤: {STRATEGY_CONFIG['trailing_stop_pct']*100}%")
            print(f"止损模式: {STRATEGY_CONFIG.get('stop_loss_mode', 'fixed')}")
            if STRATEGY_CONFIG.get('stop_loss_mode') == 'atr':
                print(f"ATR倍数: {STRATEGY_CONFIG['atr_stop_multiplier']}倍")
            else:
                print(f"固定止损: {STRATEGY_CONFIG['stop_loss_pct']*100}%")
            print(f"{'='*60}\n")
            
            while self.running:
                try:
                    now = datetime.now()
                    current_time = now.strftime("%H:%M")
                    
                    if current_time < "09:30" or current_time > "15:00":
                        time.sleep(60)
                        continue
                    
                    if "11:30" <= current_time <= "13:00":
                        time.sleep(60)
                        continue
                    
                    results = self.check_and_trade()
                    self.display_status(results)
                    
                    interval = self._calculate_interval(results)
                    print(f"⏰ 下次扫描: {interval}秒后\n")
                    
                    time.sleep(interval)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"❌ 监控错误: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(5)
            
            print("\n监控已停止")
        
        self.thread = threading.Thread(target=monitor_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self._save_trade_log()


# ============================================================
# 主函数
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="智能量化交易系统 v6.0")
    parser.add_argument("--stocks", nargs="+", help="监控股票")
    parser.add_argument("--once", action="store_true", help="运行一次")
    parser.add_argument("--log", action="store_true", help="查看交易日志")
    parser.add_argument("--balance", action="store_true", help="查询资金")
    parser.add_argument("--positions", action="store_true", help="查询持仓")
    
    args = parser.parse_args()
    
    system = QuantTradingSystem()
    
    if args.balance:
        balance = system.client.get_balance()
        if balance:
            print(f"\n💰 资金信息:")
            print(f"  账户名: {balance.get('accName')}")
            print(f"  总资产: {balance.get('totalAssets', 0):,.2f}")
            print(f"  可用余额: {balance.get('availBalance', 0):,.2f}")
    elif args.positions:
        positions = system.client.get_positions()
        if positions:
            print(f"\n📌 持仓信息:")
            for pos in positions:
                cost = pos.get("costPrice", 0) / (10 ** pos.get("costPriceDec", 2))
                current = pos.get("price", 0) / (10 ** pos.get("priceDec", 2))
                profit_pct = (current - cost) / cost if cost > 0 else 0
                emoji = "🟢" if profit_pct > 0 else "🔴"
                print(f"  {pos.get('secName')} ({pos.get('secCode')}): "
                      f"{pos.get('count')}股, 成本{cost:.2f}, 现价{current:.2f}, "
                      f"{emoji} {profit_pct:.1%}")
                
                # 显示移动止盈信息
                code = pos.get('secCode')
                if code in system.strategy.max_profit_tracker:
                    max_profit = system.strategy.max_profit_tracker[code]
                    trailing_stop = max_profit - STRATEGY_CONFIG['trailing_stop_pct']
                    print(f"    最高盈利: {max_profit:.1%}, 移动止盈线: {trailing_stop:.1%}")
        else:
            print("📭 当前无持仓")
    elif args.log:
        log = system.executor.trade_log
        if log:
            print("\n📋 交易日志:")
            for entry in log[-20:]:
                print(f"{entry['time']} | {entry['type']:4} | {entry['name']} ({entry['code']}) | "
                      f"{entry['price']:.2f} x {entry['quantity']} | {entry['status']}")
        else:
            print("📭 暂无交易记录")
    else:
        if args.stocks:
            for s in args.stocks:
                parts = s.split(":")
                if len(parts) == 2:
                    system.add_stock(parts[0], parts[1])
                else:
                    system.add_stock(s, s)
        else:
            for stock in STOCK_POOL:
                system.add_stock(stock["code"], stock["name"])
        
        if args.once:
            results = system.check_and_trade()
            system.display_status(results)
        else:
            try:
                system.start()
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                system.stop()
