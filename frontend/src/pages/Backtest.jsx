/**
 * 策略回测页面
 * - Tab 1: 策略库（一键运行内置策略）
 * - Tab 2: 自定义回测（自然语言描述）
 */

import { useState, useCallback, useEffect } from 'react'
import { runBacktest, getStrategyList, runStrategy } from '../services/api'
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

/** 分类颜色 */
const CATEGORY_COLORS = {
  '动量': 'bg-orange-100 text-orange-700',
  '趋势': 'bg-blue-100 text-blue-700',
  '价值': 'bg-green-100 text-green-700',
  '多因子': 'bg-purple-100 text-purple-700',
  '事件驱动': 'bg-red-100 text-red-700',
  '均值回归': 'bg-yellow-100 text-yellow-700',
  '风险平价': 'bg-gray-100 text-gray-700',
}

export default function Backtest() {
  const [tab, setTab] = useState('library') // 'library' | 'custom'

  // ========== 策略库状态 ==========
  const [strategies, setStrategies] = useState([])
  const [selectedStrategy, setSelectedStrategy] = useState(null)
  const [strategyLoading, setStrategyLoading] = useState(false)

  // ========== 自定义回测状态 ==========
  const [strategyDesc, setStrategyDesc] = useState('MACD 金叉买入，死叉卖出')
  const [tsCode, setTsCode] = useState('000001.SZ')
  const [startDate, setStartDate] = useState('2021-07-01')
  const [endDate, setEndDate] = useState('2026-07-01')
  const [initialCapital, setInitialCapital] = useState(1000000)
  const [benchmark, setBenchmark] = useState('000300.SH')
  const [commissionRate, setCommissionRate] = useState(0.0003)
  const [slippage, setSlippage] = useState(0.001)

  // ========== 共享状态 ==========
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  // 加载策略列表
  useEffect(() => {
    getStrategyList()
      .then((data) => setStrategies(data || []))
      .catch(() => {})
  }, [])

  /** 运行策略库策略 */
  const handleRunStrategy = useCallback(async (key) => {
    setStrategyLoading(true)
    setLoading(true)
    setError('')
    setResult(null)

    try {
      const data = await runStrategy(key, {
        start_date: startDate.replace(/-/g, ''),
        end_date: endDate.replace(/-/g, ''),
        initial_cash: initialCapital,
      })
      setResult(data)
    } catch (e) {
      setError(e.message || '回测失败')
    } finally {
      setLoading(false)
      setStrategyLoading(false)
    }
  }, [startDate, endDate, initialCapital])

  /** 执行自定义回测 */
  const handleRunCustom = useCallback(async () => {
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
      const data = await runBacktest({
        strategy_description: strategyDesc,
        ts_code: tsCode,
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
        benchmark,
        commission_rate: commissionRate,
        slippage,
      })
      setResult(data)
    } catch (e) {
      setError(e.message || '请求失败')
    } finally {
      setLoading(false)
    }
  }, [strategyDesc, tsCode, startDate, endDate, initialCapital, benchmark, commissionRate, slippage])

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        {/* 标题 + Tab */}
        <div className="flex items-center gap-4">
          <h1 className="text-xl md:text-2xl font-bold text-gray-800">策略回测</h1>
          <div className="flex bg-gray-200 rounded-lg p-0.5">
            <button
              onClick={() => setTab('library')}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                tab === 'library' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-600'
              }`}
            >
              策略库
            </button>
            <button
              onClick={() => setTab('custom')}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                tab === 'custom' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-600'
              }`}
            >
              自定义
            </button>
          </div>
        </div>

        {/* ========== 策略库 Tab ========== */}
        {tab === 'library' && (
          <div className="space-y-4">
            {/* 日期参数 */}
            <div className="bg-white rounded-lg shadow p-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">开始日期</label>
                  <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">结束日期</label>
                  <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">初始资金</label>
                  <input type="number" value={initialCapital} onChange={(e) => setInitialCapital(Number(e.target.value))}
                    min={10000} step={10000}
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                </div>
              </div>
            </div>

            {/* 策略卡片列表 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {strategies.map((s) => (
                <div key={s.key} className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="font-semibold text-gray-800">{s.name}</h3>
                      <span className={`inline-block text-xs px-2 py-0.5 rounded mt-1 ${CATEGORY_COLORS[s.category] || 'bg-gray-100 text-gray-600'}`}>
                        {s.category}
                      </span>
                    </div>
                    <button
                      onClick={() => handleRunStrategy(s.key)}
                      disabled={loading}
                      className="bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 text-white text-xs px-3 py-1.5 rounded transition-colors shrink-0"
                    >
                      {strategyLoading && selectedStrategy === s.key ? '运行中...' : '运行'}
                    </button>
                  </div>
                  <p className="text-sm text-gray-600 mb-2">{s.description}</p>
                  {s.suitable && (
                    <p className="text-xs text-gray-400">适用：{s.suitable}</p>
                  )}
                  {/* 参数预览 */}
                  {s.params && Object.keys(s.params).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {Object.entries(s.params).slice(0, 4).map(([k, v]) => (
                        <span key={k} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                          {v.label}: {v.default}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ========== 自定义 Tab ========== */}
        {tab === 'custom' && (
          <div className="bg-white rounded-lg shadow p-4 space-y-4">
            {/* 策略描述 */}
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">策略描述</label>
              <textarea
                value={strategyDesc}
                onChange={(e) => setStrategyDesc(e.target.value)}
                placeholder="用自然语言描述你的交易策略，如：MACD 金叉买入，死叉卖出"
                rows={2}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
              />
              <div className="flex flex-wrap gap-2 mt-2">
                {STRATEGY_EXAMPLES.map((ex) => (
                  <button key={ex} onClick={() => setStrategyDesc(ex)}
                    className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-500 hover:border-blue-400 hover:text-blue-500 transition-colors">
                    {ex}
                  </button>
                ))}
              </div>
            </div>

            {/* 参数配置 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">股票代码</label>
                <input type="text" value={tsCode} onChange={(e) => setTsCode(e.target.value)} placeholder="000001.SZ"
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">开始日期</label>
                <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">结束日期</label>
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">初始资金</label>
                <input type="number" value={initialCapital} onChange={(e) => setInitialCapital(Number(e.target.value))}
                  min={10000} step={10000}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">基准指数</label>
                <select value={benchmark} onChange={(e) => setBenchmark(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
                  {BENCHMARK_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">佣金率</label>
                <input type="number" value={commissionRate} onChange={(e) => setCommissionRate(Number(e.target.value))}
                  min={0} step={0.0001}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">滑点</label>
                <input type="number" value={slippage} onChange={(e) => setSlippage(Number(e.target.value))}
                  min={0} step={0.001}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button onClick={handleRunCustom} disabled={loading}
                className="bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 text-white text-sm px-6 py-2 rounded transition-colors">
                {loading ? '回测中...' : '开始回测'}
              </button>
              {error && <span className="text-red-500 text-sm">{error}</span>}
            </div>
          </div>
        )}

        {/* ========== 回测结果（共用） ========== */}
        {result && (
          <>
            {result.metrics && (
              <div className="bg-white rounded-lg shadow p-4">
                <h2 className="text-sm font-semibold text-gray-700 mb-3">核心指标</h2>
                <MetricsCards metrics={result.metrics} />
                {result.metrics && (
                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-500">
                    <span>初始资金: ¥{result.metrics.initial_capital?.toLocaleString()}</span>
                    <span>最终资产: ¥{result.metrics.final_value?.toLocaleString()}</span>
                    <span>波动率: {result.metrics.volatility}%</span>
                    <span>平均持仓: {result.metrics.avg_holding_days} 天</span>
                  </div>
                )}
              </div>
            )}

            {result.equity_curve && result.equity_curve.length > 0 && (
              <div className="bg-white rounded-lg shadow p-4">
                <h2 className="text-sm font-semibold text-gray-700 mb-3">收益曲线</h2>
                <EquityCurveChart data={result.equity_curve} height={400} />
              </div>
            )}

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
