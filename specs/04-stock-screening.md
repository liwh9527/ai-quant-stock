# 自然语言选股

## 目标

用户通过自然语言描述选股条件，AI 解析意图并返回符合条件的股票列表。

## 用户故事

作为投资者，我想要用自然语言描述选股条件（如"找 PE<20、ROE>15% 的消费行业股票"），以便快速筛选出符合条件的股票。

## 页面设计

### 布局

```
┌─────────────────────────────────────────┐
│  自然语言选股                            │
├─────────────────────────────────────────┤
│  ┌─────────────────────────────────┐    │
│  │ 输入框：描述你的选股条件...       │    │
│  └─────────────────────────────────┘    │
│  [搜索]                                  │
│                                          │
│  ┌─ 筛选条件标签 ──────────────────┐    │
│  │ [PE < 20] [ROE > 15%] [消费行业] │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌─ 结果列表 ──────────────────────┐    │
│  │ 代码    名称    PE   ROE  行业   │    │
│  │ 000001  平安银行  8.5  12.3 银行  │    │
│  │ 600036  招商银行  6.2  15.8 银行  │    │
│  │ ...                              │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

### 交互流程

1. 用户在输入框输入自然语言描述
2. 点击"搜索"或按回车
3. 前端调用 `/api/screening/parse` 解析意图
4. 显示解析出的筛选条件标签（可编辑/删除）
5. 前端调用 `/api/screening/search` 执行筛选
6. 展示股票列表结果

## API 接口

### 解析选股意图

```
POST /api/screening/parse
```

请求：
```json
{
  "query": "找 PE<20、ROE>15% 的消费行业股票"
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "conditions": [
      {"field": "pe", "operator": "<", "value": 20, "label": "PE < 20"},
      {"field": "roe", "operator": ">", "value": 15, "label": "ROE > 15%"}
    ],
    "industry": "消费",
    "sort_by": "roe",
    "sort_order": "desc"
  },
  "msg": ""
}
```

### 执行选股筛选

```
POST /api/screening/search
```

请求：
```json
{
  "conditions": [
    {"field": "pe", "operator": "<", "value": 20},
    {"field": "roe", "operator": ">", "value": 15}
  ],
  "industry": "消费",
  "sort_by": "roe",
  "sort_order": "desc",
  "page": 1,
  "page_size": 20
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "list": [
      {
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "pe": 8.5,
        "roe": 12.3,
        "industry": "银行",
        "close": 12.50,
        "pct_chg": 1.2
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 20
  },
  "msg": ""
}
```

## 核心逻辑

### 筛选条件解析

```python
# backend/app/services/screening.py

class ScreeningService:
    def __init__(self, ai_service: AIServiceBase, data_source: DataSourceBase):
        self.ai = ai_service
        self.data = data_source

    async def parse_query(self, query: str) -> Dict:
        """解析自然语言查询"""
        return await self.ai.parse_screening_intent(query)

    async def search(self, conditions: Dict) -> List[Dict]:
        """执行筛选"""
        # 1. 从数据库获取基础数据
        # 2. 应用筛选条件
        # 3. 排序和分页
        pass

    def _apply_conditions(self, df, conditions):
        """应用筛选条件到 DataFrame"""
        for cond in conditions:
            field = cond["field"]
            op = cond["operator"]
            value = cond["value"]

            if op == ">":
                df = df[df[field] > value]
            elif op == "<":
                df = df[df[field] < value]
            elif op == ">=":
                df = df[df[field] >= value]
            elif op == "<=":
                df = df[df[field] <= value]
            elif op == "=":
                df = df[df[field] == value]
            elif op == "!=":
                df = df[df[field] != value]

        return df
```

## 验收标准

- [ ] 输入自然语言可解析出筛选条件
- [ ] 筛选条件标签可编辑/删除
- [ ] 筛选结果正确
- [ ] 支持多条件组合
- [ ] 支持行业筛选
- [ ] 支持排序和分页
- [ ] 移动端界面可用
