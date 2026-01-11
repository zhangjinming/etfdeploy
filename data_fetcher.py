"""
数据获取模块

支持从多个数据源获取ETF历史数据：
1. AKShare (推荐)
2. Tushare
3. 本地CSV文件
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import os
import warnings

warnings.filterwarnings('ignore')


class DataFetcher:
    """
    ETF数据获取器
    
    支持多种数据源，自动处理数据格式。
    """
    
    def __init__(self, data_source: str = 'akshare', cache_dir: str = None):
        """
        初始化数据获取器
        
        Args:
            data_source: 数据源 ('akshare', 'tushare', 'local')
            cache_dir: 缓存目录
        """
        self.data_source = data_source
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(__file__), 'data_cache')
        self.cache: Dict[str, pd.DataFrame] = {}
        
        # 确保缓存目录存在
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_etf_history(self, symbol: str, start_date: str = None, 
                        end_date: str = None, days: int = 365) -> pd.DataFrame:
        """
        获取ETF历史数据
        
        Args:
            symbol: ETF代码 (如 '515450')
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            days: 如果未指定日期，获取最近N天数据
            
        Returns:
            包含 date, open, high, low, close, volume, amount, turnover 的DataFrame
        """
        # 检查缓存
        cache_key = f"{symbol}_{start_date}_{end_date}_{days}"
        if cache_key in self.cache:
            return self.cache[cache_key].copy()
        
        # 设置日期范围
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if start_date is None:
            start_dt = datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=days)
            start_date = start_dt.strftime('%Y-%m-%d')
        
        # 优先检查本地缓存文件
        local_filepath = os.path.join(self.cache_dir, f"{symbol}.csv")
        if os.path.exists(local_filepath):
            df = self._fetch_from_local(symbol, start_date, end_date)
            if not df.empty:
                return df
        
        # 本地无数据时，根据数据源从网络获取
        if self.data_source == 'akshare':
            df = self._fetch_from_akshare(symbol, start_date, end_date)
        elif self.data_source == 'tushare':
            df = self._fetch_from_tushare(symbol, start_date, end_date)
        elif self.data_source == 'local':
            df = self._fetch_from_local(symbol, start_date, end_date)
        else:
            # 尝试生成模拟数据用于测试
            df = self._generate_mock_data(symbol, start_date, end_date)
        
        if not df.empty:
            self.cache[cache_key] = df.copy()
        
        return df
    
    def _fetch_from_akshare(self, symbol: str, start_date: str, 
                            end_date: str) -> pd.DataFrame:
        """从AKShare获取数据"""
        try:
            import akshare as ak
            
            # ETF代码格式处理
            if symbol.startswith('5'):
                # 上海ETF
                full_symbol = f"sh{symbol}"
            else:
                # 深圳ETF
                full_symbol = f"sz{symbol}"
            
            # 获取ETF日线数据
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # 前复权
            )
            
            if df.empty:
                return pd.DataFrame()
            
            # 重命名列
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume',
                '成交额': 'amount',
                '换手率': 'turnover',
            })
            
            # 选择需要的列
            columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'turnover']
            df = df[[c for c in columns if c in df.columns]]
            
            # 确保turnover列存在
            if 'turnover' not in df.columns:
                df['turnover'] = 0.0
            
            # 计算涨跌幅
            df['pct_change'] = df['close'].pct_change() * 100
            
            # 转换日期格式
            df['date'] = pd.to_datetime(df['date'])
            
            # 按日期排序
            df = df.sort_values('date').reset_index(drop=True)
            
            return df
            
        except ImportError:
            print("请安装akshare: pip install akshare")
            return self._generate_mock_data(symbol, start_date, end_date)
        except Exception as e:
            print(f"AKShare获取数据失败: {e}")
            return self._generate_mock_data(symbol, start_date, end_date)
    
    def _fetch_from_tushare(self, symbol: str, start_date: str, 
                            end_date: str) -> pd.DataFrame:
        """从Tushare获取数据"""
        try:
            import tushare as ts
            
            # 需要设置token
            # ts.set_token('your_token')
            pro = ts.pro_api()
            
            # ETF代码格式
            if symbol.startswith('5'):
                ts_code = f"{symbol}.SH"
            else:
                ts_code = f"{symbol}.SZ"
            
            df = pro.fund_daily(
                ts_code=ts_code,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', '')
            )
            
            if df.empty:
                return pd.DataFrame()
            
            # 重命名列
            df = df.rename(columns={
                'trade_date': 'date',
                'pre_close': 'pre_close',
            })
            
            # 转换日期格式
            df['date'] = pd.to_datetime(df['date'])
            
            # 计算涨跌幅
            df['pct_change'] = df['close'].pct_change() * 100
            
            # 添加换手率（如果没有）
            if 'turnover' not in df.columns:
                df['turnover'] = 0.0
            
            df = df.sort_values('date').reset_index(drop=True)
            
            return df
            
        except ImportError:
            print("请安装tushare: pip install tushare")
            return self._generate_mock_data(symbol, start_date, end_date)
        except Exception as e:
            print(f"Tushare获取数据失败: {e}")
            return self._generate_mock_data(symbol, start_date, end_date)
    
    def _fetch_from_local(self, symbol: str, start_date: str, 
                          end_date: str) -> pd.DataFrame:
        """从本地文件获取数据"""
        filepath = os.path.join(self.cache_dir, f"{symbol}.csv")
        
        if not os.path.exists(filepath):
            print(f"本地文件不存在: {filepath}")
            return self._generate_mock_data(symbol, start_date, end_date)
        
        df = pd.read_csv(filepath)
        df['date'] = pd.to_datetime(df['date'])
        
        # 过滤日期范围
        mask = (df['date'] >= start_date) & (df['date'] <= end_date)
        df = df[mask].reset_index(drop=True)
        
        return df
    
    def _generate_mock_data(self, symbol: str, start_date: str, 
                            end_date: str) -> pd.DataFrame:
        """
        生成模拟数据（用于测试）
        
        基于ETF类型生成不同特征的模拟数据
        """
        from config import LARGE_CAP_ETFS, SMALL_CAP_ETFS, SPECIAL_ASSETS
        
        # 生成日期序列
        dates = pd.date_range(start=start_date, end=end_date, freq='B')  # 工作日
        n = len(dates)
        
        if n == 0:
            return pd.DataFrame()
        
        # 根据ETF类型设置不同的波动率和趋势
        if symbol in LARGE_CAP_ETFS:
            volatility = 0.015  # 大盘股波动小
            trend = 0.0002      # 轻微上涨趋势
            base_price = 1.0
        elif symbol in SMALL_CAP_ETFS:
            volatility = 0.025  # 小盘股波动大
            trend = 0.0003
            base_price = 1.5
        elif symbol in SPECIAL_ASSETS:
            volatility = 0.018
            trend = 0.0004      # 特殊资产有独立趋势
            base_price = 2.0
        else:
            volatility = 0.02
            trend = 0.0001
            base_price = 1.2
        
        # 生成价格序列（几何布朗运动）
        np.random.seed(hash(symbol) % 2**32)  # 确保同一symbol生成相同数据
        
        returns = np.random.normal(trend, volatility, n)
        
        # 添加一些周期性波动（模拟情绪周期）
        cycle = np.sin(np.linspace(0, 4*np.pi, n)) * 0.005
        returns = returns + cycle
        
        # 计算价格
        prices = base_price * np.cumprod(1 + returns)
        
        # 生成OHLC数据
        df = pd.DataFrame({
            'date': dates,
            'close': prices,
        })
        
        # 生成开盘价、最高价、最低价
        df['open'] = df['close'].shift(1).fillna(base_price)
        daily_range = np.abs(np.random.normal(0, volatility * 0.5, n))
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + daily_range)
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - daily_range)
        
        # 生成成交量和成交额
        base_volume = 10000000 if symbol in LARGE_CAP_ETFS else 5000000
        df['volume'] = np.random.uniform(0.5, 2.0, n) * base_volume
        df['amount'] = df['volume'] * df['close']
        
        # 生成换手率
        df['turnover'] = np.random.uniform(0.5, 3.0, n)
        
        # 计算涨跌幅
        df['pct_change'] = df['close'].pct_change() * 100
        
        return df
    
    def save_to_local(self, symbol: str, df: pd.DataFrame):
        """保存数据到本地"""
        filepath = os.path.join(self.cache_dir, f"{symbol}.csv")
        df.to_csv(filepath, index=False)
    
    def get_multiple_etfs(self, symbols: List[str], **kwargs) -> Dict[str, pd.DataFrame]:
        """批量获取多个ETF数据"""
        result = {}
        for symbol in symbols:
            df = self.get_etf_history(symbol, **kwargs)
            if not df.empty:
                result[symbol] = df
        return result
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """获取最新价格"""
        df = self.get_etf_history(symbol, days=5)
        if df.empty:
            return None
        return df.iloc[-1]['close']
    
    def get_price_change(self, symbol: str, days: int = 1) -> Optional[float]:
        """获取N日涨跌幅"""
        df = self.get_etf_history(symbol, days=days + 10)
        if len(df) < days + 1:
            return None
        return (df.iloc[-1]['close'] / df.iloc[-(days+1)]['close'] - 1) * 100
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()


class DataValidator:
    """数据验证器"""
    
    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> Dict[str, any]:
        """
        验证数据质量
        
        Returns:
            验证结果字典
        """
        result = {
            'valid': True,
            'issues': [],
            'stats': {}
        }
        
        if df.empty:
            result['valid'] = False
            result['issues'].append('数据为空')
            return result
        
        required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing_columns = [c for c in required_columns if c not in df.columns]
        if missing_columns:
            result['valid'] = False
            result['issues'].append(f'缺少列: {missing_columns}')
        
        # 检查缺失值
        null_counts = df[required_columns].isnull().sum()
        if null_counts.sum() > 0:
            result['issues'].append(f'存在缺失值: {null_counts[null_counts > 0].to_dict()}')
        
        # 检查异常值
        if 'close' in df.columns:
            price_std = df['close'].std()
            price_mean = df['close'].mean()
            outliers = df[(df['close'] > price_mean + 4*price_std) | 
                         (df['close'] < price_mean - 4*price_std)]
            if len(outliers) > 0:
                result['issues'].append(f'存在{len(outliers)}个价格异常值')
        
        # 统计信息
        result['stats'] = {
            'rows': len(df),
            'date_range': f"{df['date'].min()} ~ {df['date'].max()}" if 'date' in df.columns else 'N/A',
            'price_range': f"{df['close'].min():.2f} ~ {df['close'].max():.2f}" if 'close' in df.columns else 'N/A',
        }
        
        return result


# 全局数据获取器实例
data_fetcher = DataFetcher()
