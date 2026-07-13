"""每日选股引擎"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from datetime import datetime, timedelta


class DailyScreeningEngine:
    """每日选股引擎，支持多条件组合筛选"""

    def screen(self, date: str, config: Dict, data_manager) -> List[Dict]:
        """执行每日选股"""
        # 1. 获取候选股票池
        df = self._get_universe(date, config, data_manager)
        if df.empty:
            return []

        # 2. 构建完整数据
        df = self._build_stock_data(date, df, data_manager)
        if df.empty:
            return []

        # 3. 计算派生字段（涨幅、连续上涨等）
        df = self._calc_derived_fields(date, df, data_manager)

        # 4. 应用筛选条件
        for cond in config.get('conditions', []):
            df = self._apply_condition(df, cond)
            if df.empty:
                return []

        # 5. 排序
        sort_cfg = config.get('sort')
        if sort_cfg:
            field = sort_cfg['field']
            ascending = sort_cfg.get('order', 'asc') == 'asc'
            if field in df.columns:
                df = df.sort_values(field, ascending=ascending)

        # 6. 限制数量
        limit = config.get('limit', 10)
        df = df.head(limit)

        return df.to_dict('records')

    def _get_universe(self, date: str, config: Dict, data_manager) -> pd.DataFrame:
        """获取候选股票池"""
        stocks = data_manager.get_all_stocks(date)
        df = pd.DataFrame(stocks)
        if df.empty:
            return df

        # 排除 ST
        df = df[~df['name'].str.contains('ST', na=False)]

        # 按板块筛选
        universe = config.get('universe', 'all')
        if universe == '主板':
            df = df[df['market'].isin(['主板'])]
        elif universe == '创业板':
            df = df[df['market'] == '创业板']
        elif universe == '科创板':
            df = df[df['market'] == '科创板']

        return df

    def _build_stock_data(self, date: str, stocks_df: pd.DataFrame, data_manager) -> pd.DataFrame:
        """构建股票完整数据（合并日线、指标、财务）"""
        codes = stocks_df['ts_code'].tolist()

        # 日线数据
        daily = data_manager.get_daily_for_date(codes, date)
        daily_df = pd.DataFrame(daily.values()) if daily else pd.DataFrame()

        if daily_df.empty:
            return pd.DataFrame()

        # 合并股票信息
        merged = daily_df.merge(
            stocks_df[['ts_code', 'name', 'industry', 'market']],
            on='ts_code', how='left'
        )

        # 每日指标（turnover_rate_f 为自由流通换手率，更准确）
        basic = data_manager.get_daily_basic(codes, date)
        if basic:
            basic_df = pd.DataFrame(basic.values())
            # 优先用 turnover_rate_f（自由流通换手率）
            if 'turnover_rate_f' in basic_df.columns:
                basic_df['turnover_rate'] = basic_df['turnover_rate_f'].fillna(basic_df.get('turnover_rate'))
            cols = ['ts_code'] + [c for c in ['turnover_rate', 'circ_mv', 'pe', 'pb', 'ps']
                                  if c in basic_df.columns]
            merged = merged.merge(basic_df[cols], on='ts_code', how='left')

        # 财务指标
        fina = data_manager.get_financial(codes, date)
        if fina:
            fina_df = pd.DataFrame(fina.values())
            cols = ['ts_code'] + [c for c in ['roe', 'roa', 'gross_margin', 'net_margin']
                                  if c in fina_df.columns]
            merged = merged.merge(fina_df[cols], on='ts_code', how='left')

        # 前一日涨停标记
        prev_limit_stocks = data_manager.get_prev_limit_up_stocks(date)
        merged['prev_limit_up'] = merged['ts_code'].isin(prev_limit_stocks)

        # 竞价涨幅（简化：用开盘价/昨收-1）
        if 'open' in merged.columns and 'pre_close' in merged.columns:
            merged['auction_pct'] = (merged['open'] / merged['pre_close'] - 1).fillna(0)

        return merged

    def _calc_derived_fields(self, date: str, df: pd.DataFrame, data_manager) -> pd.DataFrame:
        """从 daily_derived 预计算表读取派生字段（极速）"""
        try:
            d = datetime.strptime(date, '%Y%m%d').strftime('%Y-%m-%d')
        except ValueError:
            d = date

        codes = df['ts_code'].tolist()
        if not codes:
            return df

        # 从预计算表查询
        import sqlite3
        conn = sqlite3.connect(data_manager.db_path)
        ph = ','.join(['?'] * len(codes))
        cur = conn.execute(
            f"SELECT ts_code, pct_chg_5d, pct_chg_10d, pct_chg_20d, consecutive_up_days "
            f"FROM daily_derived WHERE trade_date = ? AND ts_code IN ({ph})",
            [d] + codes
        )
        rows = cur.fetchall()
        conn.close()

        if rows:
            derived = pd.DataFrame(rows, columns=['ts_code', 'pct_chg_5d', 'pct_chg_10d', 'pct_chg_20d', 'consecutive_up_days'])
            df = df.merge(derived, on='ts_code', how='left')
        else:
            df['pct_chg_5d'] = np.nan
            df['pct_chg_10d'] = np.nan
            df['pct_chg_20d'] = np.nan
            df['consecutive_up_days'] = 0

        # 填充缺失值
        for col in ['pct_chg_5d', 'pct_chg_10d', 'pct_chg_20d']:
            df[col] = df[col].fillna(np.nan)
        df['consecutive_up_days'] = df['consecutive_up_days'].fillna(0).astype(int)

        return df

    def _apply_condition(self, df: pd.DataFrame, cond: Dict) -> pd.DataFrame:
        """应用单个筛选条件"""
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
