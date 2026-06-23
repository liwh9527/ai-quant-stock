#!/usr/bin/env python3
"""
每日交易报告生成器
自动汇总当日交易、持仓、盈亏，生成格式化报告
"""

import os
import json
from datetime import datetime
from trade_logger import get_trades, get_snapshots, get_trade_summary, log_snapshot

# 妙想API获取账户信息
import requests

MIXIANG_CONFIG = {
    "base_url": "https://mkapi2.dfcfs.com/finskillshub",
    "apikey": os.environ.get("MX_APIKEY", ""),
}


def get_account_info():
    """获取账户信息"""
    headers = {"Content-Type": "application/json", "apikey": MIXIANG_CONFIG["apikey"]}
    try:
        result = requests.post(
            f"{MIXIANG_CONFIG['base_url']}/api/claw/mockTrading/balance",
            headers=headers, json={"moneyUnit": 1}, timeout=10
        ).json()
        if result.get("code") == "200":
            return result.get("data", {})
    except:
        pass
    return {}


def get_positions():
    """获取持仓"""
    headers = {"Content-Type": "application/json", "apikey": MIXIANG_CONFIG["apikey"]}
    try:
        result = requests.post(
            f"{MIXIANG_CONFIG['base_url']}/api/claw/mockTrading/positions",
            headers=headers, json={"moneyUnit": 1}, timeout=10
        ).json()
        if result.get("code") == "200":
            return result.get("data", {}).get("posList", []) or []
    except:
        pass
    return []


def parse_positions(pos_list):
    """解析持仓数据"""
    positions = []
    for p in pos_list:
        code = p.get('secCode', '')
        name = p.get('secName', '')
        count = p.get('count', 0)
        cost_price = p.get('costPrice', 0)
        cost_dec = p.get('costPriceDec', 3)
        if cost_price > 0:
            cost_price = cost_price / (10 ** cost_dec)
        price = p.get('price', 0)
        price_dec = p.get('priceDec', 2)
        if price > 0:
            price = price / (10 ** price_dec)
        value = p.get('value', 0)
        profit = p.get('profit', 0)
        profit_pct = p.get('profitPct', 0)
        day_profit = p.get('dayProfit', 0)
        
        if count > 0:
            positions.append({
                'code': code,
                'name': name,
                'count': count,
                'cost_price': cost_price,
                'current_price': price,
                'value': value,
                'profit': profit,
                'profit_pct': profit_pct,
                'day_profit': day_profit,
            })
    return positions


def generate_daily_report():
    """生成每日报告"""
    # 获取账户信息
    account = get_account_info()
    total_assets = account.get('totalAssets', 0)
    cash = account.get('availBalance', 0)
    
    # 获取持仓
    raw_positions = get_positions()
    positions = parse_positions(raw_positions)
    positions_value = sum(p['value'] for p in positions)
    
    # 获取今日交易
    today = datetime.now().strftime('%Y-%m-%d')
    trades = get_trades(days=1)
    today_trades = [t for t in trades if t['timestamp'][:10] == today]
    
    # 获取交易统计
    summary = get_trade_summary()
    
    # 获取昨日快照（计算日收益）
    snapshots = get_snapshots(days=2)
    yesterday_value = 0
    if len(snapshots) >= 2:
        yesterday_value = snapshots[-2].get('total_assets', 0)
    daily_pnl = total_assets - yesterday_value if yesterday_value > 0 else 0
    daily_pnl_pct = daily_pnl / yesterday_value * 100 if yesterday_value > 0 else 0
    
    # 保存今日快照
    log_snapshot(total_assets, cash, positions_value, daily_pnl,
                 total_assets - 180751,  # 初始资金180751
                 positions)
    
    # 生成报告
    report = []
    report.append(f"📊 **每日交易报告**")
    report.append(f"📅 {today} {datetime.now().strftime('%H:%M')}")
    report.append("")
    
    # 账户概况
    report.append("💰 **账户概况**")
    report.append(f"• 总资产: ¥{total_assets:,.0f}")
    report.append(f"• 可用余额: ¥{cash:,.0f}")
    report.append(f"• 持仓市值: ¥{positions_value:,.0f}")
    if daily_pnl != 0:
        emoji = "🟢" if daily_pnl >= 0 else "🔴"
        report.append(f"• 今日盈亏: {emoji} ¥{daily_pnl:+,.0f} ({daily_pnl_pct:+.2f}%)")
    report.append("")
    
    # 当前持仓
    if positions:
        report.append("📈 **当前持仓**")
        for p in positions:
            emoji = "🟢" if p['profit'] >= 0 else "🔴"
            report.append(f"• {p['name']}({p['code']}) {p['count']}股")
            report.append(f"  成本:{p['cost_price']:.2f} 现价:{p['current_price']:.2f} {emoji}{p['profit']:+,.0f}({p['profit_pct']:+.1f}%)")
        report.append("")
    
    # 今日交易
    if today_trades:
        report.append("📝 **今日交易**")
        for t in today_trades:
            emoji = "🟢" if t['action'] == '买入' else "🔴"
            report.append(f"• {emoji} {t['action']} {t['name']} ¥{t['price']:.2f}×{t['quantity']}股")
            if t.get('reason'):
                report.append(f"  原因: {t['reason']}")
        report.append("")
    else:
        report.append("📝 **今日无交易**")
        report.append("")
    
    # 交易统计
    if summary['total_trades'] > 0:
        report.append("📊 **交易统计**")
        report.append(f"• 总交易: {summary['total_trades']}笔")
        report.append(f"• 胜率: {summary['win_rate']:.1%}")
        report.append(f"• 盈亏比: {summary['profit_ratio']:.2f}")
        emoji = "🟢" if summary['total_pnl'] >= 0 else "🔴"
        report.append(f"• 累计盈亏: {emoji} ¥{summary['total_pnl']:+,.0f}")
        report.append("")
    
    # 风险提示
    if positions:
        max_loss = min(positions, key=lambda x: x['profit_pct'])
        if max_loss['profit_pct'] < -5:
            report.append("⚠️ **风险提示**")
            report.append(f"• {max_loss['name']} 亏损{max_loss['profit_pct']:.1f}%，关注止损")
            report.append("")
    
    return "\n".join(report)


def send_report_to_qq(report):
    """发送报告到QQ"""
    queue_dir = os.path.expanduser("~/.hermes/message_queue")
    os.makedirs(queue_dir, exist_ok=True)
    msg_file = os.path.join(queue_dir, f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(msg_file, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": "qqbot",
            "message": report,
            "timestamp": datetime.now().isoformat()
        }, f, ensure_ascii=False)
    print(f"✅ 报告已发送到QQ")


if __name__ == '__main__':
    report = generate_daily_report()
    print(report)
    
    # 发送到QQ
    send_report_to_qq(report)
