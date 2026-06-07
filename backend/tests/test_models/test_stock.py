"""Stock 模型测试"""

import pytest
from app.models.stock import Stock


class TestStockModel:
    """Stock 模型单元测试"""

    def test_stock_creation(self):
        """测试股票模型创建"""
        stock = Stock(
            ts_code="000001.SZ",
            symbol="000001",
            name="平安银行",
            industry="银行",
        )
        assert stock.ts_code == "000001.SZ"
        assert stock.symbol == "000001"
        assert stock.name == "平安银行"
        assert stock.industry == "银行"

    def test_stock_optional_fields(self):
        """测试可选字段可以为 None"""
        stock = Stock(
            ts_code="600036.SH",
            symbol="600036",
            name="招商银行",
        )
        assert stock.area is None
        assert stock.industry is None
        assert stock.market is None
        assert stock.list_date is None
        assert stock.delist_date is None

    def test_stock_repr(self):
        """测试 __repr__ 方法"""
        stock = Stock(ts_code="000001.SZ", symbol="000001", name="平安银行")
        assert repr(stock) == "<Stock 000001.SZ 平安银行>"

    def test_stock_persist_to_db(self, db_session):
        """测试股票模型持久化到数据库"""
        stock = Stock(
            ts_code="000002.SZ",
            symbol="000002",
            name="万科A",
            industry="房地产",
            market="主板",
        )
        db_session.add(stock)
        db_session.flush()

        queried = db_session.query(Stock).filter_by(ts_code="000002.SZ").first()
        assert queried is not None
        assert queried.name == "万科A"
        assert queried.industry == "房地产"

    def test_stock_primary_key(self, db_session):
        """测试主键约束 - 相同 ts_code 不允许重复"""
        stock1 = Stock(ts_code="000001.SZ", symbol="000001", name="平安银行")
        stock2 = Stock(ts_code="000001.SZ", symbol="000001", name="平安银行改名")
        db_session.add(stock1)
        db_session.flush()
        db_session.add(stock2)
        with pytest.raises(Exception):
            db_session.flush()
