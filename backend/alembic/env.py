"""Alembic 数据库迁移环境配置

从 app.core.config 读取数据库 URL，并导入所有 ORM 模型以支持自动生成迁移。
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 导入应用配置和 ORM 基类
from app.core.config import settings
from app.core.database import Base

# 导入所有模型，确保 Base.metadata 包含所有表定义
from app.models import (  # noqa: F401
    Stock,
    DailyQuote,
    WeeklyQuote,
    FinancialIndicator,
    TradeSignal,
    BacktestResult,
    UserWatchlist,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 从应用配置中读取数据库 URL，覆盖 alembic.ini 中的值
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置 target_metadata 为 Base.metadata，使 autogenerate 能自动检测模型变更
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
