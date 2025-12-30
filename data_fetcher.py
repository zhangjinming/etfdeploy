"""数据获取模块"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional
import warnings
warnings.filterwarnings('ignore')


class ETFDataFetcher:
    """ETF数据获取器"""
    
    def __init__(self, simulate_date: Optional[str] = None):
        """
        初始化数据获取器
        
        Args:
            simulate_date: 模拟日期，格式 'YYYY-MM-DD'，为None时使用当前日期
        """
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.raw_data_cache: Dict[str, pd.DataFrame] = {}  # 存储原始完整数据
        self.simulate_date = simulate_date
    
    def set_simulate_date(self, date: str):
        """设置模拟日期，并清空缓存"""
        self.simulate_date = date
        self.data_cache.clear()
    
    def _get_current_date(self) -> datetime:
        """获取当前日期（模拟或真实）"""
        if self.simulate_date:
            return datetime.strptime(self.simulate_date, '%Y-%m-%d')
        return datetime.now()
    
    def get_etf_history(self, symbol: str, days: int = 250) -> pd.DataFrame:
        """获取ETF历史数据（截止到模拟日期）"""
        cache_key = f"{symbol}_{self.simulate_date}"
        if cache_key in self.data_cache:
            return self.data_cache[cache_key]
        
        try:
            current_date = self._get_current_date()
            end_date = current_date.strftime('%Y%m%d')
            # 获取足够多的历史数据
            start_date = (current_date - timedelta(days=days*2)).strftime('%Y%m%d')
            
            # 检查是否已有原始数据缓存
            if symbol not in self.raw_data_cache:
                df = ak.fund_etf_hist_em(
                    symbol=symbol,
                    period='daily',
                    start_date=start_date,
                    end_date=datetime.now().strftime('%Y%m%d'),  # 获取到今天的所有数据
                    adjust='qfq'
                )
                
                df = df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '振幅': 'amplitude',
                    '涨跌幅': 'pct_change',
                    '涨跌额': 'change',
                    '换手率': 'turnover'
                })
                
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)
                self.raw_data_cache[symbol] = df
            
            # 从原始数据中筛选截止到模拟日期的数据
            df = self.raw_data_cache[symbol].copy()
            df = df[df['date'] <= pd.to_datetime(current_date)]
            df = df.tail(days)
            
            self.data_cache[cache_key] = df
            return df
            
        except Exception as e:
            print(f"获取{symbol}数据失败: {e}")
            return pd.DataFrame()
    
    def get_market_sentiment(self) -> pd.DataFrame:
        """获取市场情绪指标（融资融券数据）"""
        try:
            margin_df = ak.stock_margin_sse()
            return margin_df
        except Exception as e:
            print(f"获取情绪数据失败: {e}")
            return pd.DataFrame()
    
    def get_fund_flow(self) -> pd.DataFrame:
        """获取资金流向数据"""
        try:
            flow_df = ak.stock_market_fund_flow()
            return flow_df
        except Exception as e:
            print(f"获取资金流向失败: {e}")
            return pd.DataFrame()
    
    def clear_cache(self):
        """清空缓存"""
        self.data_cache.clear()
    
    def clear_all_cache(self):
        """清空所有缓存（包括原始数据）"""
        self.data_cache.clear()
        self.raw_data_cache.clear()


def get_tuesdays_in_range(start_date: str, end_date: str) -> list:
    """
    获取时间范围内的所有周二日期
    
    Args:
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
    
    Returns:
        周二日期列表
    """
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    tuesdays = []
    current = start
    
    # 找到第一个周二
    while current.weekday() != 1:  # 1 表示周二
        current += timedelta(days=1)
    
    # 收集所有周二
    while current <= end:
        tuesdays.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=7)
    
    return tuesdays
