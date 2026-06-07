/**
 * K 线图组件 - 使用 TradingView Lightweight Charts
 * 支持信号标注（买入绿色箭头、卖出红色箭头）
 */

import { useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'

/**
 * K 线图
 * @param {Object} props
 * @param {Array} props.kline - K 线数据 [{date, open, high, low, close}]
 * @param {Array} props.signals - 信号列表 [{date, type, price, indicator}]
 * @param {number} props.height - 图表高度
 */
export default function KLineChart({ kline = [], signals = [], height = 400 }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || kline.length === 0) return

    // 清理旧图表
    if (chartRef.current) {
      chartRef.current.remove()
      chartRef.current = null
    }

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: '#ccc' },
      timeScale: {
        borderColor: '#ccc',
        timeVisible: false,
      },
    })

    chartRef.current = chart

    // K 线系列
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#ef5350',
      downColor: '#26a69a',
      borderUpColor: '#ef5350',
      borderDownColor: '#26a69a',
      wickUpColor: '#ef5350',
      wickDownColor: '#26a69a',
    })

    const candleData = kline.map((item) => ({
      time: item.date,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }))
    candleSeries.setData(candleData)

    // 信号标注
    if (signals.length > 0) {
      const markers = signals
        .map((sig) => ({
          time: sig.date,
          position: sig.type === 'BUY' ? 'belowBar' : 'aboveBar',
          color: sig.type === 'BUY' ? '#26a69a' : '#ef5350',
          shape: sig.type === 'BUY' ? 'arrowUp' : 'arrowDown',
          text: `${sig.type === 'BUY' ? '买' : '卖'}(${sig.indicator})`,
        }))
        .sort((a, b) => (a.time > b.time ? 1 : -1))

      candleSeries.setMarkers(markers)
    }

    // 自适应宽度
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    // 缩放到数据范围
    chart.timeScale().fitContent()

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
    }
  }, [kline, signals, height])

  if (kline.length === 0) {
    return (
      <div className="flex items-center justify-center bg-gray-50 rounded" style={{ height }}>
        <span className="text-gray-400">暂无数据</span>
      </div>
    )
  }

  return <div ref={containerRef} className="w-full rounded overflow-hidden" />
}
