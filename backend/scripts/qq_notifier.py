#!/usr/bin/env python3
"""
QQ消息推送工具
通过hermes gateway发送QQ消息
"""

import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime


def send_qq_message(message: str) -> bool:
    """发送QQ消息"""
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(message)
        tmp_file = f.name
    
    try:
        # 使用hermes的send_message工具
        # 通过写入一个消息队列文件，让hermes gateway处理
        queue_dir = os.path.expanduser("~/.hermes/message_queue")
        os.makedirs(queue_dir, exist_ok=True)
        
        # 创建消息文件
        msg_file = os.path.join(queue_dir, f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(msg_file, 'w', encoding='utf-8') as f:
            json.dump({
                "platform": "qqbot",
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }, f, ensure_ascii=False)
        
        print(f"📤 消息已加入队列: {msg_file}")
        return True
    except Exception as e:
        print(f"❌ 消息发送失败: {e}")
        return False
    finally:
        # 清理临时文件
        if os.path.exists(tmp_file):
            os.unlink(tmp_file)


def format_buy_signal(code: str, name: str, price: float, 
                      quantity: int, reason: str, indicators: dict) -> str:
    """格式化买入信号消息"""
    msg = f"""🟢 **买入信号触发**

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
    return msg


def format_sell_signal(code: str, name: str, price: float,
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


def format_trade_result(type: str, code: str, name: str, 
                       price: float, quantity: int, success: bool, msg: str = ""):
    """格式化交易结果消息"""
    emoji = "✅" if success else "❌"
    action = "买入" if type == "buy" else "卖出"
    
    text = f"""{emoji} **{action}委托{'成功' if success else '失败'}**

📊 **委托信息**
• 股票：{name} ({code})
• 价格：{price:.2f}
• 数量：{quantity} 股
• 金额：{price * quantity:,.2f}

{f'💬 {msg}' if msg else ''}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    return text


def format_daily_summary(balance: dict, positions: list, 
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


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="QQ消息推送工具")
    parser.add_argument("--test", action="store_true", help="测试消息")
    parser.add_argument("--message", type=str, help="发送消息")
    
    args = parser.parse_args()
    
    if args.test:
        send_qq_message("🧪 测试消息：量化监控系统通知功能正常")
    elif args.message:
        send_qq_message(args.message)
    else:
        print("用法: python qq_notifier.py --test 或 --message '消息内容'")
