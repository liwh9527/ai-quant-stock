"""高性能选股引擎 — 预加载 + 向量化计算

原版每天查 4 次数据库 + 逐只股票循环，5年回测需 30+ 分钟。
本版本一次性加载全部数据到内存，用 pandas 向量化运算，目标 < 3 分钟。
"""

import pandas as pd
import numpy as np
from typing import List, Dict
from datetime import datetime, timedelta
import sqlite3


class FastScreeningEngine:
    """高性能选股引擎"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._stocks_df = None
        self._daily_df = None
        self._basic_df = None
        self._fina_df = None
        self._loaded = False

    def preload(self, start_date: str, end_date: str):
        """预加载全部数据到内存（只调用一次）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # 1. 股票列表
        self._stocks_df = pd.read_sql_query(
            "SELECT ts_code, name, industry, market FROM stocks", conn
        )

        # 2. 日线行情（全量）
        s, e = self._fmt(start_date), self._fmt(end_date)
        # 多取 60 天用于计算派生字段
        pre_start = (datetime.strptime(s, '%Y-%m-%d') - timedelta(days=90)).strftime('%Y-%m-%d')
        self._daily_df = pd.read_sql_query(
            f"SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol "
            f"FROM daily_quotes WHERE trade_date >= '{pre_start}' AND trade_date <= '{e}'",
            conn
        )
        self._daily_df['trade_date'] = self._daily_df['trade_date'].astype(str)

        # 3. 每日指标
        self._basic_df = pd.read_sql_query(
            f"SELECT ts_code, trade_date, turnover_rate, turnover_rate_f, "
            f"total_mv, circ_mv, pe, pb, ps "
            f"FROM daily_basic WHERE trade_date >= '{pre_start}' AND trade_date <= '{e}'",
            conn
        )
        self._basic_df['trade_date'] = self._basic_df['trade_date'].astype(str)
        # 优先用 turnover_rate_f
        if 'turnover_rate_f' in self._basic_df.columns:
            self._basic_df['turnover_rate'] = (
                self._basic_df['turnover_rate_f']
                .fillna(self._basic_df['turnover_rate'])
            )

        # 4. 财务指标（取最新一期）
        self._fina_df = pd.read_sql_query(
            "SELECT ts_code, ann_date, end_date, roe, roa, gross_margin, net_margin "
            "FROM financial_indicators", conn
        )
        self._fina_df['ann_date'] = self._fina_df['ann_date'].astype(str)

        conn.close()

        # 5. 预计算派生字段（全量向量化）
        self._precalc_derived()

        self._loaded = True

    def _precalc_derived(self):
        """预计算所有派生字段（向量化，一次性完成）"""
        df = self._daily_df.copy()
        df = df.sort_values(['ts_code', 'trade_date'])

        # 近 N 日涨跌幅（向量化）
        for n in [5, 10, 20]:
            # 每只股票的第 n+1 个交易日的 close
            shifted = df.groupby('ts_code')['close'].shift(n)
            df[f'pct_chg_{n}d'] = ((df['close'] - shifted) / shifted * 100).round(2)

        # 连续上涨天数（向量化）
        df['is_up'] = (df['close'] > df.groupby('ts_code')['close'].shift(1)).astype(int)
        # 用 cumsum 技巧计算连续上涨
        df['up_group'] = (df['is_up'] != df.groupby('ts_code')['is_up'].shift(1)).cumsum()
        df['consecutive_up_days'] = df.groupby(['ts_code', 'up_group'])['is_up'].cumsum()
        # 只在 is_up=1 时保留，否则为 0
        df['consecutive_up_days'] = df['consecutive_up_days'] * df['is_up']

        self._daily_df = df

    def screen(self, date: str, config: Dict, data_manager=None) -> List[Dict]:
        """执行每日选股（从内存数据中取，不查数据库）"""
        if not self._loaded:
            raise RuntimeError("请先调用 preload() 加载数据")

        d = self._fmt(date)

        # 1. 当日日线
        daily_today = self._daily_df[self._daily_df['trade_date'] == d].copy()
        if daily_today.empty:
            return []

        # 2. 合并股票信息
        merged = daily_today.merge(
            self._stocks_df, on='ts_code', how='left'
        )

        # 3. 排除 ST
        merged = merged[~merged['name'].str.contains('ST', na=False)]

        # 4. 按板块筛选
        universe = config.get('universe', 'all')
        if universe == '主板':
            merged = merged[merged['market'].isin(['主板'])]
        elif universe == '创业板':
            merged = merged[merged['market'] == '创业板']
        elif universe == '科创板':
            merged = merged[merged['market'] == '科创板']

        if merged.empty:
            return []

        # 5. 合并每日指标
        basic_today = self._basic_df[self._basic_df['trade_date'] == d]
        if not basic_today.empty:
            cols = ['ts_code'] + [c for c in ['turnover_rate', 'circ_mv', 'pe', 'pb', 'ps']
                                  if c in basic_today.columns]
            merged = merged.merge(basic_today[cols], on='ts_code', how='left')

        # 6. 合并财务指标（取 ann_date <= date 的最新一期）
        if not self._fina_df.empty:
            fina = self._fina_df[self._fina_df['ann_date'] <= d]
            if not fina.empty:
                fina_latest = fina.sort_values('ann_date').groupby('ts_code').last().reset_index()
                cols = ['ts_code'] + [c for c in ['roe', 'roa', 'gross_margin', 'net_margin']
                                      if c in fina_latest.columns]
                merged = merged.merge(fina_latest[cols], on='ts_code', how='left')

        # 7. 前一日涨停标记
        prev_date = self._get_prev_trade_date(d)
        if prev_date:
            prev_daily = self._daily_df[self._daily_df['trade_date'] == prev_date]
            prev_limit = prev_daily[prev_daily['pct_chg'] >= 9.5]['ts_code'].tolist()
            merged['prev_limit_up'] = merged['ts_code'].isin(prev_limit)
        else:
            merged['prev_limit_up'] = False

        # 8. 竞价涨幅
        if 'open' in merged.columns and 'pre_close' in merged.columns:
            merged['auction_pct'] = (merged['open'] / merged['pre_close'] - 1).fillna(0)

        # 9. 应用筛选条件
        for cond in config.get('conditions', []):
            merged = self._apply_condition(merged, cond)
            if merged.empty:
                return []

        # 10. 排序
        sort_cfg = config.get('sort')
        if sort_cfg:
            field = sort_cfg['field']
            ascending = sort_cfg.get('order', 'asc') == 'asc'
            if field in merged.columns:
                merged = merged.sort_values(field, ascending=ascending)

        # 11. 限制数量
        limit = config.get('limit', 10)
        merged = merged.head(limit)

        return merged.to_dict('records')

    def _get_prev_trade_date(self, date: str) -> str:
        """获取前一个交易日"""
        dates = sorted(self._daily_df['trade_date'].unique())
        dates = [d for d in dates if d < date]
        return dates[-1] if dates else None

    def _apply_condition(self, df: pd.DataFrame, cond: Dict) -> pd.DataFrame:
        """应用筛选条件"""
        field = cond['field']
        op = cond['op']
        value = cond['value']

        if field not in df.columns:
            return df

        op_map = {
            '>': lambda s, v: s > v,
            '<': lambda s, v: s < v,
            '>=': lambda s, v: s >= v,
            '<=': lambda s, v: s <= v,
            '==': lambda s, v: s == v,
            '!=': lambda s, v: s != v,
            'in': lambda s, v: s.isin(v),
            'not_in': lambda s, v: ~s.isin(v),
        }

        if op in op_map:
            mask = op_map[op](df[field], value)
            return df[mask].copy()
        return df

    @staticmethod
    def _fmt(d: str) -> str:
        """统一日期为 YYYY-MM-DD 格式"""
        if d and '-' not in d and len(d) == 8:
            return f"{d[:4]}-{d[4:6]}-{d[6:]}"
        return d
