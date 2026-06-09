"""
股票监控服务
监控股票价格，当触发MA20策略信号时发送通知
"""
import logging
from datetime import date, datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class StockMonitor:
    """股票监控器"""
    
    def __init__(self, data_source, config: Dict):
        """
        初始化监控器
        
        Args:
            data_source: 数据源实例
            config: 监控配置
        """
        self.data_source = data_source
        self.config = config
        self.watchlist = config.get('watchlist', [])
        self.strategy = config.get('strategy', {})
        self.last_signals = {}  # 记录上一次信号，避免重复通知
        
    def check_signals(self) -> List[Dict]:
        """
        检查所有监控股票的信号
        
        Returns:
            触发的信号列表
        """
        signals = []
        
        for stock in self.watchlist:
            ts_code = stock['code']
            name = stock['name']
            
            try:
                signal = self._check_stock_signal(ts_code, name)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"检查 {name}({ts_code}) 信号失败: {e}")
        
        return signals
    
    def _check_stock_signal(self, ts_code: str, name: str) -> Optional[Dict]:
        """
        检查单只股票的信号
        
        Args:
            ts_code: 股票代码
            name: 股票名称
            
        Returns:
            信号字典，无信号返回None
        """
        # 获取最近30天数据
        end_date = date.today()
        start_date = end_date - pd.Timedelta(days=60)
        
        df = self.data_source.get_daily_quotes(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        
        if df.empty or len(df) < 20:
            return None
        
        # 计算指标
        df['MA20'] = df['close'].rolling(20).mean()
        df['vol_ma20'] = df['vol'].rolling(20).mean()
        df['vol_ratio'] = df['vol'] / df['vol_ma20']
        
        # ATR
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift(1))
        df['low_close'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['ATR'] = df['tr'].rolling(14).mean()
        df['ATR_ma20'] = df['ATR'].rolling(20).mean()
        
        # 偏离度
        df['deviation'] = abs(df['close'] - df['MA20']) / df['MA20'] * 100
        
        # 获取最新一行数据
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None
        
        close = latest['close']
        ma20 = latest['MA20']
        
        if pd.isna(ma20):
            return None
        
        # 判断信号
        is_above = close > ma20
        
        # 检查过滤条件
        vol_ok = not pd.isna(latest['vol_ratio']) and latest['vol_ratio'] >= self.strategy.get('vol_threshold', 1.2)
        atr_ok = not pd.isna(latest['ATR']) and not pd.isna(latest['ATR_ma20']) and latest['ATR'] >= latest['ATR_ma20']
        dev_ok = not pd.isna(latest['deviation']) and latest['deviation'] >= self.strategy.get('deviation_threshold', 1.0)
        
        # 判断信号类型
        signal_type = None
        signal_strength = 0
        
        if is_above and vol_ok and atr_ok and dev_ok:
            signal_type = 'BUY'
            signal_strength = self._calculate_signal_strength(latest, 'BUY')
        elif not is_above:
            signal_type = 'SELL'
            signal_strength = self._calculate_signal_strength(latest, 'SELL')
        
        if signal_type is None:
            return None
        
        # 检查是否与上次信号相同（避免重复通知）
        last_signal = self.last_signals.get(ts_code)
        if last_signal and last_signal['type'] == signal_type:
            return None
        
        # 更新上次信号
        self.last_signals[ts_code] = {
            'type': signal_type,
            'date': latest['trade_date'],
        }
        
        # 构建信号
        signal = {
            'ts_code': ts_code,
            'name': name,
            'type': signal_type,
            'date': latest['trade_date'].strftime('%Y-%m-%d'),
            'close': close,
            'ma20': round(ma20, 2),
            'deviation': round(latest['deviation'], 2) if not pd.isna(latest['deviation']) else 0,
            'vol_ratio': round(latest['vol_ratio'], 2) if not pd.isna(latest['vol_ratio']) else 0,
            'signal_strength': signal_strength,
            'filters': {
                'volume': vol_ok,
                'atr': atr_ok,
                'deviation': dev_ok,
            }
        }
        
        return signal
    
    def _calculate_signal_strength(self, row, signal_type: str) -> int:
        """
        计算信号强度（1-5）
        
        Args:
            row: 数据行
            signal_type: 信号类型
            
        Returns:
            信号强度
        """
        strength = 3  # 基础强度
        
        if signal_type == 'BUY':
            # 偏离度越大，信号越强
            if not pd.isna(row['deviation']):
                if row['deviation'] > 3:
                    strength += 1
                elif row['deviation'] > 5:
                    strength += 2
            
            # 成交量放大越大，信号越强
            if not pd.isna(row['vol_ratio']):
                if row['vol_ratio'] > 2:
                    strength += 1
                elif row['vol_ratio'] > 3:
                    strength += 2
        
        elif signal_type == 'SELL':
            # 跌破幅度越大，信号越强
            if not pd.isna(row['deviation']):
                if row['deviation'] > 3:
                    strength += 1
                elif row['deviation'] > 5:
                    strength += 2
        
        return min(strength, 5)
    
    def get_watchlist_status(self) -> List[Dict]:
        """
        获取所有监控股票的状态
        
        Returns:
            状态列表
        """
        status_list = []
        
        for stock in self.watchlist:
            ts_code = stock['code']
            name = stock['name']
            
            try:
                df = self.data_source.get_daily_quotes(
                    ts_code=ts_code,
                    start_date=date.today() - pd.Timedelta(days=30),
                    end_date=date.today(),
                )
                
                if df.empty:
                    continue
                
                latest = df.iloc[-1]
                df['MA20'] = df['close'].rolling(20).mean()
                ma20 = df.iloc[-1]['MA20']
                
                status = {
                    'code': ts_code,
                    'name': name,
                    'close': latest['close'],
                    'ma20': round(ma20, 2) if not pd.isna(ma20) else None,
                    'above_ma20': latest['close'] > ma20 if not pd.isna(ma20) else None,
                    'deviation': round((latest['close'] - ma20) / ma20 * 100, 2) if not pd.isna(ma20) else None,
                    'last_update': latest['trade_date'].strftime('%Y-%m-%d'),
                }
                status_list.append(status)
                
            except Exception as e:
                logger.error(f"获取 {name}({ts_code}) 状态失败: {e}")
        
        return status_list


def format_signal_message(signal: Dict) -> str:
    """
    格式化信号消息
    
    Args:
        signal: 信号字典
        
    Returns:
        格式化的消息
    """
    signal_type = signal['type']
    name = signal['name']
    code = signal['ts_code']
    close = signal['close']
    ma20 = signal['ma20']
    deviation = signal['deviation']
    strength = signal['signal_strength']
    
    # 信号强度图标
    strength_icon = '⭐' * strength
    
    # 信号类型图标
    type_icon = '🟢' if signal_type == 'BUY' else '🔴'
    
    # 过滤条件状态
    filters = signal['filters']
    filter_status = []
    if filters['volume']:
        filter_status.append('✅成交量')
    if filters['atr']:
        filter_status.append('✅ATR')
    if filters['deviation']:
        filter_status.append('✅偏离度')
    
    message = f"""
{type_icon} 【{signal_type}信号】{name}({code})

📊 价格信息：
• 当前价：{close:.2f}
• MA20：{ma20}
• 偏离度：{deviation:+.2f}%

📈 信号强度：{strength_icon}

🔍 过滤条件：
{'  '.join(filter_status) if filter_status else '  无'}

⏰ 信号时间：{signal['date']}
"""
    
    return message


def format_status_message(status_list: List[Dict]) -> str:
    """
    格式化状态消息
    
    Args:
        status_list: 状态列表
        
    Returns:
        格式化的消息
    """
    message = "📊 【股票监控状态】\n\n"
    
    for status in status_list:
        name = status['name']
        code = status['code']
        close = status['close']
        ma20 = status['ma20']
        above = status['above_ma20']
        deviation = status['deviation']
        
        status_icon = '🟢' if above else '🔴'
        status_text = '站上MA20' if above else '跌破MA20'
        
        message += f"{status_icon} {name}({code})\n"
        message += f"   价格：{close:.2f} | MA20：{ma20}\n"
        message += f"   状态：{status_text} | 偏离：{deviation:+.2f}%\n\n"
    
    message += f"⏰ 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    return message
