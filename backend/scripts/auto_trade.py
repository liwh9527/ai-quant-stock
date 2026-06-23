#!/usr/bin/env python3
"""
MA20策略 + 妙想模拟交易 集成脚本
当监控到买入/卖出信号时，自动执行模拟交易
"""
import sys
import json
import subprocess
from datetime import datetime

sys.path.insert(0, "/root/projects/ai-quant-stock/backend")

from app.services.data.factory import get_data_source
from app.services.monitor import StockMonitor, get_latest_trade_date

# 配置
MX_API_URL = "https://mkapi2.dfcfs.com/finskillshub"
MX_APIKEY = "mkt_XI5GNCh5-hL4V0QmdPV7fsGlCLfhM0988LEcMuZsSWI"

# 监控股票列表（只保留主板）
WATCHLIST = [
    {"code": "002916.SZ", "name": "深南电路", "theme": "PCB"},
    {"code": "600487.SH", "name": "亨通光电", "theme": "光纤光缆"},
    {"code": "002156.SZ", "name": "通富微电", "theme": "封装测试"},
    {"code": "002837.SZ", "name": "英维克", "theme": "液冷设备"},
    {"code": "002747.SZ", "name": "埃斯顿", "theme": "人形机器人"},
    {"code": "002230.SZ", "name": "科大飞", "theme": "AI大模型"},
]


def call_mx_api(endpoint, data):
    """调用妙想API"""
    url = f"{MX_API_URL}{endpoint}"
    cmd = [
        "curl", "-s", "-X", "POST", url,
        "-H", f"apikey: {MX_APIKEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(data)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)


def get_balance():
    """查询资金"""
    return call_mx_api("/api/claw/mockTrading/balance", {"moneyUnit": 1})


def get_positions():
    """查询持仓"""
    return call_mx_api("/api/claw/mockTrading/positions", {"moneyUnit": 1})


def buy_stock(stock_code, price, quantity):
    """买入股票"""
    # 移除市场后缀
    code = stock_code.split('.')[0]
    return call_mx_api("/api/claw/mockTrading/trade", {
        "type": "buy",
        "stockCode": code,
        "price": price,
        "quantity": quantity,
        "useMarketPrice": False
    })


def sell_stock(stock_code, price, quantity):
    """卖出股票"""
    code = stock_code.split('.')[0]
    return call_mx_api("/api/claw/mockTrading/trade", {
        "type": "sell",
        "stockCode": code,
        "price": price,
        "quantity": quantity,
        "useMarketPrice": False
    })


def calculate_quantity(avail_balance, price, position_pct=0.15):
    """
    计算买入数量
    
    Args:
        avail_balance: 可用余额
        price: 股价
        position_pct: 仓位比例（默认15%）
    
    Returns:
        买入数量（100的整数倍）
    """
    target_amount = avail_balance * position_pct
    quantity = int(target_amount / price / 100) * 100
    return max(quantity, 0)


def main():
    """主函数"""
    print("=" * 60)
    print("MA20策略 + 妙想模拟交易 集成系统")
    print("=" * 60)
    print()
    
    # 获取最新交易日
    latest_trade_date = get_latest_trade_date()
    print(f"📅 最新交易日: {latest_trade_date}")
    print()
    
    # 查询账户状态
    balance_result = get_balance()
    if balance_result.get("code") != "200":
        print("❌ 查询资金失败:", balance_result.get("message"))
        return
    
    balance_data = balance_result["data"]
    avail_balance = balance_data.get("availBalance", 0)
    total_assets = balance_data.get("totalAssets", 0)
    
    print(f"💰 账户资金:")
    print(f"   总资产: {total_assets:,.2f} 元")
    print(f"   可用余额: {avail_balance:,.2f} 元")
    print()
    
    # 查询持仓
    positions_result = get_positions()
    pos_list = []
    if positions_result.get("code") == "200":
        pos_list = positions_result["data"].get("posList") or []
    
    print(f"📊 当前持仓: {len(pos_list)} 只")
    for pos in pos_list:
        print(f"   {pos['secName']}({pos['secCode']}): {pos['count']}股, 市值{pos['value']:.2f}元")
    print()
    
    # 检查信号
    print("🔍 正在检查MA20策略信号...")
    print()
    
    config = {
        "watchlist": WATCHLIST,
        "strategy": {
            "vol_threshold": 1.2,
            "deviation_threshold": 1.0,
            "stop_loss": 0.05
        }
    }
    
    data_source = get_data_source()
    monitor = StockMonitor(data_source, config)
    signals = monitor.check_signals()
    
    if not signals:
        print("📭 无新信号")
        return
    
    print(f"📬 发现 {len(signals)} 个信号:")
    print()
    
    # 处理信号
    for signal in signals:
        signal_type = signal["type"]
        name = signal["name"]
        code = signal["ts_code"]
        close = signal["close"]
        strength = signal["signal_strength"]
        
        print(f"{'🟢 买入' if signal_type == 'BUY' else '🔴 卖出'}信号: {name}({code})")
        print(f"   价格: {close:.2f} | 强度: {'⭐' * strength}")
        
        if signal_type == "BUY":
            # 检查是否已有持仓
            has_position = any(p["secCode"] == code.split('.')[0] for p in pos_list)
            if has_position:
                print(f"   ⏭️ 已有持仓，跳过")
                continue
            
            # 计算买入数量
            quantity = calculate_quantity(avail_balance, close, position_pct=0.15)
            if quantity <= 0:
                print(f"   ⚠️ 可用余额不足，跳过")
                continue
            
            # 执行买入
            print(f"   📝 准备买入: {quantity}股, 预计金额: {quantity * close:,.2f}元")
            result = buy_stock(code, close, quantity)
            
            if result.get("code") == "200":
                print(f"   ✅ 买入成功!")
                avail_balance -= quantity * close
            else:
                print(f"   ❌ 买入失败: {result.get('message')}")
        
        elif signal_type == "SELL":
            # 检查是否有持仓
            pos = next((p for p in pos_list if p["secCode"] == code.split('.')[0]), None)
            if not pos:
                print(f"   ⏭️ 无持仓，跳过")
                continue
            
            # 执行卖出
            quantity = pos["availCount"]
            print(f"   📝 准备卖出: {quantity}股, 预计金额: {quantity * close:,.2f}元")
            result = sell_stock(code, close, quantity)
            
            if result.get("code") == "200":
                print(f"   ✅ 卖出成功!")
            else:
                print(f"   ❌ 卖出失败: {result.get('message')}")
        
        print()
    
    # 显示最新状态
    print("=" * 60)
    print("📊 交易后账户状态:")
    balance_result = get_balance()
    if balance_result.get("code") == "200":
        balance_data = balance_result["data"]
        print(f"   总资产: {balance_data.get('totalAssets', 0):,.2f} 元")
        print(f"   可用余额: {balance_data.get('availBalance', 0):,.2f} 元")
        print(f"   持仓市值: {balance_data.get('totalPosValue', 0):,.2f} 元")
    print("=" * 60)


if __name__ == "__main__":
    main()
