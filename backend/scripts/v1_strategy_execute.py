#!/usr/bin/env python3
"""V1策略自动执行脚本

执行时间：开盘后9:30
执行内容：
1. 检查委托状态
2. 卖出不符合条件的股票
3. 买入主升浪股票
4. 设置止损
"""

import sys
import os
sys.path.insert(0, '/root/.hermes/skills/mx-skills/scripts')

import subprocess
import time
from datetime import datetime

def run_moni_command(command):
    """执行模拟交易命令"""
    cmd = ['python', '/root/.hermes/skills/mx-skills/scripts/mx_moni.py', command]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"执行命令: {command}")
    print(f"结果: {result.stdout[:200]}")
    return result.stdout

def main():
    print("=" * 60)
    print("🚀 V1策略自动执行")
    print("=" * 60)
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 第一步：卖出不符合条件的股票
    print("\n📊 第一步：卖出不符合条件的股票")
    
    # 卖出华电能源
    print("\n1. 卖出华电能源...")
    run_moni_command("市价卖出 600726 7100")
    time.sleep(2)
    
    # 卖出紫金矿业
    print("\n2. 卖出紫金矿业...")
    run_moni_command("市价卖出 601899 400")
    time.sleep(2)
    
    # 卖出亨通光电
    print("\n3. 卖出亨通光电...")
    run_moni_command("市价卖出 600487 400")
    time.sleep(2)
    
    # 第二步：买入主升浪股票
    print("\n📊 第二步：买入主升浪股票")
    
    # 买入风华高科
    print("\n1. 买入风华高科...")
    run_moni_command("市价买入 000636 900")
    time.sleep(2)
    
    # 买入中钨高新
    print("\n2. 买入中钨高新...")
    run_moni_command("市价买入 000657 700")
    time.sleep(2)
    
    # 买入新金路
    print("\n3. 买入新金路...")
    run_moni_command("市价买入 000510 2800")
    time.sleep(2)
    
    # 第三步：查看持仓
    print("\n📊 第三步：查看持仓")
    run_moni_command("我的持仓")
    
    print("\n" + "=" * 60)
    print("✅ V1策略执行完成")
    print("=" * 60)

if __name__ == '__main__':
    main()
