"""
统一数据源模块 - 替代akshare
实时行情：腾讯 qt.gtimg.cn
历史数据：baostock
"""

import requests
import pandas as pd
from datetime import datetime, timedelta

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def to_tencent_code(code: str) -> str:
    """代码转腾讯格式: 600519 -> sh600519, 002185 -> sz002185"""
    c = code.replace(".", "").upper().replace("SH", "").replace("SZ", "").strip()
    if c.startswith("6") or c.startswith("9"):
        return f"sh{c}"
    return f"sz{c}"


def to_baostock_code(code: str) -> str:
    """代码转baostock格式: 600519 -> sh.600519"""
    c = code.replace(".", "").upper().replace("SH", "").replace("SZ", "").strip()
    if c.startswith("6") or c.startswith("9"):
        return f"sh.{c}"
    return f"sz.{c}"


def fetch_realtime_quote(code: str) -> dict:
    """
    腾讯接口获取单只股票实时行情
    返回: {'code', 'price', 'volume', 'high', 'low', 'open', 'change_pct'}
    """
    tc_code = to_tencent_code(code)
    url = f"http://qt.gtimg.cn/q={tc_code}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    parts = resp.text.split("~")
    if len(parts) < 35:
        return None

    price = float(parts[3]) if parts[3] else 0
    prev_close = float(parts[4]) if parts[4] else 0
    change_pct = float(parts[32]) if parts[32] and float(parts[32]) != 0 else (
        round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
    )

    return {
        'code': code,
        'price': price,
        'volume': float(parts[8]) if parts[8] else 0,
        'high': float(parts[6]) if parts[6] else 0,
        'low': float(parts[7]) if parts[7] else 0,
        'open': float(parts[5]) if parts[5] else 0,
        'change_pct': change_pct,
    }


def fetch_realtime_quotes_batch(codes: list) -> dict:
    """
    腾讯接口批量获取实时行情
    返回: {code: {'price', 'volume', 'high', 'low', 'open', 'change_pct'}, ...}
    """
    tc_codes = [to_tencent_code(c) for c in codes]
    url = f"http://qt.gtimg.cn/q={','.join(tc_codes)}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    results = {}
    for line in resp.text.strip().split(";"):
        line = line.strip()
        if len(line) < 20:
            continue
        parts = line.split("~")
        if len(parts) < 35:
            continue

        code = parts[2]
        price = float(parts[3]) if parts[3] else 0
        prev_close = float(parts[4]) if parts[4] else 0
        change_pct = float(parts[32]) if parts[32] and float(parts[32]) != 0 else (
            round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
        )

        results[code] = {
            'price': price,
            'volume': float(parts[8]) if parts[8] else 0,
            'high': float(parts[6]) if parts[6] else 0,
            'low': float(parts[7]) if parts[7] else 0,
            'open': float(parts[5]) if parts[5] else 0,
            'change_pct': change_pct,
        }

    return results


def fetch_historical_data(code: str, days: int = 60) -> pd.DataFrame:
    """
    baostock获取历史日K数据
    返回: DataFrame with columns [open, high, low, close, volume], index=date
    """
    import baostock as bs

    bs_code = to_baostock_code(code)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    lg = bs.login()
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2"  # 前复权
        )

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            return None

        df = pd.DataFrame(data_list, columns=rs.fields)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
        return df
    finally:
        bs.logout()


# CLI测试
if __name__ == "__main__":
    import sys
    codes = sys.argv[1:] if len(sys.argv) > 1 else ["600519", "002185"]

    print("=== 实时行情测试 ===")
    for code in codes:
        q = fetch_realtime_quote(code)
        if q:
            print(f"  {code}: {q['price']}元 ({q['change_pct']:+.2f}%)")

    print(f"\n=== 批量查询测试 ===")
    batch = fetch_realtime_quotes_batch(codes)
    for code, q in batch.items():
        print(f"  {code}: {q['price']}元 ({q['change_pct']:+.2f}%)")

    print(f"\n=== 历史数据测试 ===")
    df = fetch_historical_data(codes[0], days=30)
    if df is not None:
        print(f"  {codes[0]}: {len(df)}条记录")
        print(df.tail(3))
