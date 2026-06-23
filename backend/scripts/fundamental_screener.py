#!/usr/bin/env python3
"""
基本面筛选模块
PE、ROE、营收增长率等财务指标筛选
"""

import akshare as ak
import pandas as pd
from datetime import datetime


def get_stock_fundamentals(code):
    """获取单只股票基本面数据"""
    try:
        # 获取个股信息
        info = ak.stock_individual_info_em(symbol=code)
        info_dict = {}
        for _, row in info.iterrows():
            info_dict[row['item']] = row['value']
        
        # 获取财务指标
        try:
            fin = ak.stock_financial_abstract_ths(symbol=code)
            if not fin.empty:
                latest = fin.iloc[0]
                return {
                    'code': code,
                    'name': info_dict.get('股票简称', ''),
                    'industry': info_dict.get('行业', ''),
                    'pe': float(info_dict.get('市盈率(动态)', 0) or 0),
                    'pb': float(info_dict.get('市净率', 0) or 0),
                    'total_mv': float(info_dict.get('总市值', 0) or 0),
                    'circ_mv': float(info_dict.get('流通市值', 0) or 0),
                }
        except:
            pass
        
        return {
            'code': code,
            'name': info_dict.get('股票简称', ''),
            'industry': info_dict.get('行业', ''),
            'pe': float(info_dict.get('市盈率(动态)', 0) or 0),
            'pb': float(info_dict.get('市净率', 0) or 0),
            'total_mv': float(info_dict.get('总市值', 0) or 0),
            'circ_mv': float(info_dict.get('流通市值', 0) or 0),
        }
    except Exception as e:
        print(f"  ❌ {code} 基本面获取失败: {e}")
        return None


def screen_by_fundamentals(stock_list, filters=None):
    """基本面筛选
    
    Args:
        stock_list: [{'code': '600584', 'name': '长电科技'}, ...]
        filters: {
            'pe_min': 0, 'pe_max': 50,      # PE范围
            'pb_min': 0, 'pb_max': 10,      # PB范围
            'min_mv': 100,                   # 最小市值(亿)
        }
    
    Returns:
        筛选后的股票列表
    """
    if filters is None:
        filters = {
            'pe_min': 0,
            'pe_max': 50,
            'pb_min': 0,
            'pb_max': 10,
            'min_mv': 100,  # 最小100亿市值
        }
    
    results = []
    for stock in stock_list:
        fund = get_stock_fundamentals(stock['code'])
        if not fund:
            continue
        
        # 应用筛选条件
        pe = fund.get('pe', 0)
        pb = fund.get('pb', 0)
        mv = fund.get('circ_mv', 0) / 1e8  # 转为亿
        
        if pe <= 0:  # 排除亏损股
            continue
        if pe < filters.get('pe_min', 0) or pe > filters.get('pe_max', 999):
            continue
        if pb < filters.get('pb_min', 0) or pb > filters.get('pb_max', 999):
            continue
        if mv < filters.get('min_mv', 0):
            continue
        
        results.append({
            **stock,
            'pe': round(pe, 2),
            'pb': round(pb, 2),
            'circ_mv': round(mv, 1),
        })
    
    # 按PE排序
    results.sort(key=lambda x: x['pe'])
    return results


def screen_top_momentum_with_fundamentals(stock_list, top_n=10):
    """动量+基本面联合筛选
    
    1. 先用基本面筛选
    2. 再按近20日涨幅排序
    """
    # 基本面筛选
    filtered = screen_by_fundamentals(stock_list, {
        'pe_min': 5,
        'pe_max': 40,
        'pb_min': 0.5,
        'pb_max': 8,
        'min_mv': 200,
    })
    
    # 计算动量
    for stock in filtered:
        try:
            df = ak.stock_zh_a_hist(
                symbol=stock['code'], period="daily",
                start_date=(datetime.now() - pd.Timedelta(days=30)).strftime('%Y%m%d'),
                end_date=datetime.now().strftime('%Y%m%d'),
                adjust="qfq"
            )
            if len(df) >= 20:
                momentum = (df.iloc[-1]['收盘'] - df.iloc[-20]['收盘']) / df.iloc[-20]['收盘'] * 100
                stock['momentum_20d'] = round(momentum, 2)
            else:
                stock['momentum_20d'] = 0
        except:
            stock['momentum_20d'] = 0
    
    # 按动量排序
    filtered.sort(key=lambda x: x.get('momentum_20d', 0), reverse=True)
    return filtered[:top_n]


if __name__ == '__main__':
    # 测试筛选
    test_stocks = [
        {'code': '600584', 'name': '长电科技'},
        {'code': '601138', 'name': '工业富联'},
        {'code': '002185', 'name': '华天科技'},
        {'code': '002049', 'name': '紫光国微'},
        {'code': '600487', 'name': '亨通光电'},
        {'code': '002916', 'name': '深南电路'},
    ]
    
    print("基本面筛选...")
    results = screen_by_fundamentals(test_stocks)
    for r in results:
        print(f"  {r['name']}: PE={r['pe']}, PB={r['pb']}, 市值={r['circ_mv']}亿")
