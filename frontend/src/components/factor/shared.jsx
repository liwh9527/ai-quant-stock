/** 因子分类标签颜色 */
export const CATEGORY_COLORS = {
  '价值因子': 'bg-blue-100 text-blue-700',
  '成长因子': 'bg-green-100 text-green-700',
  '质量因子': 'bg-purple-100 text-purple-700',
  '动量因子': 'bg-orange-100 text-orange-700',
  '波动因子': 'bg-red-100 text-red-700',
}

/** 分组收益柱状图颜色 */
export const GROUP_BAR_COLORS = [
  '#3b82f6', '#22c55e', '#eab308', '#f97316', '#ef4444',
  '#8b5cf6', '#06b6d4', '#ec4899', '#14b8a6', '#f59e0b',
]

/** 指标卡片 */
export function MetricCard({ label, value, tooltip, color = 'text-gray-800' }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2" title={tooltip}>
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className={`text-lg font-semibold ${color}`}>{value}</div>
    </div>
  )
}

/** 排名徽章 */
export function RankBadge({ rank }) {
  if (rank <= 3) {
    const colors = { 1: 'bg-yellow-100 text-yellow-800', 2: 'bg-gray-100 text-gray-700', 3: 'bg-orange-100 text-orange-700' }
    return (
      <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${colors[rank]}`}>
        {rank}
      </span>
    )
  }
  return <span className="text-gray-500 text-sm">{rank}</span>
}
