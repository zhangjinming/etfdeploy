"""
策略三：资金面分析
核心逻辑：恶炒消耗资金，大盘股拉抬性强，小盘股消耗资金
优化：周线级别分析，增加资金效率和风格动量指标
"""

import pandas as pd
import numpy as np
from typing import Dict, List
from config import ETF_POOL, LARGE_CAP_ETFS, SMALL_CAP_ETFS


class CapitalFlowAnalyzer:
    """
    资金面分析器（周线级别）
    
    核心逻辑：
    1. 恶炒消耗资金 - 小盘股消耗资金是大盘股的约5倍
    2. 资金从大盘流向小票，总体市值未必增加
    3. 资金从小票流向大票，总体市值可以增加
    4. 价值白马领涨，大盘才有拉抬性和持续性
    """
    
    def __init__(self, data_fetcher, use_weekly: bool = True):
        """
        初始化分析器
        
        Args:
            data_fetcher: 数据获取器
            use_weekly: 是否使用周线分析
        """
        self.data_fetcher = data_fetcher
        self.use_weekly = use_weekly
        self.large_cap_data = {}
        self.small_cap_data = {}
        self._load_data()
    
    def _convert_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        """将日线数据转换为周线数据"""
        if df.empty:
            return df
        
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        weekly = df.resample('W').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'amount': 'sum',
            'turnover': 'sum'
        }).dropna()
        
        weekly['pct_change'] = weekly['close'].pct_change() * 100
        weekly = weekly.reset_index()
        
        return weekly
    
    def _load_data(self):
        """加载大小盘ETF数据"""
        for symbol in LARGE_CAP_ETFS:
            df = self.data_fetcher.get_etf_history(symbol)
            if not df.empty:
                if self.use_weekly:
                    df = self._convert_to_weekly(df)
                self.large_cap_data[symbol] = df
        
        for symbol in SMALL_CAP_ETFS:
            df = self.data_fetcher.get_etf_history(symbol)
            if not df.empty:
                if self.use_weekly:
                    df = self._convert_to_weekly(df)
                self.small_cap_data[symbol] = df
    
    def analyze_style_rotation(self, periods: int = None) -> Dict:
        """
        分析大小盘风格轮动
        
        Args:
            periods: 分析周期数（周线默认8周，日线默认20天）
        
        核心指标：
        1. 大小盘相对强弱
        2. 换手率对比（资金消耗效率）
        3. 风格动量
        """
        if not self.large_cap_data or not self.small_cap_data:
            return {'error': '数据不足'}
        
        if periods is None:
            periods = 8 if self.use_weekly else 20
        
        # 计算大盘股指标
        large_cap_metrics = self._calculate_style_metrics(self.large_cap_data, periods)
        
        # 计算小盘股指标
        small_cap_metrics = self._calculate_style_metrics(self.small_cap_data, periods)
        
        if not large_cap_metrics or not small_cap_metrics:
            return {'error': '数据不足'}
        
        # 风格差异分析
        style_diff = large_cap_metrics['avg_return'] - small_cap_metrics['avg_return']
        turnover_ratio = small_cap_metrics['avg_turnover'] / (large_cap_metrics['avg_turnover'] + 0.001)
        
        # 资金效率分析
        # 小盘股单位涨幅消耗的资金量
        large_efficiency = large_cap_metrics['capital_efficiency']
        small_efficiency = small_cap_metrics['capital_efficiency']
        efficiency_ratio = small_efficiency / (large_efficiency + 1e-10)
        
        # 风格动量（近期vs更早期）
        large_momentum = large_cap_metrics['momentum']
        small_momentum = small_cap_metrics['momentum']
        style_momentum = large_momentum - small_momentum
        
        # 判断风格
        if style_diff > 2:
            style = 'large_cap_dominant'
            suggestion = '大盘股占优，资金效率高，市场拉抬性强'
            allocation = {'large_cap': 0.7, 'small_cap': 0.3}
        elif style_diff < -2:
            style = 'small_cap_dominant'
            # 根据效率比判断风险
            if efficiency_ratio > 3:
                suggestion = '小盘股占优但资金消耗大，注意回调风险'
            else:
                suggestion = '小盘股占优，可适度参与'
            allocation = {'large_cap': 0.4, 'small_cap': 0.6}
        else:
            style = 'balanced'
            suggestion = '风格均衡，可分散配置'
            allocation = {'large_cap': 0.5, 'small_cap': 0.5}
        
        # 风格趋势判断
        if style_momentum > 1:
            style_trend = 'rotating_to_large'
            trend_suggestion = '风格正在向大盘股切换'
        elif style_momentum < -1:
            style_trend = 'rotating_to_small'
            trend_suggestion = '风格正在向小盘股切换'
        else:
            style_trend = 'stable'
            trend_suggestion = '风格相对稳定'
        
        return {
            'style': style,
            'style_trend': style_trend,
            'trend_suggestion': trend_suggestion,
            'large_cap_return': large_cap_metrics['avg_return'],
            'small_cap_return': small_cap_metrics['avg_return'],
            'style_diff': style_diff,
            'turnover_ratio': turnover_ratio,
            'efficiency_ratio': efficiency_ratio,
            'style_momentum': style_momentum,
            'suggestion': suggestion,
            'allocation': allocation,
            'weekly_mode': self.use_weekly,
            'large_cap_details': large_cap_metrics,
            'small_cap_details': small_cap_metrics
        }
    
    def _calculate_style_metrics(self, data_dict: Dict, periods: int) -> Dict:
        """计算风格指标"""
        returns = []
        turnovers = []
        amounts = []
        price_changes = []
        momentums = []
        
        half_period = periods // 2
        
        for symbol, df in data_dict.items():
            if len(df) < periods:
                continue
            
            recent = df.tail(periods)
            
            # 收益率
            ret = (recent['close'].iloc[-1] / recent['close'].iloc[0] - 1) * 100
            returns.append(ret)
            
            # 换手率
            turnovers.append(recent['turnover'].mean())
            
            # 成交额
            amounts.append(recent['amount'].sum())
            
            # 价格变化
            price_changes.append(recent['close'].iloc[-1] - recent['close'].iloc[0])
            
            # 动量（近半期vs前半期）
            if len(recent) >= periods:
                recent_half = (recent['close'].iloc[-1] / recent['close'].iloc[-half_period] - 1) * 100
                prev_half = (recent['close'].iloc[-half_period] / recent['close'].iloc[0] - 1) * 100
                momentums.append(recent_half - prev_half)
        
        if not returns:
            return {}
        
        # 计算资金效率（单位涨幅所需资金）
        total_amount = sum(amounts)
        total_price_change = sum([abs(pc) for pc in price_changes])
        capital_efficiency = total_amount / (total_price_change + 1e-10)
        
        return {
            'avg_return': np.mean(returns),
            'avg_turnover': np.mean(turnovers),
            'total_amount': total_amount,
            'capital_efficiency': capital_efficiency,
            'momentum': np.mean(momentums) if momentums else 0,
            'return_std': np.std(returns) if len(returns) > 1 else 0
        }
    
    def analyze_capital_efficiency(self) -> Dict:
        """
        分析各ETF资金消耗效率
        
        核心逻辑：
        - 拉动同样的市值增幅，小盘股消耗的资金约是大盘股的5倍
        - 期盼牛市，需要茅抬（价值白马领涨）
        """
        results = {}
        periods = 8 if self.use_weekly else 20
        
        all_data = {**self.large_cap_data, **self.small_cap_data}
        
        for symbol, df in all_data.items():
            if len(df) < periods:
                continue
            
            recent = df.tail(periods)
            
            # 计算单位涨幅所需成交额
            price_change = recent['close'].iloc[-1] - recent['close'].iloc[0]
            total_amount = recent['amount'].sum()
            avg_turnover = recent['turnover'].mean()
            
            # 资金效率（越低越好）
            if abs(price_change) > 0.001:
                efficiency = total_amount / abs(price_change)
            else:
                efficiency = float('inf')
            
            # 判断是大盘还是小盘
            cap_type = 'large' if symbol in LARGE_CAP_ETFS else 'small'
            
            results[symbol] = {
                'name': ETF_POOL.get(symbol, symbol),
                'cap_type': cap_type,
                'price_change': price_change,
                'price_change_pct': (price_change / recent['close'].iloc[0]) * 100,
                'total_amount': total_amount,
                'efficiency': efficiency,
                'avg_turnover': avg_turnover
            }
        
        # 计算效率排名
        sorted_by_efficiency = sorted(
            [(k, v) for k, v in results.items() if v['efficiency'] != float('inf')],
            key=lambda x: x[1]['efficiency']
        )
        
        for rank, (symbol, _) in enumerate(sorted_by_efficiency, 1):
            results[symbol]['efficiency_rank'] = rank
        
        return results
    
    def get_market_health(self) -> Dict:
        """
        评估市场健康度
        
        健康市场特征：
        - 大盘股领涨
        - 换手率适中
        - 资金效率高
        """
        style_result = self.analyze_style_rotation()
        
        if 'error' in style_result:
            return {'health': 'unknown', 'score': 0}
        
        health_score = 0
        factors = []
        
        # 1. 风格健康度
        if style_result['style'] == 'large_cap_dominant':
            health_score += 3
            factors.append("大盘股领涨，拉抬性强")
        elif style_result['style'] == 'balanced':
            health_score += 2
            factors.append("风格均衡")
        else:
            health_score += 1
            factors.append("小盘股领涨，消耗资金")
        
        # 2. 资金效率
        if style_result['efficiency_ratio'] < 2:
            health_score += 2
            factors.append("资金效率较高")
        elif style_result['efficiency_ratio'] < 4:
            health_score += 1
            factors.append("资金效率一般")
        else:
            factors.append("资金效率低，消耗大")
        
        # 3. 换手率
        if 1 < style_result['turnover_ratio'] < 3:
            health_score += 1
            factors.append("换手率比例正常")
        elif style_result['turnover_ratio'] > 5:
            factors.append("小盘股换手率过高，投机氛围重")
        
        # 4. 风格趋势
        if style_result['style_trend'] == 'rotating_to_large':
            health_score += 1
            factors.append("风格向大盘切换，利于指数")
        
        # 判断健康等级
        if health_score >= 6:
            health = 'excellent'
            suggestion = '市场结构健康，适合积极配置'
        elif health_score >= 4:
            health = 'good'
            suggestion = '市场结构较好，可正常配置'
        elif health_score >= 2:
            health = 'fair'
            suggestion = '市场结构一般，需谨慎配置'
        else:
            health = 'poor'
            suggestion = '市场结构不佳，建议防守'
        
        return {
            'health': health,
            'score': health_score,
            'max_score': 7,
            'factors': factors,
            'suggestion': suggestion,
            'style_analysis': style_result
        }
