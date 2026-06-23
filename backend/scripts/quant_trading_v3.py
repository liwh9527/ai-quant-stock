#!/usr/bin/env python3
"""
智能量化交易系统 v3.0
功能：实时监控 + 自动交易（妙想模拟账户）
"""

import os
import sys
import json
import time
import threading
import requests
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.multi_source import fetch_realtime_quote, RealtimeQuote


# ============================================================
# 配置
# ============================================================

# 妙想API配置
MIXIANG_CONFIG = {
    "base_url": "https://mxxysb.com",
    "account": "模拟组合0737708",
    "account_index": 0,
}

# 策略参数
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

# 监控配置
MONITOR_CONFIG = {
    "interval": 60,
    "fast_interval": 30,
    "slow_interval": 120,
    "fast_threshold": 2.0,
    "slow_threshold": 0.5,
    "alert_cooldown": 300,
    "price_history_size": 120,
}

# 监控股票池
STOCK_POOL = [
    {"code": "600487", "name": "亨通光电"},
    {"code": "601208", "name": "东材科技"},
    {"code": "601138", "name": "工业富联"},
]


# ============================================================
# 妙想API客户端
# ============================================================

class MixiangClient:
    """妙想模拟交易客户端"""
    
    def __init__(self, base_url: str, account: str, account_index: int = 0):
        self.base_url = base_url
        self.account = account
        self.account_index = account_index
        self.token = None
        self.headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """发送请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            if method == "GET":
                resp = requests.get(url, headers=self.headers, timeout=10)
            else:
                resp = requests.post(url, headers=self.headers, data=data, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            return {"errcode": -1, "errmsg": "无法连接到妙想服务器（可能需要特殊网络）"}
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}
    
    def get_asset(self) -> Optional[Dict]:
        """查询资产"""
        result = self._request("POST", "/api/v1/trade/asset", {
            "account_index": self.account_index,
            "account": self.account,
        })
        if result.get("errcode") == 0:
            return result.get("data")
        print(f"❌ 查询资产失败: {result.get('errmsg')}")
        return None
    
    def get_position(self) -> List[Dict]:
        """查询持仓"""
        result = self._request("POST", "/api/v1/trade/position", {
            "account_index": self.account_index,
            "account": self.account,
        })
        if result.get("errcode") == 0:
            return result.get("data", [])
        print(f"❌ 查询持仓失败: {result.get('errmsg')}")
        return []
    
    def buy(self, code: str, price: float, volume: int) -> Dict:
        """买入委托"""
        result = self._request("POST", "/api/v1/trade/entrust", {
            "account_index": self.account_index,
            "account": self.account,
            "stock_code": code,
            "price": str(price),
            "volume": str(volume),
            "entrust_type": "buy",
        })
        return result
    
    def sell(self, code: str, price: float, volume: int) -> Dict:
        """卖出委托"""
        result = self._request("POST", "/api/v1/trade/entrust", {
            "account_index": self.account_index,
            "account": self.account,
            "stock_code": code,
            "price": str(price),
            "volume": str(volume),
            "entrust_type": "sell",
        })
        return result
    
    def get_today_entrust(self) -> List[Dict]:
        """查询当日委托"""
        result = self._request("POST", "/api/v1/trade/today_entrust", {
            "account_index": self.account_index,
            "account": self.account,
        })
        if result.get("errcode") == 0:
            return result.get("data", [])
        return []


# ============================================================
# 策略分析器
# ============================================================

class StrategyAnalyzer:
    """MA20策略分析器"""
    
    def __init__(self, config: dict):
        self.config = config
    
    def calculate_ma(self, prices: List[float], period: int = 20) -> float:
        """计算移动平均线"""
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        return sum(prices[-period:]) / period
    
    def calculate_atr(self, prices: List[float], period: int = 14) -> float:
        """计算ATR"""
        if len(prices) < 2:
            return 0
        changes = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
        if len(changes) < period:
            return sum(changes) / len(changes) if changes else 0
        return sum(changes[-period:]) / period
    
    def analyze(self, code: str, name: str, price: float, volume: int, 
                price_history: List[float], volume_history: List[int],
                position: Optional[Dict] = None) -> Dict[str, Any]:
        """分析股票状态"""
        result = {
            "signal": False,
            "type": None,
            "reason": "",
            "score": 0,
            "indicators": {},
        }
        
        if len(price_history) < 5:
            result["reason"] = "历史数据不足"
            return result
        
        # 计算指标
        ma20 = self.calculate_ma(price_history, self.config["ma_period"])
        atr = self.calculate_atr(price_history, 14)
        avg_vol = sum(volume_history[-5:]) / min(5, len(volume_history))
        
        result["indicators"] = {
            "ma20": round(ma20, 2),
            "atr": round(atr, 4),
            "avg_volume": int(avg_vol),
        }
        
        # 有持仓检查卖出
        if position:
            return self._check_sell(price, position, ma20, result)
        
        # 无持仓检查买入
        return self._check_buy(price, volume, ma20, atr, avg_vol, price_history, result)
    
    def _check_buy(self, price: float, volume: int, ma20: float, atr: float,
                   avg_vol: float, price_history: List[float], result: Dict) -> Dict:
        """检查买入信号"""
        # 1. 偏离度检查
        deviation = abs(price - ma20) / ma20 if ma20 > 0 else 1
        if deviation > self.config["max_deviation_pct"]:
            result["reason"] = f"偏离MA20过远: {deviation:.1%}"
            return result
        result["score"] += 30
        
        # 2. 突破检查
        if len(price_history) >= 2:
            prev_price = price_history[-2]
            if prev_price < ma20 and price >= ma20:
                result["score"] += 30  # 突破
            elif price < ma20 and price > ma20 * 0.97:
                result["score"] += 15  # 接近
            else:
                result["score"] += 10
        
        # 3. 成交量检查
        if avg_vol > 0 and volume > avg_vol * self.config["volume_ratio"]:
            result["score"] += 20
        elif avg_vol > 0 and volume > avg_vol:
            result["score"] += 10
        
        # 4. ATR检查
        if atr > 0 and price > 0 and atr / price >= self.config["atr_threshold"]:
            result["score"] += 20
        elif atr > 0 and price > 0 and atr / price >= self.config["atr_threshold"] * 0.5:
            result["score"] += 10
        
        # 触发信号
        if result["score"] >= 70:
            result["signal"] = True
            result["type"] = "buy"
            result["reason"] = f"MA20买入信号 (评分: {result['score']}/100)"
        
        return result
    
    def _check_sell(self, price: float, position: Dict, ma20: float, result: Dict) -> Dict:
        """检查卖出信号"""
        buy_price = position.get("buy_price", 0)
        if buy_price <= 0:
            return result
        
        profit_pct = (price - buy_price) / buy_price
        
        # 止损
        if profit_pct <= -self.config["stop_loss_pct"]:
            result["signal"] = True
            result["type"] = "sell"
            result["reason"] = f"止损: 亏损 {profit_pct:.1%}"
            result["score"] = 100
            return result
        
        # 止盈
        if profit_pct >= self.config["take_profit_pct"]:
            result["signal"] = True
            result["type"] = "sell"
            result["reason"] = f"止盈: 盈利 {profit_pct:.1%}"
            result["score"] = 100
            return result
        
        # 跌破MA20
        if price < ma20 * 0.98:
            result["signal"] = True
            result["type"] = "sell"
            result["reason"] = f"跌破MA20: {price:.2f} < {ma20:.2f}"
            result["score"] = 80
            return result
        
        return result


# ============================================================
# 交易执行器
# ============================================================

class TradeExecutor:
    """交易执行器"""
    
    def __init__(self, client: MixiangClient, config: dict):
        self.client = client
        self.config = config
        self.trade_log = []
    
    def calculate_volume(self, price: float, total_asset: float) -> int:
        """计算交易数量"""
        max_amount = total_asset * self.config["max_position_pct"]
        volume = int(max_amount / price / 100) * 100
        if volume * price < self.config["min_trade_amount"]:
            return 0
        return volume
    
    def execute_buy(self, code: str, name: str, price: float, reason: str) -> bool:
        """执行买入"""
        print(f"\n{'='*50}")
        print(f"🟢 买入信号触发")
        print(f"{'='*50}")
        print(f"股票: {name} ({code})")
        print(f"价格: {price:.2f}")
        print(f"原因: {reason}")
        
        # 查询资产
        asset = self.client.get_asset()
        if not asset:
            print("❌ 无法查询资产，跳过交易")
            self._log_trade(code, name, "buy", price, 0, "失败: 无法查询资产")
            return False
        
        total_asset = float(asset.get("总资产", 0))
        available = float(asset.get("可用余额", 0))
        print(f"总资产: {total_asset:.2f}")
        print(f"可用余额: {available:.2f}")
        
        # 查询持仓
        positions = self.client.get_position()
        if len(positions) >= self.config["max_positions"]:
            print(f"❌ 持仓已满 ({len(positions)}/{self.config['max_positions']})")
            self._log_trade(code, name, "buy", price, 0, "失败: 持仓已满")
            return False
        
        # 检查重复持仓
        for pos in positions:
            if pos.get("证券代码") == code:
                print(f"❌ 已持有该股票")
                self._log_trade(code, name, "buy", price, 0, "失败: 已持有")
                return False
        
        # 计算数量
        volume = self.calculate_volume(price, total_asset)
        if volume == 0:
            print("❌ 仓位不足或金额太小")
            self._log_trade(code, name, "buy", price, 0, "失败: 仓位不足")
            return False
        
        # 检查资金
        if volume * price > available:
            volume = int(available / price / 100) * 100
            if volume == 0:
                print("❌ 可用资金不足")
                self._log_trade(code, name, "buy", price, 0, "失败: 资金不足")
                return False
        
        print(f"委托数量: {volume} 股")
        print(f"委托金额: {volume * price:.2f}")
        
        # 执行买入
        result = self.client.buy(code, price, volume)
        if result.get("errcode") == 0:
            print("✅ 买入委托成功!")
            self._log_trade(code, name, "buy", price, volume, "成功")
            return True
        else:
            print(f"❌ 买入委托失败: {result.get('errmsg')}")
            self._log_trade(code, name, "buy", price, volume, f"失败: {result.get('errmsg')}")
            return False
    
    def execute_sell(self, code: str, name: str, price: float, volume: int, reason: str) -> bool:
        """执行卖出"""
        print(f"\n{'='*50}")
        print(f"🔴 卖出信号触发")
        print(f"{'='*50}")
        print(f"股票: {name} ({code})")
        print(f"价格: {price:.2f}")
        print(f"数量: {volume} 股")
        print(f"原因: {reason}")
        
        # 执行卖出
        result = self.client.sell(code, price, volume)
        if result.get("errcode") == 0:
            print("✅ 卖出委托成功!")
            self._log_trade(code, name, "sell", price, volume, "成功")
            return True
        else:
            print(f"❌ 卖出委托失败: {result.get('errmsg')}")
            self._log_trade(code, name, "sell", price, volume, f"失败: {result.get('errmsg')}")
            return False
    
    def _log_trade(self, code: str, name: str, type: str, price: float, volume: int, status: str):
        """记录交易日志"""
        self.trade_log.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "name": name,
            "type": type,
            "price": price,
            "volume": volume,
            "status": status,
        })


# ============================================================
# 主监控系统
# ============================================================

class QuantTradingSystem:
    """智能量化交易系统"""
    
    def __init__(self):
        # 初始化组件
        self.client = MixiangClient(
            base_url=MIXIANG_CONFIG["base_url"],
            account=MIXIANG_CONFIG["account"],
            account_index=MIXIANG_CONFIG["account_index"],
        )
        self.strategy = StrategyAnalyzer(STRATEGY_CONFIG)
        self.executor = TradeExecutor(self.client, STRATEGY_CONFIG)
        
        # 股票状态
        self.stocks: Dict[str, Dict] = {}
        
        # 运行状态
        self.running = False
        self.thread = None
        self.signals = []
        
        # 交易日志文件
        self.log_file = os.path.join(os.path.dirname(__file__), "trade_log.json")
        self._load_trade_log()
    
    def _load_trade_log(self):
        """加载交易日志"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r") as f:
                    self.executor.trade_log = json.load(f)
            except:
                self.executor.trade_log = []
    
    def _save_trade_log(self):
        """保存交易日志"""
        try:
            with open(self.log_file, "w") as f:
                json.dump(self.executor.trade_log, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存日志失败: {e}")
    
    def add_stock(self, code: str, name: str, position: Dict = None):
        """添加监控股票"""
        self.stocks[code] = {
            "name": name,
            "price_history": [],
            "volume_history": [],
            "position": position,
            "last_alert_time": None,
        }
        print(f"✅ 添加监控: {name} ({code})")
    
    def update_stock(self, code: str) -> Optional[Dict]:
        """更新股票数据"""
        if code not in self.stocks:
            return None
        
        stock = self.stocks[code]
        
        # 获取实时行情
        quote = fetch_realtime_quote(code)
        if not quote:
            return None
        
        # 更新历史
        stock["price_history"].append(quote.price)
        stock["volume_history"].append(quote.volume)
        
        # 限制历史大小
        max_size = MONITOR_CONFIG["price_history_size"]
        if len(stock["price_history"]) > max_size:
            stock["price_history"] = stock["price_history"][-max_size:]
            stock["volume_history"] = stock["volume_history"][-max_size:]
        
        # 分析策略
        analysis = self.strategy.analyze(
            code=code,
            name=stock["name"],
            price=quote.price,
            volume=quote.volume,
            price_history=stock["price_history"],
            volume_history=stock["volume_history"],
            position=stock.get("position"),
        )
        
        return {
            "code": code,
            "name": stock["name"],
            "price": quote.price,
            "change_pct": quote.change_pct,
            "volume": quote.volume,
            "source": quote.source,
            "analysis": analysis,
        }
    
    def check_and_trade(self):
        """检查信号并执行交易"""
        results = []
        
        for code in list(self.stocks.keys()):
            result = self.update_stock(code)
            if not result:
                continue
            
            analysis = result["analysis"]
            
            # 触发信号
            if analysis["signal"]:
                stock = self.stocks[code]
                now = datetime.now()
                
                # 检查冷却时间
                if stock["last_alert_time"]:
                    last_alert = datetime.strptime(stock["last_alert_time"], "%Y-%m-%d %H:%M:%S")
                    if (now - last_alert).total_seconds() < MONITOR_CONFIG["alert_cooldown"]:
                        continue
                
                stock["last_alert_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
                
                # 执行交易
                if analysis["type"] == "buy":
                    self.executor.execute_buy(
                        code=code,
                        name=stock["name"],
                        price=result["price"],
                        reason=analysis["reason"],
                    )
                elif analysis["type"] == "sell":
                    position = stock.get("position", {})
                    volume = position.get("volume", 0)
                    if volume > 0:
                        self.executor.execute_sell(
                            code=code,
                            name=stock["name"],
                            price=result["price"],
                            volume=volume,
                            reason=analysis["reason"],
                        )
                
                # 保存日志
                self._save_trade_log()
            
            results.append(result)
        
        return results
    
    def display_status(self, results: List[Dict]):
        """显示监控状态"""
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
            
            print(f"{r['name']:<10} {r['price']:>8.2f} {r['change_pct']:>+7.2f}% {r['volume']:>10} "
                  f"{indicators.get('ma20', 0):>8.2f} {signal_str:<15}")
        
        print(f"{'='*70}")
    
    def _calculate_interval(self, results: List[Dict]) -> int:
        """计算自适应间隔"""
        if not results:
            return MONITOR_CONFIG["interval"]
        
        max_change = max(abs(r.get("change_pct", 0)) for r in results)
        
        if max_change > MONITOR_CONFIG["fast_threshold"]:
            interval = MONITOR_CONFIG["fast_interval"]
            print(f"⚡ 快速模式: {interval}秒")
        elif max_change < MONITOR_CONFIG["slow_threshold"]:
            interval = MONITOR_CONFIG["slow_interval"]
            print(f"🐢 慢速模式: {interval}秒")
        else:
            interval = MONITOR_CONFIG["interval"]
        
        return interval
    
    def start(self):
        """启动监控"""
        if self.running:
            print("监控已在运行")
            return
        
        self.running = True
        
        def monitor_loop():
            print(f"\n{'='*60}")
            print(f"🚀 智能量化交易系统 v3.0 启动")
            print(f"{'='*60}")
            print(f"监控股票: {len(self.stocks)} 只")
            print(f"基础间隔: {MONITOR_CONFIG['interval']}秒")
            print(f"快速模式: {MONITOR_CONFIG['fast_interval']}秒 (涨跌幅>{MONITOR_CONFIG['fast_threshold']}%)")
            print(f"慢速模式: {MONITOR_CONFIG['slow_interval']}秒 (涨跌幅<{MONITOR_CONFIG['slow_threshold']}%)")
            print(f"{'='*60}\n")
            
            while self.running:
                try:
                    now = datetime.now()
                    current_time = now.strftime("%H:%M")
                    
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
                    
                    # 计算间隔
                    interval = self._calculate_interval(results)
                    print(f"⏰ 下次扫描: {interval}秒后\n")
                    
                    time.sleep(interval)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"❌ 监控错误: {e}")
                    time.sleep(5)
            
            print("\n监控已停止")
        
        self.thread = threading.Thread(target=monitor_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """停止监控"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self._save_trade_log()
    
    def get_trade_log(self) -> List[Dict]:
        """获取交易日志"""
        return self.executor.trade_log


# ============================================================
# 主函数
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="智能量化交易系统")
    parser.add_argument("--stocks", nargs="+", help="监控股票，格式: CODE:NAME")
    parser.add_argument("--once", action="store_true", help="运行一次")
    parser.add_argument("--log", action="store_true", help="查看交易日志")
    
    args = parser.parse_args()
    
    # 创建系统
    system = QuantTradingSystem()
    
    # 添加股票
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
    
    if args.log:
        # 显示交易日志
        log = system.get_trade_log()
        if log:
            print("\n交易日志:")
            print("-" * 60)
            for entry in log[-20:]:
                print(f"{entry['time']} | {entry['type']:4} | {entry['name']} ({entry['code']}) | "
                      f"{entry['price']:.2f} x {entry['volume']} | {entry['status']}")
        else:
            print("暂无交易记录")
    elif args.once:
        # 运行一次
        results = system.check_and_trade()
        system.display_status(results)
    else:
        # 持续监控
        try:
            system.start()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            system.stop()
