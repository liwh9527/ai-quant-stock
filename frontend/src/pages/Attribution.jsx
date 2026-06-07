/**
 * 归因分析页面
 * - 选择回测任务
 * - 收益分解图表（柱状图）
 * - 行业贡献表格
 * - 因子贡献图表
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import * as echarts from 'echarts'
import {
  listBacktestResults,
  returnAttribution,
  factorAttribution,
} from '../services/api'

/** 可选因子列表 */
const FACTOR_OPTIONS = [
  { value: 'roe', label: 'ROE' },
  { value: 'pe', label: 'PE' },
  { value: 'pb', label: 'PB' },
  { value: 'ps', label: 'PS' },
  { value: 'momentum_20d', label: '20日动量' },
  { value: 'momentum_60d', label: '60日动量' },
  { value: 'volatility_20d', label: '20日波动率' },
  { value: 'turnover', label: '换手率' },
  { value: 'market_cap', label: '市值' },
  { value: 'revenue_yoy', label: '营收同比' },
  { value: 'net_profit_yoy', label: '净利润同比' },
  { value: 'gross_margin', label: '毛利率' },
  { value: 'net_margin', label: '净利率' },
]

export default function Attribution() {
  const [backtestList, setBacktestList] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [selectedFactors, setSelectedFactors] = useState(['roe', 'pe', 'momentum_20d'])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [returnResult, setReturnResult] = useState(null)
  const [factorResult, setFactorResult] = useState(null)

  const barChartRef = useRef(null)
  const factorChartRef = useRef(null)
  const barChartInstance = useRef(null)
  const factorChartInstance = useRef(null)

  // 加载回测历史列表
  useEffect(() => {
    listBacktestResults({ page: 1, page_size: 50 })
      .then((res) => {
        if (res.code === 0 && res.data?.records) {
          setBacktestList(res.data.records)
          if (res.data.records.length > 0) {
            setSelectedId(res.data.records[0].id.toString())
          }
        }
      })
      .catch(() => {})
  }, [])

  // 渲染收益分解柱状图
  useEffect(() => {
    if (!returnResult || !barChartRef.current) return

    if (!barChartInstance.current) {
      barChartInstance.current = echarts.init(barChartRef.current)
    }

    const summary = returnResult.summary
    const categories = ['行业选择', '个股选择', '交互效应', '超额收益']
    const values = [
      (summary.allocation * 100).toFixed(2),
      (summary.selection * 100).toFixed(2),
      (summary.interaction * 100).toFixed(2),
      (summary.excess_return * 100).toFixed(2),
    ]
    const colors = values.map((v) => (Number(v) >= 0 ? '#ef4444' : '#22c55e'))

    barChartInstance.current.setOption({
      tooltip: { trigger: 'axis', formatter: '{b}: {c}%' },
      grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: { fontSize: 12 },
      },
      yAxis: {
        type: 'value',
        axisLabel: { formatter: '{value}%', fontSize: 11 },
        splitLine: { lineStyle: { type: 'dashed' } },
      },
      series: [
        {
          type: 'bar',
          data: values.map((v, i) => ({
            value: Number(v),
            itemStyle: { color: colors[i] },
          })),
          barWidth: '50%',
          label: {
            show: true,
            position: 'top',
            formatter: '{c}%',
            fontSize: 12,
          },
        },
      ],
    })

    const handleResize = () => barChartInstance.current?.resize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [returnResult])

  // 渲染因子贡献图表
  useEffect(() => {
    if (!factorResult?.factors?.length || !factorChartRef.current) return

    if (!factorChartInstance.current) {
      factorChartInstance.current = echarts.init(factorChartRef.current)
    }

    const factors = factorResult.factors
    const names = factors.map((f) => f.factor_cn || f.factor)
    const contributions = factors.map((f) => (f.contribution * 100).toFixed(2))
    const colors = contributions.map((v) => (Number(v) >= 0 ? '#ef4444' : '#22c55e'))

    factorChartInstance.current.setOption({
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const p = params[0]
          const f = factors[p.dataIndex]
          return `${p.name}<br/>贡献: ${(f.contribution * 100).toFixed(2)}%<br/>暴露: ${f.exposure}<br/>占比: ${f.pct}%`
        },
      },
      grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
      xAxis: {
        type: 'category',
        data: names,
        axisLabel: { fontSize: 11, rotate: names.length > 5 ? 30 : 0 },
      },
      yAxis: {
        type: 'value',
        axisLabel: { formatter: '{value}%', fontSize: 11 },
        splitLine: { lineStyle: { type: 'dashed' } },
      },
      series: [
        {
          type: 'bar',
          data: contributions.map((v, i) => ({
            value: Number(v),
            itemStyle: { color: colors[i] },
          })),
          barWidth: '50%',
          label: {
            show: true,
            position: 'top',
            formatter: '{c}%',
            fontSize: 11,
          },
        },
      ],
    })

    const handleResize = () => factorChartInstance.current?.resize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [factorResult])

  /** 切换因子选择 */
  const toggleFactor = useCallback((factor) => {
    setSelectedFactors((prev) =>
      prev.includes(factor)
        ? prev.filter((f) => f !== factor)
        : [...prev, factor]
    )
  }, [])

  /** 执行归因分析 */
  const handleAnalyze = useCallback(async () => {
    if (!selectedId) {
      setError('请选择回测任务')
      return
    }

    setLoading(true)
    setError('')
    setReturnResult(null)
    setFactorResult(null)

    try {
      // 并行请求收益归因和因子归因
      const [returnRes, factorRes] = await Promise.all([
        returnAttribution({
          backtest_id: selectedId,
          benchmark: '000300.SH',
        }),
        factorAttribution({
          backtest_id: selectedId,
          factors: selectedFactors,
        }),
      ])

      if (returnRes.code === 0) {
        setReturnResult(returnRes.data)
      } else {
        setError(returnRes.msg || '收益归因失败')
      }

      if (factorRes.code === 0) {
        setFactorResult(factorRes.data)
      }
    } catch (e) {
      setError(e.message || '请求失败，请检查后端是否启动')
    } finally {
      setLoading(false)
    }
  }, [selectedId, selectedFactors])

  const summary = returnResult?.summary
  const details = returnResult?.details || []
  const factorSummary = factorResult?.summary
  const factorList = factorResult?.factors || []

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        {/* 标题 */}
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">归因分析</h1>

        {/* 选择组合 */}
        <div className="bg-white rounded-lg shadow p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* 回测任务选择 */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                回测任务
              </label>
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                <option value="">-- 请选择 --</option>
                {backtestList.map((bt) => (
                  <option key={bt.id} value={bt.id}>
                    {bt.strategy_name} ({bt.start_date} ~ {bt.end_date})
                  </option>
                ))}
              </select>
            </div>

            {/* 因子选择 */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                归因因子（多选）
              </label>
              <div className="flex flex-wrap gap-1.5">
                {FACTOR_OPTIONS.map((f) => (
                  <button
                    key={f.value}
                    onClick={() => toggleFactor(f.value)}
                    className={`text-xs px-2 py-1 rounded border transition-colors ${
                      selectedFactors.includes(f.value)
                        ? 'bg-blue-500 text-white border-blue-500'
                        : 'bg-white text-gray-600 border-gray-200 hover:border-blue-400'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* 执行按钮 */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleAnalyze}
              disabled={loading}
              className="bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 text-white text-sm px-6 py-2 rounded transition-colors"
            >
              {loading ? '分析中...' : '开始分析'}
            </button>
            {error && (
              <span className="text-red-500 text-sm">{error}</span>
            )}
          </div>
        </div>

        {/* 收益分解 */}
        {summary && (
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">收益分解</h2>

            {/* 汇总指标 */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
              <MetricCard
                label="行业选择"
                value={summary.allocation}
                color="text-red-600"
              />
              <MetricCard
                label="个股选择"
                value={summary.selection}
                color="text-red-600"
              />
              <MetricCard
                label="交互效应"
                value={summary.interaction}
                color="text-blue-600"
              />
              <MetricCard
                label="基准收益"
                value={summary.benchmark_return}
                color="text-gray-600"
              />
              <MetricCard
                label="超额收益"
                value={summary.excess_return}
                color="text-green-600"
              />
            </div>

            {/* 柱状图 */}
            <div ref={barChartRef} style={{ width: '100%', height: 300 }} />
          </div>
        )}

        {/* 行业贡献表格 */}
        {details.length > 0 && (
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              行业贡献明细（共 {details.length} 个行业）
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-gray-500">
                    <th className="text-left py-2 px-2 font-medium">行业</th>
                    <th className="text-right py-2 px-2 font-medium">组合权重</th>
                    <th className="text-right py-2 px-2 font-medium">基准权重</th>
                    <th className="text-right py-2 px-2 font-medium">组合收益</th>
                    <th className="text-right py-2 px-2 font-medium">基准收益</th>
                    <th className="text-right py-2 px-2 font-medium">行业选择</th>
                    <th className="text-right py-2 px-2 font-medium">个股选择</th>
                    <th className="text-right py-2 px-2 font-medium">交互效应</th>
                    <th className="text-right py-2 px-2 font-medium">合计</th>
                  </tr>
                </thead>
                <tbody>
                  {details.map((row) => (
                    <tr
                      key={row.industry}
                      className="border-b border-gray-100 hover:bg-gray-50"
                    >
                      <td className="py-2 px-2 text-gray-800">{row.industry}</td>
                      <td className="py-2 px-2 text-right text-gray-600">
                        {(row.port_weight * 100).toFixed(1)}%
                      </td>
                      <td className="py-2 px-2 text-right text-gray-600">
                        {(row.bench_weight * 100).toFixed(1)}%
                      </td>
                      <td className="py-2 px-2 text-right text-gray-600">
                        <PctValue value={row.port_return} />
                      </td>
                      <td className="py-2 px-2 text-right text-gray-600">
                        <PctValue value={row.bench_return} />
                      </td>
                      <td className="py-2 px-2 text-right">
                        <PctValue value={row.allocation} />
                      </td>
                      <td className="py-2 px-2 text-right">
                        <PctValue value={row.selection} />
                      </td>
                      <td className="py-2 px-2 text-right">
                        <PctValue value={row.interaction} />
                      </td>
                      <td className="py-2 px-2 text-right font-medium">
                        <PctValue value={row.total} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 因子贡献 */}
        {factorSummary && (
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">因子贡献</h2>

            {/* 因子汇总 */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <MetricCard
                label="组合总收益"
                value={factorSummary.total_return}
                color="text-gray-800"
              />
              <MetricCard
                label="因子解释"
                value={factorSummary.factor_explained}
                color="text-blue-600"
              />
              <MetricCard
                label="残差"
                value={factorSummary.residual}
                color="text-gray-500"
              />
            </div>

            {/* 因子柱状图 */}
            <div ref={factorChartRef} style={{ width: '100%', height: 300 }} />

            {/* 因子明细表格 */}
            {factorList.length > 0 && (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-gray-500">
                      <th className="text-left py-2 px-2 font-medium">因子</th>
                      <th className="text-right py-2 px-2 font-medium">暴露度</th>
                      <th className="text-right py-2 px-2 font-medium">因子收益</th>
                      <th className="text-right py-2 px-2 font-medium">贡献</th>
                      <th className="text-right py-2 px-2 font-medium">占比</th>
                    </tr>
                  </thead>
                  <tbody>
                    {factorList.map((f) => (
                      <tr
                        key={f.factor}
                        className="border-b border-gray-100 hover:bg-gray-50"
                      >
                        <td className="py-2 px-2 text-gray-800">
                          {f.factor_cn || f.factor}
                        </td>
                        <td className="py-2 px-2 text-right text-gray-600">
                          {f.exposure}
                        </td>
                        <td className="py-2 px-2 text-right">
                          <PctValue value={f.factor_return} />
                        </td>
                        <td className="py-2 px-2 text-right font-medium">
                          <PctValue value={f.contribution} />
                        </td>
                        <td className="py-2 px-2 text-right text-gray-600">
                          {f.pct}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* 无结果提示 */}
        {!loading && !returnResult && !error && (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-400">
            请选择回测任务并点击"开始分析"
          </div>
        )}
      </div>
    </div>
  )
}

/** 指标卡片组件 */
function MetricCard({ label, value, color = 'text-gray-800' }) {
  const pct = typeof value === 'number' ? (value * 100).toFixed(2) : '0.00'
  const sign = Number(pct) >= 0 ? '+' : ''
  return (
    <div className="bg-gray-50 rounded p-3 text-center">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-bold ${color}`}>
        {sign}{pct}%
      </div>
    </div>
  )
}

/** 百分比显示组件 */
function PctValue({ value }) {
  if (typeof value !== 'number') return <span className="text-gray-400">--</span>
  const pct = (value * 100).toFixed(2)
  const sign = Number(pct) >= 0 ? '+' : ''
  return (
    <span className={Number(pct) >= 0 ? 'text-red-600' : 'text-green-600'}>
      {sign}{pct}%
    </span>
  )
}
