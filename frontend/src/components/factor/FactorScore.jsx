/**
 * 多因子评分组件
 * - 评分配置（因子权重、Top N）
 * - 评分统计概要
 * - 排名表格（桌面端）/ 卡片（移动端）
 */

import { useState, useCallback } from 'react'
import { scoreFactors } from '../../services/api'
import { MetricCard, RankBadge } from './shared'

export default function FactorScore({ factors }) {
  const [scoreList, setScoreList] = useState([
    { name: 'roe', weight: 0.4 },
    { name: 'pe', weight: -0.3 },
    { name: 'momentum_20d', weight: 0.3 },
  ])
  const [topN, setTopN] = useState(20)
  const [result, setResult] = useState(null)
  const [scoring, setScoring] = useState(false)
  const [error, setError] = useState('')

  const handleScore = useCallback(async () => {
    setScoring(true)
    setError('')
    setResult(null)
    try {
      const res = await scoreFactors({ factors: scoreList, top_n: topN })
      if (res.code === 0) {
        setResult(res.data)
      } else {
        setError(res.msg || '多因子评分失败')
      }
    } catch (e) {
      setError(e.message || '请求失败')
    } finally {
      setScoring(false)
    }
  }, [scoreList, topN])

  const addFactor = () => {
    const used = scoreList.map(f => f.name)
    const avail = factors.find(f => !used.includes(f.key))
    if (avail) setScoreList([...scoreList, { name: avail.key, weight: 0.2 }])
  }
  const removeFactor = (i) => setScoreList(scoreList.filter((_, idx) => idx !== i))
  const updateFactor = (i, field, value) => {
    setScoreList(scoreList.map((f, idx) =>
      idx === i ? { ...f, [field]: field === 'weight' ? Number(value) : value } : f
    ))
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 text-sm rounded px-4 py-2">
          {error}
        </div>
      )}

      {/* 评分配置 */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-sm font-medium text-gray-700 mb-3">评分配置</h2>
        <div className="space-y-2">
          {scoreList.map((sf, index) => (
            <div key={index} className="flex items-center gap-2">
              <select value={sf.name} onChange={e => updateFactor(index, 'name', e.target.value)}
                className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
                {factors.map(f => (
                  <option key={f.key} value={f.key}>{f.name}</option>
                ))}
              </select>
              <span className="text-xs text-gray-500">权重:</span>
              <input type="number" step="0.1" value={sf.weight}
                onChange={e => updateFactor(index, 'weight', e.target.value)}
                className="w-20 border border-gray-300 rounded px-2 py-1.5 text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-400" />
              <span className="text-xs text-gray-400">(正=正向, 负=反向)</span>
              {scoreList.length > 1 && (
                <button onClick={() => removeFactor(index)} className="text-red-400 hover:text-red-600 text-sm">删除</button>
              )}
            </div>
          ))}
          <div className="flex items-center gap-3 pt-2">
            <button onClick={addFactor} disabled={scoreList.length >= factors.length}
              className="text-sm text-blue-500 hover:text-blue-700 disabled:text-gray-300">
              + 添加因子
            </button>
            <span className="text-xs text-gray-400">|</span>
            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-500">返回前</span>
              <input type="number" min="1" max="100" value={topN}
                onChange={e => setTopN(Number(e.target.value))}
                className="w-14 border border-gray-300 rounded px-2 py-1 text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-400" />
              <span className="text-xs text-gray-500">只</span>
            </div>
            <button onClick={handleScore} disabled={scoring}
              className="ml-auto bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 text-white text-sm px-4 py-1.5 rounded transition-colors">
              {scoring ? '评分中...' : '开始评分'}
            </button>
          </div>
        </div>
      </div>

      {/* 评分结果 */}
      {result && (
        <>
          {result.score_stats && (
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-sm font-medium text-gray-700 mb-3">评分统计</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricCard label="参与股票数" value={result.total} />
                <MetricCard label="平均分" value={result.score_stats.mean} />
                <MetricCard label="标准差" value={result.score_stats.std} />
                <MetricCard label="最高分" value={result.score_stats.max} />
              </div>
            </div>
          )}

          {/* 排名表格 */}
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="px-4 py-3 border-b">
              <h2 className="text-sm font-semibold text-gray-700">
                评分排名（前 {result.top?.length || 0} 只）
              </h2>
            </div>

            {/* 桌面端表格 */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500">
                  <tr>
                    <th className="px-4 py-2 text-center">排名</th>
                    <th className="px-4 py-2 text-left">代码</th>
                    <th className="px-4 py-2 text-left">名称</th>
                    <th className="px-4 py-2 text-right">综合得分</th>
                    {scoreList.map(sf => {
                      const info = factors.find(f => f.key === sf.name)
                      return <th key={sf.name} className="px-4 py-2 text-right">{info?.name || sf.name}</th>
                    })}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(result.top || []).map(item => (
                    <tr key={item.ts_code} className="hover:bg-gray-50">
                      <td className="px-4 py-2 text-center font-medium"><RankBadge rank={item.rank} /></td>
                      <td className="px-4 py-2 font-mono text-gray-800">{item.ts_code}</td>
                      <td className="px-4 py-2 text-gray-800">{item.name}</td>
                      <td className="px-4 py-2 text-right font-medium text-blue-600">{item.total_score}</td>
                      {scoreList.map(sf => (
                        <td key={sf.name} className="px-4 py-2 text-right text-gray-600">
                          {item[sf.name] != null ? item[sf.name] : '-'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 移动端卡片 */}
            <div className="md:hidden divide-y divide-gray-100">
              {(result.top || []).map(item => (
                <div key={item.ts_code} className="px-4 py-3">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <RankBadge rank={item.rank} />
                      <span className="font-mono text-sm text-gray-800">{item.ts_code}</span>
                      <span className="text-sm font-medium text-gray-800">{item.name}</span>
                    </div>
                    <span className="text-sm font-medium text-blue-600">{item.total_score}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                    {scoreList.map(sf => {
                      const info = factors.find(f => f.key === sf.name)
                      return (
                        <span key={sf.name}>
                          {info?.name || sf.name}: {item[sf.name] != null ? item[sf.name] : '-'}
                        </span>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {!result && !scoring && (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-400">
          配置因子权重后点击"开始评分"
        </div>
      )}
    </div>
  )
}
