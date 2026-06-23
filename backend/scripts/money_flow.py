#!/usr/bin/env python3
"""
资金流向分析模块
主力资金流入/流出、北向资金监控
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta


def get_money_flow(code):
    """获取个股资金流向"""
    try:
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
        if df.empty:
            return None
        
        latest = df.iloc[-1]
        return {
            'code': code,
            'date': str(latest.get('日期', '')),
            'main_net_inflow': float(latest.get('主力净流入-净额', 0)),  # 主力净流入
            'main_net_pct': float(latest.get('主力净流入-净占比', 0)),   # 主力净流入占比
            'super_net_inflow': float(latest.get('超大单净流入-净额', 0)),  # 超大单
            'big_net_inflow': float(latest.get('大单净流入-净额', 0)),    # 大单
            'mid_net_inflow': float(latest.get('中单净流入-净额', 0)),    # 中单
            'small_net_inflow': float(latest.get('小单净流入-净额', 0)),  # 小单
        }
    except Exception as e:
        print(f"  ❌ {code} 资金流向获取失败: {e}")
        return None


def get_sector_money_flow():
    """获取行业资金流向"""
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日")
        if df.empty:
            return []
        
        results = []
        for _, row in df.head(10).iterrows():
            results.append({
                'name': row.get('名称', ''),
                'change_pct': float(row.get('涨跌幅', 0)),
                'main_net_inflow': float(row.get('主力净流入-净额', 0)),
                'main_net_pct': float(row.get('主力净流入-净占比', 0)),
            })
        return results
    except Exception as e:
        print(f"  ❌ 行业资金流向获取失败: {e}")
        return []


def get_north_flow():
    """获取北向资金（沪股通+深股通）"""
    try:
        df = ak.stock_hsgt_north_net_flow_in_em(indicator="沪股通")
        if df.empty:
            return None
        
        latest = df.iloc[-1]
        return {
            'date': str(latest.get('date', '')),
            'value': float(latest.get('value', 0)),
        }
    except Exception as e:
        print(f"  ❌ 北向资金获取失败: {e}")
        return None


def analyze_money_flow(stock_list):
    """分析多只股票的资金流向
    
    Returns:
        按主力净流入排序的股票列表
    """
    results = []
    for stock in stock_list:
        flow = get_money_flow(stock['code'])
        if flow:
            results.append({
                **stock,
                **flow,
            })
    
    # 按主力净流入排序
    results.sort(key=lambda x: x.get('main_net_inflow', 0), reverse=True)
    return results


def filter_by_money_flow(stock_list, min_main_pct=0):
    """按资金流向筛选
    
    Args:
        stock_list: 股票列表
        min_main_pct: 最低主力净流入占比
    
    Returns:
        主力资金净流入的股票
    """
    flows = analyze_money_flow(stock_list)
    return [f for f in flows if f.get('main_net_pct', 0) >= min_main_pct]


if __name__ == '__main__':
    test_stocks = [
        {'code': '600584', 'name': '长电科技'},
        {'code': '601138', 'name': '工业富联'},
        {'code': '002185', 'name': '华天科技'},
        {'code': '002049', 'name': '紫光国微'},
        {'code': '600487', 'name': '亨通光电'},
        {'code': '002916', 'name': '深南电路'},
    ]
    
    print("资金流向分析...")
    flows = analyze_money_flow(test_stocks)
    for f in flows:
        emoji = "🟢" if f.get('main_net_inflow', 0) > 0 else "🔴"
        print(f"  {emoji} {f['name']}: 主力净流入 {f.get('main_net_inflow', 0)/1e4:+,.0f}万 ({f.get('main_net_pct', 0):+.2f}%)")
    
    print("\n行业资金流向...")
    sectors = get_sector_money_flow()
    for s in sectors[:5]:
        emoji = "🟢" if s.get('main_net_inflow', 0) > 0 else "🔴"
        print(f"  {emoji} {s['name']}: {s.get('main_net_inflow', 0)/1e8:+,.2f}亿")
