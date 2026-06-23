"""
多数据源容错系统
支持：Tushare / 新浪财经 / 东方财富 / 腾讯财经
策略：重试 + 降级 + 自动切换
"""

import requests
import time
import json
import re
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

# ============================================================
# 配置
# ============================================================

TUSHARE_TOKEN = "29479ac41a3b85cd62b519f1d32a14e343ea99b6def6ce61a646395d"

# 数据源优先级（数字越小优先级越高）
SOURCE_PRIORITY = {
    "sina": 1,      # 新浪财经：免费、实时、稳定
    "tencent": 2,   # 腾讯财经：免费、实时
    "eastmoney": 3, # 东方财富：免费、实时
    "tushare": 4,   # Tushare：延迟15分钟，作为兜底
}

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 1  # 秒
REQUEST_TIMEOUT = 10  # 秒


class DataSource(Enum):
    """数据源枚举"""
    SINA = "sina"
    TENCENT = "tencent"
    EASTMONEY = "eastmoney"
    TUSHARE = "tushare"


@dataclass
class RealtimeQuote:
    """实时行情数据"""
    code: str           # 股票代码
    name: str           # 股票名称
    price: float        # 当前价格
    change: float       # 涨跌额
    change_pct: float   # 涨跌幅(%)
    open: float         # 今开
    high: float         # 最高
    low: float          # 最低
    pre_close: float    # 昨收
    volume: int         # 成交量(手)
    amount: float       # 成交额(万元)
    bid1_price: float   # 买一价
    bid1_vol: int       # 买一量
    ask1_price: float   # 卖一价
    ask1_vol: int       # 卖一量
    timestamp: str      # 时间戳
    source: str         # 数据来源


@dataclass
class DataSourceStatus:
    """数据源状态"""
    name: str
    available: bool
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    failure_count: int = 0
    success_count: int = 0


# ============================================================
# 数据源基类
# ============================================================

class BaseDataSource:
    """数据源基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.status = DataSourceStatus(name=name, available=True)
    
    def _update_status(self, success: bool):
        """更新数据源状态"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if success:
            self.status.available = True
            self.status.last_success = now
            self.status.success_count += 1
            self.status.failure_count = 0  # 成功后重置失败计数
        else:
            self.status.failure_count += 1
            self.status.last_failure = now
            # 连续失败3次标记为不可用
            if self.status.failure_count >= 3:
                self.status.available = False
    
    def fetch(self, code: str) -> Optional[RealtimeQuote]:
        """获取实时行情（子类实现）"""
        raise NotImplementedError


# ============================================================
# 新浪财经数据源
# ============================================================

class SinaDataSource(BaseDataSource):
    """新浪财经实时行情"""
    
    def __init__(self):
        super().__init__("sina")
    
    def _convert_code(self, code: str) -> str:
        """转换股票代码为新浪格式"""
        code = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        if code.startswith("6"):
            return f"sh{code}"
        elif code.startswith(("0", "3")):
            return f"sz{code}"
        elif code.startswith(("4", "8")):
            return f"bj{code}"
        return f"sh{code}"
    
    def fetch(self, code: str) -> Optional[RealtimeQuote]:
        """从新浪财经获取实时行情"""
        try:
            sina_code = self._convert_code(code)
            url = f"https://hq.sinajs.cn/list={sina_code}"
            
            headers = {
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.encoding = "gbk"
            
            # 解析数据：var hq_str_sh601728="名称,今开,昨收,当前价,最高,最低,买一价,卖一价,成交量,成交额,..."
            match = re.search(r'="(.+)"', response.text)
            if not match:
                self._update_status(False)
                return None
            
            fields = match.group(1).split(",")
            if len(fields) < 32:
                self._update_status(False)
                return None
            
            quote = RealtimeQuote(
                code=code,
                name=fields[0],
                price=float(fields[3]) if fields[3] else 0,
                change=float(fields[3]) - float(fields[2]) if fields[3] and fields[2] else 0,
                change_pct=((float(fields[3]) - float(fields[2])) / float(fields[2]) * 100) if fields[3] and fields[2] and float(fields[2]) > 0 else 0,
                open=float(fields[1]) if fields[1] else 0,
                high=float(fields[4]) if fields[4] else 0,
                low=float(fields[5]) if fields[5] else 0,
                pre_close=float(fields[2]) if fields[2] else 0,
                volume=int(float(fields[8]) / 100) if fields[8] else 0,  # 转换为手
                amount=float(fields[9]) / 10000 if fields[9] else 0,  # 转换为万元
                bid1_price=float(fields[11]) if fields[11] else 0,
                bid1_vol=int(float(fields[10]) / 100) if fields[10] else 0,
                ask1_price=float(fields[21]) if fields[21] else 0,
                ask1_vol=int(float(fields[20]) / 100) if fields[20] else 0,
                timestamp=f"{fields[30]} {fields[31]}",
                source="sina"
            )
            
            self._update_status(True)
            return quote
            
        except Exception as e:
            print(f"[SinaDataSource] Error: {e}")
            self._update_status(False)
            return None


# ============================================================
# 腾讯财经数据源
# ============================================================

class TencentDataSource(BaseDataSource):
    """腾讯财经实时行情"""
    
    def __init__(self):
        super().__init__("tencent")
    
    def _convert_code(self, code: str) -> str:
        """转换股票代码为腾讯格式"""
        code = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        if code.startswith("6"):
            return f"sh{code}"
        elif code.startswith(("0", "3")):
            return f"sz{code}"
        elif code.startswith(("4", "8")):
            return f"bj{code}"
        return f"sh{code}"
    
    def fetch(self, code: str) -> Optional[RealtimeQuote]:
        """从腾讯财经获取实时行情"""
        try:
            tencent_code = self._convert_code(code)
            url = f"https://qt.gtimg.cn/q={tencent_code}"
            
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.encoding = "gbk"
            
            # 解析数据：v_sh601728="1~中国电信~601728~19.35~..."
            match = re.search(r'="(.+)"', response.text)
            if not match:
                self._update_status(False)
                return None
            
            fields = match.group(1).split("~")
            if len(fields) < 45:
                self._update_status(False)
                return None
            
            quote = RealtimeQuote(
                code=code,
                name=fields[1],
                price=float(fields[3]) if fields[3] else 0,
                change=float(fields[31]) if fields[31] else 0,
                change_pct=float(fields[32]) if fields[32] else 0,
                open=float(fields[5]) if fields[5] else 0,
                high=float(fields[33]) if fields[33] else 0,
                low=float(fields[34]) if fields[34] else 0,
                pre_close=float(fields[4]) if fields[4] else 0,
                volume=int(float(fields[36]) / 100) if fields[36] else 0,
                amount=float(fields[37]) / 10000 if fields[37] else 0,
                bid1_price=float(fields[9]) if fields[9] else 0,
                bid1_vol=int(float(fields[10]) / 100) if fields[10] else 0,
                ask1_price=float(fields[19]) if fields[19] else 0,
                ask1_vol=int(float(fields[20]) / 100) if fields[20] else 0,
                timestamp=fields[30] if fields[30] else "",
                source="tencent"
            )
            
            self._update_status(True)
            return quote
            
        except Exception as e:
            print(f"[TencentDataSource] Error: {e}")
            self._update_status(False)
            return None


# ============================================================
# 东方财富数据源
# ============================================================

class EastmoneyDataSource(BaseDataSource):
    """东方财富实时行情"""
    
    def __init__(self):
        super().__init__("eastmoney")
    
    def _convert_code(self, code: str) -> str:
        """转换股票代码为东方财富格式"""
        code = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        if code.startswith("6"):
            return f"1.{code}"
        elif code.startswith(("0", "3")):
            return f"0.{code}"
        elif code.startswith(("4", "8")):
            return f"0.{code}"
        return f"1.{code}"
    
    def fetch(self, code: str) -> Optional[RealtimeQuote]:
        """从东方财富获取实时行情"""
        try:
            em_code = self._convert_code(code)
            url = f"https://push2.eastmoney.com/api/qt/stock/get"
            
            params = {
                "secid": em_code,
                "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f168,f169,f170",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b"
            }
            
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            data = response.json()
            
            if not data.get("data"):
                self._update_status(False)
                return None
            
            d = data["data"]
            
            # 价格需要除以1000（东方财富返回的是毫秒级价格）
            price = d.get("f43", 0) / 100 if d.get("f43") else 0
            pre_close = d.get("f60", 0) / 100 if d.get("f60") else 0
            
            quote = RealtimeQuote(
                code=code,
                name=d.get("f58", ""),
                price=price,
                change=d.get("f169", 0) / 100 if d.get("f169") else 0,
                change_pct=d.get("f170", 0) / 100 if d.get("f170") else 0,
                open=d.get("f46", 0) / 100 if d.get("f46") else 0,
                high=d.get("f44", 0) / 100 if d.get("f44") else 0,
                low=d.get("f45", 0) / 100 if d.get("f45") else 0,
                pre_close=pre_close,
                volume=int(d.get("f47", 0) / 100) if d.get("f47") else 0,
                amount=d.get("f48", 0) / 10000 if d.get("f48") else 0,
                bid1_price=0,
                bid1_vol=0,
                ask1_price=0,
                ask1_vol=0,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                source="eastmoney"
            )
            
            self._update_status(True)
            return quote
            
        except Exception as e:
            print(f"[EastmoneyDataSource] Error: {e}")
            self._update_status(False)
            return None


# ============================================================
# Tushare数据源（兜底）
# ============================================================

class TushareDataSource(BaseDataSource):
    """Tushare数据源（延迟15分钟，作为兜底）"""
    
    def __init__(self):
        super().__init__("tushare")
        self._init_tushare()
    
    def _init_tushare(self):
        """初始化Tushare"""
        try:
            import tushare as ts
            ts.set_token(TUSHARE_TOKEN)
            self.pro = ts.pro_api()
        except Exception as e:
            print(f"[TushareDataSource] Init error: {e}")
            self.pro = None
    
    def _convert_code(self, code: str) -> str:
        """转换股票代码为Tushare格式"""
        code = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        if code.startswith("6"):
            return f"{code}.SH"
        elif code.startswith(("0", "3")):
            return f"{code}.SZ"
        elif code.startswith(("4", "8")):
            return f"{code}.BJ"
        return f"{code}.SH"
    
    def fetch(self, code: str) -> Optional[RealtimeQuote]:
        """从Tushare获取行情（延迟15分钟）"""
        if not self.pro:
            self._update_status(False)
            return None
        
        try:
            ts_code = self._convert_code(code)
            
            # 获取最新日线数据
            df = self.pro.daily(ts_code=ts_code, limit=1)
            if df.empty:
                self._update_status(False)
                return None
            
            row = df.iloc[0]
            
            # 获取股票名称
            basic_df = self.pro.stock_basic(ts_code=ts_code, fields="ts_code,name")
            name = basic_df.iloc[0]["name"] if not basic_df.empty else ""
            
            quote = RealtimeQuote(
                code=code,
                name=name,
                price=float(row["close"]),
                change=float(row["close"]) - float(row["pre_close"]),
                change_pct=float(row["pct_chg"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                pre_close=float(row["pre_close"]),
                volume=int(row["vol"]),
                amount=float(row["amount"]),
                bid1_price=0,
                bid1_vol=0,
                ask1_price=0,
                ask1_vol=0,
                timestamp=str(row["trade_date"]),
                source="tushare"
            )
            
            self._update_status(True)
            return quote
            
        except Exception as e:
            print(f"[TushareDataSource] Error: {e}")
            self._update_status(False)
            return None


# ============================================================
# 多数据源管理器（重试 + 降级）
# ============================================================

class MultiSourceManager:
    """多数据源管理器：重试 + 降级策略"""
    
    def __init__(self):
        self.sources: Dict[str, BaseDataSource] = {
            "sina": SinaDataSource(),
            "tencent": TencentDataSource(),
            "eastmoney": EastmoneyDataSource(),
            "tushare": TushareDataSource(),
        }
        self.priority = SOURCE_PRIORITY
    
    def get_status(self) -> Dict[str, DataSourceStatus]:
        """获取所有数据源状态"""
        return {name: src.status for name, src in self.sources.items()}
    
    def reset_source(self, name: str):
        """重置数据源状态"""
        if name in self.sources:
            self.sources[name].status.available = True
            self.sources[name].status.failure_count = 0
    
    def _get_sorted_sources(self) -> List[tuple]:
        """按优先级排序，只返回可用的数据源"""
        available = []
        for name, src in self.sources.items():
            if src.status.available:
                available.append((self.priority.get(name, 99), name, src))
        
        # 按优先级排序
        available.sort(key=lambda x: x[0])
        return available
    
    def fetch_realtime(self, code: str, max_retries: int = MAX_RETRIES) -> Optional[RealtimeQuote]:
        """
        获取实时行情（带重试和降级）
        
        策略：
        1. 按优先级尝试各数据源
        2. 某数据源失败后重试（最多3次）
        3. 重试失败则降级到下一数据源
        4. 所有数据源都失败则返回None
        """
        sorted_sources = self._get_sorted_sources()
        
        for priority, source_name, source in sorted_sources:
            print(f"[MultiSource] 尝试数据源: {source_name} (优先级: {priority})")
            
            for retry in range(max_retries):
                result = source.fetch(code)
                
                if result:
                    print(f"[MultiSource] ✅ 成功: {source_name} (重试: {retry})")
                    return result
                
                if retry < max_retries - 1:
                    print(f"[MultiSource] ⚠️ 重试: {source_name} ({retry + 1}/{max_retries})")
                    time.sleep(RETRY_DELAY * (retry + 1))  # 指数退避
            
            print(f"[MultiSource] ❌ 失败: {source_name}，降级到下一数据源")
        
        print("[MultiSource] ❌ 所有数据源都失败")
        return None
    
    def fetch_batch(self, codes: List[str]) -> Dict[str, Optional[RealtimeQuote]]:
        """批量获取实时行情"""
        results = {}
        for code in codes:
            results[code] = self.fetch_realtime(code)
        return results


# ============================================================
# 全局实例
# ============================================================

_manager = None

def get_manager() -> MultiSourceManager:
    """获取全局数据源管理器"""
    global _manager
    if _manager is None:
        _manager = MultiSourceManager()
    return _manager


def fetch_realtime_quote(code: str) -> Optional[RealtimeQuote]:
    """便捷函数：获取单只股票实时行情"""
    return get_manager().fetch_realtime(code)


def fetch_realtime_batch(codes: List[str]) -> Dict[str, Optional[RealtimeQuote]]:
    """便捷函数：批量获取实时行情"""
    return get_manager().fetch_batch(codes)


def get_source_status() -> Dict[str, DataSourceStatus]:
    """便捷函数：获取数据源状态"""
    return get_manager().get_status()


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("多数据源实时行情测试")
    print("=" * 60)
    
    manager = get_manager()
    
    # 测试单只股票
    test_code = "601728"
    print(f"\n测试获取 {test_code} 实时行情:")
    print("-" * 60)
    
    quote = manager.fetch_realtime(test_code)
    
    if quote:
        print(f"✅ 获取成功!")
        print(f"   股票: {quote.name} ({quote.code})")
        print(f"   价格: {quote.price:.2f}")
        print(f"   涨跌: {quote.change:+.2f} ({quote.change_pct:+.2f}%)")
        print(f"   今开: {quote.open:.2f}")
        print(f"   最高: {quote.high:.2f}")
        print(f"   最低: {quote.low:.2f}")
        print(f"   成交量: {quote.volume} 手")
        print(f"   成交额: {quote.amount:.2f} 万元")
        print(f"   时间: {quote.timestamp}")
        print(f"   来源: {quote.source}")
    else:
        print("❌ 获取失败")
    
    # 显示数据源状态
    print("\n" + "=" * 60)
    print("数据源状态:")
    print("-" * 60)
    
    for name, status in manager.get_status().items():
        available = "✅ 可用" if status.available else "❌ 不可用"
        print(f"  {name}: {available}")
        print(f"    成功: {status.success_count} 次")
        print(f"    失败: {status.failure_count} 次")
        if status.last_success:
            print(f"    最后成功: {status.last_success}")
        if status.last_failure:
            print(f"    最后失败: {status.last_failure}")
    
    # 测试批量获取
    print("\n" + "=" * 60)
    print("批量获取测试:")
    print("-" * 60)
    
    test_codes = ["601728", "600941", "600050"]
    results = manager.fetch_batch(test_codes)
    
    for code, q in results.items():
        if q:
            print(f"  {q.name} ({code}): {q.price:.2f} ({q.change_pct:+.2f}%) [{q.source}]")
        else:
            print(f"  {code}: 获取失败")
