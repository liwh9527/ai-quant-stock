"""数据初始化脚本

首次使用时运行，导入股票基础数据和日线行情。
用法：
    cd backend
    python ../scripts/init_data.py
"""
import sys
import os

# 添加 backend 目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from datetime import date, timedelta
from app.core.database import SessionLocal
from app.core.config import settings
from app.services.data.tushare_source import TushareSource
from app.services.data.import_service import DataImportService
from app.models.stock import Stock
from app.models.daily import DailyQuote
from app.models.financial import FinancialIndicator


def init_stock_list(import_service):
    """导入股票列表"""
    print("=" * 50)
    print("1. 导入股票列表...")
    try:
        count = import_service.import_stock_list()
        print(f"   股票列表导入完成: {count} 条")
    except Exception as e:
        print(f"   导入失败: {e}")


def init_daily_quotes(import_service, days=30):
    """导入最近 N 天的日线行情"""
    import time
    print("=" * 50)
    print(f"2. 导入最近 {days} 天日线行情...")
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    session = SessionLocal()
    stocks = session.query(Stock).limit(50).all()  # 先导入前 50 只
    session.close()

    success = 0
    fail = 0
    for i, stock in enumerate(stocks):
        try:
            count = import_service.import_daily_quotes(stock.ts_code, start_date, end_date)
            success += 1
            if count > 0:
                print(f"   [{i+1}/{len(stocks)}] {stock.ts_code} {stock.name}: {count} 条新增")
            time.sleep(0.5)  # 避免请求过快
        except Exception as e:
            fail += 1
            if i < 5:
                print(f"   [{i+1}/{len(stocks)}] {stock.ts_code}: 失败 - {e}")
            time.sleep(1)  # 失败后多等一会

    print(f"   日线导入完成: {success} 成功, {fail} 失败")


def init_financial_data(import_service):
    """导入财务指标"""
    print("=" * 50)
    print("3. 导入财务指标...")
    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    session = SessionLocal()
    stocks = session.query(Stock).limit(50).all()
    session.close()

    success = 0
    for i, stock in enumerate(stocks):
        try:
            count = import_service.import_financial_indicators(stock.ts_code, start_date, end_date)
            if count > 0:
                success += 1
        except Exception:
            pass

    print(f"   财务指标导入完成: {success} 只股票")


def show_stats():
    """显示数据库统计"""
    print("=" * 50)
    print("数据库统计:")
    session = SessionLocal()
    stock_count = session.query(Stock).count()
    daily_count = session.query(DailyQuote).count()
    fin_count = session.query(FinancialIndicator).count()
    session.close()
    print(f"   股票数量: {stock_count}")
    print(f"   日线记录: {daily_count}")
    print(f"   财务记录: {fin_count}")


def main():
    print("AI 量化选股工具 - 数据初始化")
    print("=" * 50)

    # 创建数据源和导入服务（优先使用 AkShare，无频率限制）
    from app.services.data.akshare_source import AkShareSource
    source = AkShareSource()
    import_service = DataImportService(source)

    # 步骤 1: 导入股票列表
    init_stock_list(import_service)

    # 步骤 2: 导入日线行情
    init_daily_quotes(import_service, days=30)

    # 步骤 3: 导入财务指标
    init_financial_data(import_service)

    # 显示统计
    show_stats()

    print("\n数据初始化完成！")


if __name__ == "__main__":
    main()
