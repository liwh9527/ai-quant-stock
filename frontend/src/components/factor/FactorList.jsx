/**
 * 因子列表组件
 * - 分类标签筛选
 * - 因子表格（桌面端）/ 卡片（移动端）
 * - 显示 IC、IR、状态（测试后）
 */

import { CATEGORY_COLORS } from './shared'

export default function FactorList({ factors, categories, activeCategory, onCategoryChange, testResult }) {
  const filtered = activeCategory === '全部'
    ? factors
    : factors.filter(f => f.category_name === activeCategory)

  return (
    <div className="space-y-4">
      {/* 分类标签 */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onCategoryChange('全部')}
          className={`px-3 py-1 text-sm rounded-full transition-colors ${
            activeCategory === '全部'
              ? 'bg-gray-800 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          全部 ({factors.length})
        </button>
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => onCategoryChange(cat)}
            className={`px-3 py-1 text-sm rounded-full transition-colors ${
              activeCategory === cat
                ? 'bg-gray-800 text-white'
                : `${CATEGORY_COLORS[cat] || 'bg-gray-100 text-gray-600'} hover:opacity-80`
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* 因子列表 */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {/* 桌面端表格 */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500">
              <tr>
                <th className="px-4 py-2 text-left">因子</th>
                <th className="px-4 py-2 text-left">分类</th>
                <th className="px-4 py-2 text-left">说明</th>
                <th className="px-4 py-2 text-center">IC</th>
                <th className="px-4 py-2 text-center">IR</th>
                <th className="px-4 py-2 text-center">状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(f => {
                const active = testResult?.factor?.key === f.key
                const ic = active ? testResult.ic : null
                const ir = active ? testResult.ir : null
                return (
                  <tr key={f.key} className={`hover:bg-gray-50 ${active ? 'bg-blue-50' : ''}`}>
                    <td className="px-4 py-2 font-mono text-gray-800">
                      <span className="font-medium">{f.name}</span>
                      <span className="text-gray-400 text-xs ml-2">({f.key})</span>
                    </td>
                    <td className="px-4 py-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs ${CATEGORY_COLORS[f.category_name] || 'bg-gray-100 text-gray-600'}`}>
                        {f.category_name}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-gray-500">{f.description}</td>
                    <td className="px-4 py-2 text-center">
                      <ICValue value={ic} />
                    </td>
                    <td className="px-4 py-2 text-center">
                      <IRValue value={ir} />
                    </td>
                    <td className="px-4 py-2 text-center">
                      <FactorStatus ic={ic} ir={ir} active={active} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* 移动端卡片 */}
        <div className="md:hidden divide-y divide-gray-100">
          {filtered.map(f => {
            const active = testResult?.factor?.key === f.key
            const ic = active ? testResult.ic : null
            const ir = active ? testResult.ir : null
            return (
              <div key={f.key} className={`px-4 py-3 ${active ? 'bg-blue-50' : ''}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-gray-800">{f.name}</span>
                  <FactorStatus ic={ic} ir={ir} active={active} />
                </div>
                <div className="text-xs text-gray-500 space-y-0.5">
                  <span className={`inline-block px-2 py-0.5 rounded-full text-xs ${CATEGORY_COLORS[f.category_name] || 'bg-gray-100'}`}>
                    {f.category_name}
                  </span>
                  <div>{f.description}</div>
                  {active && (
                    <div className="flex gap-4 text-xs mt-1">
                      <span>IC: <ICValue value={ic} /></span>
                      <span>IR: <IRValue value={ir} /></span>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}


/** IC 值显示 */
function ICValue({ value }) {
  if (value == null) return <span className="text-gray-400">-</span>
  const color = Math.abs(value) >= 0.03 ? 'text-green-600' : Math.abs(value) >= 0.02 ? 'text-yellow-600' : 'text-red-500'
  return <span className={`font-mono ${color}`}>{value.toFixed(4)}</span>
}

/** IR 值显示 */
function IRValue({ value }) {
  if (value == null) return <span className="text-gray-400">-</span>
  const color = Math.abs(value) >= 0.5 ? 'text-green-600' : Math.abs(value) >= 0.3 ? 'text-yellow-600' : 'text-red-500'
  return <span className={`font-mono ${color}`}>{value.toFixed(4)}</span>
}

/** 因子状态标签 */
function FactorStatus({ ic, ir, active }) {
  if (!active || ic == null) {
    return (
      <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-400">未测试</span>
    )
  }
  const good = Math.abs(ic) >= 0.03 && Math.abs(ir) >= 0.5
  const medium = Math.abs(ic) >= 0.02 || Math.abs(ir) >= 0.3
  if (good) {
    return <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700">有效</span>
  }
  if (medium) {
    return <span className="text-xs px-2 py-0.5 rounded bg-yellow-100 text-yellow-700">一般</span>
  }
  return <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">较弱</span>
}
