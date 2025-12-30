"""数据获取器测试用例"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_fetcher import ETFDataFetcher


class TestETFDataFetcher:
    """ETF数据获取器测试"""
    
    def test_init(self):
        """测试初始化"""
        fetcher = ETFDataFetcher()
        assert fetcher.data_cache == {}
    
    def test_clear_cache(self):
        """测试清空缓存"""
        fetcher = ETFDataFetcher()
        fetcher.data_cache['test'] = pd.DataFrame()
        fetcher.clear_cache()
        assert fetcher.data_cache == {}
    
    @patch('data_fetcher.ak.fund_etf_hist_em')
    def test_get_etf_history_success(self, mock_ak):
        """测试成功获取ETF历史数据"""
        # 模拟akshare返回数据
        mock_data = pd.DataFrame({
            '日期': pd.date_range('2024-01-01', periods=100),
            '开盘': [100.0] * 100,
            '收盘': [101.0] * 100,
            '最高': [102.0] * 100,
            '最低': [99.0] * 100,
            '成交量': [1000000] * 100,
            '成交额': [100000000] * 100,
            '振幅': [2.0] * 100,
            '涨跌幅': [1.0] * 100,
            '涨跌额': [1.0] * 100,
            '换手率': [1.5] * 100
        })
        mock_ak.return_value = mock_data
        
        fetcher = ETFDataFetcher()
        result = fetcher.get_etf_history('510300')
        
        assert not result.empty
        assert 'close' in result.columns
        assert 'date' in result.columns
    
    @patch('data_fetcher.ak.fund_etf_hist_em')
    def test_get_etf_history_cache(self, mock_ak):
        """测试缓存机制"""
        mock_data = pd.DataFrame({
            '日期': pd.date_range('2024-01-01', periods=100),
            '开盘': [100.0] * 100,
            '收盘': [101.0] * 100,
            '最高': [102.0] * 100,
            '最低': [99.0] * 100,
            '成交量': [1000000] * 100,
            '成交额': [100000000] * 100,
            '振幅': [2.0] * 100,
            '涨跌幅': [1.0] * 100,
            '涨跌额': [1.0] * 100,
            '换手率': [1.5] * 100
        })
        mock_ak.return_value = mock_data
        
        fetcher = ETFDataFetcher()
        
        # 第一次调用
        result1 = fetcher.get_etf_history('510300')
        # 第二次调用应该使用缓存
        result2 = fetcher.get_etf_history('510300')
        
        # akshare只应该被调用一次
        assert mock_ak.call_count == 1
        assert result1.equals(result2)
    
    @patch('data_fetcher.ak.fund_etf_hist_em')
    def test_get_etf_history_failure(self, mock_ak):
        """测试获取数据失败"""
        mock_ak.side_effect = Exception("Network error")
        
        fetcher = ETFDataFetcher()
        result = fetcher.get_etf_history('510300')
        
        assert result.empty
    
    @patch('data_fetcher.ak.stock_margin_sse')
    def test_get_market_sentiment_success(self, mock_ak):
        """测试获取市场情绪数据"""
        mock_data = pd.DataFrame({'融资余额': [1000000000]})
        mock_ak.return_value = mock_data
        
        fetcher = ETFDataFetcher()
        result = fetcher.get_market_sentiment()
        
        assert not result.empty
    
    @patch('data_fetcher.ak.stock_margin_sse')
    def test_get_market_sentiment_failure(self, mock_ak):
        """测试获取情绪数据失败"""
        mock_ak.side_effect = Exception("API error")
        
        fetcher = ETFDataFetcher()
        result = fetcher.get_market_sentiment()
        
        assert result.empty
    
    @patch('data_fetcher.ak.stock_market_fund_flow')
    def test_get_fund_flow_success(self, mock_ak):
        """测试获取资金流向数据"""
        mock_data = pd.DataFrame({'主力净流入': [1000000]})
        mock_ak.return_value = mock_data
        
        fetcher = ETFDataFetcher()
        result = fetcher.get_fund_flow()
        
        assert not result.empty
    
    @patch('data_fetcher.ak.stock_market_fund_flow')
    def test_get_fund_flow_failure(self, mock_ak):
        """测试获取资金流向失败"""
        mock_ak.side_effect = Exception("API error")
        
        fetcher = ETFDataFetcher()
        result = fetcher.get_fund_flow()
        
        assert result.empty


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
