/**
 * 因子测试组件
 * - 测试配置（因子选择、分组数、日期区间）
 * - 因子有效性指标卡片
 * - 分组收益柱状图（ECharts）
 * - IC 时间序列折线图（ECharts）
 */

import { useState, useCallback } from 'react'
import ReactECharts from 'echarts-for-react'
import { testFactor } from '../../services/api'
import { MetricCard } from './shared'

export default function FactorTest({ factors, onTestResult }) {
  const [factorName, setFactorName] = useState('roe')
  const [groups, setGroups] = useState(5)
  const [startDate, setStartDate] = useState('2023-01-01')
  const [endDate, setEndDate] = useState('2024-12-31')
  const [result, setResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState('')

  const handleTest = useCallback(async () => {
    setTesting(true)
    setError('')
    setResult(null)
    try {
      const res = await testFactor({
        factor_name: factorName,
        groups,
        start_date: startDate,
        end_date: endDate,
      })
      if (res.code === 0) {
        setResult(res.data)
        if (onTestResult) onTestResult(res.data)
      } else {
        setError(res.msg || '因子测试失败')
      }
    } catch (e) {
      setError(e.message || '请求失败')
    } finally {
      setTesting(false)
    }
  }, [factorName, groups, startDate, endDate])

  // 分组收益柱状图配置
  const groupBarOption = (() => {
    const groupsData = result?.group_returns?.groups || []
    if (!groupsData.length) return null
    return {
      tooltip: { trigger: 'axis', formatter: '{b}: {c}%' },
      xAxis: {
        type: 'category',
        data: groupsData.map(g => `第${g.group}组`),
      },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series: [{
        type: 'bar',
        data: groupsData.map(g => +(g.mean_return * 100).toFixed(2)),
        itemStyle: {
          color: (params) => {
            const colors = ['#3b82f6', '#22c55e', '#eab308', '#f97316', '#ef4444',
              '#8b5cf6', '#06b6d4', '#ec4899', '#14b8a6', '#f59e0b']
            return colors[params.dataIndex % colors.length]
          },
          borderRadius: [4, 4, 0, 0],
        },
      }],
      grid: { left: 50, right: 20, top: 20, bottom: 30 },
    }
  })()

  // IC 序列折线图配置
  const icLineOption = (() => {
    const icData = result?.ic_series || []
    if (!icData.length) return null
    return {
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: icData.map(d => d.date),
        axisLabel: { fontSize: 10 },
      },
      yAxis: { type: 'value' },
      series: [{
        type: 'line',
        data: icData.map(d => d.ic),
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color: '#3b82f6' },
        itemStyle: { color: '#3b82f6' },
      }],
      grid: { left: 50, right: 20, top: 10, bottom: 30 },
    }
  })()

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 text-sm rounded px-4 py-2">
          {error}
        </div>
      )}

      {/* 测试配置 */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-sm font-medium text-gray-700 mb-3">测试配置</h2>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">因子</label>
            <select value={factorName} onChange={e => setFactorName(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
              {factors.map(f => (
                <option key={f.key} value={f.key}>{f.name} ({f.key})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">分组数</label>
            <select value={groups} onChange={e => setGroups(Number(e.target.value))}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
              {[3, 4, 5, 6, 7, 8, 10].map(n => (
                <option key={n} value={n}>{n} 组</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">开始日期</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">结束日期</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>
          <div className="flex items-end">
            <button onClick={handleTest} disabled={testing}
              className="w-full bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 text-white text-sm px-4 py-1.5 rounded transition-colors">
              {testing ? '测试中...' : '开始测试'}
            </button>
          </div>
        </div>
      </div>

      {/* 测试结果 */}
      {result && (
        <>
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-sm font-medium text-gray-700 mb-3">
              因子有效性指标 — {result.factor?.name} ({result.factor?.key})
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="IC" value={result.ic} tooltip="信息系数，衡量因子预测能力" />
              <MetricCard label="IR" value={result.ir} tooltip="信息比率，衡量预测稳定性" />
              <MetricCard label="IC>0 占比" value={`${(result.ic_positive_ratio * 100).toFixed(1)}%`} />
              <MetricCard label="数据量" value={result.config?.data_count || '-'} />
            </div>
            {result.group_returns?.long_short_return != null && (
              <div className="grid grid-cols-3 gap-3 mt-3">
                <MetricCard label="多头收益"
                  value={`${(result.group_returns.long_return * 100).toFixed(2)}%`}
                  color={result.group_returns.long_return >= 0 ? 'text-green-600' : 'text-red-600'} />
                <MetricCard label="空头收益"
                  value={`${(result.group_returns.short_return * 100).toFixed(2)}%`}
                  color={result.group_returns.short_return >= 0 ? 'text-green-600' : 'text-red-600'} />
                <MetricCard label="多空收益"
                  value={`${(result.group_returns.long_short_return * 100).toFixed(2)}%`}
                  color={result.group_returns.long_short_return >= 0 ? 'text-green-600' : 'text-red-600'} />
              </div>
            )}
          </div>

          {groupBarOption && (
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-sm font-medium text-gray-700 mb-3">分组收益对比</h2>
              <ReactECharts option={groupBarOption} style={{ height: 280 }} />
            </div>
          )}

          {icLineOption && (
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-sm font-medium text-gray-700 mb-3">IC 时间序列</h2>
              <ReactECharts option={icLineOption} style={{ height: 220 }} />
            </div>
          )}
        </>
      )}

      {!result && !testing && (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-400">
          请选择因子和参数后点击"开始测试"
        </div>
      )}
    </div>
  )
}
