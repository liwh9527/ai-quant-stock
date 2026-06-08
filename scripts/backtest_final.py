"""
最终方案：三合一优化

选股条件：
1. 昨日涨停（涨幅>=9.8%）
2. 竞价涨幅 > 5%（方案A提高门槛）
3. 主板、非ST、股价<50元
4. 流通市值 < 200亿、昨日成交额 > 5亿

持仓逻辑：
5. 大盘5日均线上方才开仓（方案A大盘择时）
6. 竞价5-7%半仓，7%+满仓（方案B分级仓位）
7. 每天收盘涨停则持有（追求连板）
8. 断板则收盘卖出
9. 跌破买入价-5%止损（盘中）
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
import numpy as np
from app.core.database import SessionLocal
from app.models.stock import Stock
from app.models.daily import DailyQuote


def load_data(session):
    stocks = session.query(Stock.ts_code, Stock.name, Stock.market).filter(
        Stock.market.like('%主板%'), Stock.name.notlike('%ST%')
    ).all()
    stock_map = {s.ts_code: s for s in stocks}
    valid_codes = set(stock_map.keys())
    quotes = session.query(
        DailyQuote.ts_code, DailyQuote.trade_date,
        DailyQuote.open, DailyQuote.high, DailyQuote.low, DailyQuote.close,
        DailyQuote.pre_close, DailyQuote.amount
    ).filter(
        DailyQuote.ts_code.in_(valid_codes),
        DailyQuote.pre_close.isnot(None), DailyQuote.pre_close > 0,
    ).order_by(DailyQuote.ts_code, DailyQuote.trade_date).all()
    import pandas as pd
    df = pd.DataFrame([{
        'ts_code': q.ts_code, 'trade_date': q.trade_date,
        'open': q.open, 'high': q.high, 'low': q.low, 'close': q.close,
        'pre_close': q.pre_close, 'amount': q.amount,
    } for q in quotes])
    return df, stock_map


def get_market_index(df):
    daily_avg = df.groupby('trade_date')['close'].mean().reset_index()
    daily_avg.columns = ['trade_date', 'index']
    daily_avg = daily_avg.sort_values('trade_date')
    daily_avg['ma5'] = daily_avg['index'].rolling(5).mean()
    return daily_avg


def is_limit_up(close, pre_close):
    if not pre_close or pre_close <= 0: return False
    return (close - pre_close) / pre_close >= 0.098


def get_position_ratio(auction_pct):
    """竞价涨幅分级仓位"""
    if auction_pct >= 0.07:
        return 1.0   # 满仓
    elif auction_pct >= 0.05:
        return 0.5    # 半仓
    return 0.33


def run_backtest(df, stock_map, config):
    dates = sorted(df['trade_date'].unique())
    date_groups = df.groupby('trade_date')
    market = get_market_index(df)
    market_map = {row['trade_date']: row for _, row in market.iterrows()}

    capital = config['initial_capital']
    positions = {}
    trades = []
    daily_values = [{'date': dates[0], 'value': capital}]

    for i in range(1, len(dates)):
        trade_date = dates[i]
        prev_date = dates[i - 1]
        today_data = date_groups.get_group(trade_date)
        prev_data = date_groups.get_group(prev_date)
        prev_map = {row['ts_code']: row for _, row in prev_data.iterrows()}

        # 大盘择时
        market_info = market_map.get(trade_date)
        market_bullish = True
        if market_info is not None and not np.isnan(market_info.get('ma5', np.nan)):
            market_bullish = market_info['index'] > market_info['ma5']

        # === 卖出（T+1）===
        closed_codes = []
        for ts_code, pos in positions.items():
            if pos['buy_date'] >= trade_date:
                continue
            row = today_data[today_data['ts_code'] == ts_code]
            if row.empty: continue
            row = row.iloc[0]

            # 盘中止损
            if row['low'] <= pos['buy_price'] * (1 - config['stop_loss']):
                sell_price = pos['buy_price'] * (1 - config['stop_loss'])
                pnl = (sell_price - pos['buy_price']) * pos['shares']
                cost = pos['buy_price'] * pos['shares'] * 0.0003
                stamp = sell_price * pos['shares'] * 0.001
                pnl -= (cost + stamp)
                capital += pos['shares'] * sell_price - cost
                trades.append({
                    'buy_date': pos['buy_date'], 'sell_date': trade_date,
                    'ts_code': ts_code, 'name': stock_map.get(ts_code, type('', (), {'name': ts_code})).name,
                    'buy': pos['buy_price'], 'sell': round(sell_price, 2),
                    'pnl': round(pnl, 2),
                    'pct': round((sell_price - pos['buy_price']) / pos['buy_price'] * 100, 2),
                    'hold_days': i - pos['buy_idx'], 'reason': '止损',
                })
                closed_codes.append(ts_code)
                continue

            # 断板卖出
            if not is_limit_up(row['close'], row['pre_close']):
                sell_price = row['close']
                pnl = (sell_price - pos['buy_price']) * pos['shares']
                cost = pos['buy_price'] * pos['shares'] * 0.0003
                stamp = sell_price * pos['shares'] * 0.001
                pnl -= (cost + stamp)
                capital += pos['shares'] * sell_price - cost
                trades.append({
                    'buy_date': pos['buy_date'], 'sell_date': trade_date,
                    'ts_code': ts_code, 'name': stock_map.get(ts_code, type('', (), {'name': ts_code})).name,
                    'buy': pos['buy_price'], 'sell': round(sell_price, 2),
                    'pnl': round(pnl, 2),
                    'pct': round((sell_price - pos['buy_price']) / pos['buy_price'] * 100, 2),
                    'hold_days': i - pos['buy_idx'], 'reason': '断板',
                })
                closed_codes.append(ts_code)

        for code in closed_codes:
            del positions[code]

        # === 买入（大盘看多 + 分级仓位）===
        if market_bullish and len(positions) < config['max_positions']:
            candidates = []
            for _, row in today_data.iterrows():
                ts_code = row['ts_code']
                if ts_code in positions or ts_code not in prev_map: continue
                prev = prev_map[ts_code]
                pre_close = prev['close']
                if not pre_close or pre_close <= 0 or not prev['pre_close'] or prev['pre_close'] <= 0: continue
                if not is_limit_up(prev['close'], prev['pre_close']): continue
                auction_pct = (row['open'] - pre_close) / pre_close
                if auction_pct <= config['min_auction_pct']: continue
                if row['open'] >= config['max_price']: continue
                amount_亿 = prev['amount'] / 100000 if prev['amount'] else 0
                if amount_亿 / 0.10 >= config['max_mv']: continue
                if amount_亿 < config['min_amount_亿']: continue
                candidates.append({
                    'ts_code': ts_code,
                    'name': stock_map.get(ts_code, type('', (), {'name': ts_code})).name,
                    'auction_pct': auction_pct, 'open': row['open'],
                })

            candidates.sort(key=lambda x: x['auction_pct'], reverse=True)

            # 分级仓位买入
            total_value = capital
            for pc, pp in positions.items():
                prow = today_data[today_data['ts_code'] == pc]
                total_value += prow.iloc[0]['close'] * pp['shares'] if not prow.empty else pp['buy_price'] * pp['shares']

            for s in candidates:
                if len(positions) >= config['max_positions']:
                    break
                buy_price = s['open']
                ratio = get_position_ratio(s['auction_pct'])
                budget = min(total_value * ratio, capital)
                shares = int(budget / buy_price / 100) * 100
                if shares > 0:
                    positions[s['ts_code']] = {
                        'buy_price': buy_price, 'buy_date': trade_date,
                        'buy_idx': i, 'shares': shares,
                    }
                    capital -= buy_price * shares

        total_value = capital
        for pc, pp in positions.items():
            prow = today_data[today_data['ts_code'] == pc]
            total_value += prow.iloc[0]['close'] * pp['shares'] if not prow.empty else pp['buy_price'] * pp['shares']
        daily_values.append({'date': trade_date, 'value': round(total_value, 2)})

    return trades, daily_values


def print_results(trades, daily_values, config):
    initial = config['initial_capital']
    final = daily_values[-1]['value'] if daily_values else initial
    ret = (final / initial - 1) * 100
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    values = [v['value'] for v in daily_values]
    peak = values[0]; max_dd = 0
    for v in values:
        if v > peak: peak = v
        dd = (peak - v) / peak
        if dd > max_dd: max_dd = dd

    print(f"\n{'='*70}")
    print("最终方案回测结果")
    print(f"{'='*70}")
    print(f"初始资金: {initial:,.0f}")
    print(f"最终资金: {final:,.0f}")
    print(f"总收益率: {ret:+.2f}%")
    print(f"总交易次数: {len(trades)}")
    if trades:
        print(f"胜率: {len(wins)/len(trades)*100:.1f}% ({len(wins)}/{len(trades)})")
    if wins:
        print(f"盈利: {len(wins)}次 平均+{np.mean([t['pct'] for t in wins]):.2f}%")
        print(f"最大单笔盈利: +{max(t['pct'] for t in wins):.2f}%")
    if losses:
        print(f"亏损: {len(losses)}次 平均{np.mean([t['pct'] for t in losses]):.2f}%")
        print(f"最大单笔亏损: {min(t['pct'] for t in losses):.2f}%")
    print(f"最大回撤: {max_dd*100:.2f}%")
    if wins and losses:
        avg_w = np.mean([t['pct'] for t in wins])
        avg_l = abs(np.mean([t['pct'] for t in losses]))
        if avg_l > 0: print(f"盈亏比: {avg_w/avg_l:.2f}")

    # 持仓统计
    hold_days = [t['hold_days'] for t in trades]
    print(f"\n持仓天数: 平均{np.mean(hold_days):.1f}天, 最长{max(hold_days)}天")
    multi = [t for t in trades if t['hold_days'] >= 2]
    if multi:
        print(f"连板交易: {len(multi)}次")
        for t in sorted(multi, key=lambda x: x['hold_days'], reverse=True)[:5]:
            print(f"  {t['ts_code']} {t['name']:8s} 持{t['hold_days']}天 {t['pct']:+.2f}%")

    # 卖出原因统计
    duanban = [t for t in trades if t['reason'] == '断板']
    zhisun = [t for t in trades if t['reason'] == '止损']
    if duanban:
        print(f"\n断板卖出: {len(duanban)}次 平均{np.mean([t['pct'] for t in duanban]):+.2f}%")
    if zhisun:
        print(f"止损卖出: {len(zhisun)}次 平均{np.mean([t['pct'] for t in zhisun]):.2f}%")

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
        'initial_capital': 100000, 'max_positions': 3,
        'min_auction_pct': 0.05, 'max_price': 50, 'max_mv': 200,
        'min_amount_亿': 5, 'stop_loss': 0.05,
    }
    print("最终方案：大盘择时 + 竞价5%+ + 分级仓位 + 盘中止损")
    print("=" * 70)
    print("优化点:")
    print("  1. 大盘5日均线上方才开仓（过滤系统性风险）")
    print("  2. 竞价涨幅门槛提高到5%（只追最强）")
    print("  3. 竞价5-7%半仓，7%+满仓（重仓高确定性）")
    print("  4. 盘中跌破买入价-5%止损（控制单笔亏损）")
    print("  5. 收盘涨停则持有（追求连板收益）")
    print("=" * 70)

    session = SessionLocal()
    df, stock_map = load_data(session)
    session.close()

    trades, daily_values = run_backtest(df, stock_map, config)
    print_results(trades, daily_values, config)


if __name__ == "__main__":
    main()
