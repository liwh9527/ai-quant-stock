"""pytest 配置文件

提供测试共用的 fixtures：数据库会话、示例数据、Mock 服务等。
"""

import sys
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 将 backend 目录加入 sys.path，确保 app 模块可导入
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.database import Base  # noqa: E402


# ---------- 数据库 fixtures ----------


@pytest.fixture(scope="session")
def db_engine():
    """创建内存 SQLite 测试数据库引擎"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """创建数据库会话（每个测试结束后回滚）"""
    connection = db_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------- 示例数据 fixtures ----------


@pytest.fixture
def sample_stocks():
    """示例股票数据"""
    return [
        {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "industry": "银行", "market": "主板"},
        {"ts_code": "600036.SH", "symbol": "600036", "name": "招商银行", "industry": "银行", "market": "主板"},
        {"ts_code": "000858.SZ", "symbol": "000858", "name": "五粮液", "industry": "白酒", "market": "主板"},
    ]


@pytest.fixture
def sample_financial_data():
    """示例财务数据"""
    return {
        "pe": 8.5,
        "pb": 1.2,
        "roe": 15.3,
        "roa": 8.1,
        "gross_margin": 35.0,
        "net_margin": 20.5,
        "revenue_yoy": 12.5,
        "net_profit_yoy": 18.0,
    }
