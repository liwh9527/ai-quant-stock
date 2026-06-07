/**
 * 信号表格组件
 * 展示信号列表，支持买入/卖出标签颜色区分
 */

/**
 * @param {Object} props
 * @param {Array} props.signals - [{date, type, indicator, price, strength, reason}]
 * @param {string} props.title - 表格标题
 */
export default function SignalTable({ signals = [], title = '信号列表' }) {
  if (signals.length === 0) return null

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">
        {title}（共 {signals.length} 条）
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-4">日期</th>
              <th className="py-2 pr-4">类型</th>
              <th className="py-2 pr-4">指标</th>
              <th className="py-2 pr-4 text-right">价格</th>
              <th className="py-2 pr-4 text-right">强度</th>
              <th className="py-2">原因</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((sig, i) => (
              <tr key={i} className="border-b last:border-b-0 hover:bg-gray-50">
                <td className="py-2 pr-4 whitespace-nowrap">{sig.date}</td>
                <td className="py-2 pr-4">
                  <span
                    className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                      sig.type === 'BUY'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-red-100 text-red-700'
                    }`}
                  >
                    {sig.type === 'BUY' ? '买入' : '卖出'}
                  </span>
                </td>
                <td className="py-2 pr-4 uppercase">{sig.indicator}</td>
                <td className="py-2 pr-4 text-right">{sig.price}</td>
                <td className="py-2 pr-4 text-right">{sig.strength}</td>
                <td className="py-2 text-gray-600">{sig.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
