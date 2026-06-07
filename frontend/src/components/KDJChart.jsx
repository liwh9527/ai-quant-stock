/**
 * KDJ 指标图组件 - 使用 ECharts
 */

import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

/**
 * KDJ 图
 * @param {Object} props
 * @param {Array} props.data - [{date, k, d, j}]
 * @param {number} props.height - 图表高度
 */
export default function KDJChart({ data = [], height = 200 }) {
  const chartRef = useRef(null)
  const instanceRef = useRef(null)

  useEffect(() => {
    if (!chartRef.current || data.length === 0) return

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current)
    }
    const chart = instanceRef.current

    const dates = data.map((d) => d.date)
    const k = data.map((d) => d.k)
    const d = data.map((d) => d.d)
    const j = data.map((d) => d.j)

    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['K', 'D', 'J'], top: 0, textStyle: { fontSize: 11 } },
      grid: { left: 50, right: 20, top: 30, bottom: 30 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { fontSize: 10 },
        min: 0,
        max: 100,
      },
      visualMap: {
        show: false,
        pieces: [
          { lte: 20, color: '#26a69a' },
          { gt: 20, lte: 80, color: '#999' },
          { gt: 80, color: '#ef5350' },
        ],
        seriesIndex: 0,
      },
      series: [
        {
          name: 'K',
          type: 'line',
          data: k,
          lineStyle: { width: 1.5 },
          symbol: 'none',
        },
        {
          name: 'D',
          type: 'line',
          data: d,
          lineStyle: { width: 1.5 },
          symbol: 'none',
        },
        {
          name: 'J',
          type: 'line',
          data: j,
          lineStyle: { width: 1, type: 'dashed' },
          symbol: 'none',
        },
      ],
    })

    const handleResize = () => chart.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
    }
  }, [data])

  useEffect(() => {
    return () => {
      if (instanceRef.current) {
        instanceRef.current.dispose()
        instanceRef.current = null
      }
    }
  }, [])

  if (data.length === 0) return null

  return (
    <div
      ref={chartRef}
      className="w-full rounded"
      style={{ height }}
    />
  )
}
