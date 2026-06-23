#!/usr/bin/env python3
"""
智能量化交易系统 v5.0
功能：实时监控 + 自动交易 + QQ消息推送
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

STRATEGY_CONFIG = {
    "ma_period": 20,
    "volume_ratio": 1.5,
    "atr_threshold": 0.02,
    "max_deviation_pct": 0.10,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.15,
    "max_position_pct": 0.15,
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
    {"code": "600487", "name": "亨通光电"},
    {"code": "601208", "name": "东材科技"},
    {"code": "601138", "name": "工业富联"},
]


# ============================================================
# QQ消息推送
# ============================================================

class QQNotifier:
    """QQ消息推送器"""
    
    def __init__(self):
        self.hermes_bin = "/usr/local/lib/hermes-agent/venv/bin/hermes"
    
    def send(self, message: str):
        """发送QQ消息"""
        try:
            # 通过hermes send命令发送
            cmd = [self.hermes_bin, "send", "qqbot", message]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"📤 QQ消息已发送")
            else:
                print(f"📤 QQ消息发送失败: {result.stderr}")
        except Exception as e:
            print(f"📤 QQ消息发送异常: {e}")
    
    def format_buy_signal(self, code: str, name: str, price: float, 
                          quantity: int, reason: str, indicators: Dict) -> str:
        """格式化买入信号消息"""
        msg = f"""🟢 **买入信号触发**

📊 **股票信息**
• 名称：{name} ({code})
• 价格：{price:.2f}
• 数量：{quantity} 股
• 金额：{price * quantity:.2f}

📈 **技术指标**
• MA20：{indicators.get('ma20', 0):.2f}
• ATR：{indicators.get('atr', 0):.4f}

💡 **触发原因**
{reason}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return msg
    
    def format_sell_signal(self, code: str, name: str, price: float,
                           quantity: int, reason: str, profit_pct: float) -> str:
        """格式化卖出信号消息"""
        emoji = "🟢" if profit_pct > 0 else "🔴"
        msg = f"""🔴 **卖出信号触发**

📊 **股票信息**
• 名称：{name} ({code})
• 价格：{price:.2f}
• 数量：{quantity} 股
• 盈亏：{emoji} {profit_pct:.1%}

💡 **触发原因**
{reason}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return msg
    
    def format_trade_result(self, type: str, code: str, name: str, 
                           price: float, quantity: int, success: bool, msg: str = ""):
        """格式化交易结果消息"""
        emoji = "✅" if success else "❌"
        action = "买入" if type == "buy" else "卖出"
        
        text = f"""{emoji} **{action}委托{'成功' if success else '失败'}**

📊 **委托信息**
• 股票：{name} ({code})
• 价格：{price:.2f}
• 数量：{quantity} 股
• 金额：{price * quantity:.2f}

{f'💬 {msg}' if msg else ''}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return text
    
    def format_daily_summary(self, balance: Dict, positions: List[Dict], 
                            signals_count: int, trades_count: int):
        """格式化每日摘要"""
        pos_text = ""
        if positions:
            for pos in positions:
                cost = pos.get("costPrice", 0) / (10 ** pos.get("costPriceDec", 2))
                current = pos.get("price", 0) / (10 ** pos.get("priceDec", 2))
                profit_pct = pos.get("profitPct", 0)
                emoji = "🟢" if profit_pct > 0 else "🔴"
                pos_text += f"\n• {pos.get('secName')}: {emoji} {profit_pct:.1f}%"
        else:
            pos_text = "\n• 空仓"
        
        msg = f"""📊 **每日交易摘要**

💰 **账户信息**
• 总资产：{balance.get('totalAssets', 0):,.2f}
• 可用余额：{balance.get('availBalance', 0):,.2f}
• 持仓市值：{balance.get('totalPosValue', 0):,.2f}
• 仓位：{balance.get('totalPosPct', 0):.1f}%

📌 **持仓情况**{pos_text}

📈 **今日统计**
• 信号触发：{signals_count} 次
• 交易执行：{trades_count} 次

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return msg


# ============================================================
# 妙想API客户端
# ============================================================

class MixiangClient:
    """妙想模拟交易客户端"""
    
    def __init__(self, base_url: str, apikey: str):
        self.base_url = base_url
        self.apikey = apikey
        self.headers = {
            "Content-Type": "application/json",
            "apikey": apikey,
        }
    
    def _request(self, endpoint: str, data: dict = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.post(url, headers=self.headers, json=data or {}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"code": "-1", "message": str(e)}
    
    def get_balance(self) -> Optional[Dict]:
        result = self._request("/api/claw/mockTrading/balance", {"moneyUnit": 1})
        if result.get("code") == "200":
            return result.get("data")
        return None
    
    def get_positions(self) -> List[Dict]:
        result = self._request("/api/claw/mockTrading/positions", {"moneyUnit": 1})
        if result.get("code") == "200":
            data = result.get("data", {})
            return data.get("posList", []) or []
        return []
    
    def buy(self, code: str, price: float, quantity: int, use_market_price: bool = False) -> Dict:
        return self._request("/api/claw/mockTrading/trade", {
            "type": "buy",
            "stockCode": code,
            "price": price,
            "quantity": quantity,
            "useMarketPrice": use_market_price,
        })
    
    def sell(self, code: str, price: float, quantity: int, use_market_price: bool = False) -> Dict:
        return self._request("/api/claw/mockTrading/trade", {
            "type": "sell",
            "stockCode": code,
            "price": price,
            "quantity": quantity,
            "useMarketPrice": use_market_price,
        })


# ============================================================
# 策略分析器
# ============================================================

class StrategyAnalyzer:
    """MA20策略分析器"""
    
    def __init__(self, config: dict):
        self.config = config
    
    def calculate_ma(self, prices: List[float], period: int = 20) -> float:
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        return sum(prices[-period:]) / period
    
    def calculate_atr(self, prices: List[float], period: int = 14) -> float:
        if len(prices) < 2:
            return 0
        changes = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
        if len(changes) < period:
            return sum(changes) / len(changes) if changes else 0
        return sum(changes[-period:]) / period
    
    def analyze(self, code: str, name: str, price: float, volume: int, 
                price_history: List[float], volume_history: List[int],
                position: Optional[Dict] = None) -> Dict[str, Any]:
        result = {"signal": False, "type": None, "reason": "", "score": 0, "indicators": {}}
        
        if len(price_history) < 5:
            result["reason"] = "历史数据不足"
            return result
        
        ma20 = self.calculate_ma(price_history, self.config["ma_period"])
        atr = self.calculate_atr(price_history, 14)
        avg_vol = sum(volume_history[-5:]) / min(5, len(volume_history))
        
        result["indicators"] = {"ma20": round(ma20, 2), "atr": round(atr, 4), "avg_volume": int(avg_vol)}
        
        if position:
            return self._check_sell(price, position, ma20, result)
        return self._check_buy(price, volume, ma20, atr, avg_vol, price_history, result)
    
    def _check_buy(self, price: float, volume: int, ma20: float, atr: float,
                   avg_vol: float, price_history: List[float], result: Dict) -> Dict:
        deviation = abs(price - ma20) / ma20 if ma20 > 0 else 1
        if deviation > self.config["max_deviation_pct"]:
            result["reason"] = f"偏离MA20过远: {deviation:.1%}"
            return result
        result["score"] += 30
        
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
    
    def _check_sell(self, price: float, position: Dict, ma20: float, result: Dict) -> Dict:
        cost_price = position.get("costPrice", 0)
        cost_price_dec = position.get("costPriceDec", 2)
        if cost_price > 0:
            cost_price = cost_price / (10 ** cost_price_dec)
        else:
            return result
        
        profit_pct = (price - cost_price) / cost_price
        
        if profit_pct <= -self.config["stop_loss_pct"]:
            result["signal"] = True
            result["type"] = "sell"
            result["reason"] = f"止损: 亏损 {profit_pct:.1%}"
            result["score"] = 100
            result["profit_pct"] = profit_pct
        elif profit_pct >= self.config["take_profit_pct"]:
            result["signal"] = True
            result["type"] = "sell"
            result["reason"] = f"止盈: 盈利 {profit_pct:.1%}"
            result["score"] = 100
            result["profit_pct"] = profit_pct
        elif price < ma20 * 0.98:
            result["signal"] = True
            result["type"] = "sell"
            result["reason"] = f"跌破MA20: {price:.2f} < {ma20:.2f}"
            result["score"] = 80
            result["profit_pct"] = profit_pct
        
        return result


# ============================================================
# 交易执行器
# ============================================================

class TradeExecutor:
    """交易执行器"""
    
    def __init__(self, client: MixiangClient, notifier: QQNotifier, config: dict):
        self.client = client
        self.notifier = notifier
        self.config = config
        self.trade_log = []
        self.today_signals = 0
        self.today_trades = 0
    
    def calculate_quantity(self, price: float, total_assets: float) -> int:
        max_amount = total_assets * self.config["max_position_pct"]
        quantity = int(max_amount / price / 100) * 100
        if quantity * price < self.config["min_trade_amount"]:
            return 0
        return quantity
    
    def execute_buy(self, code: str, name: str, price: float, reason: str, indicators: Dict) -> bool:
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
        
        # 发送买入信号通知
        msg = self.notifier.format_buy_signal(code, name, price, quantity, reason, indicators)
        self.notifier.send(msg)
        
        # 执行买入
        result = self.client.buy(code, price, quantity)
        success = result.get("code") == "200"
        
        # 发送交易结果通知
        result_msg = result.get("message", "")
        trade_msg = self.notifier.format_trade_result("buy", code, name, price, quantity, success, result_msg)
        self.notifier.send(trade_msg)
        
        if success:
            self.today_trades += 1
            self._log_trade(code, name, "buy", price, quantity, "成功")
        else:
            self._log_trade(code, name, "buy", price, quantity, f"失败: {result_msg}")
        
        return success
    
    def execute_sell(self, code: str, name: str, price: float, quantity: int, 
                    reason: str, profit_pct: float) -> bool:
        self.today_signals += 1
        
        # 发送卖出信号通知
        msg = self.notifier.format_sell_signal(code, name, price, quantity, reason, profit_pct)
        self.notifier.send(msg)
        
        # 执行卖出
        result = self.client.sell(code, price, quantity)
        success = result.get("code") == "200"
        
        # 发送交易结果通知
        result_msg = result.get("message", "")
        trade_msg = self.notifier.format_trade_result("sell", code, name, price, quantity, success, result_msg)
        self.notifier.send(trade_msg)
        
        if success:
            self.today_trades += 1
            self._log_trade(code, name, "sell", price, quantity, "成功")
        else:
            self._log_trade(code, name, "sell", price, quantity, f"失败: {result_msg}")
        
        return success
    
    def _log_trade(self, code: str, name: str, type: str, price: float, quantity: int, status: str):
        self.trade_log.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "code": code, "name": name, "type": type,
            "price": price, "quantity": quantity, "status": status,
        })
    
    def reset_daily_stats(self):
        self.today_signals = 0
        self.today_trades = 0


# ============================================================
# 主监控系统
# ============================================================

class QuantTradingSystem:
    """智能量化交易系统"""
    
    def __init__(self):
        self.client = MixiangClient(MIXIANG_CONFIG["base_url"], MIXIANG_CONFIG["apikey"])
        self.notifier = QQNotifier()
        self.strategy = StrategyAnalyzer(STRATEGY_CONFIG)
        self.executor = TradeExecutor(self.client, self.notifier, STRATEGY_CONFIG)
        
        self.stocks: Dict[str, Dict] = {}
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
    
    def add_stock(self, code: str, name: str):
        self.stocks[code] = {
            "name": name,
            "price_history": [],
            "volume_history": [],
            "last_alert_time": None,
        }
        print(f"✅ 添加监控: {name} ({code})")
    
    def update_stock(self, code: str, positions: List[Dict]) -> Optional[Dict]:
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
                        )
                
                self._save_trade_log()
            
            results.append(result)
        
        return results
    
    def display_status(self, results: List[Dict]):
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
    
    def _calculate_interval(self, results: List[Dict]) -> int:
        if not results:
            return MONITOR_CONFIG["interval"]
        max_change = max(abs(r.get("change_pct", 0)) for r in results)
        if max_change > MONITOR_CONFIG["fast_threshold"]:
            return MONITOR_CONFIG["fast_interval"]
        elif max_change < MONITOR_CONFIG["slow_threshold"]:
            return MONITOR_CONFIG["slow_interval"]
        return MONITOR_CONFIG["interval"]
    
    def send_daily_summary(self):
        """发送每日摘要"""
        balance = self.client.get_balance()
        positions = self.client.get_positions()
        if balance:
            msg = self.notifier.format_daily_summary(
                balance, positions,
                self.executor.today_signals, self.executor.today_trades
            )
            self.notifier.send(msg)
    
    def start(self):
        if self.running:
            print("监控已在运行")
            return
        
        self.running = True
        last_summary_date = None
        
        def monitor_loop():
            nonlocal last_summary_date
            
            print(f"\n{'='*60}")
            print(f"🚀 智能量化交易系统 v5.0 启动")
            print(f"{'='*60}")
            print(f"监控股票: {len(self.stocks)} 只")
            print(f"基础间隔: {MONITOR_CONFIG['interval']}秒")
            print(f"QQ推送: 已启用")
            print(f"{'='*60}\n")
            
            # 启动通知
            self.notifier.send(f"🚀 量化监控系统已启动\n监控股票: {', '.join(s['name'] for s in STOCK_POOL)}")
            
            while self.running:
                try:
                    now = datetime.now()
                    current_time = now.strftime("%H:%M")
                    today = now.strftime("%Y-%m-%d")
                    
                    # 每日重置统计
                    if last_summary_date and last_summary_date != today:
                        self.send_daily_summary()
                        self.executor.reset_daily_stats()
                    last_summary_date = today
                    
                    # 非交易时间
                    if current_time < "09:30" or current_time > "15:00":
                        time.sleep(60)
                        continue
                    
                    # 午休时间
                    if "11:30" <= current_time <= "13:00":
                        time.sleep(60)
                        continue
                    
                    # 执行检查和交易
                    results = self.check_and_trade()
                    self.display_status(results)
                    
                    # 收盘前发送摘要
                    if current_time >= "14:50" and current_time <= "14:55":
                        self.send_daily_summary()
                    
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
        self.notifier.send("⏹️ 量化监控系统已停止")


# ============================================================
# 主函数
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="智能量化交易系统 v5.0")
    parser.add_argument("--stocks", nargs="+", help="监控股票")
    parser.add_argument("--once", action="store_true", help="运行一次")
    parser.add_argument("--log", action="store_true", help="查看交易日志")
    parser.add_argument("--balance", action="store_true", help="查询资金")
    parser.add_argument("--positions", action="store_true", help="查询持仓")
    parser.add_argument("--test-notify", action="store_true", help="测试QQ通知")
    
    args = parser.parse_args()
    
    system = QuantTradingSystem()
    
    if args.test_notify:
        system.notifier.send("🧪 测试消息：量化监控系统通知功能正常")
    elif args.balance:
        balance = system.client.get_balance()
        if balance:
            print(f"\n💰 资金信息:")
            print(f"  账户名: {balance.get('accName')}")
            print(f"  总资产: {balance.get('totalAssets', 0):,.2f}")
            print(f"  可用余额: {balance.get('availBalance', 0):,.2f}")
            print(f"  持仓市值: {balance.get('totalPosValue', 0):,.2f}")
            print(f"  仓位: {balance.get('totalPosPct', 0):.1f}%")
    elif args.positions:
        positions = system.client.get_positions()
        if positions:
            print(f"\n📌 持仓信息:")
            for pos in positions:
                cost = pos.get("costPrice", 0) / (10 ** pos.get("costPriceDec", 2))
                current = pos.get("price", 0) / (10 ** pos.get("priceDec", 2))
                print(f"  {pos.get('secName')} ({pos.get('secCode')}): "
                      f"{pos.get('count')}股, 成本{cost:.2f}, 现价{current:.2f}")
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
