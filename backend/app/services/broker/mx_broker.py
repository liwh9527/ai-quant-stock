"""东财妙想模拟交易 Broker 实现

封装妙想模拟交易 API，实现 BrokerBase 接口。
支持两种 API 端点：
  - mxxysb.com（表单提交，默认）
  - mkapi2.dfcfs.com（JSON + apikey）
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime

import requests

from .base import BrokerBase, BrokerError, AccountInfo, QuoteData
from ..shared.order import Order, OrderStatus, OrderType
from ..shared.position import Position

logger = logging.getLogger(__name__)


class MxBroker(BrokerBase):
    """东财妙想模拟交易 Broker

    配置项（通过 __init__ 传入或从环境变量读取）：
        base_url: API 地址
        account: 模拟账户名称（mxxysb 模式）
        account_index: 账户序号
        apikey: API 密钥（dfcfs 模式）
    """

    def __init__(
        self,
        base_url: str = 'https://mxxysb.com',
        account: str = '',
        account_index: int = 0,
        apikey: str = '',
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip('/')
        self.account = account
        self.account_index = account_index
        self.apikey = apikey
        self.timeout = timeout
        self._session: Optional[requests.Session] = None
        self._connected = False

        # 判断使用哪种 API 模式
        self._mode = 'dfcfs' if 'dfcfs' in self.base_url or apikey else 'mxxysb'

    # ---- 连接管理 ----

    async def connect(self) -> bool:
        """连接到妙想 API"""
        try:
            self._session = requests.Session()
            self._session.timeout = self.timeout
            # 验证连接：查询账户
            account = await self.query_account()
            self._connected = True
            logger.info(f"妙想API连接成功: {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"妙想API连接失败: {type(e).__name__}: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """断开连接"""
        if self._session:
            self._session.close()
            self._session = None
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected and self._session is not None

    # ---- 底层请求 ----

    async def _request(self, endpoint: str, data: dict = None) -> dict:
        """发送请求到妙想 API"""
        if not self._session:
            raise BrokerError("未连接，请先调用 connect()")

        url = f"{self.base_url}{endpoint}"

        try:
            if self._mode == 'dfcfs':
                # JSON + apikey 模式
                headers = {
                    'apikey': self.apikey,
                    'Content-Type': 'application/json',
                }
                resp = self._session.post(url, json=data or {}, headers=headers, timeout=self.timeout)
            else:
                # 表单提交模式
                form_data = {
                    'account': self.account,
                    'account_index': str(self.account_index),
                    **(data or {}),
                }
                resp = self._session.post(url, data=form_data, timeout=self.timeout)

            resp.raise_for_status()
            result = resp.json()

            # 统一错误码检查
            errcode = result.get('errcode', result.get('code', 0))
            if errcode not in (0, 200, '0', '200'):
                errmsg = result.get('errmsg', result.get('message', '未知错误'))
                raise BrokerError(f"API错误 [{errcode}]: {errmsg}")

            return result

        except requests.exceptions.HTTPError as e:
            raise BrokerError(f"HTTP错误 {e.response.status_code}: {e}")
        except requests.exceptions.RequestException as e:
            raise BrokerError(f"请求失败: {type(e).__name__}: {e}")
        except Exception as e:
            raise BrokerError(f"未知错误: {type(e).__name__}: {e}")

    # ---- 交易 ----

    async def submit_order(self, order: Order) -> str:
        """提交订单到妙想模拟盘

        Args:
            order: 订单对象

        Returns:
            妙想返回的订单信息
        """
        code = order.ts_code.split('.')[0]  # 去掉 .SH/.SZ 后缀

        if self._mode == 'dfcfs':
            result = await self._request('/api/claw/mockTrading/trade', {
                'type': 'buy' if order.is_buy else 'sell',
                'stockCode': code,
                'price': order.price,
                'quantity': order.shares,
                'useMarketPrice': order.order_type == OrderType.MARKET,
            })
        else:
            result = await self._request('/api/v1/trade/entrust', {
                'stock_code': code,
                'price': str(order.price),
                'volume': str(order.shares),
                'entrust_type': 'buy' if order.is_buy else 'sell',
            })

        # 更新订单状态
        order.mark_submitted(broker_order_id=str(result.get('data', '')))
        logger.info(f"订单已提交: {order.action} {order.ts_code} {order.shares}股@{order.price}")
        return str(result.get('data', ''))

    async def cancel_order(self, broker_order_id: str) -> bool:
        """撤单

        妙想 API 撤单接口：/api/v1/trade/cancel_entrust
        """
        if self._mode == 'mxxysb':
            try:
                result = await self._request('/api/v1/trade/cancel_entrust', {
                    'entrust_no': broker_order_id,
                })
                return result.get('errcode') == 0
            except BrokerError:
                return False
        else:
            # dfcfs 模式暂不支持撤单
            logger.warning("dfcfs 模式暂不支持撤单")
            return False

    async def query_orders(self) -> List[Order]:
        """查询当日委托"""
        if self._mode == 'mxxysb':
            result = await self._request('/api/v1/trade/today_entrust')
            orders = []
            for item in result.get('data', []):
                order = Order(
                    ts_code=f"{item.get('stock_code', '')}.{'SH' if item.get('stock_code', '').startswith('6') else 'SZ'}",
                    action='BUY' if item.get('entrust_type') == 'buy' else 'SELL',
                    price=float(item.get('price', 0)),
                    shares=int(item.get('volume', 0)),
                    broker_order_id=str(item.get('entrust_no', '')),
                    status=self._map_order_status(item.get('status', '')),
                    filled_price=float(item.get('deal_price', 0)),
                    filled_shares=int(item.get('deal_volume', 0)),
                )
                orders.append(order)
            return orders
        return []

    # ---- 持仓与账户 ----

    async def query_positions(self) -> List[Position]:
        """查询当前持仓"""
        if self._mode == 'dfcfs':
            result = await self._request('/api/claw/mockTrading/positions', {'moneyUnit': 1})
            pos_list = result.get('data', {}).get('posList', []) if isinstance(result.get('data'), dict) else []
        else:
            result = await self._request('/api/v1/trade/position')
            pos_list = result.get('data', [])

        positions = []
        for item in pos_list:
            code = item.get('secCode', item.get('stock_code', ''))
            market = 'SH' if code.startswith('6') else 'SZ'
            pos = Position(
                ts_code=f"{code}.{market}",
                buy_price=float(item.get('costPrice', item.get('cost_price', 0))),
                buy_date=item.get('openDate', item.get('open_date', '')),
                shares=int(item.get('count', item.get('volume', 0))),
                available_shares=int(item.get('availCount', item.get('available_volume', 0))),
            )
            positions.append(pos)
        return positions

    async def query_account(self) -> AccountInfo:
        """查询账户资金"""
        if self._mode == 'dfcfs':
            result = await self._request('/api/claw/mockTrading/balance', {'moneyUnit': 1})
            data = result.get('data', {})
            return AccountInfo(
                total_assets=float(data.get('totalAssets', 0)),
                available_cash=float(data.get('availBalance', 0)),
                market_value=float(data.get('totalPosValue', 0)),
                frozen_cash=float(data.get('frozenBalance', 0)),
            )
        else:
            result = await self._request('/api/v1/trade/asset')
            data = result.get('data', {})
            return AccountInfo(
                total_assets=float(data.get('total_asset', 0)),
                available_cash=float(data.get('available_cash', data.get('avail_balance', 0))),
                market_value=float(data.get('market_value', 0)),
                frozen_cash=float(data.get('frozen_cash', 0)),
            )

    # ---- 行情 ----

    async def get_quote(self, ts_code: str) -> Optional[QuoteData]:
        """获取实时行情

        优先使用项目的数据源（Tushare），降级到妙想持仓中的价格。
        """
        try:
            from app.services.data.factory import get_data_source
            from datetime import datetime, timedelta

            ds = get_data_source()
            end_date = datetime.now()
            start_date = end_date - timedelta(days=5)
            quotes = ds.get_daily_quotes(ts_code, start_date, end_date)
            if quotes:
                q = quotes[-1]  # 最新的一条
                return QuoteData(
                    ts_code=ts_code,
                    name='',
                    price=q.close,
                    open=q.open,
                    high=q.high,
                    low=q.low,
                    pre_close=q.pre_close,
                    volume=int(q.vol) if q.vol else 0,
                    amount=float(q.amount) if q.amount else 0,
                    change_pct=float(q.pct_chg) if q.pct_chg else 0,
                    timestamp=str(q.trade_date),
                )
        except Exception as e:
            logger.warning(f"获取行情失败 {ts_code}: {e}")
        return None

    # ---- 内部工具 ----

    @staticmethod
    def _map_order_status(status) -> OrderStatus:
        """映射妙想订单状态到 OrderStatus"""
        status_map = {
            '未成交': OrderStatus.SUBMITTED,
            '已报': OrderStatus.SUBMITTED,
            '部分成交': OrderStatus.PARTIAL_FILLED,
            '已成交': OrderStatus.FILLED,
            '已撤': OrderStatus.CANCELLED,
            '已撤单': OrderStatus.CANCELLED,
            '废单': OrderStatus.REJECTED,
            # 数字状态码
            0: OrderStatus.SUBMITTED,
            1: OrderStatus.PARTIAL_FILLED,
            2: OrderStatus.FILLED,
            3: OrderStatus.CANCELLED,
            4: OrderStatus.REJECTED,
        }
        return status_map.get(status, OrderStatus.SUBMITTED)
