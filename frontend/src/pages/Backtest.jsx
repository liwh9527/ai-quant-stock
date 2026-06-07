/**
 * 策略回测页面
 * - 策略描述输入
 * - 回测参数配置（日期、资金、基准）
 * - 收益曲线图表（ECharts）
 * - 指标卡片
 * - 交易记录列表
 */

import { useState, useCallback } from 'react'
import { runBacktest } from '../services/api'
import EquityCurveChart from '../components/EquityCurveChart'
import MetricsCards from '../components/MetricsCards'
import TradeList from '../components/TradeList'

/** 基准指数选项 */
const BENCHMARK_OPTIONS = [
  { value: '000300.SH', label: '沪深300' },
  { value: '000905.SH', label: '中证500' },
  { value: '000016.SH', label: '上证50' },
  { value: '399006.SZ', label: '创业板指' },
]

/** 策略示例 */
const STRATEGY_EXAMPLES = [
  'MACD 金叉买入，死叉卖出',
  'KDJ 金叉买入，死叉卖出',
  'RSI 低于30买入，高于70卖出',
  '20日均线上穿60日均线买入，下穿卖出',
]

export default function Backtest() {
  const [strategyDesc, setStrategyDesc] = useState('MACD 金叉买入，死叉卖出')
  const [tsCode, setTsCode] = useState('000001.SZ')
  const [startDate, setStartDate] = useState('2020-01-01')
  const [endDate, setEndDate] = useState('2024-12-31')
  const [initialCapital, setInitialCapital] = useState(100000)
  const [benchmark, setBenchmark] = useState('000300.SH')
  const [commissionRate, setCommissionRate] = useState(0.0003)
  const [slippage, setSlippage] = useState(0.001)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  /** 执行回测 */
  const handleRun = useCallback(async () => {
    if (!strategyDesc.trim()) {
      setError('请输入策略描述')
      return
    }
    if (!tsCode.trim()) {
      setError('请输入股票代码')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)

    try {
      const res = await runBacktest({
        strategy_description: strategyDesc,
        ts_code: tsCode,
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
        benchmark,
        commission_rate: commissionRate,
        slippage,
      })

      if (res.code === 0) {
        setResult(res.data)
      } else {
        setError(res.msg || '回测失败')
      }
    } catch (e) {
      setError(e.message || '请求失败，请检查后端是否启动')
    } finally {
      setLoading(false)
    }
  }, [
    strategyDesc, tsCode, startDate, endDate,
    initialCapital, benchmark, commissionRate, slippage,
  ])

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        {/* 标题 */}
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">策略回测</h1>

        {/* 策略配置 */}
        <div className="bg-white rounded-lg shadow p-4 space-y-4">
          {/* 策略描述 */}
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">
              策略描述
            </label>
            <textarea
              value={strategyDesc}
              onChange={(e) => setStrategyDesc(e.target.value)}
              placeholder="用自然语言描述你的交易策略，如：MACD 金叉买入，死叉卖出"
              rows={2}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
            />
            {/* 策略示例 */}
            <div className="flex flex-wrap gap-2 mt-2">
              {STRATEGY_EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => setStrategyDesc(ex)}
                  className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-500 hover:border-blue-400 hover:text-blue-500 transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* 参数配置行 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* 股票代码 */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                股票代码
              </label>
              <input
                type="text"
                value={tsCode}
                onChange={(e) => setTsCode(e.target.value)}
                placeholder="000001.SZ"
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>

            {/* 回测区间 */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                开始日期
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                结束日期
              </label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>

            {/* 初始资金 */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                初始资金
              </label>
              <input
                type="number"
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
                min={10000}
                step={10000}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
          </div>

          {/* 第二行参数 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* 基准 */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                基准指数
              </label>
              <select
                value={benchmark}
                onChange={(e) => setBenchmark(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                {BENCHMARK_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* 佣金率 */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                佣金率
              </label>
              <input
                type="number"
                value={commissionRate}
                onChange={(e) => setCommissionRate(Number(e.target.value))}
                min={0}
                step={0.0001}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>

            {/* 滑点 */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                滑点
              </label>
              <input
                type="number"
                value={slippage}
                onChange={(e) => setSlippage(Number(e.target.value))}
                min={0}
                step={0.001}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
          </div>

          {/* 执行按钮 */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleRun}
              disabled={loading}
              className="bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 text-white text-sm px-6 py-2 rounded transition-colors"
            >
              {loading ? '回测中...' : '开始回测'}
            </button>
            {error && (
              <span className="text-red-500 text-sm">{error}</span>
            )}
          </div>
        </div>

        {/* 回测结果 */}
        {result && (
          <>
            {/* 策略信息 */}
            {result.strategy_config && (
              <div className="bg-white rounded-lg shadow p-4">
                <h2 className="text-sm font-semibold text-gray-700 mb-2">
                  策略配置
                </h2>
                <p className="text-sm text-gray-600">
                  {result.strategy_config.description || strategyDesc}
                </p>
                {result.strategy_config.entry_rules && (
                  <div className="mt-2 text-xs text-gray-500">
                    <span className="font-medium">入场规则：</span>
                    {result.strategy_config.entry_rules
                      .map((r) => `${r.indicator.toUpperCase()} ${r.condition}`)
                      .join(' + ')}
                  </div>
                )}
              </div>
            )}

            {/* 指标卡片 */}
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-sm font-semibold text-gray-700 mb-3">
                核心指标
              </h2>
              <MetricsCards metrics={result.metrics} />
              {result.metrics && (
                <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-500">
                  <span>
                    初始资金: ¥{result.metrics.initial_capital?.toLocaleString()}
                  </span>
                  <span>
                    最终资产: ¥{result.metrics.final_value?.toLocaleString()}
                  </span>
                  <span>
                    波动率: {result.metrics.volatility}%
                  </span>
                  <span>
                    平均持仓: {result.metrics.avg_holding_days} 天
                  </span>
                </div>
              )}
            </div>

            {/* 收益曲线 */}
            {result.equity_curve && result.equity_curve.length > 0 && (
              <div className="bg-white rounded-lg shadow p-4">
                <h2 className="text-sm font-semibold text-gray-700 mb-3">
                  收益曲线
                </h2>
                <EquityCurveChart data={result.equity_curve} height={400} />
              </div>
            )}

            {/* 交易记录 */}
            {result.trades && result.trades.length > 0 && (
              <div className="bg-white rounded-lg shadow p-4">
                <h2 className="text-sm font-semibold text-gray-700 mb-3">
                  交易记录（共 {result.trades.length} 笔）
                </h2>
                <TradeList trades={result.trades} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
