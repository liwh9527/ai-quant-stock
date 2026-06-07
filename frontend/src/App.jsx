import { useState } from 'react'
import Signal from './pages/Signal'
import Backtest from './pages/Backtest'
import Screening from './pages/Screening'

const PAGES = {
  screening: { label: '自然语言选股', component: Screening },
  signal: { label: '买卖信号', component: Signal },
  backtest: { label: '策略回测', component: Backtest },
}

function App() {
  const [currentPage, setCurrentPage] = useState('screening')

  const PageComponent = PAGES[currentPage]?.component

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部导航 */}
      <nav className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
          <h1 className="text-lg font-bold text-gray-800 shrink-0">
            AI 量化选股
          </h1>
          <div className="flex gap-2 overflow-x-auto">
            {Object.entries(PAGES).map(([key, { label }]) => (
              <button
                key={key}
                onClick={() => setCurrentPage(key)}
                className={`px-3 py-1 text-sm rounded whitespace-nowrap transition-colors ${
                  currentPage === key
                    ? 'bg-blue-500 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* 页面内容 */}
      {PageComponent && <PageComponent />}
    </div>
  )
}

export default App
