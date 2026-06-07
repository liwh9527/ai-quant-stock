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
import SignalTable from '../components/SignalTable'

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

/** 日期格式化 */
const fmtDate = (d) => d.toISOString().slice(0, 10)

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

      const res = await generateSignals({
        ts_code: tsCode,
        indicators: selectedIndicators,
        start_date: fmtDate(startDate),
        end_date: fmtDate(endDate),
      })

      if (res.code === 0) {
        setSignals(res.data.signals)
        setChartData(res.data.chart_data)
      } else {
        setError(res.msg || '生成失败')
      }

      const listRes = await listSignals({ ts_code: tsCode, page: 1, page_size: 50 })
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
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">买卖信号</h1>

        {/* 信号配置 */}
        <div className="bg-white rounded-lg shadow p-4 space-y-3">
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

          <div className="flex flex-col sm:flex-row sm:items-center gap-2">
            <label className="text-sm font-medium text-gray-600 shrink-0">技术指标</label>
            <div className="flex flex-wrap gap-2">
              {INDICATOR_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => toggleIndicator(opt.value)}
                  className={`px-3 py-1 text-sm rounded border transition-colors ${
                    selectedIndicators.includes(opt.value)
                      ? 'bg-blue-500 text-white border-blue-500'
                      : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center gap-2">
            <label className="text-sm font-medium text-gray-600 shrink-0">时间范围</label>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full sm:w-40 focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {RANGE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

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
            <h2 className="text-sm font-semibold text-gray-700">K 线图 + 信号标注</h2>
            <KLineChart kline={chartData.kline} signals={signals} height={380} />
            {chartData.macd?.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-600 mt-2">MACD 指标</h3>
                <MACDChart data={chartData.macd} height={180} />
              </div>
            )}
            {chartData.kdj?.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-600 mt-2">KDJ 指标</h3>
                <KDJChart data={chartData.kdj} height={180} />
              </div>
            )}
          </div>
        )}

        {/* 信号列表 */}
        <SignalTable signals={signals} title="信号列表" />
        <SignalTable signals={signalRecords} title="历史信号记录" />
      </div>
    </div>
  )
}
