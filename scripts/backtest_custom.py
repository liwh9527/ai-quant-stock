"""
竞价策略回测（连板追踪版）

选股条件：
1. 昨日涨停（涨幅>=9.8%）
2. 竞价涨幅 > 3%
3. 主板、非ST
4. 流通市值 < 200亿
5. 昨日成交额 > 5亿
6. 股价 < 50元

持仓逻辑（T+1，追求连板）：
- Day T: 涨停
- Day T+1: 竞价>3%，开盘买入
- 之后每天：收盘涨停则继续持有
- 断板（收盘未涨停）：收盘卖出
- 止损：跌破买入价-5%，无条件卖出
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import numpy as np
from datetime import date
from app.core.database import SessionLocal
from app.models.stock import Stock
from app.models.daily import DailyQuote


def load_data(session):
    print("加载数据...")
    stocks = session.query(
        Stock.ts_code, Stock.name, Stock.industry, Stock.market
    ).filter(
        Stock.market.like('%主板%'), Stock.name.notlike('%ST%')
    ).all()
    stock_map = {s.ts_code: s for s in stocks}
    valid_codes = set(stock_map.keys())
    print(f"  主板非ST: {len(valid_codes)} 只")

    quotes = session.query(
        DailyQuote.ts_code, DailyQuote.trade_date,
        DailyQuote.open, DailyQuote.high, DailyQuote.low, DailyQuote.close,
        DailyQuote.pre_close, DailyQuote.vol, DailyQuote.amount
    ).filter(
        DailyQuote.ts_code.in_(valid_codes),
        DailyQuote.pre_close.isnot(None), DailyQuote.pre_close > 0,
    ).order_by(DailyQuote.ts_code, DailyQuote.trade_date).all()

    import pandas as pd
    df = pd.DataFrame([{
        'ts_code': q.ts_code, 'trade_date': q.trade_date,
        'open': q.open, 'high': q.high, 'low': q.low, 'close': q.close,
        'pre_close': q.pre_close, 'vol': q.vol, 'amount': q.amount,
    } for q in quotes])

    print(f"  日线: {len(df)} 条")
    return df, stock_map


def estimate_mv(amount_千亿):
    """用成交额估算流通市值（亿元），假设涨停换手率10%"""
    return amount_千亿 / 0.10 if amount_千亿 > 0 else 999


def is_limit_up(close, pre_close):
    """判断是否涨停（涨幅>=9.8%）"""
    if not pre_close or pre_close <= 0:
        return False
    return (close - pre_close) / pre_close >= 0.098


def run_backtest(df, stock_map, config):
    dates = sorted(df['trade_date'].unique())
    print(f"\n回测区间: {dates[0]} ~ {dates[-1]}, 共 {len(dates)} 个交易日")

    date_groups = df.groupby('trade_date')
    capital = config['initial_capital']
    positions = {}  # {ts_code: {buy_price, buy_date, shares}}
    trades = []
    daily_values = [{'date': dates[0], 'value': capital}]

    for i in range(1, len(dates)):
        trade_date = dates[i]
        prev_date = dates[i - 1]

        today_data = date_groups.get_group(trade_date)
        prev_data = date_groups.get_group(prev_date)
        prev_map = {row['ts_code']: row for _, row in prev_data.iterrows()}

        # === 1. 处理持仓：检查是否需要卖出 ===
        # T+1 规则：只有昨天及之前买入的股票才能卖出
        closed_codes = []
        for ts_code, pos in positions.items():
            # T+1: 今天买入的不能卖
            if pos['buy_date'] >= trade_date:
                continue

            row = today_data[today_data['ts_code'] == ts_code]
            if row.empty:
                continue
            row = row.iloc[0]

            # 止损：跌破买入价-5%
            if row['low'] <= pos['buy_price'] * (1 - config['stop_loss']):
                sell_price = pos['buy_price'] * (1 - config['stop_loss'])
                pnl = (sell_price - pos['buy_price']) * pos['shares']
                cost = pos['buy_price'] * pos['shares'] * 0.0003
                stamp = sell_price * pos['shares'] * 0.001
                pnl -= (cost + stamp)
                capital += pos['shares'] * sell_price - cost
                trades.append({
                    'buy_date': pos['buy_date'], 'sell_date': trade_date,
                    'ts_code': ts_code,
                    'name': stock_map.get(ts_code, type('', (), {'name': ts_code})).name,
                    'buy': pos['buy_price'], 'sell': round(sell_price, 2),
                    'pnl': round(pnl, 2),
                    'pct': round((sell_price - pos['buy_price']) / pos['buy_price'] * 100, 2),
                    'hold_days': i - pos['buy_idx'],
                    'reason': '止损',
                })
                closed_codes.append(ts_code)
                continue

            # 检查今天是否涨停
            if not is_limit_up(row['close'], row['pre_close']):
                # 断板，收盘卖出
                sell_price = row['close']
                pnl = (sell_price - pos['buy_price']) * pos['shares']
                cost = pos['buy_price'] * pos['shares'] * 0.0003
                stamp = sell_price * pos['shares'] * 0.001
                pnl -= (cost + stamp)
                capital += pos['shares'] * sell_price - cost
                trades.append({
                    'buy_date': pos['buy_date'], 'sell_date': trade_date,
                    'ts_code': ts_code,
                    'name': stock_map.get(ts_code, type('', (), {'name': ts_code})).name,
                    'buy': pos['buy_price'], 'sell': round(sell_price, 2),
                    'pnl': round(pnl, 2),
                    'pct': round((sell_price - pos['buy_price']) / pos['buy_price'] * 100, 2),
                    'hold_days': i - pos['buy_idx'],
                    'reason': '断板',
                })
                closed_codes.append(ts_code)
            # else: 继续持有（连板）

        for code in closed_codes:
            del positions[code]

        # === 2. 寻找新买入机会 ===
        if len(positions) < config['max_positions']:
            candidates = []
            for _, row in today_data.iterrows():
                ts_code = row['ts_code']
                if ts_code in positions:
                    continue
                if ts_code not in prev_map:
                    continue

                prev = prev_map[ts_code]
                pre_close = prev['close']
                if not pre_close or pre_close <= 0:
                    continue
                if not prev['pre_close'] or prev['pre_close'] <= 0:
                    continue

                # 条件1: 昨日涨停
                if not is_limit_up(prev['close'], prev['pre_close']):
                    continue

                # 条件2: 竞价涨幅 > 3%
                auction_pct = (row['open'] - pre_close) / pre_close
                if auction_pct <= config['min_auction_pct']:
                    continue

                # 条件3: 股价 < 50
                if row['open'] >= config['max_price']:
                    continue

                # 条件4: 流通市值 < 200亿
                amount_亿 = prev['amount'] / 100000 if prev['amount'] else 0
                mv = estimate_mv(amount_亿)
                if mv >= config['max_mv']:
                    continue

                # 条件5: 昨日成交额 > 5亿
                if amount_亿 < config['min_amount_亿']:
                    continue

                stock_info = stock_map.get(ts_code)
                candidates.append({
                    'ts_code': ts_code,
                    'name': stock_info.name if stock_info else ts_code,
                    'auction_pct': auction_pct,
                    'open': row['open'],
                    'amount_亿': amount_亿,
                    'mv': mv,
                })

            # 按竞价涨幅排名
            candidates.sort(key=lambda x: x['auction_pct'], reverse=True)
            slots = config['max_positions'] - len(positions)
            selected = candidates[:slots]

            # 计算总资金（现金 + 持仓市值）
            total_value = capital
            for pc, pp in positions.items():
                prow = today_data[today_data['ts_code'] == pc]
                if not prow.empty:
                    total_value += prow.iloc[0]['close'] * pp['shares']
                else:
                    total_value += pp['buy_price'] * pp['shares']

            # 每只分配总资金的 1/max_positions
            per_stock_budget = total_value / config['max_positions']

            for s in selected:
                buy_price = s['open']
                # 不超过单只预算，也不超过可用现金
                budget = min(per_stock_budget, capital)
                shares = int(budget / buy_price / 100) * 100
                if shares > 0:
                    positions[s['ts_code']] = {
                        'buy_price': buy_price,
                        'buy_date': trade_date,
                        'buy_idx': i,
                        'shares': shares,
                    }
                    capital -= buy_price * shares

        # 计算当日总市值
        total_value = capital
        for ts_code, pos in positions.items():
            row = today_data[today_data['ts_code'] == ts_code]
            if not row.empty:
                total_value += row.iloc[0]['close'] * pos['shares']
            else:
                total_value += pos['buy_price'] * pos['shares']

        daily_values.append({'date': trade_date, 'value': round(total_value, 2)})

    # 清仓剩余持仓
    for ts_code, pos in positions.items():
        trades.append({
            'buy_date': pos['buy_date'], 'sell_date': dates[-1],
            'ts_code': ts_code,
            'name': stock_map.get(ts_code, type('', (), {'name': ts_code})).name,
            'buy': pos['buy_price'], 'sell': pos['buy_price'],
            'pnl': 0, 'pct': 0, 'hold_days': 0, 'reason': '清仓',
        })

    return trades, daily_values


def print_results(trades, daily_values, config):
    initial = config['initial_capital']
    final = daily_values[-1]['value'] if daily_values else initial
    total_return = (final / initial - 1) * 100

    print("\n" + "=" * 70)
    print("回测结果")
    print("=" * 70)
    print(f"初始资金: {initial:,.0f}")
    print(f"最终资金: {final:,.0f}")
    print(f"总收益率: {total_return:.2f}%")
    print(f"总交易次数: {len(trades)}")

    if not trades:
        print("无交易")
        return

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    flat = [t for t in trades if t['pnl'] == 0]

    print(f"胜率: {len(wins)/len(trades)*100:.1f}% ({len(wins)}/{len(trades)})")
    if wins:
        print(f"盈利: {len(wins)} 次, 平均 +{np.mean([t['pct'] for t in wins]):.2f}%")
    if losses:
        print(f"亏损: {len(losses)} 次, 平均 {np.mean([t['pct'] for t in losses]):.2f}%")
    print(f"最大单笔盈利: {max(t['pct'] for t in trades):.2f}%")
    print(f"最大单笔亏损: {min(t['pct'] for t in trades):.2f}%")

    # 连板统计
    hold_days = [t['hold_days'] for t in trades]
    print(f"\n持仓天数: 平均{np.mean(hold_days):.1f}天, 最长{max(hold_days)}天")
    multi_day = [t for t in trades if t['hold_days'] >= 2]
    if multi_day:
        print(f"连板交易（持仓>=2天）: {len(multi_day)} 次")
        for t in sorted(multi_day, key=lambda x: x['hold_days'], reverse=True)[:5]:
            print(f"  {t['ts_code']} {t['name']:8s} 持{t['hold_days']}天 {t['pct']:+.2f}% ({t['reason']})")

    # 断板 vs 止损
    duanban = [t for t in trades if t['reason'] == '断板']
    zhisun = [t for t in trades if t['reason'] == '止损']
    print(f"\n断板卖出: {len(duanban)} 次, 平均 {np.mean([t['pct'] for t in duanban]):.2f}%" if duanban else "")
    print(f"止损卖出: {len(zhisun)} 次, 平均 {np.mean([t['pct'] for t in zhisun]):.2f}%" if zhisun else "")

    # 最大回撤
    values = [v['value'] for v in daily_values]
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    print(f"\n最大回撤: {max_dd*100:.2f}%")

    # 盈亏比
    avg_win = np.mean([t['pct'] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t['pct'] for t in losses])) if losses else 1
    print(f"盈亏比: {avg_win/avg_loss:.2f}" if avg_loss > 0 else "")

    # 月度收益
    from collections import defaultdict
    monthly = defaultdict(float)
    for t in trades:
        month = str(t['buy_date'])[:7]
        monthly[month] += t['pnl']
    print(f"\n月度收益:")
    for month in sorted(monthly.keys()):
        pnl = monthly[month]
        sign = '+' if pnl >= 0 else ''
        print(f"  {month}: {sign}{pnl:,.0f}")

    # 最近15笔
    print(f"\n最近 15 笔交易:")
    print(f"{'买入日':12s} {'卖出日':12s} {'代码':12s} {'名称':8s} {'买入':>7s} {'卖出':>7s} {'盈亏%':>6s} {'持仓':>3s} {'原因':4s}")
    for t in trades[-15:]:
        print(f"{str(t['buy_date']):12s} {str(t['sell_date']):12s} {t['ts_code']:12s} {t['name']:8s} "
              f"{t['buy']:>7.2f} {t['sell']:>7.2f} {t['pct']:>+5.2f}% {t['hold_days']:>2d}天 {t['reason']}")


def main():
    config = {
        'initial_capital': 100000,
        'max_positions': 3,
        'min_auction_pct': 0.03,
        'max_price': 50,
        'max_mv': 200,
        'min_amount_亿': 5,
        'stop_loss': 0.05,
    }

    print("竞价策略回测（连板追踪）")
    print("=" * 70)
    print("选股条件:")
    print("  1. 昨日涨停（涨幅>=9.8%）")
    print("  2. 竞价涨幅 > 3%")
    print("  3. 主板、非ST、股价<50元")
    print("  4. 流通市值 < 200亿、昨日成交额 > 5亿")
    print("持仓逻辑:")
    print("  5. T+1 竞价买入")
    print("  6. 每天收盘涨停则持有（追求连板）")
    print("  7. 断板（收盘未涨停）则卖出")
    print("  8. 跌破买入价-5%止损")
    print("=" * 70)

    session = SessionLocal()
    df, stock_map = load_data(session)
    session.close()

    if df.empty:
        print("无数据")
        return

    trades, daily_values = run_backtest(df, stock_map, config)
    print_results(trades, daily_values, config)


if __name__ == "__main__":
    main()
