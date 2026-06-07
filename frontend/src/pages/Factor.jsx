/**
 * 多因子系统页面
 * 整合因子库、因子测试、多因子评分三个 Tab
 */

import { useState, useEffect } from 'react'
import { getFactorList } from '../services/api'
import FactorList from '../components/factor/FactorList'
import FactorTest from '../components/factor/FactorTest'
import FactorScore from '../components/factor/FactorScore'

const TABS = [
  { key: 'list', label: '因子库' },
  { key: 'test', label: '因子测试' },
  { key: 'score', label: '多因子评分' },
]

export default function Factor() {
  const [factors, setFactors] = useState([])
  const [categories, setCategories] = useState([])
  const [activeCategory, setActiveCategory] = useState('全部')
  const [tab, setTab] = useState('list')
  const [testResult, setTestResult] = useState(null)

  useEffect(() => {
    getFactorList().then((res) => {
      if (res.code === 0) {
        setFactors(res.data.factors || [])
        setCategories(res.data.categories || [])
      }
    }).catch(() => {})
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">多因子系统</h1>

        {/* Tab 切换 */}
        <div className="flex gap-2 border-b">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'list' && (
          <FactorList
            factors={factors}
            categories={categories}
            activeCategory={activeCategory}
            onCategoryChange={setActiveCategory}
            testResult={testResult}
          />
        )}
        {tab === 'test' && <FactorTest factors={factors} onTestResult={setTestResult} />}
        {tab === 'score' && <FactorScore factors={factors} />}
      </div>
    </div>
  )
}
