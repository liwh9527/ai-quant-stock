/**
 * 应用入口 - 路由配置
 */
import { Routes, Route, NavLink } from 'react-router-dom'
import Home from './pages/Home'
import Screening from './pages/Screening'
import Backtest from './pages/Backtest'
import Signal from './pages/Signal'
import Trading from './pages/Trading'

const NAV_ITEMS = [
  { path: '/', label: '首页' },
  { path: '/screening', label: '选股' },
  { path: '/backtest', label: '回测' },
  { path: '/signal', label: '信号' },
  { path: '/trading', label: '交易' },
]

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部导航 */}
      <nav className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
          <h1 className="text-lg font-bold text-gray-800 shrink-0">
            AI 量化选股
          </h1>
          <div className="flex gap-2 overflow-x-auto">
            {NAV_ITEMS.map(({ path, label }) => (
              <NavLink
                key={path}
                to={path}
                end={path === '/'}
                className={({ isActive }) =>
                  `px-3 py-1 text-sm rounded whitespace-nowrap transition-colors ${
                    isActive
                      ? 'bg-blue-500 text-white'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </div>
        </div>
      </nav>

      {/* 路由出口 */}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/screening" element={<Screening />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/signal" element={<Signal />} />
        <Route path="/trading" element={<Trading />} />
      </Routes>
    </div>
  )
}

export default App
