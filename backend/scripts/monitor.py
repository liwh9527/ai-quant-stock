#!/usr/bin/env python3
"""
股票监控主程序
检查信号并发送通知
"""
import sys
import json
import logging
from datetime import datetime

# 添加项目路径
sys.path.insert(0, "/root/projects/ai-quant-stock/backend")

from app.services.data.factory import get_data_source
from app.services.monitor import StockMonitor, format_signal_message, format_status_message
from app.services.notification import create_notification_service

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    print("=" * 60)
    print("股票监控系统")
    print("=" * 60)
    print()
    
    # 加载配置
    config_path = '/root/projects/ai-quant-stock/backend/config/monitor_config.json'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        return
    
    # 初始化服务
    data_source = get_data_source()
    monitor = StockMonitor(data_source, config)
    notifier = create_notification_service(config_path)
    
    print(f"监控股票: {len(config.get('watchlist', []))} 只")
    print(f"策略: {config.get('strategy', {}).get('name', 'MA20')}")
    print()
    
    # 检查信号
    print("正在检查信号...")
    signals = monitor.check_signals()
    
    if signals:
        print(f"发现 {len(signals)} 个信号")
        print()
        
        for signal in signals:
            # 格式化消息
            message = format_signal_message(signal)
            
            # 发送通知
            notifier.send_signal(signal, message)
            
            # 打印信号
            print(message)
            print("-" * 40)
    else:
        print("无新信号")
    
    # 获取状态
    print()
    print("正在获取监控状态...")
    status_list = monitor.get_watchlist_status()
    
    if status_list:
        status_message = format_status_message(status_list)
        print(status_message)
    
    print()
    print("=" * 60)
    print(f"检查完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    main()
