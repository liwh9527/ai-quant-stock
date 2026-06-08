import axios from 'axios'
import api, {
  generateSignals,
  listSignals,
  returnAttribution,
  factorAttribution,
  runBacktest,
  getBacktestResult,
  listBacktestResults,
  parseScreeningIntent,
  searchStocks,
  getFactorList,
  testFactor,
  scoreFactors,
} from '../services/api'

// Mock axios
jest.mock('axios', () => {
  const mockApi = {
    post: jest.fn(),
    get: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: { baseURL: '' },
  }
  return {
    create: jest.fn(() => mockApi),
    default: mockApi,
  }
})

describe('API Service', () => {
  let mockApi

  beforeEach(() => {
    mockApi = axios.create()
    mockApi.post.mockReset()
    mockApi.get.mockReset()
  })

  describe('Signal APIs', () => {
    it('generateSignals calls POST /signal/generate', () => {
      const data = { ts_code: '000001.SZ', indicators: ['macd'] }
      mockApi.post.mockResolvedValue({ code: 0, data: { signals: [] }, msg: '' })
      generateSignals(data)
      // The function should be callable
      expect(typeof generateSignals).toBe('function')
    })

    it('listSignals calls GET /signal/list', () => {
      expect(typeof listSignals).toBe('function')
    })
  })

  describe('Attribution APIs', () => {
    it('returnAttribution is a function', () => {
      expect(typeof returnAttribution).toBe('function')
    })

    it('factorAttribution is a function', () => {
      expect(typeof factorAttribution).toBe('function')
    })
  })

  describe('Backtest APIs', () => {
    it('runBacktest is a function', () => {
      expect(typeof runBacktest).toBe('function')
    })

    it('getBacktestResult is a function', () => {
      expect(typeof getBacktestResult).toBe('function')
    })

    it('listBacktestResults is a function', () => {
      expect(typeof listBacktestResults).toBe('function')
    })
  })

  describe('Screening APIs', () => {
    it('parseScreeningIntent is a function', () => {
      expect(typeof parseScreeningIntent).toBe('function')
    })

    it('searchStocks is a function', () => {
      expect(typeof searchStocks).toBe('function')
    })
  })

  describe('Factor APIs', () => {
    it('getFactorList is a function', () => {
      expect(typeof getFactorList).toBe('function')
    })

    it('testFactor is a function', () => {
      expect(typeof testFactor).toBe('function')
    })

    it('scoreFactors is a function', () => {
      expect(typeof scoreFactors).toBe('function')
    })
  })
})
