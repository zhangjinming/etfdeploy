"""分析器测试用例（优化版）"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzers.strength import StrengthWeaknessAnalyzer
from analyzers.emotion import EmotionCycleAnalyzer


def create_mock_etf_data(days: int = 200, trend: str = 'neutral') -> pd.DataFrame:
    """创建模拟ETF数据"""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    if trend == 'up':
        base_prices = np.linspace(100, 140, days) + np.random.randn(days) * 2
    elif trend == 'down':
        base_prices = np.linspace(140, 100, days) + np.random.randn(days) * 2
    elif trend == 'volatile':
        base_prices = 100 + np.sin(np.linspace(0, 4*np.pi, days)) * 20 + np.random.randn(days) * 3
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


class TestStrengthWeaknessAnalyzer:
    """强弱分析器测试"""
    
    def test_init_daily_mode(self):
        """测试日线模式初始化"""
        df = create_mock_etf_data(200)
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=False)
        assert analyzer.df is not None
        assert 'rsi' in analyzer.df.columns
        assert 'macd' in analyzer.df.columns
        assert analyzer.use_weekly is False
    
    def test_init_weekly_mode(self):
        """测试周线模式初始化"""
        df = create_mock_etf_data(200)
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        assert analyzer.df is not None
        assert analyzer.use_weekly is True
        # 周线数据应该比日线少
        assert len(analyzer.df) < len(df)
    
    def test_weekly_conversion(self):
        """测试周线转换"""
        df = create_mock_etf_data(100)
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        # 100天约14周
        assert 10 <= len(analyzer.df) <= 20
    
    def test_analyze_strength_returns_dict(self):
        """测试返回字典格式"""
        df = create_mock_etf_data(200)
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        result = analyzer.analyze_strength()
        
        assert isinstance(result, dict)
        assert 'signal' in result
        assert 'score' in result
        assert 'reasons' in result
        assert 'rsi' in result
        assert 'weekly_mode' in result
    
    def test_analyze_strength_signal_values(self):
        """测试信号值范围"""
        df = create_mock_etf_data(200)
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        result = analyzer.analyze_strength()
        
        valid_signals = ['strong_buy', 'buy', 'neutral', 'sell', 'strong_sell']
        assert result['signal'] in valid_signals
    
    def test_analyze_strength_insufficient_data(self):
        """测试数据不足情况"""
        df = create_mock_etf_data(20)
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        result = analyzer.analyze_strength()
        
        assert result['signal'] == 'neutral'
        assert '数据不足' in result['reasons']
    
    def test_uptrend_detection(self):
        """测试上涨趋势检测"""
        df = create_mock_etf_data(200, trend='up')
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        result = analyzer.analyze_strength()
        
        assert result['rsi'] > 40
        assert result['price_position'] > 0.5
    
    def test_downtrend_detection(self):
        """测试下跌趋势检测"""
        df = create_mock_etf_data(200, trend='down')
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        result = analyzer.analyze_strength()
        
        assert result['rsi'] < 60
        assert result['price_position'] < 0.5
    
    def test_bollinger_band_position(self):
        """测试布林带位置计算"""
        df = create_mock_etf_data(200)
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        result = analyzer.analyze_strength()
        
        assert 'bb_position' in result
        assert 0 <= result['bb_position'] <= 1
    
    def test_daily_confirmation(self):
        """测试日线确认信号"""
        df = create_mock_etf_data(200)
        analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        result = analyzer.get_daily_confirmation()
        
        assert 'confirmed' in result
        assert 'daily_rsi' in result


class TestEmotionCycleAnalyzer:
    """情绪周期分析器测试"""
    
    def test_init_weekly_mode(self):
        """测试周线模式初始化"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        assert analyzer.df is not None
        assert 'emotion_index' in analyzer.df.columns
        assert analyzer.use_weekly is True
    
    def test_emotion_indicators_calculated(self):
        """测试情绪指标计算"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        
        assert 'turnover_zscore' in analyzer.df.columns
        assert 'price_position' in analyzer.df.columns
        assert 'momentum' in analyzer.df.columns
        assert 'up_weeks_ratio' in analyzer.df.columns
    
    def test_get_emotion_phase_returns_dict(self):
        """测试返回字典格式"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        result = analyzer.get_emotion_phase()
        
        assert isinstance(result, dict)
        assert 'phase' in result
        assert 'scores' in result
        assert 'suggestion' in result
        assert 'action' in result
        assert 'phase_strength' in result
    
    def test_emotion_phase_values(self):
        """测试情绪阶段值范围"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        result = analyzer.get_emotion_phase()
        
        valid_phases = ['despair', 'hesitation', 'frenzy', 'unknown']
        assert result['phase'] in valid_phases
    
    def test_action_values(self):
        """测试操作建议值范围"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        result = analyzer.get_emotion_phase()
        
        valid_actions = ['buy', 'strong_buy', 'hold', 'sell', 'strong_sell']
        assert result['action'] in valid_actions
    
    def test_emotion_index_range(self):
        """测试情绪指数范围"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        result = analyzer.get_emotion_phase()
        
        # 情绪指数应该在-1到1之间
        assert -1.5 <= result['emotion_index'] <= 1.5
    
    def test_phase_strength(self):
        """测试阶段强度"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        result = analyzer.get_emotion_phase()
        
        assert 0 <= result['phase_strength'] <= 1
    
    def test_emotion_trend(self):
        """测试情绪趋势"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        result = analyzer.get_emotion_trend()
        
        assert 'trend' in result
        assert 'description' in result
        assert 'change' in result
        
        valid_trends = ['improving_fast', 'improving', 'stable', 'deteriorating', 'deteriorating_fast', 'unknown']
        assert result['trend'] in valid_trends
    
    def test_scores_structure(self):
        """测试得分结构"""
        df = create_mock_etf_data(200)
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        result = analyzer.get_emotion_phase()
        
        assert 'despair' in result['scores']
        assert 'hesitation' in result['scores']
        assert 'frenzy' in result['scores']
    
    def test_insufficient_data(self):
        """测试数据不足情况"""
        df = create_mock_etf_data(10)  # 非常少的数据
        analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        result = analyzer.get_emotion_phase()
        
        # 数据不足时应该返回unknown或有效结果
        valid_phases = ['despair', 'hesitation', 'frenzy', 'unknown']
        assert result['phase'] in valid_phases


class TestIntegration:
    """集成测试"""
    
    def test_analyzers_work_together(self):
        """测试分析器协同工作"""
        df = create_mock_etf_data(200)
        
        strength_analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        strength_result = strength_analyzer.analyze_strength()
        
        emotion_analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        emotion_result = emotion_analyzer.get_emotion_phase()
        
        assert strength_result['signal'] is not None
        assert emotion_result['phase'] is not None
    
    def test_consistent_weekly_mode(self):
        """测试周线模式一致性"""
        df = create_mock_etf_data(200)
        
        strength_analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        emotion_analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        
        assert strength_analyzer.use_weekly == emotion_analyzer.use_weekly
    
    def test_rsi_in_valid_range(self):
        """测试RSI在有效范围内"""
        df = create_mock_etf_data(200)
        
        strength_analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        emotion_analyzer = EmotionCycleAnalyzer(df, use_weekly=True)
        
        strength_result = strength_analyzer.analyze_strength()
        emotion_result = emotion_analyzer.get_emotion_phase()
        
        assert 0 <= strength_result['rsi'] <= 100
        assert 0 <= emotion_result['rsi'] <= 100
    
    def test_volatile_market(self):
        """测试波动市场"""
        df = create_mock_etf_data(200, trend='volatile')
        
        strength_analyzer = StrengthWeaknessAnalyzer(df, use_weekly=True)
        result = strength_analyzer.analyze_strength()
        
        # 波动市场信号应该更中性
        assert result['signal'] is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
