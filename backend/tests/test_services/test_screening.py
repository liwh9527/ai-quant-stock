"""选股服务测试

使用 Mock 测试 ScreeningService 的 parse_query 和 search 方法。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.screening import ScreeningService


@pytest.fixture
def mock_ai_service():
    """Mock AI 服务"""
    service = AsyncMock()
    service.parse_screening_intent.return_value = {
        "conditions": [
            {"field": "pe", "operator": "<", "value": 20},
            {"field": "roe", "operator": ">", "value": 15},
        ],
        "industry": "消费",
        "market": None,
        "sort_by": "roe",
        "sort_order": "desc",
        "limit": 20,
    }
    return service


@pytest.fixture
def mock_db():
    """Mock 数据库会话"""
    return MagicMock()


@pytest.fixture
def screening_service(mock_ai_service, mock_db):
    """创建 ScreenService 实例"""
    return ScreeningService(mock_ai_service, mock_db)


class TestParseQuery:
    """测试 parse_query 方法"""

    @pytest.mark.asyncio
    async def test_parse_query_returns_conditions(self, screening_service):
        """测试解析查询返回筛选条件"""
        result = await screening_service.parse_query("找 PE<20 的消费股")
        assert "conditions" in result
        assert len(result["conditions"]) > 0

    @pytest.mark.asyncio
    async def test_parse_query_contains_field_operator_value(self, screening_service):
        """测试返回条件包含 field、operator、value"""
        result = await screening_service.parse_query("找 PE<20 的消费股")
        cond = result["conditions"][0]
        assert "field" in cond
        assert "operator" in cond
        assert "value" in cond

    @pytest.mark.asyncio
    async def test_parse_query_generates_labels(self, screening_service):
        """测试 parse_query 自动生成可读 label"""
        result = await screening_service.parse_query("找 PE<20 的消费股")
        for cond in result["conditions"]:
            assert "label" in cond
            assert len(cond["label"]) > 0

    @pytest.mark.asyncio
    async def test_parse_query_calls_ai_service(self, screening_service, mock_ai_service):
        """测试 parse_query 正确调用 AI 服务"""
        await screening_service.parse_query("找 PE<20 的消费股")
        mock_ai_service.parse_screening_intent.assert_called_once_with("找 PE<20 的消费股")

    @pytest.mark.asyncio
    async def test_parse_query_label_format(self, screening_service):
        """测试 label 格式正确（包含字段名、运算符、值）"""
        result = await screening_service.parse_query("找 PE<20 的消费股")
        # 第一个条件 PE < 20 应生成 "PE < 20" 类似 label
        label = result["conditions"][0]["label"]
        assert "PE" in label
        assert "<" in label
        assert "20" in label

    @pytest.mark.asyncio
    async def test_parse_query_percentage_label(self, screening_service):
        """测试百分比字段的 label 带 % 后缀"""
        result = await screening_service.parse_query("找 PE<20 的消费股")
        # roe 条件的 label 应带 % 后缀
        roe_conds = [c for c in result["conditions"] if c["field"] == "roe"]
        if roe_conds:
            assert "%" in roe_conds[0]["label"]


class TestSearch:
    """测试 search 方法"""

    def test_search_returns_dict_with_expected_keys(self, screening_service, mock_db):
        """测试 search 返回包含 list/total/page/page_size 的字典"""
        # 模拟查询链
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[])
        assert "list" in result
        assert "total" in result
        assert "page" in result
        assert "page_size" in result

    def test_search_default_pagination(self, screening_service, mock_db):
        """测试默认分页参数"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[])
        assert result["page"] == 1
        assert result["page_size"] == 20

    def test_search_custom_pagination(self, screening_service, mock_db):
        """测试自定义分页参数"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[], page=3, page_size=10)
        assert result["page"] == 3
        assert result["page_size"] == 10


class TestApplyConditions:
    """测试 _apply_conditions 方法"""

    def test_apply_gt_condition(self, screening_service, mock_db):
        """测试 > 运算符"""
        mock_query = MagicMock()
        mock_col = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": ">", "value": 10}],
        )
        mock_query.filter.assert_called_once()

    def test_apply_lt_condition(self, screening_service, mock_db):
        """测试 < 运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": "<", "value": 20}],
        )
        mock_query.filter.assert_called_once()

    def test_apply_eq_condition(self, screening_service, mock_db):
        """测试 = 运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "roe", "operator": "=", "value": 15}],
        )
        mock_query.filter.assert_called_once()

    def test_skip_unsupported_field(self, screening_service, mock_db):
        """测试跳过不支持的字段"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "market_cap", "operator": ">", "value": 100}],
        )
        mock_query.filter.assert_not_called()

    def test_skip_unsupported_operator(self, screening_service, mock_db):
        """测试跳过不支持的运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": "like", "value": 20}],
        )
        mock_query.filter.assert_not_called()

    def test_multiple_conditions(self, screening_service, mock_db):
        """测试多个条件"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [
                {"field": "pe", "operator": "<", "value": 20},
                {"field": "roe", "operator": ">", "value": 15},
            ],
        )
        assert mock_query.filter.call_count == 2
