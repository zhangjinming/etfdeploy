"""资金面分析和对冲策略测试用例（优化版）"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzers.capital import CapitalFlowAnalyzer
from analyzers.hedge import HedgeStrategy


def create_mock_etf_data(days: int = 200, trend: str = 'neutral') -> pd.DataFrame:
    """创建模拟ETF数据"""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    if trend == 'up':
        base_prices = np.linspace(100, 140, days) + np.random.randn(days) * 2
    elif trend == 'down':
        base_prices = np.linspace(140, 100, days) + np.random.randn(days) * 2
    else:
        base_prices = 100 + np.cumsum(np.random.randn(days) * 0.5)
    
    df = pd.DataFrame({
        'date': dates,
        'open': base_prices * (1 + np.random.randn(days) * 0.01),
        'close': base_prices,
        'high': base_prices * (1 + abs(np.random.randn(days) * 0.02)),
        'low': base_prices * (1 - abs(np.random.randn(days) * 0.02)),
        'volume': np.random.randint(1000000, 5000000, days),
        'amount': np.random.randint(100000000, 500000000, days),
        'pct_change': np.concatenate([[0], np.diff(base_prices) / base_prices[:-1] * 100]),
        'turnover': np.random.uniform(0.5, 3.0, days)
    })
    
    return df


def create_mock_data_fetcher():
    """创建模拟数据获取器"""
    mock_fetcher = MagicMock()
    
    def get_history(symbol, days=250):
        if symbol in ['510300', '510050', '512800', '515180']:  # 大盘
            return create_mock_etf_data(200, 'up')
        elif symbol in ['510500', '159915', '512100']:  # 小盘
            return create_mock_etf_data(200, 'down')
        else:
            return create_mock_etf_data(200, 'neutral')
    
    mock_fetcher.get_etf_history = get_history
    return mock_fetcher


class TestCapitalFlowAnalyzer:
    """资金面分析器测试"""
    
    def test_init_weekly_mode(self):
        """测试周线模式初始化"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        
        assert len(analyzer.large_cap_data) > 0
        assert len(analyzer.small_cap_data) > 0
        assert analyzer.use_weekly is True
    
    def test_init_daily_mode(self):
        """测试日线模式初始化"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=False)
        
        assert analyzer.use_weekly is False
    
    def test_analyze_style_rotation_returns_dict(self):
        """测试返回字典格式"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        result = analyzer.analyze_style_rotation()
        
        assert isinstance(result, dict)
        assert 'style' in result
        assert 'allocation' in result
        assert 'weekly_mode' in result
    
    def test_style_values(self):
        """测试风格值范围"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        result = analyzer.analyze_style_rotation()
        
        valid_styles = ['large_cap_dominant', 'small_cap_dominant', 'balanced']
        assert result['style'] in valid_styles
    
    def test_style_trend(self):
        """测试风格趋势"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        result = analyzer.analyze_style_rotation()
        
        assert 'style_trend' in result
        valid_trends = ['rotating_to_large', 'rotating_to_small', 'stable']
        assert result['style_trend'] in valid_trends
    
    def test_allocation_sum(self):
        """测试配置比例总和"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        result = analyzer.analyze_style_rotation()
        
        allocation = result['allocation']
        total = allocation['large_cap'] + allocation['small_cap']
        assert abs(total - 1.0) < 0.01
    
    def test_efficiency_ratio(self):
        """测试资金效率比"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        result = analyzer.analyze_style_rotation()
        
        assert 'efficiency_ratio' in result
        assert result['efficiency_ratio'] > 0
    
    def test_analyze_capital_efficiency(self):
        """测试资金效率分析"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        result = analyzer.analyze_capital_efficiency()
        
        assert isinstance(result, dict)
        for symbol, data in result.items():
            assert 'efficiency' in data
            assert 'avg_turnover' in data
            assert 'cap_type' in data
    
    def test_market_health(self):
        """测试市场健康度"""
        mock_fetcher = create_mock_data_fetcher()
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        result = analyzer.get_market_health()
        
        assert 'health' in result
        assert 'score' in result
        assert 'factors' in result
        
        valid_health = ['excellent', 'good', 'fair', 'poor', 'unknown']
        assert result['health'] in valid_health
    
    def test_empty_data_handling(self):
        """测试空数据处理"""
        mock_fetcher = MagicMock()
        mock_fetcher.get_etf_history = lambda x, y=250: pd.DataFrame()
        
        analyzer = CapitalFlowAnalyzer(mock_fetcher, use_weekly=True)
        result = analyzer.analyze_style_rotation()
        
        assert 'error' in result


class TestHedgeStrategy:
    """对冲策略测试"""
    
    def test_init_weekly_mode(self):
        """测试周线模式初始化"""
        mock_fetcher = create_mock_data_fetcher()
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        
        assert strategy.data_fetcher is not None
        assert strategy.use_weekly is True
    
    def test_generate_hedge_portfolio_returns_dict(self):
        """测试返回字典格式"""
        mock_fetcher = create_mock_data_fetcher()
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        result = strategy.generate_hedge_portfolio()
        
        assert isinstance(result, dict)
        assert 'long_positions' in result
        assert 'hedge_positions' in result
        assert 'cash_ratio' in result
        assert 'analysis_mode' in result
    
    def test_cash_ratio_dynamic(self):
        """测试动态现金比例"""
        mock_fetcher = create_mock_data_fetcher()
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        result = strategy.generate_hedge_portfolio()
        
        # 现金比例应该在合理范围
        assert 0.1 <= result['cash_ratio'] <= 0.5
    
    def test_net_exposure(self):
        """测试净敞口计算"""
        mock_fetcher = create_mock_data_fetcher()
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        result = strategy.generate_hedge_portfolio()
        
        assert 'net_exposure' in result
        assert 'total_long_weight' in result
        assert 'risk_alerts_count' in result  # 对冲仓位是回避建议，用风险提示数量表示
    
    def test_positions_structure(self):
        """测试持仓结构"""
        mock_fetcher = create_mock_data_fetcher()
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        result = strategy.generate_hedge_portfolio()
        
        for pos in result['long_positions']:
            assert 'symbol' in pos
            assert 'name' in pos
            assert 'weight' in pos
            assert 'reason' in pos
            assert 'composite_score' in pos
            assert 'cap_type' in pos
    
    def test_max_long_positions(self):
        """测试最大多头持仓数"""
        mock_fetcher = create_mock_data_fetcher()
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        result = strategy.generate_hedge_portfolio()
        
        assert len(result['long_positions']) <= 4
    
    def test_max_hedge_positions(self):
        """测试最大对冲持仓数"""
        mock_fetcher = create_mock_data_fetcher()
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        result = strategy.generate_hedge_portfolio()
        
        assert len(result['hedge_positions']) <= 2
    
    def test_scenario_strategies(self):
        """测试情景策略"""
        mock_fetcher = create_mock_data_fetcher()
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        result = strategy.generate_scenario_strategies()
        
        assert 'base' in result
        assert 'bullish' in result
        assert 'bearish' in result
        assert 'volatile' in result
    
    def test_empty_data_handling(self):
        """测试空数据处理"""
        mock_fetcher = MagicMock()
        mock_fetcher.get_etf_history = lambda x, y=250: pd.DataFrame()
        
        strategy = HedgeStrategy(mock_fetcher, use_weekly=True)
        result = strategy.generate_hedge_portfolio()
        
        assert result['long_positions'] == []
        assert result['cash_ratio'] == 0.2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
