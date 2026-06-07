/** API 请求封装 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * 通用请求方法
 */
async function request(url, options = {}) {
  const res = await fetch(`${BASE_URL}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`请求失败: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

/**
 * POST JSON 请求
 */
export function post(url, data) {
  return request(url, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/**
 * GET 请求
 */
export function get(url, params = {}) {
  const qs = new URLSearchParams(params).toString()
  const full = qs ? `${url}?${qs}` : url
  return request(full)
}

/** 生成信号 */
export function generateSignals(data) {
  return post('/api/signal/generate', data)
}

/** 获取信号列表 */
export function listSignals(params) {
  return get('/api/signal/list', params)
}

/** 创建回测任务 */
export function runBacktest(data) {
  return post('/api/backtest/run', data)
}

/** 查询回测结果 */
export function getBacktestResult(taskId) {
  return get(`/api/backtest/result/${taskId}`)
}

/** 查询回测历史列表 */
export function listBacktestResults(params) {
  return get('/api/backtest/list', params)
}
