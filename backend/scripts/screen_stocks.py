#!/usr/bin/env python3
"""
股票池筛选工具
筛选适合MA20策略的股票
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TUSHARE_TOKEN = "29479ac41a3b85cd62b519f1d32a14e343ea99b6def6ce61a646395d"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def calculate_metrics(code, start_date, end_date):
    """计算股票的各项指标"""
    try:
        ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df.empty or len(df) < 60:
            return None
        
        df = df.sort_values('trade_date').reset_index(drop=True)
        
        # 计算技术指标
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['atr'] = df['close'].diff().abs().rolling(14).mean()
        df['vol_ma5'] = df['vol'].rolling(5).mean()
        df['vol_ma20'] = df['vol'].rolling(20).mean()
        
        # 取最近数据
        latest = df.iloc[-1]
        
        # 1. 流动性指标
        avg_vol_20d = df['vol'].tail(20).mean()  # 20日平均成交量
        avg_amount_20d = df['amount'].tail(20).mean()  # 20日平均成交额
        
        # 2. 波动性指标
        atr_pct = latest['atr'] / latest['close'] * 100 if latest['close'] > 0 else 0
        volatility = df['close'].pct_change().std() * np.sqrt(252) * 100  # 年化波动率
        
        # 3. 趋势性指标
        price_vs_ma20 = (latest['close'] - latest['ma20']) / latest['ma20'] * 100
        price_vs_ma60 = (latest['close'] - latest['ma60']) / latest['ma60'] * 100
        ma20_slope = (df['ma20'].iloc[-1] - df['ma20'].iloc[-5]) / df['ma20'].iloc[-5] * 100
        
        # 4. 突破信号统计
        cross_up_count = 0
        for i in range(1, len(df)):
            if df.iloc[i]['close'] >= df.iloc[i]['ma20'] and df.iloc[i-1]['close'] < df.iloc[i-1]['ma20']:
                cross_up_count += 1
        cross_up_rate = cross_up_count / len(df) * 252  # 年化突破次数
        
        # 5. 成交量放大比例
        vol_amplification = latest['vol'] / latest['vol_ma20'] if latest['vol_ma20'] > 0 else 0
        
        # 6. 价格位置（相对60日高低点）
        high_60d = df['high'].tail(60).max()
        low_60d = df['low'].tail(60).min()
        price_position = (latest['close'] - low_60d) / (high_60d - low_60d) * 100 if high_60d != low_60d else 50
        
        return {
            'code': code,
            'price': latest['close'],
            'avg_vol_20d': avg_vol_20d,
            'avg_amount_20d': avg_amount_20d,
            'atr_pct': atr_pct,
            'volatility': volatility,
            'price_vs_ma20': price_vs_ma20,
            'price_vs_ma60': price_vs_ma60,
            'ma20_slope': ma20_slope,
            'cross_up_rate': cross_up_rate,
            'vol_amplification': vol_amplification,
            'price_position': price_position,
        }
    except Exception as e:
        print(f"计算{code}指标失败: {e}")
        return None


def score_stock(metrics):
    """对股票进行评分"""
    score = 0
    reasons = []
    
    # 1. 流动性评分 (0-20分)
    if metrics['avg_amount_20d'] > 50000:  # 日均成交额>5亿
        score += 20
        reasons.append("流动性优秀")
    elif metrics['avg_amount_20d'] > 20000:  # 日均成交额>2亿
        score += 15
        reasons.append("流动性良好")
    elif metrics['avg_amount_20d'] > 10000:  # 日均成交额>1亿
        score += 10
        reasons.append("流动性一般")
    else:
        score += 5
        reasons.append("流动性较差")
    
    # 2. 波动性评分 (0-20分)
    if 15 < metrics['volatility'] < 40:  # 适中波动
        score += 20
        reasons.append("波动性适中")
    elif 10 < metrics['volatility'] <= 15 or 40 <= metrics['volatility'] < 50:
        score += 15
        reasons.append("波动性偏低/偏高")
    else:
        score += 5
        reasons.append("波动性极端")
    
    # 3. 趋势性评分 (0-20分)
    if metrics['ma20_slope'] > 0:
        score += 15
        reasons.append("MA20上升趋势")
    else:
        score += 5
        reasons.append("MA20下降趋势")
    
    if metrics['price_vs_ma20'] > 0:
        score += 5
        reasons.append("价格在MA20上方")
    
    # 4. 突破信号评分 (0-20分)
    if 3 < metrics['cross_up_rate'] < 15:  # 年化突破3-15次
        score += 20
        reasons.append("突破频率适中")
    elif 1 < metrics['cross_up_rate'] <= 3 or 15 <= metrics['cross_up_rate'] < 20:
        score += 15
        reasons.append("突破频率偏低/偏高")
    else:
        score += 5
        reasons.append("突破频率极端")
    
    # 5. 价格位置评分 (0-20分)
    if 30 < metrics['price_position'] < 70:  # 中间位置
        score += 20
        reasons.append("价格位置适中")
    elif 20 < metrics['price_position'] <= 30 or 70 <= metrics['price_position'] < 80:
        score += 15
        reasons.append("价格位置偏低/偏高")
    else:
        score += 5
        reasons.append("价格位置极端")
    
    return score, reasons


def screen_stocks(stock_list, start_date, end_date, min_score=60):
    """筛选股票"""
    print(f"\n筛选股票池")
    print(f"回测期间: {start_date} ~ {end_date}")
    print(f"最低评分: {min_score}")
    print("="*80)
    
    results = []
    
    for i, stock in enumerate(stock_list):
        code = stock['code']
        name = stock['name']
        
        print(f"\r处理中: {i+1}/{len(stock_list)} - {name}", end="", flush=True)
        
        metrics = calculate_metrics(code, start_date, end_date)
        if metrics is None:
            continue
        
        score, reasons = score_stock(metrics)
        
        results.append({
            'code': code,
            'name': name,
            'score': score,
            'reasons': reasons,
            'metrics': metrics,
        })
    
    print("\n")
    
    # 按评分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # 筛选
    selected = [r for r in results if r['score'] >= min_score]
    
    return results, selected


def main():
    # 股票池候选（可以根据需要扩展）
    stock_list = [
        # 电信运营商
        {'code': '601728', 'name': '中国电信'},
        {'code': '600941', 'name': '中国移动'},
        {'code': '600050', 'name': '中国联通'},
        
        # 光通信
        {'code': '600487', 'name': '亨通光电'},
        {'code': '002281', 'name': '光迅科技'},
        {'code': '300308', 'name': '中际旭创'},
        
        # 电子制造
        {'code': '601138', 'name': '工业富联'},
        {'code': '002475', 'name': '立讯精密'},
        {'code': '002241', 'name': '歌尔股份'},
        
        # 新材料
        {'code': '601208', 'name': '东材科技'},
        {'code': '002326', 'name': '永太科技'},
        {'code': '300037', 'name': '新宙邦'},
        
        # 银行
        {'code': '601398', 'name': '工商银行'},
        {'code': '601939', 'name': '建设银行'},
        {'code': '600036', 'name': '招商银行'},
        
        # 电力
        {'code': '600025', 'name': '华能水电'},
        {'code': '600900', 'name': '长江电力'},
        {'code': '601985', 'name': '中国核电'},
    ]
    
    start_date = '20250101'
    end_date = '20260611'
    
    results, selected = screen_stocks(stock_list, start_date, end_date, min_score=60)
    
    # 打印结果
    print("="*80)
    print("股票筛选结果")
    print("="*80)
    
    print(f"\n{'排名':>4} {'代码':<8} {'名称':<10} {'评分':>6} {'价格':>8} {'ATR%':>8} {'波动率':>8} {'MA20斜率':>10} {'突破频率':>10}")
    print("-"*80)
    
    for i, r in enumerate(results):
        m = r['metrics']
        marker = " ✅" if r['score'] >= 60 else ""
        print(f"{i+1:>4} {r['code']:<8} {r['name']:<10} {r['score']:>6} {m['price']:>8.2f} {m['atr_pct']:>7.1f}% {m['volatility']:>7.1f}% {m['ma20_slope']:>+9.1f}% {m['cross_up_rate']:>9.1f}{marker}")
    
    print("\n" + "="*80)
    print(f"推荐股票池 (评分>=60): {len(selected)} 只")
    print("="*80)
    
    for i, r in enumerate(selected):
        m = r['metrics']
        print(f"\n{i+1}. {r['name']} ({r['code']}) - 评分: {r['score']}")
        print(f"   价格: {m['price']:.2f}")
        print(f"   ATR: {m['atr_pct']:.1f}%")
        print(f"   波动率: {m['volatility']:.1f}%")
        print(f"   MA20斜率: {m['ma20_slope']:+.1f}%")
        print(f"   突破频率: {m['cross_up_rate']:.1f}次/年")
        print(f"   优势: {', '.join(r['reasons'][:3])}")
    
    # 输出推荐股票池
    print("\n" + "="*80)
    print("推荐股票池配置")
    print("="*80)
    print("\n# 复制到 quant_trading_v6.py")
    print("STOCK_POOL = [")
    for r in selected:
        print(f"    {{\"code\": \"{r['code']}\", \"name\": \"{r['name']}\"}},")
    print("]")


if __name__ == "__main__":
    main()
