/**
 * Axios 封装 - 统一请求/响应处理
 * 响应格式: { code: 0, data: ..., msg: "" }
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 后续可在此添加 token 等认证信息
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - 统一处理响应格式 {code, data, msg}
api.interceptors.response.use(
  (response) => {
    const { data } = response
    // 后端已返回统一格式 {code, data, msg}
    if (data.code === 0) {
      return data.data
    }
    // 业务错误，抛出包含 msg 的错误
    const error = new Error(data.msg || '请求失败')
    error.code = data.code
    return Promise.reject(error)
  },
  (error) => {
    // HTTP 错误（网络异常、超时、服务端错误等）
    if (error.response) {
      const { status } = error.response
      const errorMap = {
        400: '请求参数错误',
        401: '未授权，请重新登录',
        403: '拒绝访问',
        404: '请求的资源不存在',
        500: '服务器内部错误',
        502: '网关错误',
        503: '服务不可用',
      }
      error.message = errorMap[status] || `HTTP 错误 ${status}`
    } else if (error.code === 'ECONNABORTED') {
      error.message = '请求超时，请稍后重试'
    } else {
      error.message = '网络异常，请检查网络连接'
    }
    return Promise.reject(error)
  }
)

// ---- 选股相关 ----

/** 解析选股意图 */
export function parseScreeningIntent(data) {
  return api.post('/screening/parse', data)
}

/** 执行选股筛选 */
export function searchStocks(data) {
  return api.post('/screening/search', data)
}

// ---- 回测相关 ----

/** 创建回测任务 */
export function runBacktest(data) {
  return api.post('/backtest/run', data)
}

/** 查询回测结果 */
export function getBacktestResult(taskId) {
  return api.get(`/backtest/result/${taskId}`)
}

/** 查询回测历史列表 */
export function listBacktestResults(params) {
  return api.get('/backtest/list', { params })
}

// ---- 信号相关 ----

/** 生成信号 */
export function generateSignals(data) {
  return api.post('/signal/generate', data)
}

/** 获取信号列表 */
export function listSignals(params) {
  return api.get('/signal/list', { params })
}

// ---- 归因分析 ----

/** 收益归因分析 */
export function returnAttribution(data) {
  return api.post('/attribution/return', data)
}

/** 因子归因分析 */
export function factorAttribution(data) {
  return api.post('/attribution/factor', data)
}

// ---- 策略库 ----

/** 获取策略列表 */
export function getStrategyList(params) {
  return api.get('/backtest/strategies', { params })
}

/** 获取策略详情 */
export function getStrategyDetail(key) {
  return api.get(`/backtest/strategies/${key}`)
}

/** 运行策略 */
export function runStrategy(key, params) {
  return api.post(`/backtest/strategies/${key}/run`, params)
}

// ---- 因子系统 ----

/** 获取因子列表 */
export function getFactorList() {
  return api.get('/factor/list')
}

/** 因子测试 */
export function testFactor(data) {
  return api.post('/factor/test', data)
}

/** 多因子评分 */
export function scoreFactors(data) {
  return api.post('/factor/score', data)
}

// ---- 交易相关 ----

/** 启动交易引擎 */
export function startTradingEngine() {
  return api.post('/trading/start')
}

/** 停止交易引擎 */
export function stopTradingEngine() {
  return api.post('/trading/stop')
}

/** 获取引擎状态 */
export function getTradingStatus() {
  return api.get('/trading/status')
}

/** 查询账户资金 */
export function getTradingAccount() {
  return api.get('/trading/account')
}

/** 查询持仓 */
export function getTradingPositions() {
  return api.get('/trading/positions')
}

/** 手动下单 */
export function placeTradingOrder(data) {
  return api.post('/trading/order', data)
}

/** 查询订单列表 */
export function getTradingOrders(params) {
  return api.get('/trading/orders', { params })
}

/** 查询待确认信号 */
export function getTradingSignals() {
  return api.get('/trading/signals')
}

/** 确认信号 */
export function confirmTradingSignal(index) {
  return api.post(`/trading/signals/${index}/confirm`)
}

/** 触发风控扫描 */
export function scanTradingRisk() {
  return api.post('/trading/risk/scan')
}

/** 获取风控状态 */
export function getTradingRiskStatus() {
  return api.get('/trading/risk/status')
}

/** 更新风控配置 */
export function updateTradingRiskConfig(data) {
  return api.put('/trading/risk/config', data)
}

export default api
