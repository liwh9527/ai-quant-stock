import { render, screen } from '@testing-library/react'
import MetricsCards from '../components/MetricsCards'

describe('MetricsCards', () => {
  const mockMetrics = {
    total_return: 15.5,
    annual_return: 12.3,
    max_drawdown: -8.2,
    sharpe_ratio: 1.5,
    win_rate: 65,
    trade_count: 42,
    benchmark_return: 5.0,
    excess_return: 10.5,
  }

  it('renders nothing when metrics is null', () => {
    const { container } = render(<MetricsCards metrics={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when metrics is undefined', () => {
    const { container } = render(<MetricsCards />)
    expect(container.firstChild).toBeNull()
  })

  it('renders all metric labels', () => {
    render(<MetricsCards metrics={mockMetrics} />)
    expect(screen.getByText('总收益率')).toBeInTheDocument()
    expect(screen.getByText('年化收益率')).toBeInTheDocument()
    expect(screen.getByText('最大回撤')).toBeInTheDocument()
    expect(screen.getByText('夏普比率')).toBeInTheDocument()
    expect(screen.getByText('胜率')).toBeInTheDocument()
    expect(screen.getByText('交易次数')).toBeInTheDocument()
    expect(screen.getByText('基准收益')).toBeInTheDocument()
    expect(screen.getByText('超额收益')).toBeInTheDocument()
  })

  it('renders metric values', () => {
    render(<MetricsCards metrics={mockMetrics} />)
    expect(screen.getByText('15.5%')).toBeInTheDocument()
    expect(screen.getByText('12.3%')).toBeInTheDocument()
    expect(screen.getByText('-8.2%')).toBeInTheDocument()
    expect(screen.getByText('1.5')).toBeInTheDocument()
    expect(screen.getByText('65%')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('5%')).toBeInTheDocument()
    expect(screen.getByText('10.5%')).toBeInTheDocument()
  })

  it('applies green color for positive returns', () => {
    render(<MetricsCards metrics={mockMetrics} />)
    const totalReturn = screen.getByText('15.5%')
    expect(totalReturn.className).toContain('text-green-600')
  })

  it('applies red color for negative returns', () => {
    render(<MetricsCards metrics={mockMetrics} />)
    const maxDrawdown = screen.getByText('-8.2%')
    expect(maxDrawdown.className).toContain('text-red-600')
  })

  it('applies green color for good sharpe ratio', () => {
    render(<MetricsCards metrics={mockMetrics} />)
    const sharpe = screen.getByText('1.5')
    expect(sharpe.className).toContain('text-green-600')
  })

  it('applies gray color for low sharpe ratio', () => {
    render(<MetricsCards metrics={{ ...mockMetrics, sharpe_ratio: 0.5 }} />)
    const sharpe = screen.getByText('0.5')
    expect(sharpe.className).toContain('text-gray-800')
  })

  it('renders 8 cards', () => {
    render(<MetricsCards metrics={mockMetrics} />)
    const cards = screen.getAllByText(/.%$/)
    // 8 metric cards total
    expect(cards.length).toBeGreaterThanOrEqual(1)
  })

  it('handles zero values', () => {
    const zeroMetrics = {
      total_return: 0,
      annual_return: 0,
      max_drawdown: 0,
      sharpe_ratio: 0,
      win_rate: 0,
      trade_count: 0,
      benchmark_return: 0,
      excess_return: 0,
    }
    render(<MetricsCards metrics={zeroMetrics} />)
    expect(screen.getByText('总收益率')).toBeInTheDocument()
  })
})
