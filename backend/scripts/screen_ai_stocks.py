#!/usr/bin/env python3
"""
AI算力产业链股票筛选
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
        
        latest = df.iloc[-1]
        
        # 1. 流动性指标
        avg_amount_20d = df['amount'].tail(20).mean()
        
        # 2. 波动性指标
        atr_pct = latest['atr'] / latest['close'] * 100 if latest['close'] > 0 else 0
        volatility = df['close'].pct_change().std() * np.sqrt(252) * 100
        
        # 3. 趋势性指标
        price_vs_ma20 = (latest['close'] - latest['ma20']) / latest['ma20'] * 100
        ma20_slope = (df['ma20'].iloc[-1] - df['ma20'].iloc[-5]) / df['ma20'].iloc[-5] * 100
        
        # 4. 突破信号统计
        cross_up_count = 0
        for i in range(1, len(df)):
            if df.iloc[i]['close'] >= df.iloc[i]['ma20'] and df.iloc[i-1]['close'] < df.iloc[i-1]['ma20']:
                cross_up_count += 1
        cross_up_rate = cross_up_count / len(df) * 252
        
        # 5. 价格位置
        high_60d = df['high'].tail(60).max()
        low_60d = df['low'].tail(60).min()
        price_position = (latest['close'] - low_60d) / (high_60d - low_60d) * 100 if high_60d != low_60d else 50
        
        return {
            'code': code,
            'price': latest['close'],
            'avg_amount_20d': avg_amount_20d,
            'atr_pct': atr_pct,
            'volatility': volatility,
            'price_vs_ma20': price_vs_ma20,
            'ma20_slope': ma20_slope,
            'cross_up_rate': cross_up_rate,
            'price_position': price_position,
        }
    except Exception as e:
        return None


def score_stock(metrics):
    """对股票进行评分"""
    score = 0
    reasons = []
    
    # 1. 流动性评分 (0-20分)
    if metrics['avg_amount_20d'] > 50000:
        score += 20
        reasons.append("流动性优秀")
    elif metrics['avg_amount_20d'] > 20000:
        score += 15
        reasons.append("流动性良好")
    elif metrics['avg_amount_20d'] > 10000:
        score += 10
        reasons.append("流动性一般")
    else:
        score += 5
        reasons.append("流动性较差")
    
    # 2. 波动性评分 (0-20分)
    if 15 < metrics['volatility'] < 40:
        score += 20
        reasons.append("波动性适中")
    elif 10 < metrics['volatility'] <= 15 or 40 <= metrics['volatility'] < 60:
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
    
    # 4. 突破频率评分 (0-20分)
    if 3 < metrics['cross_up_rate'] < 15:
        score += 20
        reasons.append("突破频率适中")
    elif 1 < metrics['cross_up_rate'] <= 3 or 15 <= metrics['cross_up_rate'] < 20:
        score += 15
        reasons.append("突破频率偏低/偏高")
    else:
        score += 5
        reasons.append("突破频率极端")
    
    # 5. 价格位置评分 (0-20分)
    if 30 < metrics['price_position'] < 70:
        score += 20
        reasons.append("价格位置适中")
    elif 20 < metrics['price_position'] <= 30 or 70 <= metrics['price_position'] < 80:
        score += 15
        reasons.append("价格位置偏低/偏高")
    else:
        score += 5
        reasons.append("价格位置极端")
    
    return score, reasons


def main():
    # AI算力产业链股票池
    stock_list = [
        # 光模块/光通信 (算力基础设施)
        {'code': '300308', 'name': '中际旭创', 'segment': '光模块'},
        {'code': '300502', 'name': '新易盛', 'segment': '光模块'},
        {'code': '002281', 'name': '光迅科技', 'segment': '光模块'},
        {'code': '300394', 'name': '天孚通信', 'segment': '光器件'},
        {'code': '600487', 'name': '亨通光电', 'segment': '光纤光缆'},
        
        # AI芯片/GPU
        {'code': '688256', 'name': '寒武纪', 'segment': 'AI芯片'},
        {'code': '688041', 'name': '海光信息', 'segment': 'AI芯片'},
        {'code': '688012', 'name': '中微公司', 'segment': '半导体设备'},
        
        # 服务器/算力
        {'code': '601138', 'name': '工业富联', 'segment': 'AI服务器'},
        {'code': '000977', 'name': '浪潮信息', 'segment': 'AI服务器'},
        {'code': '603019', 'name': '中科曙光', 'segment': 'AI服务器'},
        
        # PCB/封装
        {'code': '002916', 'name': '深南电路', 'segment': 'PCB'},
        {'code': '600584', 'name': '长电科技', 'segment': '封装'},
        {'code': '002049', 'name': '紫光国微', 'segment': '芯片设计'},
        
        # 存储
        {'code': '688981', 'name': '中芯国际', 'segment': '晶圆代工'},
        {'code': '002185', 'name': '华天科技', 'segment': '封装'},
        
        # 散热/电源
        {'code': '002837', 'name': '英维克', 'segment': '散热'},
        {'code': '300861', 'name': '美畅股份', 'segment': '金刚线'},
    ]
    
    start_date = '20250101'
    end_date = '20260611'
    
    print("="*80)
    print("AI算力产业链股票筛选")
    print("="*80)
    print(f"回测期间: {start_date} ~ {end_date}")
    print("="*80)
    
    results = []
    
    for i, stock in enumerate(stock_list):
        code = stock['code']
        name = stock['name']
        segment = stock['segment']
        
        print(f"\r处理中: {i+1}/{len(stock_list)} - {name}", end="", flush=True)
        
        metrics = calculate_metrics(code, start_date, end_date)
        if metrics is None:
            continue
        
        score, reasons = score_stock(metrics)
        
        results.append({
            'code': code,
            'name': name,
            'segment': segment,
            'score': score,
            'reasons': reasons,
            'metrics': metrics,
        })
    
    print("\n")
    
    # 按评分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # 打印结果
    print("="*80)
    print("AI算力产业链股票筛选结果")
    print("="*80)
    
    print(f"\n{'排名':>4} {'代码':<8} {'名称':<10} {'板块':<10} {'评分':>6} {'价格':>10} {'波动率':>8} {'MA20斜率':>10} {'突破频率':>10}")
    print("-"*90)
    
    for i, r in enumerate(results):
        m = r['metrics']
        marker = " ✅" if r['score'] >= 70 else ""
        print(f"{i+1:>4} {r['code']:<8} {r['name']:<10} {r['segment']:<10} {r['score']:>6} {m['price']:>10.2f} {m['volatility']:>7.1f}% {m['ma20_slope']:>+9.1f}% {m['cross_up_rate']:>9.1f}{marker}")
    
    # 按板块分组
    print("\n" + "="*80)
    print("按板块分组")
    print("="*80)
    
    segments = {}
    for r in results:
        seg = r['segment']
        if seg not in segments:
            segments[seg] = []
        segments[seg].append(r)
    
    for seg, stocks in segments.items():
        print(f"\n{seg}:")
        for s in stocks:
            m = s['metrics']
            emoji = '🟢' if s['score'] >= 70 else '🟡' if s['score'] >= 60 else '🔴'
            print(f"  {emoji} {s['name']} ({s['code']}) - 评分:{s['score']} 价格:{m['price']:.2f} 波动率:{m['volatility']:.1f}%")
    
    # 推荐股票池
    selected = [r for r in results if r['score'] >= 70]
    
    print("\n" + "="*80)
    print(f"推荐股票池 (评分>=70): {len(selected)} 只")
    print("="*80)
    
    for i, r in enumerate(selected):
        m = r['metrics']
        print(f"\n{i+1}. {r['name']} ({r['code']}) - {r['segment']}")
        print(f"   评分: {r['score']}")
        print(f"   价格: {m['price']:.2f}")
        print(f"   波动率: {m['volatility']:.1f}%")
        print(f"   MA20斜率: {m['ma20_slope']:+.1f}%")
        print(f"   突破频率: {m['cross_up_rate']:.1f}次/年")
        print(f"   优势: {', '.join(r['reasons'][:3])}")
    
    # 输出配置
    print("\n" + "="*80)
    print("推荐股票池配置")
    print("="*80)
    print("\n# AI算力产业链股票池")
    print("STOCK_POOL = [")
    for r in selected:
        print(f"    {{\"code\": \"{r['code']}\", \"name\": \"{r['name']}\"}},  # {r['segment']}")
    print("]")


if __name__ == "__main__":
    main()
