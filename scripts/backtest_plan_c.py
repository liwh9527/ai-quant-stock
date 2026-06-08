"""
方案C：连板止盈 + 连亏暂停
- 连板3天以上，跌破前日收盘价止盈（不等断板）
- 连续亏损3次暂停1天不开仓
- 其他条件不变
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


def is_limit_up(close, pre_close):
    if not pre_close or pre_close <= 0: return False
    return (close - pre_close) / pre_close >= 0.098


def run_backtest(df, stock_map, config):
    dates = sorted(df['trade_date'].unique())
    date_groups = df.groupby('trade_date')
    capital = config['initial_capital']
    positions = {}
    trades = []
    daily_values = [{'date': dates[0], 'value': capital}]
    consecutive_losses = 0  # 连续亏损计数
    pause_until = None  # 暂停到期日

    for i in range(1, len(dates)):
        trade_date = dates[i]
        prev_date = dates[i - 1]
        today_data = date_groups.get_group(trade_date)
        prev_data = date_groups.get_group(prev_date)
        prev_map = {row['ts_code']: row for _, row in prev_data.iterrows()}

        # 卖出（T+1）
        closed_codes = []
        day_trades = []
        for ts_code, pos in positions.items():
            if pos['buy_date'] >= trade_date:
                continue
            row = today_data[today_data['ts_code'] == ts_code]
            if row.empty: continue
            row = row.iloc[0]

            sell_reason = None
            sell_price = None

            # 止损
            if row['low'] <= pos['buy_price'] * (1 - config['stop_loss']):
                sell_price = pos['buy_price'] * (1 - config['stop_loss'])
                sell_reason = '止损'

            # 方案C：连板3天以上，跌破前日收盘价止盈
            elif pos['hold_days'] >= 2 and row['close'] < pos['prev_close']:
                sell_price = row['close']
                sell_reason = '止盈'

            # 断板
            elif not is_limit_up(row['close'], row['pre_close']):
                sell_price = row['close']
                sell_reason = '断板'

            if sell_reason:
                pnl = (sell_price - pos['buy_price']) * pos['shares']
                cost = pos['buy_price'] * pos['shares'] * 0.0003
                stamp = sell_price * pos['shares'] * 0.001
                pnl -= (cost + stamp)
                capital += pos['shares'] * sell_price - cost
                t = {
                    'buy_date': pos['buy_date'], 'sell_date': trade_date,
                    'ts_code': ts_code, 'name': stock_map.get(ts_code, type('', (), {'name': ts_code})).name,
                    'buy': pos['buy_price'], 'sell': round(sell_price, 2),
                    'pnl': round(pnl, 2),
                    'pct': round((sell_price - pos['buy_price']) / pos['buy_price'] * 100, 2),
                    'hold_days': pos['hold_days'], 'reason': sell_reason,
                }
                trades.append(t)
                day_trades.append(t)
                closed_codes.append(ts_code)
            else:
                # 更新持仓信息
                pos['hold_days'] = pos.get('hold_days', 0) + 1
                pos['prev_close'] = row['close']

        for code in closed_codes:
            del positions[code]

        # 更新连续亏损计数
        for t in day_trades:
            if t['pnl'] < 0:
                consecutive_losses += 1
            else:
                consecutive_losses = 0

        # 连亏暂停判断
        if consecutive_losses >= config['max_consecutive_losses']:
            pause_until = trade_date
            consecutive_losses = 0

        can_buy = pause_until is None or trade_date > pause_until

        # 买入
        if can_buy and len(positions) < config['max_positions']:
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
                    'prev_close': prev['close'],
                })

            candidates.sort(key=lambda x: x['auction_pct'], reverse=True)
            slots = config['max_positions'] - len(positions)
            selected = candidates[:slots]

            total_value = capital
            for pc, pp in positions.items():
                prow = today_data[today_data['ts_code'] == pc]
                total_value += prow.iloc[0]['close'] * pp['shares'] if not prow.empty else pp['buy_price'] * pp['shares']
            per_stock = total_value / config['max_positions']

            for s in selected:
                buy_price = s['open']
                budget = min(per_stock, capital)
                shares = int(budget / buy_price / 100) * 100
                if shares > 0:
                    positions[s['ts_code']] = {
                        'buy_price': buy_price, 'buy_date': trade_date,
                        'buy_idx': i, 'shares': shares,
                        'hold_days': 0, 'prev_close': s['prev_close'],
                    }
                    capital -= buy_price * shares

        total_value = capital
        for pc, pp in positions.items():
            prow = today_data[today_data['ts_code'] == pc]
            total_value += prow.iloc[0]['close'] * pp['shares'] if not prow.empty else pp['buy_price'] * pp['shares']
        daily_values.append({'date': trade_date, 'value': round(total_value, 2)})

    return trades, daily_values


def print_results(trades, daily_values, config, label):
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

    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"收益率: {ret:+.2f}%  最终资金: {final:,.0f}")
    print(f"交易次数: {len(trades)}  胜率: {len(wins)/len(trades)*100:.1f}%" if trades else "无交易")
    if wins: print(f"盈利: {len(wins)}次 平均+{np.mean([t['pct'] for t in wins]):.2f}%")
    if losses: print(f"亏损: {len(losses)}次 平均{np.mean([t['pct'] for t in losses]):.2f}%")
    print(f"最大回撤: {max_dd*100:.2f}%")
    if wins and losses:
        avg_w = np.mean([t['pct'] for t in wins])
        avg_l = abs(np.mean([t['pct'] for t in losses]))
        if avg_l > 0: print(f"盈亏比: {avg_w/avg_l:.2f}")
    multi = [t for t in trades if t['hold_days'] >= 2]
    if multi: print(f"连板交易: {len(multi)}次, 最长{max(t['hold_days'] for t in multi)}天")
    zhiying = [t for t in trades if t['reason'] == '止盈']
    if zhiying: print(f"主动止盈: {len(zhiying)}次, 平均{np.mean([t['pct'] for t in zhiying]):.2f}%")


def main():
    config = {
        'initial_capital': 100000, 'max_positions': 3,
        'min_auction_pct': 0.03, 'max_price': 50, 'max_mv': 200,
        'min_amount_亿': 5, 'stop_loss': 0.05,
        'max_consecutive_losses': 3,
    }
    print("方案C：连板止盈 + 连亏暂停")
    session = SessionLocal()
    df, stock_map = load_data(session)
    session.close()
    trades, daily_values = run_backtest(df, stock_map, config)
    print_results(trades, daily_values, config, "方案C结果")

if __name__ == "__main__":
    main()
