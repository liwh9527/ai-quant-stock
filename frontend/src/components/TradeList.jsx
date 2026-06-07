/**
 * 交易记录列表组件
 * 展示回测期间的每笔交易明细
 */

export default function TradeList({ trades }) {
  if (!trades || trades.length === 0) {
    return (
      <div className="text-center text-gray-400 py-8 text-sm">
        暂无交易记录
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="py-2 pr-4">日期</th>
            <th className="py-2 pr-4">操作</th>
            <th className="py-2 pr-4">股票代码</th>
            <th className="py-2 pr-4 text-right">成交价</th>
            <th className="py-2 pr-4 text-right">数量</th>
            <th className="py-2 text-right">盈亏</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade, i) => (
            <tr
              key={i}
              className="border-b last:border-b-0 hover:bg-gray-50"
            >
              <td className="py-2 pr-4 whitespace-nowrap">{trade.date}</td>
              <td className="py-2 pr-4">
                <span
                  className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                    trade.action === 'BUY'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-red-100 text-red-700'
                  }`}
                >
                  {trade.action === 'BUY' ? '买入' : '卖出'}
                </span>
              </td>
              <td className="py-2 pr-4 font-mono text-xs">{trade.ts_code}</td>
              <td className="py-2 pr-4 text-right">
                ¥{trade.price?.toFixed(2)}
              </td>
              <td className="py-2 pr-4 text-right">{trade.shares}</td>
              <td className="py-2 text-right">
                {trade.pnl != null ? (
                  <span
                    className={
                      trade.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }
                  >
                    {trade.pnl > 0 ? '+' : ''}
                    {trade.pnl}%
                  </span>
                ) : (
                  <span className="text-gray-400">--</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
