/**
 * MACD 指标图组件 - 使用 ECharts
 */

import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

/**
 * MACD 图
 * @param {Object} props
 * @param {Array} props.data - [{date, dif, dea, hist}]
 * @param {number} props.height - 图表高度
 */
export default function MACDChart({ data = [], height = 200 }) {
  const chartRef = useRef(null)
  const instanceRef = useRef(null)

  useEffect(() => {
    if (!chartRef.current || data.length === 0) return

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current)
    }
    const chart = instanceRef.current

    const dates = data.map((d) => d.date)
    const dif = data.map((d) => d.dif)
    const dea = data.map((d) => d.dea)
    const hist = data.map((d) => d.hist)

    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['DIF', 'DEA', 'MACD'], top: 0, textStyle: { fontSize: 11 } },
      grid: { left: 50, right: 20, top: 30, bottom: 30 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { fontSize: 10 },
      },
      yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 10 } },
      series: [
        {
          name: 'DIF',
          type: 'line',
          data: dif,
          lineStyle: { width: 1 },
          symbol: 'none',
        },
        {
          name: 'DEA',
          type: 'line',
          data: dea,
          lineStyle: { width: 1 },
          symbol: 'none',
        },
        {
          name: 'MACD',
          type: 'bar',
          data: hist.map((v) => ({
            value: v,
            itemStyle: { color: v >= 0 ? '#ef5350' : '#26a69a' },
          })),
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
