"""配置测试用例"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ETF_POOL, LARGE_CAP_ETFS, SMALL_CAP_ETFS


class TestConfig:
    """配置测试"""
    
    def test_etf_pool_not_empty(self):
        """测试ETF池不为空"""
        assert len(ETF_POOL) > 0
    
    def test_etf_pool_structure(self):
        """测试ETF池结构"""
        for symbol, name in ETF_POOL.items():
            assert isinstance(symbol, str)
            assert isinstance(name, str)
            assert len(symbol) == 6  # ETF代码为6位
    
    def test_large_cap_etfs_in_pool(self):
        """测试大盘ETF在池中"""
        for symbol in LARGE_CAP_ETFS:
            assert symbol in ETF_POOL
    
    def test_small_cap_etfs_in_pool(self):
        """测试小盘ETF在池中"""
        for symbol in SMALL_CAP_ETFS:
            assert symbol in ETF_POOL
    
    def test_no_overlap(self):
        """测试大小盘分类无重叠"""
        large_set = set(LARGE_CAP_ETFS)
        small_set = set(SMALL_CAP_ETFS)
        assert len(large_set & small_set) == 0
    
    def test_etf_codes_valid(self):
        """测试ETF代码格式有效"""
        for symbol in ETF_POOL.keys():
            assert symbol.isdigit()
            # 上海ETF以51开头，深圳ETF以15开头
            assert symbol.startswith('51') or symbol.startswith('15')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
