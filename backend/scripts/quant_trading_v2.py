#!/usr/bin/env python3
"""
智能量化交易系统 v2.0
数据源：多源容错（新浪/腾讯/东方财富/Tushare）
策略：MA20趋势跟踪 + 过滤器
交易：妙想模拟API
"""

import os
import sys
import json
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入多数据源
from scripts.multi_source import fetch_realtime_quote, get_source_status, RealtimeQuote


# ============================================================
# 配置
# ============================================================

# 妙想API配置
MIxiang_CONFIG = {
    "base_url": "https://mxxysb.com",
    "account": "模拟组合0737708",
    "token": None,
    "expires_at": None,
}

# 策略参数
STRATEGY_PARAMS = {
    # MA20策略
    "ma_period": 20,
    "stop_loss_pct": 0.05,         # 止损线 5%
    "take_profit_pct": 0.15,       # 止盈线 15%
    
    # 过滤器参数
    "volume_ratio": 1.5,           # 成交量放大倍数
    "atr_period": 14,              # ATR周期
    "atr_threshold": 0.02,         # ATR阈值（相对价格）
    "max_deviation_pct": 0.10,     # 最大偏离度 10%
    
    # 仓位管理
    "max_position_pct": 0.15,      # 单只最大仓位 15%
    "max_positions": 5,            # 最大持仓数
    "min_trade_amount": 10000,     # 最小交易金额
}

# 监控股票池
STOCK_POOL = [
    {"code": "601728", "name": "中国电信"},
    {"code": "600941", "name": "中国移动"},
    {"code": "600050", "name": "中国联通"},
    {"code": "601006", "name": "大秦铁路"},
    {"code": "600025", "name": "华能水电"},
    {"code": "601398", "name": "工商银行"},
    {"code": "601939", "name": "建设银行"},
    {"code": "601288", "name": "农业银行"},
    {"code": "601166", "name": "兴业银行"},
    {"code": "600036", "name": "招商银行"},
]


# ============================================================
# 妙想API客户端
# ============================================================

class MxxysbClient:
    """妙想模拟交易客户端"""
    
    def __init__(self, base_url: str, account: str):
        self.base_url = base_url
        self.account = account
        self.token = None
        self.headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            if method == "GET":
                resp = requests.get(url, headers=self.headers, timeout=10)
            else:
                resp = requests.post(url, headers=self.headers, data=data, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"errcode": 999, "errmsg": str(e)}
    
    def get_asset(self) -> Optional[dict]:
        """查询资产"""
        result = self._request("POST", "/api/v1/trade/asset", {
            "account_index": 0,
            "account": self.account,
        })
        if result.get("errcode") == 0:
            return result.get("data")
        return None
    
    def get_position(self) -> List[dict]:
        """查询持仓"""
        result = self._request("POST", "/api/v1/trade/position", {
            "account_index": 0,
            "account": self.account,
        })
        if result.get("errcode") == 0:
            return result.get("data", [])
        return []
    
    def buy(self, code: str, price: float, volume: int) -> Optional[dict]:
        """买入"""
        result = self._request("POST", "/api/v1/trade/entrust", {
            "account_index": 0,
            "account": self.account,
            "stock_code": code,
            "price": str(price),
            "volume": str(volume),
            "entrust_type": "buy",
        })
        return result
    
    def sell(self, code: str, price: float, volume: int) -> Optional[dict]:
        """卖出"""
        result = self._request("POST", "/api/v1/trade/entrust", {
            "account_index": 0,
            "account": self.account,
            "stock_code": code,
            "price": str(price),
            "volume": str(volume),
            "entrust_type": "sell",
        })
        return result
    
    def get_today_entrust(self) -> List[dict]:
        """查询当日委托"""
        result = self._request("POST", "/api/v1/trade/today_entrust", {
            "account_index": 0,
            "account": self.account,
        })
        if result.get("errcode") == 0:
            return result.get("data", [])
        return []


# ============================================================
# MA20策略
# ============================================================

class MA20Strategy:
    """MA20趋势跟踪策略"""
    
    def __init__(self, params: dict):
        self.params = params
    
    def calculate_ma(self, prices: List[float], period: int = 20) -> float:
        """计算移动平均线"""
        if len(prices) < period:
            return prices[-1] if prices else 0
        return sum(prices[-period:]) / period
    
    def calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """计算ATR"""
        if len(highs) < period:
            return 0
        
        tr_list = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)
        
        return sum(tr_list[-period:]) / period
    
    def check_buy_signal(self, 
                         current_price: float,
                         ma20: float,
                         volume: int,
                         avg_volume: float,
                         atr: float,
                         price_history: List[float]) -> Dict[str, Any]:
        """
        检查买入信号
        
        条件：
        1. 价格在MA20附近（偏离度<10%）
        2. 成交量放大（>1.5倍）
        3. ATR足够（有波动空间）
        """
        result = {
            "signal": False,
            "reason": "",
            "score": 0,
        }
        
        # 计算偏离度
        deviation = abs(current_price - ma20) / ma20
        
        # 条件1：价格在MA20附近
        if deviation > self.params["max_deviation_pct"]:
            result["reason"] = f"偏离度过大: {deviation:.2%}"
            return result
        result["score"] += 30
        
        # 条件2：成交量放大
        if avg_volume > 0 and volume < avg_volume * self.params["volume_ratio"]:
            result["reason"] = f"成交量不足: {volume} < {avg_volume * self.params['volume_ratio']:.0f}"
            return result
        result["score"] += 30
        
        # 条件3：ATR足够
        if atr > 0 and atr / current_price < self.params["atr_threshold"]:
            result["reason"] = f"波动率不足: {atr/current_price:.4f}"
            return result
        result["score"] += 20
        
        # 条件4：价格从下方突破MA20
        if len(price_history) >= 2:
            prev_price = price_history[-2]
            if prev_price < ma20 and current_price >= ma20:
                result["score"] += 20  # 突破加分
        
        # 满足所有条件
        result["signal"] = True
        result["reason"] = f"MA20买入信号 (评分: {result['score']})"
        return result
    
    def check_sell_signal(self, 
                          current_price: float,
                          buy_price: float,
                          ma20: float) -> Dict[str, Any]:
        """
        检查卖出信号
        
        条件：
        1. 止损：价格跌破买入价的5%
        2. 止盈：价格超过买入价的15%
        3. 跌破MA20
        """
        result = {
            "signal": False,
            "reason": "",
            "type": "",  # "stop_loss" / "take_profit" / "break_ma"
        }
        
        # 计算收益率
        profit_pct = (current_price - buy_price) / buy_price
        
        # 止损
        if profit_pct <= -self.params["stop_loss_pct"]:
            result["signal"] = True
            result["reason"] = f"止损: {profit_pct:.2%}"
            result["type"] = "stop_loss"
            return result
        
        # 止盈
        if profit_pct >= self.params["take_profit_pct"]:
            result["signal"] = True
            result["reason"] = f"止盈: {profit_pct:.2%}"
            result["type"] = "take_profit"
            return result
        
        # 跌破MA20
        if current_price < ma20 * 0.98:  # 跌破MA20的2%
            result["signal"] = True
            result["reason"] = f"跌破MA20: 当前{current_price:.2f} < MA20 {ma20:.2f}"
            result["type"] = "break_ma"
            return result
        
        return result


# ============================================================
# 交易执行器
# ============================================================

class TradeExecutor:
    """交易执行器"""
    
    def __init__(self, client: MxxysbClient, params: dict):
        self.client = client
        self.params = params
    
    def calculate_position_size(self, price: float, total_asset: float) -> int:
        """计算仓位大小"""
        # 最大仓位金额
        max_amount = total_asset * self.params["max_position_pct"]
        
        # 计算股数（100的倍数）
        volume = int(max_amount / price / 100) * 100
        
        # 确保最小交易金额
        if volume * price < self.params["min_trade_amount"]:
            return 0
        
        return volume
    
    def execute_buy(self, code: str, price: float, reason: str) -> bool:
        """执行买入"""
        # 查询资产
        asset = self.client.get_asset()
        if not asset:
            print(f"  ❌ 查询资产失败")
            return False
        
        total_asset = float(asset.get("总资产", 0))
        available = float(asset.get("可用余额", 0))
        
        # 查询持仓
        positions = self.client.get_position()
        if len(positions) >= self.params["max_positions"]:
            print(f"  ❌ 持仓已满: {len(positions)}/{self.params['max_positions']}")
            return False
        
        # 检查是否已持有
        for pos in positions:
            if pos.get("证券代码") == code:
                print(f"  ❌ 已持有该股票: {code}")
                return False
        
        # 计算仓位
        volume = self.calculate_position_size(price, total_asset)
        if volume == 0:
            print(f"  ❌ 仓位不足")
            return False
        
        # 确保资金充足
        if volume * price > available:
            volume = int(available / price / 100) * 100
            if volume == 0:
                print(f"  ❌ 可用资金不足")
                return False
        
        # 执行买入
        print(f"  📝 买入: {code} @ {price:.2f} x {volume}股")
        result = self.client.buy(code, price, volume)
        
        if result and result.get("errcode") == 0:
            print(f"  ✅ 买入成功: {reason}")
            return True
        else:
            print(f"  ❌ 买入失败: {result}")
            return False
    
    def execute_sell(self, code: str, price: float, volume: int, reason: str) -> bool:
        """执行卖出"""
        print(f"  📝 卖出: {code} @ {price:.2f} x {volume}股")
        result = self.client.sell(code, price, volume)
        
        if result and result.get("errcode") == 0:
            print(f"  ✅ 卖出成功: {reason}")
            return True
        else:
            print(f"  ❌ 卖出失败: {result}")
            return False


# ============================================================
# 主系统
# ============================================================

class QuantTradingSystem:
    """智能量化交易系统"""
    
    def __init__(self):
        self.client = MxxysbClient(
            base_url=MIxiang_CONFIG["base_url"],
            account=MIxiang_CONFIG["account"]
        )
        self.strategy = MA20Strategy(STRATEGY_PARAMS)
        self.executor = TradeExecutor(self.client, STRATEGY_PARAMS)
        self.trade_log = []
    
    def run(self, dry_run: bool = False):
        """运行交易系统"""
        print("=" * 60)
        print("智能量化交易系统 v2.0")
        print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"模式: {'模拟' if dry_run else '实盘'}")
        print("=" * 60)
        
        # 1. 检查数据源状态
        print("\n[1/4] 检查数据源状态...")
        status = get_source_status()
        available_count = sum(1 for s in status.values() if s.available)
        print(f"  可用数据源: {available_count}/{len(status)}")
        
        # 2. 查询账户
        print("\n[2/4] 查询账户信息...")
        asset = self.client.get_asset()
        if asset:
            print(f"  总资产: {asset.get('总资产', 0)} 元")
            print(f"  可用余额: {asset.get('可用余额', 0)} 元")
        else:
            print("  ❌ 查询账户失败")
            return
        
        # 3. 查询持仓
        print("\n[3/4] 查询持仓...")
        positions = self.client.get_position()
        print(f"  当前持仓: {len(positions)} 只")
        for pos in positions:
            print(f"    - {pos.get('股票名称', '')} ({pos.get('证券代码', '')}): "
                  f"{pos.get('股票余额', 0)}股, 市值 {pos.get('市值', 0):.2f}元")
        
        # 4. 扫描股票池
        print("\n[4/4] 扫描股票池...")
        print("-" * 60)
        
        for stock in STOCK_POOL:
            code = stock["code"]
            name = stock["name"]
            print(f"\n检查: {name} ({code})")
            
            # 获取实时行情
            quote = fetch_realtime_quote(code)
            if not quote:
                print(f"  ❌ 获取行情失败")
                continue
            
            print(f"  当前价: {quote.price:.2f} ({quote.change_pct:+.2f}%)")
            print(f"  成交量: {quote.volume} 手")
            
            # TODO: 获取历史数据计算MA20和ATR
            # 这里暂时使用简单逻辑
            
            # 检查是否持有
            held = False
            for pos in positions:
                if pos.get("证券代码") == code:
                    held = True
                    # 检查卖出信号
                    # sell_signal = self.strategy.check_sell_signal(...)
                    break
            
            if not held:
                # 检查买入信号（简化版）
                # 实际应该计算MA20和ATR
                if quote.change_pct > 0 and quote.change_pct < 5:
                    print(f"  📈 可能的买入机会 (涨幅适中)")
                    if not dry_run:
                        # self.executor.execute_buy(code, quote.price, "MA20买入信号")
                        pass
        
        print("\n" + "=" * 60)
        print("扫描完成")
        print("=" * 60)
    
    def check_single_stock(self, code: str):
        """检查单只股票"""
        quote = fetch_realtime_quote(code)
        if quote:
            print(f"{quote.name} ({code})")
            print(f"  价格: {quote.price:.2f}")
            print(f"  涨跌: {quote.change_pct:+.2f}%")
            print(f"  成交量: {quote.volume} 手")
            print(f"  来源: {quote.source}")
        else:
            print(f"获取 {code} 行情失败")


# ============================================================
# 主函数
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="智能量化交易系统")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不执行交易")
    parser.add_argument("--check", type=str, help="检查单只股票")
    parser.add_argument("--status", action="store_true", help="显示数据源状态")
    
    args = parser.parse_args()
    
    system = QuantTradingSystem()
    
    if args.status:
        print("\n数据源状态:")
        for name, status in get_source_status().items():
            available = "✅" if status.available else "❌"
            print(f"  {available} {name}: 成功{status.success_count}次, 失败{status.failure_count}次")
    elif args.check:
        system.check_single_stock(args.check)
    else:
        system.run(dry_run=args.dry_run)
