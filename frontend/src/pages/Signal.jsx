/**
 * 买卖信号页面
 * - 股票选择 + 指标选择 + 时间范围
 * - K 线图 + 信号标注
 * - MACD / KDJ 指标副图
 * - 信号列表
 */

import { useState, useCallback } from 'react'
import { generateSignals, listSignals } from '../services/api'
import KLineChart from '../components/KLineChart'
import MACDChart from '../components/MACDChart'
import KDJChart from '../components/KDJChart'

/** 指标选项 */
const INDICATOR_OPTIONS = [
  { value: 'macd', label: 'MACD' },
  { value: 'kdj', label: 'KDJ' },
  { value: 'ma', label: '均线' },
]

/** 时间范围选项 */
const RANGE_OPTIONS = [
  { value: 30, label: '最近 30 天' },
  { value: 60, label: '最近 60 天' },
  { value: 90, label: '最近 90 天' },
  { value: 180, label: '最近 180 天' },
]

export default function Signal() {
  const [tsCode, setTsCode] = useState('000001.SZ')
  const [selectedIndicators, setSelectedIndicators] = useState(['macd'])
  const [days, setDays] = useState(60)
  const [loading, setLoading] = useState(false)
  const [signals, setSignals] = useState([])
  const [chartData, setChartData] = useState(null)
  const [signalRecords, setSignalRecords] = useState([])
  const [error, setError] = useState('')

  /** 切换指标选中状态 */
  const toggleIndicator = useCallback((value) => {
    setSelectedIndicators((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    )
  }, [])

  /** 生成信号 */
  const handleGenerate = useCallback(async () => {
    if (selectedIndicators.length === 0) {
      setError('请至少选择一个指标')
      return
    }
    setLoading(true)
    setError('')
    try {
      const endDate = new Date()
      const startDate = new Date()
      startDate.setDate(endDate.getDate() - days)

      const fmt = (d) => d.toISOString().slice(0, 10)

      const res = await generateSignals({
        ts_code: tsCode,
        indicators: selectedIndicators,
        start_date: fmt(startDate),
        end_date: fmt(endDate),
      })

      if (res.code === 0) {
        setSignals(res.data.signals)
        setChartData(res.data.chart_data)
      } else {
        setError(res.msg || '生成失败')
      }

      // 同时获取信号列表
      const listRes = await listSignals({
        ts_code: tsCode,
        page: 1,
        page_size: 50,
      })
      if (listRes.code === 0) {
        setSignalRecords(listRes.data.records)
      }
    } catch (e) {
      setError(e.message || '请求失败，请检查后端是否启动')
    } finally {
      setLoading(false)
    }
  }, [tsCode, selectedIndicators, days])

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        {/* 标题 */}
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">买卖信号</h1>

        {/* 信号配置 */}
        <div className="bg-white rounded-lg shadow p-4 space-y-3">
          {/* 股票代码 */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2">
            <label className="text-sm font-medium text-gray-600 shrink-0">股票代码</label>
            <input
              type="text"
              value={tsCode}
              onChange={(e) => setTsCode(e.target.value)}
              placeholder="如 000001.SZ"
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full sm:w-48 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>

          {/* 指标选择 */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2">
            <label className="text-sm font-medium text-gray-600 shrink-0">技术指标</label>
            <div className="flex flex-wrap gap-2">
              {INDICATOR_OPTIONS.map((opt) => {
                const active = selectedIndicators.includes(opt.value)
                return (
                  <button
                    key={opt.value}
                    onClick={() => toggleIndicator(opt.value)}
                    className={`px-3 py-1 text-sm rounded border transition-colors ${
                      active
                        ? 'bg-blue-500 text-white border-blue-500'
                        : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                    }`}
                  >
                    {opt.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* 时间范围 */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2">
            <label className="text-sm font-medium text-gray-600 shrink-0">时间范围</label>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full sm:w-40 focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {RANGE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* 生成按钮 */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 text-white text-sm px-5 py-2 rounded transition-colors"
            >
              {loading ? '计算中...' : '生成信号'}
            </button>
            {error && <span className="text-red-500 text-sm">{error}</span>}
          </div>
        </div>

        {/* 图表区域 */}
        {chartData && (
          <div className="bg-white rounded-lg shadow p-4 space-y-3">
            <h2 className="text-sm font-semibold text-gray-700">
              K 线图 + 信号标注
            </h2>
            <KLineChart kline={chartData.kline} signals={signals} height={380} />

            {/* MACD 副图 */}
            {chartData.macd && chartData.macd.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-600 mt-2">MACD 指标</h3>
                <MACDChart data={chartData.macd} height={180} />
              </div>
            )}

            {/* KDJ 副图 */}
            {chartData.kdj && chartData.kdj.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-600 mt-2">KDJ 指标</h3>
                <KDJChart data={chartData.kdj} height={180} />
              </div>
            )}
          </div>
        )}

        {/* 信号列表 */}
        {signals.length > 0 && (
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              信号列表（共 {signals.length} 条）
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
        )}

        {/* 历史信号（从数据库查询） */}
        {signalRecords.length > 0 && (
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              历史信号记录（共 {signalRecords.length} 条）
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
                  {signalRecords.map((rec, i) => (
                    <tr key={i} className="border-b last:border-b-0 hover:bg-gray-50">
                      <td className="py-2 pr-4 whitespace-nowrap">{rec.date}</td>
                      <td className="py-2 pr-4">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                            rec.type === 'BUY'
                              ? 'bg-green-100 text-green-700'
                              : 'bg-red-100 text-red-700'
                          }`}
                        >
                          {rec.type === 'BUY' ? '买入' : '卖出'}
                        </span>
                      </td>
                      <td className="py-2 pr-4 uppercase">{rec.indicator}</td>
                      <td className="py-2 pr-4 text-right">{rec.price}</td>
                      <td className="py-2 pr-4 text-right">{rec.strength}</td>
                      <td className="py-2 text-gray-600">{rec.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
