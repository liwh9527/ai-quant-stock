# 数据源接入层

## 目标

封装 Tushare、AkShare 等数据源的调用，提供统一的数据访问接口，上层业务不感知具体数据源。

## 用户故事

作为开发者，我想要一个统一的数据访问层，以便切换数据源时不影响业务代码。

## 技术设计

### 接口定义

```python
# backend/app/services/data/base.py

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import date
import pandas as pd

class DataSourceBase(ABC):
    """数据源基类"""

    @abstractmethod
    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表"""
        pass

    @abstractmethod
    def get_daily_quotes(
        self,
        ts_code: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """获取日线行情"""
        pass

    @abstractmethod
    def get_financial_indicators(
        self,
        ts_code: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """获取财务指标"""
        pass

    @abstractmethod
    def get_index_daily(
        self,
        ts_code: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """获取指数日线（用于基准对比）"""
        pass
```

### Tushare 实现

```python
# backend/app/services/data/tushare_source.py

class TushareSource(DataSourceBase):
    def __init__(self, token: str):
        self.pro = ts.pro_api(token)

    def get_stock_list(self) -> pd.DataFrame:
        """调用 stock_basic 接口"""
        df = self.pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,area,industry,market,list_date'
        )
        return df

    def get_daily_quotes(self, ts_code, start_date, end_date) -> pd.DataFrame:
        """调用 daily 接口"""
        df = self.pro.daily(
            ts_code=ts_code,
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d')
        )
        return df
```

### AkShare 实现（备用）

```python
# backend/app/services/data/akshare_source.py

class AkShareSource(DataSourceBase):
    def get_stock_list(self) -> pd.DataFrame:
        """调用 ak.stock_info_a_code_name()"""
        import akshare as ak
        df = ak.stock_info_a_code_name()
        return df

    def get_daily_quotes(self, ts_code, start_date, end_date) -> pd.DataFrame:
        """调用 ak.stock_zh_a_hist()"""
        import akshare as ak
        symbol = ts_code.split('.')[0]
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
            adjust="qfq"
        )
        return df
```

### 数据源工厂

```python
# backend/app/services/data/factory.py

from app.core.config import settings

def get_data_source() -> DataSourceBase:
    """根据配置返回数据源实例"""
    source_type = settings.DATA_SOURCE_TYPE  # "tushare" or "akshare"

    if source_type == "tushare":
        from .tushare_source import TushareSource
        return TushareSource(token=settings.TUSHARE_TOKEN)
    elif source_type == "akshare":
        from .akshare_source import AkShareSource
        return AkShareSource()
    else:
        raise ValueError(f"Unknown data source: {source_type}")
```

### 缓存策略

```python
# backend/app/services/data/cache.py

from functools import lru_cache
from datetime import date

class DataCache:
    """数据缓存层，减少重复 API 调用"""

    def __init__(self, source: DataSourceBase):
        self.source = source
        self._cache = {}

    def get_daily_quotes(self, ts_code, start_date, end_date):
        cache_key = f"daily:{ts_code}:{start_date}:{end_date}"
        if cache_key not in self._cache:
            self._cache[cache_key] = self.source.get_daily_quotes(
                ts_code, start_date, end_date
            )
        return self._cache[cache_key]
```

### 数据落库服务

```python
# backend/app/services/data/import_service.py

class DataImportService:
    """将数据源数据导入本地数据库"""

    def import_stock_list(self):
        """导入股票列表到 stocks 表"""
        pass

    def import_daily_quotes(self, ts_code, start_date, end_date):
        """导入日线数据到 daily_quotes 表"""
        pass

    def import_financial_indicators(self, ts_code, start_date, end_date):
        """导入财务数据到 financial_indicators 表"""
        pass
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/data/sync/stocks` | 同步股票列表 |
| POST | `/api/data/sync/daily` | 同步日线数据 |
| POST | `/api/data/sync/financial` | 同步财务数据 |

## 验收标准

- [ ] DataSourceBase 接口定义完成
- [ ] TushareSource 实现完成
- [ ] AkShareSource 实现完成
- [ ] 数据源工厂可切换数据源
- [ ] 缓存层生效，减少重复调用
- [ ] 数据落库服务可用
- [ ] 环境变量配置数据源类型
