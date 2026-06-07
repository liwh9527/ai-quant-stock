/**
 * 因子列表组件
 * - 分类标签筛选
 * - 因子表格（桌面端）/ 卡片（移动端）
 */

import { CATEGORY_COLORS } from './shared'

export default function FactorList({ factors, categories, activeCategory, onCategoryChange }) {
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
                <th className="px-4 py-2 text-center">方向</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(f => (
                <tr key={f.key} className="hover:bg-gray-50">
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
                    {f.direction === 1
                      ? <span className="text-green-600">正向 ↑</span>
                      : <span className="text-red-600">反向 ↓</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* 移动端卡片 */}
        <div className="md:hidden divide-y divide-gray-100">
          {filtered.map(f => (
            <div key={f.key} className="px-4 py-3">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-gray-800">{f.name}</span>
                <span className={`px-2 py-0.5 rounded-full text-xs ${CATEGORY_COLORS[f.category_name] || 'bg-gray-100'}`}>
                  {f.category_name}
                </span>
              </div>
              <div className="text-xs text-gray-500 space-y-0.5">
                <div><span className="text-gray-400">Key:</span> {f.key}</div>
                <div>{f.description}</div>
                <div>
                  方向: {f.direction === 1
                    ? <span className="text-green-600">正向</span>
                    : <span className="text-red-600">反向</span>
                  }
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
