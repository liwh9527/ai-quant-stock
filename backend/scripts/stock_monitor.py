#!/usr/bin/env python3
"""
实时股票监控系统
功能：监听指定股票，检测MA20策略买卖信号，发送通知
"""

import os
import sys
import json
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.multi_source import fetch_realtime_quote, RealtimeQuote


# ============================================================
# 配置
# ============================================================

# 策略参数
STRATEGY_CONFIG = {
    "ma_period": 20,               # MA周期
    "volume_ratio": 1.5,           # 成交量放大倍数
    "atr_period": 14,              # ATR周期
    "atr_threshold": 0.02,         # ATR阈值（相对价格）
    "max_deviation_pct": 0.10,     # 最大偏离度 10%
    "stop_loss_pct": 0.05,         # 止损线 5%
    "take_profit_pct": 0.15,       # 止盈线 15%
}

# 监控配置
MONITOR_CONFIG = {
    "interval": 60,                # 刷新间隔（秒）
    "alert_cooldown": 300,         # 告警冷却时间（秒）
    "price_history_size": 120,     # 价格历史大小（2小时数据）
    "fast_interval": 30,           # 快速模式间隔（涨跌幅>2%时）
    "slow_interval": 120,          # 慢速模式间隔（涨跌幅<0.5%时）
    "fast_threshold": 2.0,         # 快速模式触发阈值（%）
    "slow_threshold": 0.5,         # 慢速模式触发阈值（%）
    "trading_hours": {             # 交易时间
        "start": "09:30",
        "end": "15:00",
        "lunch_start": "11:30",
        "lunch_end": "13:00",
    }
}


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Signal:
    """交易信号"""
    timestamp: str
    code: str
    name: str
    type: str           # "buy" / "sell"
    price: float
    reason: str
    score: int
    details: Dict[str, Any]


@dataclass
class StockState:
    """股票状态"""
    code: str
    name: str
    current_price: float = 0
    change_pct: float = 0
    volume: int = 0
    
    # 技术指标
    ma20: float = 0
    atr: float = 0
    avg_volume: float = 0
    
    # 价格历史
    price_history: List[float] = None
    volume_history: List[int] = None
    
    # 状态
    last_update: str = ""
    last_alert_time: str = ""
    position: Optional[Dict] = None  # 持仓信息
    
    def __post_init__(self):
        if self.price_history is None:
            self.price_history = []
        if self.volume_history is None:
            self.volume_history = []


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
        """计算ATR（简化版，基于价格变化）"""
        if len(prices) < 2:
            return 0
        
        changes = []
        for i in range(1, len(prices)):
            changes.append(abs(prices[i] - prices[i-1]))
        
        if len(changes) < period:
            return sum(changes) / len(changes) if changes else 0
        return sum(changes[-period:]) / period
    
    def calculate_avg_volume(self, volumes: List[int], period: int = 5) -> float:
        """计算平均成交量"""
        if not volumes:
            return 0
        if len(volumes) < period:
            return sum(volumes) / len(volumes)
        return sum(volumes[-period:]) / period
    
    def analyze(self, state: StockState) -> Dict[str, Any]:
        """分析股票状态，生成信号"""
        result = {
            "signal": False,
            "type": None,
            "reason": "",
            "score": 0,
            "indicators": {},
        }
        
        if len(state.price_history) < 5:
            result["reason"] = "历史数据不足"
            return result
        
        # 计算技术指标
        ma20 = self.calculate_ma(state.price_history, self.config["ma_period"])
        atr = self.calculate_atr(state.price_history, self.config["atr_period"])
        avg_vol = self.calculate_avg_volume(state.volume_history, 5)
        
        state.ma20 = ma20
        state.atr = atr
        state.avg_volume = avg_vol
        
        result["indicators"] = {
            "ma20": round(ma20, 2),
            "atr": round(atr, 4),
            "avg_volume": int(avg_vol),
            "price": state.current_price,
            "volume": state.volume,
        }
        
        # 如果有持仓，检查卖出信号
        if state.position:
            sell_signal = self._check_sell_signal(state, ma20)
            if sell_signal["signal"]:
                return sell_signal
        
        # 无持仓，检查买入信号
        else:
            buy_signal = self._check_buy_signal(state, ma20, atr, avg_vol)
            if buy_signal["signal"]:
                return buy_signal
        
        result["reason"] = "无信号"
        return result
    
    def _check_buy_signal(self, state: StockState, ma20: float, atr: float, avg_vol: float) -> Dict:
        """检查买入信号"""
        result = {
            "signal": False,
            "type": "buy",
            "reason": "",
            "score": 0,
        }
        
        price = state.current_price
        volume = state.volume
        
        # 1. 价格在MA20附近（偏离度<10%）
        deviation = abs(price - ma20) / ma20 if ma20 > 0 else 1
        if deviation > self.config["max_deviation_pct"]:
            result["reason"] = f"偏离MA20过远: {deviation:.1%}"
            return result
        result["score"] += 30
        
        # 2. 价格从下方接近或突破MA20
        if len(state.price_history) >= 2:
            prev_price = state.price_history[-2]
            # 从下方突破MA20
            if prev_price < ma20 and price >= ma20:
                result["score"] += 30
            # 在MA20下方但正在接近
            elif price < ma20 and price > ma20 * 0.97:
                result["score"] += 15
            else:
                result["score"] += 10
        else:
            result["score"] += 10
        
        # 3. 成交量放大
        if avg_vol > 0 and volume > avg_vol * self.config["volume_ratio"]:
            result["score"] += 20
        elif avg_vol > 0 and volume > avg_vol:
            result["score"] += 10
        
        # 4. ATR足够（有波动空间）
        if atr > 0 and price > 0:
            atr_pct = atr / price
            if atr_pct >= self.config["atr_threshold"]:
                result["score"] += 20
            elif atr_pct >= self.config["atr_threshold"] * 0.5:
                result["score"] += 10
        
        # 判断是否触发信号
        if result["score"] >= 70:
            result["signal"] = True
            result["reason"] = f"MA20买入信号 (评分: {result['score']}/100)"
        
        return result
    
    def _check_sell_signal(self, state: StockState, ma20: float) -> Dict:
        """检查卖出信号"""
        result = {
            "signal": False,
            "type": "sell",
            "reason": "",
            "score": 0,
        }
        
        price = state.current_price
        buy_price = state.position.get("buy_price", 0)
        
        if buy_price <= 0:
            return result
        
        # 计算收益率
        profit_pct = (price - buy_price) / buy_price
        
        # 1. 止损
        if profit_pct <= -self.config["stop_loss_pct"]:
            result["signal"] = True
            result["reason"] = f"止损信号: 亏损 {profit_pct:.1%}"
            result["score"] = 100
            return result
        
        # 2. 止盈
        if profit_pct >= self.config["take_profit_pct"]:
            result["signal"] = True
            result["reason"] = f"止盈信号: 盈利 {profit_pct:.1%}"
            result["score"] = 100
            return result
        
        # 3. 跌破MA20
        if price < ma20 * 0.98:
            result["signal"] = True
            result["reason"] = f"跌破MA20: 当前{price:.2f} < MA20 {ma20:.2f}"
            result["score"] = 80
            return result
        
        # 4. 连续下跌
        if len(state.price_history) >= 3:
            if state.price_history[-1] < state.price_history[-2] < state.price_history[-3]:
                if profit_pct < 0:
                    result["signal"] = True
                    result["reason"] = f"连续下跌 + 浮亏 {profit_pct:.1%}"
                    result["score"] = 70
                    return result
        
        return result


# ============================================================
# 通知器
# ============================================================

class Notifier:
    """通知发送器"""
    
    def __init__(self):
        self.notification_history = []
    
    def format_signal_message(self, signal: Signal) -> str:
        """格式化信号消息"""
        emoji = "🟢" if signal.type == "buy" else "🔴"
        
        msg = f"""
{emoji} **量化交易信号**

**股票**: {signal.name} ({signal.code})
**类型**: {'买入' if signal.type == 'buy' else '卖出'}
**价格**: {signal.price:.2f}
**时间**: {signal.timestamp}
**原因**: {signal.reason}
**评分**: {signal.score}/100

**技术指标**:
"""
        for key, value in signal.details.items():
            msg += f"• {key}: {value}\n"
        
        return msg.strip()
    
    def send_notification(self, signal: Signal, callback=None):
        """发送通知"""
        message = self.format_signal_message(signal)
        self.notification_history.append({
            "time": datetime.now().isoformat(),
            "signal": asdict(signal),
        })
        
        # 调用回调函数（可以是QQ/飞书/邮件等）
        if callback:
            callback(message)
        
        return message


# ============================================================
# 主监控器
# ============================================================

class StockMonitor:
    """股票监控器"""
    
    def __init__(self, config: dict = None):
        self.config = config or MONITOR_CONFIG
        self.strategy = StrategyAnalyzer(STRATEGY_CONFIG)
        self.notifier = Notifier()
        
        # 股票状态
        self.stocks: Dict[str, StockState] = {}
        
        # 运行状态
        self.running = False
        self.thread = None
        
        # 信号历史
        self.signals: List[Signal] = []
    
    def add_stock(self, code: str, name: str, position: Dict = None):
        """添加监控股票"""
        self.stocks[code] = StockState(
            code=code,
            name=name,
            position=position,
        )
        print(f"✅ 添加监控: {name} ({code})")
        if position:
            print(f"   持仓: {position}")
    
    def remove_stock(self, code: str):
        """移除监控股票"""
        if code in self.stocks:
            name = self.stocks[code].name
            del self.stocks[code]
            print(f"❌ 移除监控: {name} ({code})")
    
    def update_stock(self, code: str) -> Optional[Dict]:
        """更新股票数据并分析"""
        if code not in self.stocks:
            return None
        
        state = self.stocks[code]
        
        # 获取实时行情
        quote = fetch_realtime_quote(code)
        if not quote:
            return None
        
        # 更新状态
        state.current_price = quote.price
        state.change_pct = quote.change_pct
        state.volume = quote.volume
        state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 更新历史
        state.price_history.append(quote.price)
        state.volume_history.append(quote.volume)
        
        # 限制历史大小
        if len(state.price_history) > self.config["price_history_size"]:
            state.price_history = state.price_history[-self.config["price_history_size"]:]
            state.volume_history = state.volume_history[-self.config["price_history_size"]:]
        
        # 分析策略
        analysis = self.strategy.analyze(state)
        
        return {
            "code": code,
            "name": state.name,
            "price": quote.price,
            "change_pct": quote.change_pct,
            "volume": quote.volume,
            "source": quote.source,
            "analysis": analysis,
        }
    
    def check_signals(self, notification_callback=None):
        """检查所有股票的信号"""
        results = []
        
        for code in list(self.stocks.keys()):
            result = self.update_stock(code)
            if not result:
                continue
            
            analysis = result["analysis"]
            
            # 检查是否触发信号
            if analysis["signal"]:
                # 检查冷却时间
                state = self.stocks[code]
                now = datetime.now()
                
                if state.last_alert_time:
                    last_alert = datetime.strptime(state.last_alert_time, "%Y-%m-%d %H:%M:%S")
                    if (now - last_alert).total_seconds() < self.config["alert_cooldown"]:
                        continue
                
                # 创建信号
                signal = Signal(
                    timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
                    code=code,
                    name=state.name,
                    type=analysis["type"],
                    price=result["price"],
                    reason=analysis["reason"],
                    score=analysis["score"],
                    details=analysis.get("indicators", {}),
                )
                
                self.signals.append(signal)
                state.last_alert_time = now.strftime("%Y-%m-%d %H:%M:%S")
                
                # 发送通知
                msg = self.notifier.send_notification(signal, notification_callback)
                print(f"\n{'='*50}")
                print(msg)
                print(f"{'='*50}\n")
            
            results.append(result)
        
        return results
    
    def display_status(self, results: List[Dict]):
        """显示监控状态"""
        print(f"\n{'='*70}")
        print(f"监控状态 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
    
    def run_once(self, display: bool = True, callback=None) -> List[Dict]:
        """运行一次检查"""
        results = self.check_signals(callback)
        if display:
            self.display_status(results)
        return results
    
    def _calculate_adaptive_interval(self, results: List[Dict]) -> int:
        """根据市场波动计算自适应扫描间隔"""
        if not results:
            return self.config["interval"]
        
        # 找出最大涨跌幅
        max_change = max(abs(r.get("change_pct", 0)) for r in results)
        
        # 根据波动调整间隔
        if max_change > self.config["fast_threshold"]:
            interval = self.config["fast_interval"]
            print(f"⚡ 快速模式: 涨跌幅 {max_change:.1f}% > {self.config['fast_threshold']}%")
        elif max_change < self.config["slow_threshold"]:
            interval = self.config["slow_interval"]
            print(f"🐢 慢速模式: 涨跌幅 {max_change:.1f}% < {self.config['slow_threshold']}%")
        else:
            interval = self.config["interval"]
        
        return interval
    
    def start(self, callback=None):
        """启动监控（后台线程）"""
        if self.running:
            print("监控已在运行")
            return
        
        self.running = True
        
        def monitor_loop():
            print(f"🚀 启动监控 | 基础间隔: {self.config['interval']}秒")
            print(f"   快速模式: {self.config['fast_interval']}秒 (涨跌幅>{self.config['fast_threshold']}%)")
            print(f"   慢速模式: {self.config['slow_interval']}秒 (涨跌幅<{self.config['slow_threshold']}%)")
            
            while self.running:
                try:
                    # 检查是否在交易时间
                    now = datetime.now()
                    current_time = now.strftime("%H:%M")
                    
                    # 非交易时间跳过
                    if current_time < "09:30" or current_time > "15:00":
                        time.sleep(60)
                        continue
                    
                    # 午休时间
                    if "11:30" <= current_time <= "13:00":
                        print("⏸️ 午休时间，暂停扫描")
                        time.sleep(60)
                        continue
                    
                    # 执行扫描
                    results = self.run_once(display=True, callback=callback)
                    
                    # 计算自适应间隔
                    interval = self._calculate_adaptive_interval(results)
                    print(f"⏰ 下次扫描: {interval}秒后")
                    
                    time.sleep(interval)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"监控错误: {e}")
                    time.sleep(5)
            
            print("监控已停止")
        
        self.thread = threading.Thread(target=monitor_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """停止监控"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def get_signals(self, limit: int = 10) -> List[Signal]:
        """获取最近的信号"""
        return self.signals[-limit:]
    
    def get_summary(self) -> Dict:
        """获取监控摘要"""
        return {
            "monitored_stocks": len(self.stocks),
            "total_signals": len(self.signals),
            "buy_signals": sum(1 for s in self.signals if s.type == "buy"),
            "sell_signals": sum(1 for s in self.signals if s.type == "sell"),
            "stocks": {code: {
                "name": state.name,
                "price": state.current_price,
                "change_pct": state.change_pct,
                "ma20": state.ma20,
                "data_points": len(state.price_history),
            } for code, state in self.stocks.items()},
        }


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="股票监控系统")
    parser.add_argument("--stocks", nargs="+", help="监控股票列表，格式: CODE:NAME")
    parser.add_argument("--once", action="store_true", help="运行一次")
    parser.add_argument("--interval", type=int, default=60, help="监控间隔（秒）")
    
    args = parser.parse_args()
    
    # 创建监控器
    monitor = StockMonitor()
    monitor.config["interval"] = args.interval
    
    # 添加股票
    if args.stocks:
        for stock_str in args.stocks:
            parts = stock_str.split(":")
            if len(parts) == 2:
                monitor.add_stock(parts[0], parts[1])
            else:
                monitor.add_stock(stock_str, stock_str)
    else:
        # 默认股票池
        monitor.add_stock("600487", "亨通光电")
        monitor.add_stock("601208", "东材科技")
        monitor.add_stock("601138", "工业富联")
    
    print("\n" + "="*50)
    print("股票监控系统")
    print("="*50)
    print(f"监控股票: {len(monitor.stocks)} 只")
    print(f"监控间隔: {args.interval} 秒")
    print("="*50)
    
    if args.once:
        # 运行一次
        monitor.run_once()
    else:
        # 持续监控
        try:
            monitor.start()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            monitor.stop()
