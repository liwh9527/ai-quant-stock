"""券商接口抽象基类

所有 Broker 实现（妙想、MiniQMT、SimBroker）都实现此接口。
回测引擎可使用 SimBroker 做回测。
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass

from ..shared.order import Order
from ..shared.position import Position


@dataclass
class AccountInfo:
    """账户信息"""
    total_assets: float = 0.0       # 总资产
    available_cash: float = 0.0     # 可用资金
    market_value: float = 0.0       # 持仓市值
    frozen_cash: float = 0.0        # 冻结资金
    currency: str = 'CNY'


@dataclass
class QuoteData:
    """实时行情快照"""
    ts_code: str = ''               # 股票代码
    name: str = ''                  # 股票名称
    price: float = 0.0              # 最新价
    open: float = 0.0               # 开盘价
    high: float = 0.0               # 最高价
    low: float = 0.0                # 最低价
    pre_close: float = 0.0          # 昨收价
    volume: int = 0                 # 成交量
    amount: float = 0.0             # 成交额
    bid1: float = 0.0               # 买一价
    ask1: float = 0.0               # 卖一价
    change_pct: float = 0.0         # 涨跌幅 (%)
    timestamp: str = ''             # 行情时间


class BrokerBase(ABC):
    """券商接口抽象基类

    所有 Broker 实现必须实现以下方法。
    回测引擎可通过 SimBroker 实现此接口。
    """

    @abstractmethod
    async def connect(self) -> bool:
        """连接到券商/交易系统"""
        ...

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """是否已连接"""
        ...

    # ---- 交易 ----

    @abstractmethod
    async def submit_order(self, order: Order) -> str:
        """提交订单，返回券商订单号

        Args:
            order: 订单对象，price/shares/action 必须已设置

        Returns:
            券商返回的订单号

        Raises:
            BrokerError: 提交失败
        """
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """撤单

        Args:
            broker_order_id: 券商订单号

        Returns:
            是否成功撤单
        """
        ...

    @abstractmethod
    async def query_orders(self) -> List[Order]:
        """查询当日委托列表"""
        ...

    # ---- 持仓与账户 ----

    @abstractmethod
    async def query_positions(self) -> List[Position]:
        """查询当前持仓"""
        ...

    @abstractmethod
    async def query_account(self) -> AccountInfo:
        """查询账户资金"""
        ...

    # ---- 行情 ----

    @abstractmethod
    async def get_quote(self, ts_code: str) -> Optional[QuoteData]:
        """获取单只股票实时行情"""
        ...

    async def get_quotes(self, ts_codes: List[str]) -> List[QuoteData]:
        """批量获取行情（默认逐个查询，子类可覆盖优化）"""
        results = []
        for code in ts_codes:
            q = await self.get_quote(code)
            if q:
                results.append(q)
        return results


class BrokerError(Exception):
    """券商操作异常"""
    pass
