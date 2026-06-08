"""导入 daily_basic 数据（流通市值、换手率等）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from datetime import date, timedelta
import tinyshare as ts
import pandas as pd
from app.core.database import SessionLocal, engine, Base
from app.models.stock import Stock

TOKEN = 'ovL7T12Mct8o5nWWRM1h9W8S2x6PhQf3uXci67G1mbWv34na646MTSLU6d37ddd7'

# 创建 daily_basic 表
from sqlalchemy import Column, String, Float, Date, Integer, UniqueConstraint

class DailyBasic(Base):
    __tablename__ = 'daily_basic'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    turnover_rate = Column(Float)      # 换手率(%)
    turnover_rate_f = Column(Float)    # 换手率(自由流通股本)
    total_mv = Column(Float)           # 总市值(万元)
    circ_mv = Column(Float)            # 流通市值(万元)
    pe = Column(Float)
    pb = Column(Float)
    ps = Column(Float)
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uix_daily_basic'),
    )

def main():
    Base.metadata.create_all(engine)
    print("daily_basic 表已就绪")

    ts.set_token(TOKEN)
    pro = ts.pro_api()
    session = SessionLocal()

    # 获取日期范围
    start_date = date(2026, 3, 10)
    end_date = date.today()
    dates = []
    d = start_date
    while d <= end_date:
        if d.weekday() < 5:  # 跳过周末
            dates.append(d)
        d += timedelta(days=1)

    print(f"导入日期范围: {dates[0]} ~ {dates[-1]}, 共 {len(dates)} 个交易日")

    total_saved = 0
    for i, d in enumerate(dates):
        try:
            df = pro.daily_basic(trade_date=d.strftime("%Y%m%d"),
                                fields='ts_code,trade_date,turnover_rate,turnover_rate_f,total_mv,circ_mv,pe,pb,ps')
            if df is None or df.empty:
                continue

            count = 0
            for _, row in df.iterrows():
                td = pd.Timestamp(row['trade_date']).date()
                session.add(DailyBasic(
                    ts_code=row['ts_code'], trade_date=td,
                    turnover_rate=row.get('turnover_rate'),
                    turnover_rate_f=row.get('turnover_rate_f'),
                    total_mv=row.get('total_mv'),
                    circ_mv=row.get('circ_mv'),
                    pe=row.get('pe'), pb=row.get('pb'), ps=row.get('ps'),
                ))
                count += 1

            session.commit()
            total_saved += count
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(dates)}] {d}: {count} 条")

        except Exception as e:
            session.rollback()
            print(f"  {d} 失败: {e}")

    print(f"\n导入完成: {total_saved} 条")
    session.close()

if __name__ == "__main__":
    main()
