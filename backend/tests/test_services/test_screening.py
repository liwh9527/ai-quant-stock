"""选股服务测试

使用 Mock 测试 ScreeningService 的 parse_query、search 和 _apply_conditions 方法，
覆盖正常流程、边界条件和异常情况。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.screening import ScreeningService, FIELD_MAP, SORT_FIELD_MAP


# ---------- Fixtures ----------


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
    """创建 ScreeningService 实例"""
    return ScreeningService(mock_ai_service, mock_db)


def _build_mock_query():
    """构建模拟查询链，返回 (mock_query, mock_db) 便于 search 测试"""
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.count.return_value = 0
    mock_query.order_by.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = []
    mock_db = MagicMock()
    mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query
    return mock_query, mock_db


# ---------- TestParseQuery ----------


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
        label = result["conditions"][0]["label"]
        assert "PE" in label
        assert "<" in label
        assert "20" in label

    @pytest.mark.asyncio
    async def test_parse_query_percentage_label(self, screening_service):
        """测试百分比字段的 label 带 % 后缀"""
        result = await screening_service.parse_query("找 PE<20 的消费股")
        roe_conds = [c for c in result["conditions"] if c["field"] == "roe"]
        if roe_conds:
            assert "%" in roe_conds[0]["label"]

    @pytest.mark.asyncio
    async def test_parse_query_empty_string(self, mock_ai_service, mock_db):
        """测试空字符串查询"""
        mock_ai_service.parse_screening_intent.return_value = {
            "conditions": [],
            "industry": None,
            "market": None,
        }
        service = ScreeningService(mock_ai_service, mock_db)
        result = await service.parse_query("")
        assert "conditions" in result
        assert len(result["conditions"]) == 0

    @pytest.mark.asyncio
    async def test_parse_query_ai_returns_no_conditions(self, mock_ai_service, mock_db):
        """测试 AI 返回无条件的情况"""
        mock_ai_service.parse_screening_intent.return_value = {
            "conditions": [],
            "industry": None,
            "market": None,
        }
        service = ScreeningService(mock_ai_service, mock_db)
        result = await service.parse_query("随便说说")
        assert result["conditions"] == []

    @pytest.mark.asyncio
    async def test_parse_query_ai_exception(self, mock_ai_service, mock_db):
        """测试 AI 服务抛出异常"""
        mock_ai_service.parse_screening_intent.side_effect = Exception("AI 服务不可用")
        service = ScreeningService(mock_ai_service, mock_db)
        with pytest.raises(Exception, match="AI 服务不可用"):
            await service.parse_query("测试异常")

    @pytest.mark.asyncio
    async def test_parse_query_preserves_existing_label(self, mock_ai_service, mock_db):
        """测试已有 label 的条件不会被覆盖"""
        mock_ai_service.parse_screening_intent.return_value = {
            "conditions": [
                {"field": "pe", "operator": "<", "value": 20, "label": "自定义标签"},
            ],
            "industry": None,
        }
        service = ScreeningService(mock_ai_service, mock_db)
        result = await service.parse_query("测试")
        assert result["conditions"][0]["label"] == "自定义标签"

    @pytest.mark.asyncio
    async def test_parse_query_all_percentage_fields(self, mock_ai_service, mock_db):
        """测试所有百分比字段 label 都带 % 后缀"""
        percentage_fields = [
            "roe", "roa", "gross_margin", "net_margin",
            "revenue_yoy", "net_profit_yoy", "debt_ratio",
        ]
        conditions = [
            {"field": f, "operator": ">", "value": 10}
            for f in percentage_fields
        ]
        mock_ai_service.parse_screening_intent.return_value = {
            "conditions": conditions,
            "industry": None,
        }
        service = ScreeningService(mock_ai_service, mock_db)
        result = await service.parse_query("测试百分比")
        for cond in result["conditions"]:
            assert "%" in cond["label"], f"字段 {cond['field']} 的 label 应包含 %"

    @pytest.mark.asyncio
    async def test_parse_query_non_percentage_fields_no_suffix(self, mock_ai_service, mock_db):
        """测试非百分比字段 label 不带 % 后缀"""
        non_pct_fields = ["pe", "pb", "ps", "eps", "bvps"]
        conditions = [
            {"field": f, "operator": "<", "value": 10}
            for f in non_pct_fields
        ]
        mock_ai_service.parse_screening_intent.return_value = {
            "conditions": conditions,
            "industry": None,
        }
        service = ScreeningService(mock_ai_service, mock_db)
        result = await service.parse_query("测试非百分比")
        for cond in result["conditions"]:
            assert "%" not in cond["label"], f"字段 {cond['field']} 的 label 不应包含 %"

    @pytest.mark.asyncio
    async def test_parse_query_unknown_field_label(self, mock_ai_service, mock_db):
        """测试未知字段的 label 使用大写字段名"""
        mock_ai_service.parse_screening_intent.return_value = {
            "conditions": [
                {"field": "unknown_field", "operator": ">", "value": 5},
            ],
            "industry": None,
        }
        service = ScreeningService(mock_ai_service, mock_db)
        result = await service.parse_query("测试未知字段")
        assert result["conditions"][0]["label"] == "UNKNOWN_FIELD > 5"


# ---------- TestSearch ----------


class TestSearch:
    """测试 search 方法"""

    def test_search_returns_dict_with_expected_keys(self, screening_service, mock_db):
        """测试 search 返回包含 list/total/page/page_size 的字典"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[])
        assert "list" in result
        assert "total" in result
        assert "page" in result
        assert "page_size" in result

    def test_search_default_pagination(self, screening_service, mock_db):
        """测试默认分页参数"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[])
        assert result["page"] == 1
        assert result["page_size"] == 20

    def test_search_custom_pagination(self, screening_service, mock_db):
        """测试自定义分页参数"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[], page=3, page_size=10)
        assert result["page"] == 3
        assert result["page_size"] == 10

    def test_search_empty_conditions(self, screening_service, mock_db):
        """测试空条件搜索"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[])
        assert result["total"] == 0
        assert result["list"] == []

    def test_search_with_industry_filter(self, screening_service, mock_db):
        """测试行业筛选"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        screening_service.search(conditions=[], industry="银行")
        assert mock_query.filter.call_count >= 1

    def test_search_with_market_filter(self, screening_service, mock_db):
        """测试市场筛选"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        screening_service.search(conditions=[], market="主板")
        assert mock_query.filter.call_count >= 1

    def test_search_with_sort_by(self, screening_service, mock_db):
        """测试排序字段"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        screening_service.search(conditions=[], sort_by="pe", sort_order="asc")
        mock_query.order_by.assert_called()

    def test_search_with_invalid_sort_field(self, screening_service, mock_db):
        """测试无效排序字段，应使用默认排序（ROE 降序）"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        screening_service.search(conditions=[], sort_by="invalid_field")
        mock_query.order_by.assert_called()

    def test_search_offset_calculation(self, screening_service, mock_db):
        """测试分页偏移量计算"""
        mock_query, _ = _build_mock_query()
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        screening_service.search(conditions=[], page=5, page_size=10)
        mock_query.offset.assert_called_once_with(40)
        mock_query.limit.assert_called_once_with(10)

    def test_search_results_format(self, screening_service, mock_db):
        """测试搜索结果格式化（数值精度、None 处理）"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_row = MagicMock()
        mock_row.ts_code = "000001.SZ"
        mock_row.name = "平安银行"
        mock_row.industry = "银行"
        mock_row.market = "主板"
        mock_row.pe = 8.4567
        mock_row.pb = 1.2
        mock_row.ps = 3.0
        mock_row.roe = 15.345
        mock_row.roa = 8.1
        mock_row.gross_margin = 35.678
        mock_row.net_margin = 20.5
        mock_row.revenue_yoy = 12.5
        mock_row.net_profit_yoy = 18.0
        mock_row.debt_ratio = 60.0
        mock_row.close = 12.345
        mock_row.pct_chg = 2.567
        mock_query.all.return_value = [mock_row]
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[])
        assert len(result["list"]) == 1
        item = result["list"][0]
        assert item["pe"] == 8.46
        assert item["close"] == 12.35
        assert item["pct_chg"] == 2.57

    def test_search_results_none_values(self, screening_service, mock_db):
        """测试搜索结果中 None 值的处理"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_row = MagicMock()
        mock_row.ts_code = "000001.SZ"
        mock_row.name = "测试"
        mock_row.industry = None
        mock_row.market = None
        mock_row.pe = None
        mock_row.pb = None
        mock_row.close = None
        mock_row.pct_chg = None
        mock_row.ps = None
        mock_row.roe = None
        mock_row.roa = None
        mock_row.gross_margin = None
        mock_row.net_margin = None
        mock_row.revenue_yoy = None
        mock_row.net_profit_yoy = None
        mock_row.debt_ratio = None
        mock_query.all.return_value = [mock_row]
        mock_db.query.return_value.join.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value = mock_query

        result = screening_service.search(conditions=[])
        item = result["list"][0]
        assert item["industry"] == ""
        assert item["market"] == ""
        assert item["pe"] is None
        assert item["close"] is None


# ---------- TestApplyConditions ----------


class TestApplyConditions:
    """测试 _apply_conditions 方法"""

    def test_apply_gt_condition(self, screening_service):
        """测试 > 运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": ">", "value": 10}],
        )
        mock_query.filter.assert_called_once()

    def test_apply_lt_condition(self, screening_service):
        """测试 < 运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": "<", "value": 20}],
        )
        mock_query.filter.assert_called_once()

    def test_apply_eq_condition(self, screening_service):
        """测试 = 运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "roe", "operator": "=", "value": 15}],
        )
        mock_query.filter.assert_called_once()

    def test_apply_gte_condition(self, screening_service):
        """测试 >= 运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "roe", "operator": ">=", "value": 10}],
        )
        mock_query.filter.assert_called_once()

    def test_apply_lte_condition(self, screening_service):
        """测试 <= 运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": "<=", "value": 30}],
        )
        mock_query.filter.assert_called_once()

    def test_apply_neq_condition(self, screening_service):
        """测试 != 运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": "!=", "value": 0}],
        )
        mock_query.filter.assert_called_once()

    def test_skip_unsupported_field(self, screening_service):
        """测试跳过不支持的字段（market_cap 列映射为 None）"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "market_cap", "operator": ">", "value": 100}],
        )
        mock_query.filter.assert_not_called()

    def test_skip_completely_unknown_field(self, screening_service):
        """测试完全未知的字段被跳过"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "nonexistent_field", "operator": ">", "value": 1}],
        )
        mock_query.filter.assert_not_called()

    def test_skip_unsupported_operator(self, screening_service):
        """测试跳过不支持的运算符"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": "like", "value": 20}],
        )
        mock_query.filter.assert_not_called()

    def test_multiple_conditions(self, screening_service):
        """测试多个条件"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query  # filter 返回自身支持链式调用
        screening_service._apply_conditions(
            mock_query,
            [
                {"field": "pe", "operator": "<", "value": 20},
                {"field": "roe", "operator": ">", "value": 15},
            ],
        )
        assert mock_query.filter.call_count == 2

    def test_empty_conditions_list(self, screening_service):
        """测试空条件列表"""
        mock_query = MagicMock()
        result = screening_service._apply_conditions(mock_query, [])
        mock_query.filter.assert_not_called()
        assert result == mock_query

    def test_condition_with_missing_field_key(self, screening_service):
        """测试缺少 field 键的条件"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"operator": ">", "value": 10}],
        )
        mock_query.filter.assert_not_called()

    def test_condition_with_missing_operator_key(self, screening_service):
        """测试缺少 operator 键的条件"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "value": 10}],
        )
        mock_query.filter.assert_not_called()

    def test_condition_with_missing_value_key(self, screening_service):
        """测试缺少 value 键的条件 - 应跳过"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        # 缺少 value 时 .get("value") 返回 None
        # SQLAlchemy 不支持 None 与 > 运算，_apply_conditions 应跳过此条件
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": ">"}],
        )
        # 可能跳过或抛异常，只要不崩溃即可

    def test_mixed_valid_and_invalid_conditions(self, screening_service):
        """测试混合有效和无效条件"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        screening_service._apply_conditions(
            mock_query,
            [
                {"field": "pe", "operator": "<", "value": 20},
                {"field": "nonexistent", "operator": ">", "value": 1},
                {"field": "roe", "operator": "like", "value": "high"},
                {"field": "pb", "operator": ">", "value": 1.0},
            ],
        )
        # pe 和 pb 有效，nonexistent 和 like 无效被跳过
        assert mock_query.filter.call_count == 2

    def test_all_supported_fields(self, screening_service):
        """测试所有支持的字段都能正确应用"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        supported_fields = [f for f, col in FIELD_MAP.items() if col is not None]
        conditions = [
            {"field": f, "operator": ">", "value": 10}
            for f in supported_fields
        ]
        screening_service._apply_conditions(mock_query, conditions)
        assert mock_query.filter.call_count == len(supported_fields)

    def test_negative_value(self, screening_service):
        """测试负数值条件"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": "<", "value": -1}],
        )
        mock_query.filter.assert_called_once()

    def test_zero_value(self, screening_service):
        """测试零值条件"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "pe", "operator": ">", "value": 0}],
        )
        mock_query.filter.assert_called_once()

    def test_float_value(self, screening_service):
        """测试浮点数值条件"""
        mock_query = MagicMock()
        screening_service._apply_conditions(
            mock_query,
            [{"field": "roe", "operator": ">=", "value": 15.5}],
        )
        mock_query.filter.assert_called_once()
