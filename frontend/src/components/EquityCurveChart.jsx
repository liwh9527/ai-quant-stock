/**
 * 收益曲线图表组件
 * 使用 ECharts 展示策略收益 vs 基准收益
 */

import ReactECharts from 'echarts-for-react'

export default function EquityCurveChart({ data, height = 400 }) {
  if (!data || data.length === 0) return null

  const dates = data.map((d) => d.date)
  const strategyValues = data.map((d) => d.strategy)
  const benchmarkValues = data.map((d) => d.benchmark)

  const hasBenchmark = benchmarkValues.some((v) => v !== null)

  const series = [
    {
      name: '策略收益',
      type: 'line',
      data: strategyValues,
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2, color: '#3b82f6' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(59,130,246,0.15)' },
            { offset: 1, color: 'rgba(59,130,246,0)' },
          ],
        },
      },
    },
  ]

  if (hasBenchmark) {
    series.push({
      name: '基准收益',
      type: 'line',
      data: benchmarkValues,
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2, color: '#f59e0b', type: 'dashed' },
    })
  }

  const option = {
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        let html = `<div style="font-size:12px">${params[0].axisValue}</div>`
        params.forEach((p) => {
          if (p.value != null) {
            html += `<div style="font-size:12px">${p.marker} ${p.seriesName}: ¥${p.value.toLocaleString()}</div>`
          }
        })
        return html
      },
    },
    legend: {
      top: 0,
      right: 0,
      textStyle: { fontSize: 12 },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '40px',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 11,
        formatter(val) {
          return val.slice(5) // 只显示月-日
        },
      },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        fontSize: 11,
        formatter(val) {
          return `¥${(val / 10000).toFixed(1)}万`
        },
      },
      splitLine: { lineStyle: { type: 'dashed' } },
    },
    series,
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
      },
      {
        type: 'slider',
        height: 20,
        bottom: 0,
        start: 0,
        end: 100,
      },
    ],
  }

  return <ReactECharts option={option} style={{ height: `${height}px` }} />
}
