/**
 * 指标卡片组件
 * 展示回测的核心风险收益指标
 */

export default function MetricsCards({ metrics }) {
  if (!metrics) return null

  const cards = [
    {
      label: '总收益率',
      value: `${metrics.total_return}%`,
      color: metrics.total_return >= 0 ? 'text-green-600' : 'text-red-600',
    },
    {
      label: '年化收益率',
      value: `${metrics.annual_return}%`,
      color: metrics.annual_return >= 0 ? 'text-green-600' : 'text-red-600',
    },
    {
      label: '最大回撤',
      value: `${metrics.max_drawdown}%`,
      color: 'text-red-600',
    },
    {
      label: '夏普比率',
      value: metrics.sharpe_ratio,
      color: metrics.sharpe_ratio >= 1 ? 'text-green-600' : 'text-gray-800',
    },
    {
      label: '胜率',
      value: `${metrics.win_rate}%`,
      color: metrics.win_rate >= 50 ? 'text-green-600' : 'text-gray-800',
    },
    {
      label: '交易次数',
      value: metrics.trade_count,
      color: 'text-gray-800',
    },
    {
      label: '基准收益',
      value: `${metrics.benchmark_return}%`,
      color: metrics.benchmark_return >= 0 ? 'text-green-600' : 'text-red-600',
    },
    {
      label: '超额收益',
      value: `${metrics.excess_return}%`,
      color: metrics.excess_return >= 0 ? 'text-green-600' : 'text-red-600',
    },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {cards.map((card) => (
        <div key={card.label} className="bg-gray-50 rounded-lg p-3 text-center">
          <div className="text-xs text-gray-500 mb-1">{card.label}</div>
          <div className={`text-lg font-bold ${card.color}`}>{card.value}</div>
        </div>
      ))}
    </div>
  )
}
