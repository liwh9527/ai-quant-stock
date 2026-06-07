# 测试规范

## 目标

为每个模块编写全面的测试，确保代码质量、功能正确性和系统稳定性。

## 测试策略

### 测试类型

| 类型 | 说明 | 工具 | 优先级 |
|------|------|------|--------|
| 单元测试 | 测试单个函数/类 | pytest | P0 |
| 集成测试 | 测试 API 接口 | pytest + httpx | P0 |
| Mock 测试 | 模拟外部服务 | unittest.mock | P0 |
| 边界测试 | 测试边界条件 | pytest | P0 |
| 错误处理测试 | 测试异常情况 | pytest | P0 |
| 前端组件测试 | 测试 React 组件 | Jest + Testing Library | P1 |
| 性能测试 | 测试性能瓶颈 | pytest-benchmark | P2 |
| E2E 测试 | 测试完整流程 | Playwright | P2 |

### 测试目录结构

```
backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # pytest 配置
│   ├── test_models/             # 模型测试
│   │   ├── __init__.py
│   │   ├── test_stock.py
│   │   └── test_daily.py
│   ├── test_services/           # 服务层测试
│   │   ├── __init__.py
│   │   ├── test_ai_service.py
│   │   ├── test_data_source.py
│   │   └── test_screening.py
│   ├── test_api/                # API 测试
│   │   ├── __init__.py
│   │   ├── test_health.py
│   │   ├── test_screening.py
│   │   └── test_backtest.py
│   └── test_utils/              # 工具函数测试
│       └── __init__.py
```

## 测试规范

### 1. 模型测试

```python
# backend/tests/test_models/test_stock.py

import pytest
from app.models.stock import Stock

def test_stock_creation():
    """测试股票模型创建"""
    stock = Stock(
        ts_code="000001.SZ",
        symbol="000001",
        name="平安银行",
        industry="银行"
    )
    assert stock.ts_code == "000001.SZ"
    assert stock.name == "平安银行"

def test_stock_required_fields():
    """测试必填字段"""
    with pytest.raises(Exception):
        Stock(ts_code=None)  # 应该抛出异常
```

### 2. 服务层测试

```python
# backend/tests/test_services/test_screening.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.screening import ScreeningService

@pytest.fixture
def mock_ai_service():
    """Mock AI 服务"""
    service = AsyncMock()
    service.parse_screening_intent.return_value = {
        "conditions": [{"field": "pe", "operator": "<", "value": 20}],
        "industry": "消费"
    }
    return service

@pytest.fixture
def mock_data_source():
    """Mock 数据源"""
    return MagicMock()

async def test_parse_query(mock_ai_service, mock_data_source):
    """测试查询解析"""
    service = ScreeningService(mock_ai_service, mock_data_source)
    result = await service.parse_query("找 PE<20 的消费股")
    assert "conditions" in result
    assert len(result["conditions"]) > 0
```

### 3. API 测试

```python
# backend/tests/test_api/test_screening.py

import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

async def test_screening_parse(client):
    """测试选股意图解析 API"""
    response = await client.post("/api/screening/parse", json={
        "query": "找 PE<20 的消费股"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "conditions" in data["data"]
```

### 4. 数据源测试

```python
# backend/tests/test_services/test_data_source.py

import pytest
from app.services.data.factory import get_data_source

def test_tushare_source_creation():
    """测试 Tushare 数据源创建"""
    source = get_data_source("tushare")
    assert source is not None

def test_get_stock_list():
    """测试获取股票列表"""
    source = get_data_source("tushare")
    df = source.get_stock_list()
    assert len(df) > 0
    assert "ts_code" in df.columns
```

## pytest 配置

```python
# backend/tests/conftest.py

import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def db_engine():
    """创建测试数据库引擎"""
    engine = create_engine("sqlite:///test.db")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(db_engine):
    """创建数据库会话"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
```

## 运行测试

```bash
cd backend

# 运行所有测试
pytest

# 运行特定模块测试
pytest tests/test_models/

# 运行并显示覆盖率
pytest --cov=app --cov-report=html

# 运行并显示详细输出
pytest -v
```

## 测试覆盖率目标

| 模块 | 目标覆盖率 |
|------|-----------|
| models | 90% |
| services | 80% |
| api | 70% |
| utils | 90% |

### 5. Mock 外部服务测试

```python
# backend/tests/test_services/test_data_source_mock.py

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

class TestTushareSourceMock:
    """使用 Mock 测试 Tushare 数据源"""

    @patch("tushare.pro_api")
    def test_get_stock_list_success(self, mock_pro):
        """测试成功获取股票列表"""
        # 准备 Mock 数据
        mock_df = pd.DataFrame({
            "ts_code": ["000001.SZ", "600036.SH"],
            "name": ["平安银行", "招商银行"]
        })
        mock_pro.return_value.stock_basic.return_value = mock_df

        # 执行测试
        from app.services.data.tushare_source import TushareSource
        source = TushareSource(token="test_token")
        result = source.get_stock_list()

        # 验证
        assert len(result) == 2
        assert "ts_code" in result.columns

    @patch("tushare.pro_api")
    def test_get_stock_list_api_failure(self, mock_pro):
        """测试 API 调用失败"""
        # 模拟 API 异常
        mock_pro.return_value.stock_basic.side_effect = Exception("API Error")

        from app.services.data.tushare_source import TushareSource
        source = TushareSource(token="test_token")

        # 验证异常处理
        with pytest.raises(Exception) as exc_info:
            source.get_stock_list()
        assert "API Error" in str(exc_info.value)

    @patch("tushare.pro_api")
    def test_get_stock_list_empty_result(self, mock_pro):
        """测试空结果"""
        mock_pro.return_value.stock_basic.return_value = pd.DataFrame()

        from app.services.data.tushare_source import TushareSource
        source = TushareSource(token="test_token")
        result = source.get_stock_list()

        assert len(result) == 0
```

### 6. 边界条件测试

```python
# backend/tests/test_services/test_screening_edge.py

class TestScreeningEdgeCases:
    """选股边界条件测试"""

    def test_empty_conditions(self):
        """测试空筛选条件"""
        service = ScreeningService(mock_ai, mock_data)
        result = service.search(conditions=[])
        # 应返回所有股票或提示错误
        assert result is not None

    def test_invalid_field_name(self):
        """测试无效字段名"""
        conditions = [{"field": "invalid_field", "operator": "<", "value": 20}]
        with pytest.raises(ValueError):
            service.search(conditions=conditions)

    def test_invalid_operator(self):
        """测试无效运算符"""
        conditions = [{"field": "pe", "operator": "invalid", "value": 20}]
        with pytest.raises(ValueError):
            service.search(conditions=conditions)

    def test_negative_value(self):
        """测试负数值"""
        conditions = [{"field": "pe", "operator": "<", "value": -10}]
        result = service.search(conditions=conditions)
        # PE 为负数的股票应该很少或没有
        assert len(result) >= 0

    def test_extreme_large_value(self):
        """测试极大数值"""
        conditions = [{"field": "pe", "operator": "<", "value": 999999}]
        result = service.search(conditions=conditions)
        # 应返回所有股票
        assert len(result) > 0

    def test_duplicate_conditions(self):
        """测试重复条件"""
        conditions = [
            {"field": "pe", "operator": "<", "value": 20},
            {"field": "pe", "operator": "<", "value": 30}
        ]
        result = service.search(conditions=conditions)
        # 应取更严格的条件
        assert all(stock["pe"] < 20 for stock in result)
```

### 7. 错误处理测试

```python
# backend/tests/test_services/test_error_handling.py

class TestErrorHandling:
    """错误处理测试"""

    @patch("httpx.AsyncClient.post")
    async def test_deepseek_api_timeout(self, mock_post):
        """测试 DeepSeek API 超时"""
        mock_post.side_effect = httpx.TimeoutException("Request timeout")

        from app.services.ai.deepseek_service import DeepSeekService
        service = DeepSeekService()

        with pytest.raises(TimeoutError):
            await service.chat([{"role": "user", "content": "test"}])

    @patch("httpx.AsyncClient.post")
    async def test_deepseek_api_invalid_json(self, mock_post):
        """测试无效 JSON 响应"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"invalid": "response"}
        mock_post.return_value = mock_response

        from app.services.ai.deepseek_service import DeepSeekService
        service = DeepSeekService()

        with pytest.raises(KeyError):
            await service.chat([{"role": "user", "content": "test"}])

    def test_database_connection_error(self):
        """测试数据库连接失败"""
        with patch("sqlalchemy.create_engine") as mock_engine:
            mock_engine.side_effect = Exception("Connection refused")

            with pytest.raises(Exception):
                from app.core.database import get_db
                next(get_db())

    def test_invalid_stock_code_format(self):
        """测试无效股票代码格式"""
        invalid_codes = ["", None, "12345", "ABCDEF", "000001.XX"]

        for code in invalid_codes:
            with pytest.raises(ValueError):
                validate_stock_code(code)
```

### 8. 前端组件测试

```javascript
// frontend/src/components/__tests__/StockList.test.jsx

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import StockList from '../StockList';

describe('StockList Component', () => {
  const mockStocks = [
    { ts_code: '000001.SZ', name: '平安银行', pe: 8.5, roe: 12.3 },
    { ts_code: '600036.SH', name: '招商银行', pe: 6.2, roe: 15.8 }
  ];

  test('renders stock list correctly', () => {
    render(<StockList stocks={mockStocks} />);

    expect(screen.getByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('招商银行')).toBeInTheDocument();
    expect(screen.getByText('8.5')).toBeInTheDocument();
  });

  test('handles empty stock list', () => {
    render(<StockList stocks={[]} />);

    expect(screen.getByText('暂无数据')).toBeInTheDocument();
  });

  test('handles loading state', () => {
    render(<StockList stocks={[]} loading={true} />);

    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  test('handles click event', () => {
    const handleClick = jest.fn();
    render(<StockList stocks={mockStocks} onStockClick={handleClick} />);

    fireEvent.click(screen.getByText('平安银行'));
    expect(handleClick).toHaveBeenCalledWith('000001.SZ');
  });
});
```

## 测试覆盖率目标

| 模块 | 目标覆盖率 | 说明 |
|------|-----------|------|
| models | 90% | 模型验证和约束 |
| services | 85% | 核心业务逻辑 |
| api | 80% | API 端点 |
| utils | 90% | 工具函数 |
| 前端组件 | 70% | 关键交互 |

## 测试数据管理

### 测试数据 Fixtures

```python
# backend/tests/conftest.py

@pytest.fixture
def sample_stocks():
    """示例股票数据"""
    return [
        {"ts_code": "000001.SZ", "name": "平安银行", "industry": "银行"},
        {"ts_code": "600036.SH", "name": "招商银行", "industry": "银行"},
        {"ts_code": "000858.SZ", "name": "五粮液", "industry": "白酒"},
    ]

@pytest.fixture
def sample_daily_quotes():
    """示例日线数据"""
    return pd.DataFrame({
        "trade_date": pd.date_range("2024-01-01", periods=10),
        "open": [10.0, 10.5, 11.0, ...],
        "close": [10.5, 11.0, 10.8, ...],
        "high": [11.0, 11.5, 11.2, ...],
        "low": [9.8, 10.2, 10.5, ...],
    })

@pytest.fixture
def sample_financial_data():
    """示例财务数据"""
    return {
        "pe": 8.5,
        "pb": 1.2,
        "roe": 15.3,
        "revenue_yoy": 12.5,
    }
```

## CI/CD 集成

```yaml
# .github/workflows/test.yml

name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        cd backend
        pip install -r requirements.txt
        pip install pytest pytest-cov pytest-asyncio

    - name: Run tests
      run: |
        cd backend
        pytest --cov=app --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v2
      with:
        file: ./backend/coverage.xml
```

## 验收标准

- [ ] 每个模块都有对应的测试文件
- [ ] 核心功能测试通过
- [ ] Mock 测试覆盖所有外部服务
- [ ] 边界条件测试完整
- [ ] 错误处理测试完整
- [ ] 测试覆盖率达到目标
- [ ] 所有测试可独立运行
- [ ] 测试不依赖外部服务（使用 mock）
- [ ] 前端组件测试覆盖关键交互
- [ ] CI/CD 流水线配置完成
