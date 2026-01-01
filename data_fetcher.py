"""数据获取模块"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')


class ETFDataFetcher:
    """ETF数据获取器"""
    
    # 本地缓存目录
    CACHE_DIR = Path(__file__).parent / "data_cache"
    
    def __init__(self, simulate_date: Optional[str] = None):
        """
        初始化数据获取器
        
        Args:
            simulate_date: 模拟日期，格式 'YYYY-MM-DD'，为None时使用当前日期
        """
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.raw_data_cache: Dict[str, pd.DataFrame] = {}  # 存储原始完整数据
        self.simulate_date = simulate_date
        
        # 确保缓存目录存在
        self.CACHE_DIR.mkdir(exist_ok=True)
    
    def set_simulate_date(self, date: str):
        """设置模拟日期，并清空缓存"""
        self.simulate_date = date
        self.data_cache.clear()
    
    def _get_current_date(self) -> datetime:
        """获取当前日期（模拟或真实）"""
        if self.simulate_date:
            return datetime.strptime(self.simulate_date, '%Y-%m-%d')
        return datetime.now()
    
    def _get_cache_file_path(self, symbol: str) -> Path:
        """获取本地缓存文件路径"""
        return self.CACHE_DIR / f"{symbol}.csv"
    
    def _load_from_local(self, symbol: str) -> Optional[pd.DataFrame]:
        """从本地CSV文件加载数据"""
        cache_file = self._get_cache_file_path(symbol)
        if cache_file.exists():
            try:
                df = pd.read_csv(cache_file)
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)
                return df
            except Exception as e:
                print(f"读取本地缓存{symbol}失败: {e}")
        return None
    
    def _save_to_local(self, symbol: str, df: pd.DataFrame):
        """保存数据到本地CSV文件"""
        try:
            cache_file = self._get_cache_file_path(symbol)
            df.to_csv(cache_file, index=False)
        except Exception as e:
            print(f"保存本地缓存{symbol}失败: {e}")
    
    def _fetch_from_network(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """从网络获取ETF数据"""
        try:
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                period='daily',
                start_date=start_date,
                end_date=end_date,
                adjust='qfq'
            )
            
            if df is None or df.empty:
                return None
            
            # 兼容不同版本的akshare列名
            column_mapping = {
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
            }
            
            # 只重命名存在的列
            existing_columns = {k: v for k, v in column_mapping.items() if k in df.columns}
            if existing_columns:
                df = df.rename(columns=existing_columns)
            
            # 检查是否有date列，如果没有则尝试其他可能的列名
            if 'date' not in df.columns:
                # 尝试查找日期列
                date_candidates = ['日期', 'Date', 'DATE', 'trade_date', '交易日期']
                for col in date_candidates:
                    if col in df.columns:
                        df = df.rename(columns={col: 'date'})
                        break
                
                # 如果还是没有date列，检查是否有索引可用
                if 'date' not in df.columns and df.index.name in ['日期', 'date', 'Date']:
                    df = df.reset_index()
                    if '日期' in df.columns:
                        df = df.rename(columns={'日期': 'date'})
            
            if 'date' not in df.columns:
                print(f"警告: {symbol}数据缺少日期列，可用列: {df.columns.tolist()}")
                return None
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            return df
        except Exception as e:
            print(f"从网络获取{symbol}数据失败: {e}")
            return None
    
    def get_etf_history(self, symbol: str, days: int = 250) -> pd.DataFrame:
        """获取ETF历史数据（截止到模拟日期）"""
        cache_key = f"{symbol}_{self.simulate_date}"
        if cache_key in self.data_cache:
            return self.data_cache[cache_key]
        
        try:
            current_date = self._get_current_date()
            today = datetime.now()
            # 获取足够多的历史数据
            start_date = (current_date - timedelta(days=days*2)).strftime('%Y%m%d')
            
            # 判断需要数据的截止日期：回测模式用模拟日期，否则用今天
            # 这样回测时如果本地数据已覆盖模拟日期，就不会去网络获取
            required_end_date = current_date if self.simulate_date else today
            
            # 检查是否已有内存缓存
            if symbol not in self.raw_data_cache:
                # 优先从本地CSV加载
                local_df = self._load_from_local(symbol)
                
                if local_df is not None and len(local_df) > 0:
                    # 检查本地数据是否满足需求
                    latest_date = local_df['date'].max()
                    if latest_date.date() < required_end_date.date():
                        # 本地数据不够，从网络获取增量数据
                        new_start = (latest_date + timedelta(days=1)).strftime('%Y%m%d')
                        new_end = today.strftime('%Y%m%d')  # 网络获取还是用真实今天
                        new_df = self._fetch_from_network(symbol, new_start, new_end)
                        
                        if new_df is not None and len(new_df) > 0:
                            # 合并数据并去重
                            df = pd.concat([local_df, new_df], ignore_index=True)
                            df = df.drop_duplicates(subset=['date'], keep='last')
                            df = df.sort_values('date').reset_index(drop=True)
                            # 保存更新后的数据到本地
                            self._save_to_local(symbol, df)
                        else:
                            df = local_df
                    else:
                        df = local_df
                else:
                    # 本地无数据，从网络获取
                    df = self._fetch_from_network(symbol, start_date, today.strftime('%Y%m%d'))
                    if df is not None and len(df) > 0:
                        # 保存到本地
                        self._save_to_local(symbol, df)
                    else:
                        return pd.DataFrame()
                
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


def get_tuesdays_in_range(start_date: str, end_date: str, monthly_only: bool = True) -> list:
    """
    获取时间范围内的周二日期
    
    Args:
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
        monthly_only: 【测试加速】True=只返回每月第一周的周二，False=返回所有周二
                      注意：这是测试用参数，实际使用时应设为 False
    
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
    
    # 收集周二
    while current <= end:
        if monthly_only:
            # 【测试模式】只取每月第一周的周二（日期 <= 7）
            if current.day <= 7:
                tuesdays.append(current.strftime('%Y-%m-%d'))
        else:
            # 【正常模式】取所有周二
            tuesdays.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=7)
    
    return tuesdays
