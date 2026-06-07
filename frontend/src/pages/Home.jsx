/**
 * 首页 - 入口页面
 */
import { Link } from 'react-router-dom'

function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* 头部导航 */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">AI 量化选股</h1>
          <nav className="flex gap-4 text-sm">
            <Link to="/" className="text-blue-600 font-medium">首页</Link>
            <Link to="/screening" className="text-gray-600 hover:text-blue-600">选股</Link>
            <Link to="/backtest" className="text-gray-600 hover:text-blue-600">回测</Link>
            <Link to="/signal" className="text-gray-600 hover:text-blue-600">信号</Link>
          </nav>
        </div>
      </header>

      {/* 主内容 */}
      <main className="max-w-7xl mx-auto px-4 py-12">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            用自然语言，发现投资机会
          </h2>
          <p className="text-gray-600 max-w-2xl mx-auto">
            AI 辅助量化选股工具，支持自然语言选股、策略回测、买卖信号生成
          </p>
        </div>

        {/* 功能入口卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
          <Link
            to="/screening"
            className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow"
          >
            <div className="text-2xl mb-3">🔍</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">智能选股</h3>
            <p className="text-sm text-gray-600">
              用自然语言描述选股条件，AI 自动解析并筛选股票
            </p>
          </Link>

          <Link
            to="/backtest"
            className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow"
          >
            <div className="text-2xl mb-3">📊</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">策略回测</h3>
            <p className="text-sm text-gray-600">
              验证选股策略的历史表现，查看收益曲线和关键指标
            </p>
          </Link>

          <Link
            to="/signal"
            className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow"
          >
            <div className="text-2xl mb-3">📈</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">买卖信号</h3>
            <p className="text-sm text-gray-600">
              基于技术指标生成实时买卖信号，K 线图可视化展示
            </p>
          </Link>
        </div>
      </main>
    </div>
  )
}

export default Home
