/**
 * 交易面板
 * - 引擎状态控制（启停）
 * - 账户资金概览
 * - Tab 1: 持仓总览
 * - Tab 2: 今日订单
 * - Tab 3: 风控状态
 */

import { useState, useEffect, useCallback } from 'react'
import React from 'react'
import {
  getTradingStatus,
  startTradingEngine,
  stopTradingEngine,
  getTradingAccount,
  getTradingPositions,
  getTradingOrders,
  getTradingRiskStatus,
  placeTradingOrder,
  scanTradingRisk,
} from '../services/api'

const TABS = [
  { key: 'positions', label: '持仓总览' },
  { key: 'orders', label: '今日订单' },
  { key: 'risk', label: '风控状态' },
]

export default function Trading() {
  const [activeTab, setActiveTab] = useState('positions')
  const [engineStatus, setEngineStatus] = useState(null)
  const [account, setAccount] = useState(null)
  const [positions, setPositions] = useState([])
  const [orders, setOrders] = useState([])
  const [riskStatus, setRiskStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // 刷新引擎状态
  const refreshStatus = useCallback(async () => {
    try {
      const status = await getTradingStatus()
      setEngineStatus(status)
    } catch (e) {
      setEngineStatus({ running: false })
    }
  }, [])

  // 刷新账户和持仓
  const refreshData = useCallback(async () => {
    try {
      const [acc, pos, ord] = await Promise.all([
        getTradingAccount().catch(() => null),
        getTradingPositions().catch(() => []),
        getTradingOrders({}).catch(() => []),
      ])
      setAccount(acc)
      setPositions(pos || [])
      setOrders(ord || [])
    } catch (e) {
      // ignore
    }
  }, [])

  // 初始加载
  useEffect(() => {
    refreshStatus()
  }, [refreshStatus])

  // 引擎运行时自动刷新
  useEffect(() => {
    if (!engineStatus?.running) return
    refreshData()
    const timer = setInterval(refreshData, 10000) // 10秒刷新
    return () => clearInterval(timer)
  }, [engineStatus?.running, refreshData])

  // 启动引擎
  const handleStart = async () => {
    setLoading(true)
    setError('')
    try {
      await startTradingEngine()
      await refreshStatus()
      await refreshData()
    } catch (e) {
      setError(e.message || '启动失败')
    }
    setLoading(false)
  }

  // 停止引擎
  const handleStop = async () => {
    setLoading(true)
    setError('')
    try {
      await stopTradingEngine()
      await refreshStatus()
    } catch (e) {
      setError(e.message || '停止失败')
    }
    setLoading(false)
  }

  // 风控扫描
  const handleRiskScan = async () => {
    setLoading(true)
    try {
      const result = await scanTradingRisk()
      if (result.triggered > 0) {
        alert(`触发 ${result.triggered} 笔止损/止盈订单`)
      } else {
        alert('风控扫描完成，无触发')
      }
      await refreshData()
    } catch (e) {
      setError(e.message || '扫描失败')
    }
    setLoading(false)
  }

  const isRunning = engineStatus?.running

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
      {/* 引擎控制栏 */}
      <div className="bg-white rounded-lg shadow p-4 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
          <span className="font-medium text-gray-800">
            交易引擎: {isRunning ? '运行中' : '已停止'}
          </span>
        </div>
        <div className="flex gap-2">
          {isRunning ? (
            <>
              <button onClick={handleRiskScan} disabled={loading}
                className="px-4 py-1.5 text-sm bg-yellow-500 text-white rounded hover:bg-yellow-600 disabled:opacity-50">
                风控扫描
              </button>
              <button onClick={handleStop} disabled={loading}
                className="px-4 py-1.5 text-sm bg-red-500 text-white rounded hover:bg-red-600 disabled:opacity-50">
                停止
              </button>
            </>
          ) : (
            <button onClick={handleStart} disabled={loading}
              className="px-4 py-1.5 text-sm bg-green-500 text-white rounded hover:bg-green-600 disabled:opacity-50">
              {loading ? '启动中...' : '启动引擎'}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded text-sm">{error}</div>
      )}

      {/* 账户概览 */}
      {account && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label="总资产" value={account.total_assets} prefix="¥" />
          <MetricCard label="可用资金" value={account.available_cash} prefix="¥" />
          <MetricCard label="持仓市值" value={account.market_value} prefix="¥" />
          <MetricCard label="冻结资金" value={account.frozen_cash} prefix="¥" />
        </div>
      )}

      {/* Tab 切换 */}
      <div className="bg-white rounded-lg shadow">
        <div className="flex border-b">
          {TABS.map(tab => (
            <button key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-500 hover:text-gray-700'
              }`}>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-4">
          {activeTab === 'positions' && (
            <PositionsTable positions={positions} />
          )}
          {activeTab === 'orders' && (
            <OrdersTable orders={orders} />
          )}
          {activeTab === 'risk' && (
            <RiskPanel riskStatus={riskStatus} onRefresh={async () => {
              const s = await getTradingRiskStatus().catch(() => null)
              setRiskStatus(s)
            }} />
          )}
        </div>
      </div>
    </div>
  )
}

// ---- 子组件 ----

function MetricCard({ label, value, prefix = '' }) {
  const formatted = typeof value === 'number'
    ? `${prefix}${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : '-'
  return (
    <div className="bg-white rounded-lg shadow p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-semibold text-gray-800 mt-1">{formatted}</div>
    </div>
  )
}

function PositionsTable({ positions }) {
  if (!positions.length) {
    return <div className="text-center text-gray-400 py-8">暂无持仓</div>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 border-b">
            <th className="py-2 pr-4">股票</th>
            <th className="py-2 pr-4 text-right">持仓</th>
            <th className="py-2 pr-4 text-right">可卖</th>
            <th className="py-2 pr-4 text-right">成本价</th>
            <th className="py-2 pr-4 text-right">现价</th>
            <th className="py-2 pr-4 text-right">盈亏</th>
            <th className="py-2 pr-4 text-right">盈亏%</th>
            <th className="py-2 text-right">天数</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const pnlClass = pos.profit_pct >= 0 ? 'text-red-600' : 'text-green-600'
            return (
              <tr key={pos.ts_code} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-4 font-medium">{pos.ts_code}</td>
                <td className="py-2 pr-4 text-right">{pos.shares}</td>
                <td className="py-2 pr-4 text-right">{pos.available_shares}</td>
                <td className="py-2 pr-4 text-right">{pos.buy_price?.toFixed(2)}</td>
                <td className="py-2 pr-4 text-right">{pos.current_price?.toFixed(2)}</td>
                <td className={`py-2 pr-4 text-right ${pnlClass}`}>
                  {pos.profit_amount?.toFixed(2)}
                </td>
                <td className={`py-2 pr-4 text-right ${pnlClass}`}>
                  {(pos.profit_pct * 100)?.toFixed(2)}%
                </td>
                <td className="py-2 text-right">{pos.hold_days}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function OrdersTable({ orders }) {
  if (!orders.length) {
    return <div className="text-center text-gray-400 py-8">今日暂无订单</div>
  }

  const statusColor = {
    FILLED: 'text-green-600',
    SUBMITTED: 'text-blue-600',
    PENDING: 'text-yellow-600',
    CANCELLED: 'text-gray-500',
    REJECTED: 'text-red-600',
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 border-b">
            <th className="py-2 pr-4">时间</th>
            <th className="py-2 pr-4">股票</th>
            <th className="py-2 pr-4">方向</th>
            <th className="py-2 pr-4 text-right">价格</th>
            <th className="py-2 pr-4 text-right">数量</th>
            <th className="py-2 pr-4 text-right">成交价</th>
            <th className="py-2 pr-4">状态</th>
            <th className="py-2">原因</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o, i) => (
            <tr key={i} className="border-b hover:bg-gray-50">
              <td className="py-2 pr-4 text-xs text-gray-500">{o.created_at?.slice(11, 19)}</td>
              <td className="py-2 pr-4 font-medium">{o.ts_code}</td>
              <td className={`py-2 pr-4 font-medium ${o.action === 'BUY' ? 'text-red-600' : 'text-green-600'}`}>
                {o.action === 'BUY' ? '买入' : '卖出'}
              </td>
              <td className="py-2 pr-4 text-right">{o.price?.toFixed(2)}</td>
              <td className="py-2 pr-4 text-right">{o.shares}</td>
              <td className="py-2 pr-4 text-right">{o.filled_price?.toFixed(2) || '-'}</td>
              <td className={`py-2 pr-4 ${statusColor[o.status] || ''}`}>
                {o.status}
              </td>
              <td className="py-2 text-xs text-gray-500 max-w-[200px] truncate">{o.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RiskPanel({ riskStatus, onRefresh }) {
  useEffect(() => { onRefresh() }, [onRefresh])

  if (!riskStatus?.config) {
    return <div className="text-center text-gray-400 py-8">暂无风控数据</div>
  }

  const { config, state } = riskStatus

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <RiskItem label="最大持仓" value={`${config.max_positions} 只`} />
        <RiskItem label="单只仓位上限" value={`${(config.max_single_position_pct * 100).toFixed(0)}%`} />
        <RiskItem label="总仓位上限" value={`${(config.max_total_position_pct * 100).toFixed(0)}%`} />
        <RiskItem label="止损线" value={`${(config.stop_loss_pct * 100).toFixed(0)}%`} color="text-red-600" />
        <RiskItem label="移动止损" value={`${(config.trailing_stop_pct * 100).toFixed(0)}%`} color="text-orange-500" />
        <RiskItem label="止盈线" value={`+${(config.take_profit_pct * 100).toFixed(0)}%`} color="text-green-600" />
        <RiskItem label="组合回撤上限" value={`${(config.max_drawdown_pct * 100).toFixed(0)}%`} color="text-red-600" />
        <RiskItem label="连续亏损暂停" value={`${config.consecutive_loss_pause} 次`} />
        <RiskItem label="ST股过滤" value={config.block_st ? '开启' : '关闭'} />
      </div>

      <div className="border-t pt-3">
        <h4 className="text-sm font-medium text-gray-700 mb-2">运行状态</h4>
        <div className="grid grid-cols-3 gap-3">
          <RiskItem label="连续亏损" value={`${state.consecutive_losses} 次`} />
          <RiskItem label="历史最高净值" value={`¥${state.peak_value?.toLocaleString()}`} />
          <RiskItem label="暂停状态" value={state.pause_until || '正常'} />
        </div>
      </div>
    </div>
  )
}

function RiskItem({ label, value, color = 'text-gray-800' }) {
  return (
    <div className="bg-gray-50 rounded p-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-sm font-semibold ${color} mt-0.5`}>{value}</div>
    </div>
  )
}
