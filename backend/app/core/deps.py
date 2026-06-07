"""FastAPI 依赖注入"""

from sqlalchemy.orm import Session
from fastapi import Depends

from app.core.database import get_db


def get_database() -> Session:
    """获取数据库会话的依赖函数"""
    return Depends(get_db)
