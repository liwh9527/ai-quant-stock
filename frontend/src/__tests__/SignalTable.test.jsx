import { render, screen } from '@testing-library/react'
import SignalTable from '../components/SignalTable'

describe('SignalTable', () => {
  const mockSignals = [
    {
      date: '2024-02-15',
      type: 'BUY',
      indicator: 'macd',
      price: 10.5,
      strength: 0.3,
      reason: 'MACD 金叉，DIF 上穿 DEA',
    },
    {
      date: '2024-02-20',
      type: 'SELL',
      indicator: 'kdj',
      price: 11.2,
      strength: 0.6,
      reason: 'KDJ 死叉（J=85.2），K 下穿 D，超买区域',
    },
  ]

  it('renders nothing when signals is empty', () => {
    const { container } = render(<SignalTable signals={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when signals is not provided', () => {
    const { container } = render(<SignalTable />)
    expect(container.firstChild).toBeNull()
  })

  it('renders title with signal count', () => {
    render(<SignalTable signals={mockSignals} title="测试信号" />)
    expect(screen.getByText(/测试信号/)).toBeInTheDocument()
    expect(screen.getByText(/2 条/)).toBeInTheDocument()
  })

  it('renders default title', () => {
    render(<SignalTable signals={mockSignals} />)
    expect(screen.getByText(/信号列表/)).toBeInTheDocument()
  })

  it('renders signal dates', () => {
    render(<SignalTable signals={mockSignals} />)
    expect(screen.getByText('2024-02-15')).toBeInTheDocument()
    expect(screen.getByText('2024-02-20')).toBeInTheDocument()
  })

  it('renders BUY as 买入 with green style', () => {
    render(<SignalTable signals={[mockSignals[0]]} />)
    const badge = screen.getByText('买入')
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain('bg-green-100')
  })

  it('renders SELL as 卖出 with red style', () => {
    render(<SignalTable signals={[mockSignals[1]]} />)
    const badge = screen.getByText('卖出')
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain('bg-red-100')
  })

  it('renders indicator in uppercase', () => {
    render(<SignalTable signals={[mockSignals[0]]} />)
    expect(screen.getByText('macd')).toBeInTheDocument()
  })

  it('renders price and strength', () => {
    render(<SignalTable signals={[mockSignals[0]]} />)
    expect(screen.getByText('10.5')).toBeInTheDocument()
    expect(screen.getByText('0.3')).toBeInTheDocument()
  })

  it('renders reason text', () => {
    render(<SignalTable signals={mockSignals} />)
    expect(screen.getByText(/MACD 金叉/)).toBeInTheDocument()
    expect(screen.getByText(/KDJ 死叉/)).toBeInTheDocument()
  })

  it('renders correct number of rows', () => {
    render(<SignalTable signals={mockSignals} />)
    const rows = screen.getAllByRole('row')
    // 1 header row + 2 data rows
    expect(rows).toHaveLength(3)
  })
})
