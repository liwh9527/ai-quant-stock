#!/usr/bin/env python3
"""历史日线数据批量导入脚本（使用新浪接口）

功能：
- 批量导入 2021-01-01 至今的完整历史日线数据
- 支持断点续传（记录已完成的股票）
- 进度显示
- 错误重试机制

用法：
    cd /root/projects/ai-quant-stock/backend
    python ../scripts/init_data_full.py
"""

import sys
import os
import json
import time
import logging
from datetime import date, timedelta
from pathlib import Path

# 添加 backend 目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.core.database import SessionLocal
from app.models.stock import Stock
from app.models.daily import DailyQuote
from sqlalchemy import select

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/root/projects/ai-quant-stock/scripts/import.log')
    ]
)
logger = logging.getLogger(__name__)

# 进度文件路径
PROGRESS_FILE = Path('/root/projects/ai-quant-stock/scripts/import_progress.json')


def load_progress() -> dict:
    """加载导入进度"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'completed': [], 'failed': [], 'last_update': None}


def save_progress(progress: dict):
    """保存导入进度"""
    progress['last_update'] = date.today().isoformat()
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def ts_code_to_sina(ts_code: str) -> str:
    """将 ts_code 转换为新浪格式 (000001.SZ -> sz000001)"""
    code, market = ts_code.split('.')
    return f"{'sh' if market == 'SH' else 'sz'}{code}"


def import_daily_quotes_sina(ts_code: str, start_date: date, end_date: date, session) -> int:
    """使用baostock导入日线数据（替代akshare）"""
    import baostock as bs
    import pandas as pd

    # 转换为baostock格式
    code, market = ts_code.split('.')
    bs_code = f"{'sh' if market == 'SH' else 'sz'}.{code}"

    lg = bs.login()
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume",
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            frequency="d",
            adjustflag="2"
        )

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            return 0

        df = pd.DataFrame(data_list, columns=rs.fields)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    except Exception as e:
        raise Exception(f"获取数据失败: {e}")
    finally:
        bs.logout()
    
    if df.empty:
        return 0
    
    # 计算缺失字段
    df['ts_code'] = ts_code
    df['trade_date'] = pd.to_datetime(df['date'])
    df['pre_close'] = df['close'].shift(1)
    df['change'] = df['close'] - df['pre_close']
    df['pct_chg'] = (df['change'] / df['pre_close'] * 100).round(2)
    
    # 重命名列
    df = df.rename(columns={'volume': 'vol'})
    
    # 批量插入
    count = 0
    for _, row in df.iterrows():
        trade_date = row['trade_date'].date() if hasattr(row['trade_date'], 'date') else row['trade_date']
        
        # 检查是否已存在
        existing = session.execute(
            select(DailyQuote).where(
                DailyQuote.ts_code == ts_code,
                DailyQuote.trade_date == trade_date,
            )
        ).scalar_one_or_none()
        
        if existing:
            continue
        
        quote = DailyQuote(
            ts_code=ts_code,
            trade_date=trade_date,
            open=row.get('open'),
            high=row.get('high'),
            low=row.get('low'),
            close=row.get('close'),
            pre_close=row.get('pre_close'),
            change=row.get('change'),
            pct_chg=row.get('pct_chg'),
            vol=row.get('vol'),
            amount=row.get('amount'),
        )
        session.add(quote)
        count += 1
    
    session.commit()
    return count


def main():
    print("=" * 60)
    print("AI 量化选股工具 - 历史日线数据批量导入")
    print("=" * 60)
    print(f"目标时间范围: 2021-01-01 ~ {date.today().isoformat()}")
    print(f"数据源: 新浪接口（stock_zh_a_daily）")
    print()

    session = SessionLocal()

    # 获取所有股票
    stocks = session.query(Stock).all()
    total_stocks = len(stocks)
    print(f"股票总数: {total_stocks}")

    # 加载进度
    progress = load_progress()
    completed_set = set(progress.get('completed', []))
    print(f"已完成: {len(completed_set)}")
    print(f"待导入: {total_stocks - len(completed_set)}")
    print()

    # 时间范围
    start_date = date(2021, 1, 1)
    end_date = date.today()

    # 统计
    success_count = 0
    fail_count = 0
    skip_count = 0
    total_records = 0

    print("开始导入...")
    print("-" * 60)

    for i, stock in enumerate(stocks):
        ts_code = stock.ts_code
        stock_name = stock.name or ''

        # 跳过已完成的
        if ts_code in completed_set:
            skip_count += 1
            continue

        # 重试机制
        max_retries = 3
        retry_count = 0
        imported = False

        while retry_count < max_retries:
            try:
                count = import_daily_quotes_sina(ts_code, start_date, end_date, session)
                total_records += count
                success_count += 1
                imported = True

                # 显示进度
                progress_pct = (i + 1) / total_stocks * 100
                print(
                    f"[{i+1}/{total_stocks}] ({progress_pct:.1f}%) "
                    f"{ts_code} {stock_name}: {count} 条"
                )

                # 每 50 只股票保存一次进度
                if (i + 1) % 50 == 0:
                    progress['completed'] = list(completed_set)
                    save_progress(progress)

                # 避免请求过快
                time.sleep(0.5)
                break

            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(
                        f"[{ts_code}] 第 {retry_count} 次失败，重试中: {e}"
                    )
                    time.sleep(2 * retry_count)  # 递增等待
                else:
                    logger.error(f"[{ts_code}] 导入失败: {e}")
                    fail_count += 1
                    progress.setdefault('failed', []).append({
                        'ts_code': ts_code,
                        'error': str(e)
                    })

        # 记录完成
        if imported:
            completed_set.add(ts_code)

    # 最终保存进度
    progress['completed'] = list(completed_set)
    save_progress(progress)
    session.close()

    # 输出统计
    print()
    print("=" * 60)
    print("导入完成！")
    print("=" * 60)
    print(f"成功导入: {success_count} 只")
    print(f"跳过已完成: {skip_count} 只")
    print(f"导入失败: {fail_count} 只")
    print(f"总记录数: {total_records:,} 条")
    print()
    print(f"进度文件: {PROGRESS_FILE}")
    print(f"日志文件: /root/projects/ai-quant-stock/scripts/import.log")


if __name__ == "__main__":
    main()
