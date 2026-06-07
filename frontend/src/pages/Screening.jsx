/**
 * 自然语言选股页面
 * - 自然语言输入框
 * - 筛选条件标签（可编辑/删除）
 * - 股票结果列表（表格形式）
 * - 分页
 */

import { useState, useCallback } from 'react'
import { parseScreeningIntent, searchStocks } from '../services/api'

/** 示例查询 */
const QUERY_EXAMPLES = [
  '找 PE<20、ROE>15% 的消费行业股票',
  'ROE 大于 20% 的银行股',
  '市盈率低于 15，毛利率大于 30%',
  '净利润同比增长超过 20% 的科技股',
]

export default function Screening() {
  const [query, setQuery] = useState('')
  const [conditions, setConditions] = useState([])
  const [industry, setIndustry] = useState(null)
  const [sortBy, setSortBy] = useState(null)
  const [sortOrder, setSortOrder] = useState('desc')

  const [results, setResults] = useState(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [pageSize] = useState(20)

  const [parsing, setParsing] = useState(false)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')

  /** 解析自然语言并执行搜索 */
  const handleSearch = useCallback(async () => {
    if (!query.trim()) return

    setParsing(true)
    setError('')
    setResults(null)

    try {
      // 1. 解析意图
      const parseRes = await parseScreeningIntent({ query: query.trim() })
      if (parseRes.code !== 0) {
        setError(parseRes.msg || '解析失败')
        return
      }

      const data = parseRes.data
      setConditions(data.conditions || [])
      setIndustry(data.industry || null)
      setSortBy(data.sort_by || null)
      setSortOrder(data.sort_order || 'desc')
      setPage(1)

      // 2. 执行筛选
      setSearching(true)
      const searchRes = await searchStocks({
        conditions: data.conditions || [],
        industry: data.industry || null,
        market: data.market || null,
        sort_by: data.sort_by || null,
        sort_order: data.sort_order || 'desc',
        page: 1,
        page_size: pageSize,
      })

      if (searchRes.code === 0) {
        setResults(searchRes.data.list || [])
        setTotal(searchRes.data.total || 0)
      } else {
        setError(searchRes.msg || '筛选失败')
      }
    } catch (e) {
      setError(e.message || '请求失败，请检查后端是否启动')
    } finally {
      setParsing(false)
      setSearching(false)
    }
  }, [query, pageSize])

  /** 仅执行搜索（条件变化后重新搜索） */
  const doSearch = useCallback(async (newPage = 1) => {
    setSearching(true)
    setError('')

    try {
      const searchRes = await searchStocks({
        conditions: conditions.map(({ field, operator, value }) => ({
          field, operator, value,
        })),
        industry,
        sort_by: sortBy,
        sort_order: sortOrder,
        page: newPage,
        page_size: pageSize,
      })

      if (searchRes.code === 0) {
        setResults(searchRes.data.list || [])
        setTotal(searchRes.data.total || 0)
        setPage(newPage)
      } else {
        setError(searchRes.msg || '筛选失败')
      }
    } catch (e) {
      setError(e.message || '请求失败')
    } finally {
      setSearching(false)
    }
  }, [conditions, industry, sortBy, sortOrder, pageSize])

  /** 删除条件标签 */
  const removeCondition = useCallback((index) => {
    const newConds = conditions.filter((_, i) => i !== index)
    setConditions(newConds)
    // 重新搜索
    if (results !== null) {
      setTimeout(() => doSearch(1), 0)
    }
  }, [conditions, results, doSearch])

  /** 编辑条件标签 */
  const editCondition = useCallback((index, field, value) => {
    const newConds = conditions.map((c, i) => {
      if (i !== index) return c
      const updated = { ...c, [field]: value }
      // 更新 label
      const fieldNames = {
        pe: 'PE', pb: 'PB', ps: 'PS', roe: 'ROE', roa: 'ROA',
        gross_margin: '毛利率', net_margin: '净利率',
        revenue_yoy: '营收同比', net_profit_yoy: '净利润同比',
        debt_ratio: '资产负债率', current_ratio: '流动比率',
      }
      const suffix = ['roe', 'roa', 'gross_margin', 'net_margin',
        'revenue_yoy', 'net_profit_yoy', 'debt_ratio'].includes(updated.field) ? '%' : ''
      updated.label = `${fieldNames[updated.field] || updated.field} ${updated.operator} ${updated.value}${suffix}`
      return updated
    })
    setConditions(newConds)
  }, [conditions])

  /** 确认编辑后重新搜索 */
  const handleConditionEditDone = useCallback(() => {
    if (results !== null) {
      doSearch(1)
    }
  }, [results, doSearch])

  /** 键盘回车 */
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
  }

  /** 切换排序 */
  const toggleSort = useCallback((field) => {
    const newOrder = sortBy === field && sortOrder === 'desc' ? 'asc' : 'desc'
    setSortBy(field)
    setSortOrder(newOrder)
    if (results !== null) {
      setTimeout(() => doSearch(1), 0)
    }
  }, [sortBy, sortOrder, results, doSearch])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        {/* 标题 */}
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">自然语言选股</h1>

        {/* 输入区域 */}
        <div className="bg-white rounded-lg shadow p-4 space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="用自然语言描述选股条件，如：找 PE<20、ROE>15% 的消费行业股票"
              className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <button
              onClick={handleSearch}
              disabled={parsing || searching}
              className="bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 text-white text-sm px-5 py-2 rounded whitespace-nowrap transition-colors"
            >
              {parsing ? '解析中...' : searching ? '搜索中...' : '搜索'}
            </button>
          </div>

          {/* 示例查询 */}
          <div className="flex flex-wrap gap-2">
            {QUERY_EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setQuery(ex)}
                className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-500 hover:border-blue-400 hover:text-blue-500 transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-600 text-sm rounded px-4 py-2">
            {error}
          </div>
        )}

        {/* 筛选条件标签 */}
        {(conditions.length > 0 || industry) && (
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-sm font-medium text-gray-600 mb-2">筛选条件</h2>
            <div className="flex flex-wrap gap-2">
              {conditions.map((cond, index) => (
                <ConditionTag
                  key={index}
                  condition={cond}
                  onRemove={() => removeCondition(index)}
                  onEdit={(field, value) => editCondition(index, field, value)}
                  onEditDone={handleConditionEditDone}
                />
              ))}
              {industry && (
                <span className="inline-flex items-center gap-1 px-3 py-1 bg-purple-100 text-purple-700 text-sm rounded-full">
                  行业: {industry}
                  <button
                    onClick={() => {
                      setIndustry(null)
                      if (results !== null) setTimeout(() => doSearch(1), 0)
                    }}
                    className="ml-1 text-purple-400 hover:text-purple-600"
                  >
                    &times;
                  </button>
                </span>
              )}
            </div>
          </div>
        )}

        {/* 结果列表 */}
        {results !== null && (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="px-4 py-3 border-b flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-700">
                筛选结果（共 {total} 只）
              </h2>
              {searching && (
                <span className="text-xs text-blue-500">加载中...</span>
              )}
            </div>

            {/* 表格（桌面端） */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500">
                  <tr>
                    <th className="px-4 py-2 text-left">代码</th>
                    <th className="px-4 py-2 text-left">名称</th>
                    <th className="px-4 py-2 text-left">行业</th>
                    <SortableHeader label="PE" field="pe" sortBy={sortBy} sortOrder={sortOrder} onToggle={toggleSort} />
                    <SortableHeader label="PB" field="pb" sortBy={sortBy} sortOrder={sortOrder} onToggle={toggleSort} />
                    <SortableHeader label="ROE" field="roe" sortBy={sortBy} sortOrder={sortOrder} onToggle={toggleSort} />
                    <SortableHeader label="毛利率" field="gross_margin" sortBy={sortBy} sortOrder={sortOrder} onToggle={toggleSort} />
                    <SortableHeader label="营收同比" field="revenue_yoy" sortBy={sortBy} sortOrder={sortOrder} onToggle={toggleSort} />
                    <th className="px-4 py-2 text-right">最新价</th>
                    <th className="px-4 py-2 text-right">涨跌幅</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {results.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="px-4 py-8 text-center text-gray-400">
                        暂无符合条件的股票
                      </td>
                    </tr>
                  ) : (
                    results.map((stock) => (
                      <tr key={stock.ts_code} className="hover:bg-gray-50 transition-colors">
                        <td className="px-4 py-2 font-mono text-gray-800">{stock.ts_code}</td>
                        <td className="px-4 py-2 text-gray-800">{stock.name}</td>
                        <td className="px-4 py-2 text-gray-500">{stock.industry}</td>
                        <td className="px-4 py-2 text-right">{stock.pe ?? '-'}</td>
                        <td className="px-4 py-2 text-right">{stock.pb ?? '-'}</td>
                        <td className="px-4 py-2 text-right">{stock.roe != null ? `${stock.roe}%` : '-'}</td>
                        <td className="px-4 py-2 text-right">{stock.gross_margin != null ? `${stock.gross_margin}%` : '-'}</td>
                        <td className="px-4 py-2 text-right">{stock.revenue_yoy != null ? `${stock.revenue_yoy}%` : '-'}</td>
                        <td className="px-4 py-2 text-right">{stock.close ?? '-'}</td>
                        <td className={`px-4 py-2 text-right ${stock.pct_chg > 0 ? 'text-red-500' : stock.pct_chg < 0 ? 'text-green-500' : ''}`}>
                          {stock.pct_chg != null ? `${stock.pct_chg > 0 ? '+' : ''}${stock.pct_chg}%` : '-'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* 卡片列表（移动端） */}
            <div className="md:hidden divide-y divide-gray-100">
              {results.length === 0 ? (
                <div className="px-4 py-8 text-center text-gray-400">
                  暂无符合条件的股票
                </div>
              ) : (
                results.map((stock) => (
                  <div key={stock.ts_code} className="px-4 py-3">
                    <div className="flex items-center justify-between mb-1">
                      <div>
                        <span className="font-mono text-sm text-gray-800 mr-2">{stock.ts_code}</span>
                        <span className="text-sm font-medium text-gray-800">{stock.name}</span>
                      </div>
                      <span className={`text-sm ${stock.pct_chg > 0 ? 'text-red-500' : stock.pct_chg < 0 ? 'text-green-500' : 'text-gray-500'}`}>
                        {stock.pct_chg != null ? `${stock.pct_chg > 0 ? '+' : ''}${stock.pct_chg}%` : '-'}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                      <span>行业: {stock.industry || '-'}</span>
                      <span>PE: {stock.pe ?? '-'}</span>
                      <span>ROE: {stock.roe != null ? `${stock.roe}%` : '-'}</span>
                      <span>毛利率: {stock.gross_margin != null ? `${stock.gross_margin}%` : '-'}</span>
                      <span>价格: {stock.close ?? '-'}</span>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* 分页 */}
            {totalPages > 1 && (
              <div className="px-4 py-3 border-t flex items-center justify-between text-sm">
                <span className="text-gray-500">
                  第 {page} / {totalPages} 页
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => doSearch(page - 1)}
                    disabled={page <= 1 || searching}
                    className="px-3 py-1 border rounded text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    上一页
                  </button>
                  <button
                    onClick={() => doSearch(page + 1)}
                    disabled={page >= totalPages || searching}
                    className="px-3 py-1 border rounded text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    下一页
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}


/** 可排序表头 */
function SortableHeader({ label, field, sortBy, sortOrder, onToggle }) {
  const active = sortBy === field
  return (
    <th
      className="px-4 py-2 text-right cursor-pointer select-none hover:text-gray-700"
      onClick={() => onToggle(field)}
    >
      {label}
      {active && (
        <span className="ml-1">{sortOrder === 'desc' ? '↓' : '↑'}</span>
      )}
    </th>
  )
}


/** 筛选条件标签（可编辑/删除） */
function ConditionTag({ condition, onRemove, onEdit, onEditDone }) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(String(condition.value))

  const handleSave = () => {
    const numVal = Number(editValue)
    if (!isNaN(numVal)) {
      onEdit('value', numVal)
      setEditing(false)
      onEditDone()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSave()
    if (e.key === 'Escape') {
      setEditValue(String(condition.value))
      setEditing(false)
    }
  }

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 border border-blue-300 text-sm rounded-full">
        <span className="text-blue-600 text-xs">
          {condition.label?.split(/[><=!]+/)[0]?.trim() || condition.field}
          {' '}{condition.operator}{' '}
        </span>
        <input
          type="number"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleSave}
          className="w-16 px-1 py-0.5 text-sm border rounded text-center focus:outline-none focus:ring-1 focus:ring-blue-400"
          autoFocus
        />
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 text-sm rounded-full">
      <span
        className="cursor-pointer hover:text-blue-900"
        onClick={() => {
          setEditValue(String(condition.value))
          setEditing(true)
        }}
        title="点击编辑"
      >
        {condition.label}
      </span>
      <button
        onClick={onRemove}
        className="ml-1 text-blue-400 hover:text-blue-600"
        title="删除条件"
      >
        &times;
      </button>
    </span>
  )
}
