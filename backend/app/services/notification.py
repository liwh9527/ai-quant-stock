"""
通知服务
支持QQ和飞书消息通知
"""
import logging
import subprocess
import json
from typing import Dict, List

logger = logging.getLogger(__name__)


class NotificationService:
    """通知服务"""
    
    def __init__(self, config: Dict):
        """
        初始化通知服务
        
        Args:
            config: 通知配置
        """
        self.config = config
        self.enabled = config.get('enabled', True)
        self.channels = config.get('channels', ['qq'])
        self.min_strength = config.get('min_strength', 3)
        
    def send_signal(self, signal: Dict, message: str) -> bool:
        """
        发送信号通知
        
        Args:
            signal: 信号字典
            message: 格式化的消息
            
        Returns:
            是否发送成功
        """
        if not self.enabled:
            return False
        
        # 检查信号强度
        if signal.get('signal_strength', 0) < self.min_strength:
            logger.info(f"信号强度不足，跳过通知: {signal['name']}")
            return False
        
        success = False
        
        for channel in self.channels:
            try:
                if channel == 'qq':
                    self._send_qq(message)
                    success = True
                elif channel == 'feishu':
                    self._send_feishu(message)
                    success = True
            except Exception as e:
                logger.error(f"发送{channel}通知失败: {e}")
        
        return success
    
    def _send_qq(self, message: str):
        """
        发送QQ消息
        
        Args:
            message: 消息内容
        """
        # 通过hermes-agent发送QQ消息
        # 这里需要调用hermes的send_message工具
        logger.info(f"发送QQ消息: {message[:50]}...")
        
        # 使用subprocess调用hermes命令
        try:
            # 写入临时文件
            with open('/tmp/notify_message.txt', 'w', encoding='utf-8') as f:
                f.write(message)
            
            # 调用hermes发送消息（需要根据实际情况调整）
            # subprocess.run(['hermes', 'send', 'qq', '--message', message], 
            #               capture_output=True, text=True)
            
            print(f"[QQ通知] {message}")
        except Exception as e:
            logger.error(f"QQ通知失败: {e}")
    
    def _send_feishu(self, message: str):
        """
        发送飞书消息
        
        Args:
            message: 消息内容
        """
        logger.info(f"发送飞书消息: {message[:50]}...")
        
        try:
            # 使用lark-cli发送消息
            # subprocess.run(['lark-cli', 'im', 'send', '--message', message],
            #               capture_output=True, text=True)
            
            print(f"[飞书通知] {message}")
        except Exception as e:
            logger.error(f"飞书通知失败: {e}")
    
    def send_status(self, message: str) -> bool:
        """
        发送状态通知
        
        Args:
            message: 状态消息
            
        Returns:
            是否发送成功
        """
        if not self.enabled:
            return False
        
        for channel in self.channels:
            try:
                if channel == 'qq':
                    print(f"[QQ状态] {message}")
                elif channel == 'feishu':
                    print(f"[飞书状态] {message}")
            except Exception as e:
                logger.error(f"发送{channel}状态失败: {e}")
        
        return True


def create_notification_service(config_path: str = None) -> NotificationService:
    """
    创建通知服务实例
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        通知服务实例
    """
    if config_path is None:
        config_path = '/root/projects/ai-quant-stock/backend/config/monitor_config.json'
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return NotificationService(config.get('notification', {}))
    except Exception as e:
        logger.error(f"加载通知配置失败: {e}")
        return NotificationService({})
