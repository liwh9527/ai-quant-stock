"""应用配置，从环境变量加载"""

from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    """应用配置项"""

    # 应用
    APP_ENV: str = "development"
    DEBUG: bool = True

    # 数据库
    DATABASE_URL: str = "sqlite:///data/quant.db"

    # 数据源配置
    DATA_SOURCE_TYPE: str = "tushare"  # 可选值: "tushare", "akshare"
    TUSHARE_TOKEN: str = ""
    TUSHARE_API_URL: str = ""  # 留空使用官方API，填写则使用代理

    # AI 服务
    AI_PROVIDER: str = "deepseek"  # 可选值: "deepseek", "qwen"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Broker 配置（交易）
    BROKER_TYPE: str = "mx"  # 可选值: "mx", "xtquant", "sim"
    MX_BASE_URL: str = "https://mxxysb.com"
    MX_ACCOUNT: str = ""
    MX_ACCOUNT_INDEX: int = 0
    MX_APIKEY: str = ""

    # CORS 配置
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        """将 CORS_ORIGINS 字符串解析为列表"""
        try:
            return json.loads(self.CORS_ORIGINS)
        except json.JSONDecodeError:
            return ["http://localhost:5173", "http://localhost:3000"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
