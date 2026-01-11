"""
综合分析引擎

整合五大策略：
1. 强弱分析法 - 该涨不涨看跌，该跌不跌看涨
2. 情绪周期分析 - 绝望中产生→犹豫中发展→疯狂中消亡
3. 资金面分析 - 恶炒消耗资金，大盘拉抬性强
4. 对冲战法 - 以变应变，留有余地
5. 分类应对法 - 不同ETF有单独的策略

提供准确的入场点和出场点。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

from config import (
    ETF_POOL, LARGE_CAP_ETFS, SMALL_CAP_ETFS, SPECIAL_ASSETS,
    SIGNAL_THRESHOLDS, RISK_PARAMS, ETFStrategyConfig
)
from etf_strategies import ETFStrategy, ETFStrategyManager, strategy_manager
from data_fetcher import DataFetcher, data_fetcher
from analyzers.strength import StrengthWeaknessAnalyzer
from analyzers.emotion import EmotionCycleAnalyzer
from analyzers.capital import CapitalFlowAnalyzer
from analyzers.hedge import HedgeStrategy


@dataclass
class TradeSignal:
    """交易信号"""
    symbol: str
    name: str
    action: str              # strong_buy, buy, hold, sell, strong_sell
    confidence: float        # 置信度 0-1
    entry_price: float       # 建议入场价
    stop_loss: float         # 止损价
    take_profit: float       # 止盈价
    position_size: float     # 建议仓位
    reasons: List[str]       # 理由
    timestamp: datetime      # 信号时间
    validity_weeks: int      # 信号有效周数
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'action': self.action,
            'confidence': self.confidence,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'position_size': self.position_size,
            'reasons': self.reasons,
            'timestamp': self.timestamp.isoformat(),
            'validity_weeks': self.validity_weeks,
        }


@dataclass
class AnalysisResult:
    """分析结果"""
    symbol: str
    name: str
    
    # 强弱分析
    strength_signal: str
    strength_score: float
    strength_reasons: List[str]
    
    # 情绪分析
    emotion_phase: str
    emotion_score: float
    emotion_trend: str
    
    # 趋势分析
    trend_direction: str
    trend_confirmed: bool
    
    # 综合评分
    composite_score: float
    
    # 交易信号
    trade_signal: Optional[TradeSignal]
    
    # 策略配置
    strategy_config: Dict
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'strength': {
                'signal': self.strength_signal,
                'score': self.strength_score,
                'reasons': self.strength_reasons,
            },
            'emotion': {
                'phase': self.emotion_phase,
                'score': self.emotion_score,
                'trend': self.emotion_trend,
            },
            'trend': {
                'direction': self.trend_direction,
                'confirmed': self.trend_confirmed,
            },
            'composite_score': self.composite_score,
            'trade_signal': self.trade_signal.to_dict() if self.trade_signal else None,
            'strategy_config': self.strategy_config,
        }


class AnalyzerEngine:
    """
    综合分析引擎
    
    整合所有分析器，根据每个ETF的独立策略配置生成交易信号。
    """
    
    def __init__(self, data_fetcher: DataFetcher = None, 
                 strategy_manager: ETFStrategyManager = None):
        """
        初始化分析引擎
        
        Args:
            data_fetcher: 数据获取器
            strategy_manager: 策略管理器
        """
        self.data_fetcher = data_fetcher or DataFetcher()
        self.strategy_manager = strategy_manager or ETFStrategyManager()
        self.market_regime: Optional[Dict] = None
        self.capital_analyzer: Optional[CapitalFlowAnalyzer] = None
    
    def analyze_etf(self, symbol: str) -> Optional[AnalysisResult]:
        """
        分析单个ETF
        
        Args:
            symbol: ETF代码
            
        Returns:
            分析结果
        """
        # 获取策略配置
        strategy = self.strategy_manager.get_strategy(symbol)
        if strategy is None:
            # 使用默认配置
            strategy = self.strategy_manager.create_strategy_from_template(
                symbol, 
                ETF_POOL.get(symbol, symbol),
                'balanced'
            )
        
        # 获取数据
        df = self.data_fetcher.get_etf_history(symbol, days=365)
        if df.empty or len(df) < 60:
            return None
        
        # 1. 强弱分析
        strength_analyzer = StrengthWeaknessAnalyzer(
            df, 
            use_weekly=strategy.use_weekly,
            symbol=symbol
        )
        strength_result = strength_analyzer.analyze_strength()
        
        # 2. 情绪分析
        emotion_analyzer = EmotionCycleAnalyzer(
            df,
            use_weekly=strategy.use_weekly
        )
        emotion_result = emotion_analyzer.get_emotion_phase(market_regime=self.market_regime)
        emotion_trend = emotion_analyzer.get_emotion_trend()
        
        # 3. 计算综合评分（使用策略权重）
        composite_score = self._calculate_composite_score(
            strength_result, 
            emotion_result,
            strategy
        )
        
        # 4. 生成交易信号
        trade_signal = self._generate_trade_signal(
            symbol,
            df,
            strength_result,
            emotion_result,
            composite_score,
            strategy
        )
        
        # 构建分析结果
        trend_info = strength_result.get('trend', {})
        
        return AnalysisResult(
            symbol=symbol,
            name=strategy.name,
            strength_signal=strength_result['signal'],
            strength_score=strength_result['score'],
            strength_reasons=strength_result.get('reasons', []),
            emotion_phase=emotion_result['phase'],
            emotion_score=emotion_result.get('emotion_index', 0),
            emotion_trend=emotion_trend.get('trend', 'unknown'),
            trend_direction=trend_info.get('direction', 'unknown'),
            trend_confirmed=trend_info.get('confirmed', False),
            composite_score=composite_score,
            trade_signal=trade_signal,
            strategy_config=strategy.to_dict(),
        )
    
    def _calculate_composite_score(self, strength: Dict, emotion: Dict, 
                                   strategy: ETFStrategy) -> float:
        """
        根据策略权重计算综合评分
        
        Args:
            strength: 强弱分析结果
            emotion: 情绪分析结果
            strategy: 策略配置
            
        Returns:
            综合评分 (-1 到 1)
        """
        weights = strategy.weights
        
        # 强弱得分归一化 (-5 ~ 5 -> -1 ~ 1)
        strength_score = strength['score'] / 5
        
        # 情绪阶段得分
        phase = emotion['phase']
        if phase == 'despair':
            emotion_phase_score = 1.0
        elif phase == 'hesitation':
            emotion_phase_score = 0.0
        elif phase == 'frenzy':
            emotion_phase_score = -0.8
        else:
            emotion_phase_score = 0.0
        
        # 趋势得分
        trend_info = strength.get('trend', {})
        trend_direction = trend_info.get('direction', 'unknown')
        trend_confirmed = trend_info.get('confirmed', False)
        
        if trend_direction == 'uptrend':
            trend_score = 0.8 if trend_confirmed else 0.4
        elif trend_direction == 'downtrend':
            trend_score = -0.8 if trend_confirmed else -0.4
        else:
            trend_score = 0.0
        
        # 情绪指数得分（反转）
        emotion_index = emotion.get('emotion_index', 0)
        emotion_index_score = -emotion_index
        
        # 特殊规则处理
        special_rules = strategy.special_rules
        
        # 趋势跟踪资产：忽略情绪周期
        if special_rules.get('trend_following'):
            weights.emotion = 0.05
            weights.trend = 0.50
            weights.normalize()
        
        # 避险资产：忽略A股情绪
        if special_rules.get('ignore_a_share_emotion'):
            weights.emotion = 0.05
            weights.normalize()
        
        # 综合计算
        composite = (
            strength_score * weights.strength +
            emotion_phase_score * weights.emotion +
            trend_score * weights.trend +
            emotion_index_score * (1 - weights.strength - weights.emotion - weights.trend)
        )
        
        # 绝望期加成
        if phase == 'despair' and special_rules.get('prefer_despair_phase', True):
            rsi = emotion.get('rsi', 50)
            if rsi < 25:
                composite += 0.2
            elif rsi < 35:
                composite += 0.1
        
        # 市场环境调整
        if self.market_regime:
            regime = self.market_regime.get('regime', 'unknown')
            if regime == 'bear' and composite > 0:
                composite *= 0.7
            elif regime == 'bull' and composite < 0:
                composite *= 0.8
        
        return max(-1, min(1, composite))
    
    def _generate_trade_signal(self, symbol: str, df: pd.DataFrame,
                               strength: Dict, emotion: Dict,
                               composite_score: float,
                               strategy: ETFStrategy) -> Optional[TradeSignal]:
        """
        生成交易信号
        
        Args:
            symbol: ETF代码
            df: 历史数据
            strength: 强弱分析结果
            emotion: 情绪分析结果
            composite_score: 综合评分
            strategy: 策略配置
            
        Returns:
            交易信号
        """
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # 确定交易动作
        action = self._determine_action(composite_score, strength, emotion, strategy)
        
        # 计算置信度
        confidence = self._calculate_confidence(strength, emotion, composite_score, strategy)
        
        # 计算止损止盈价
        risk_control = strategy.risk_control
        stop_loss = current_price * (1 + risk_control.stop_loss / 100)
        take_profit = current_price * (1 + risk_control.take_profit / 100)
        
        # 计算建议仓位
        position_size = self._calculate_position_size(
            composite_score, 
            confidence,
            risk_control
        )
        
        # 构建理由
        reasons = self._build_reasons(strength, emotion, composite_score, strategy)
        
        # 信号有效期
        validity_weeks = self._get_signal_validity(action)
        
        return TradeSignal(
            symbol=symbol,
            name=strategy.name,
            action=action,
            confidence=confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            reasons=reasons,
            timestamp=datetime.now(),
            validity_weeks=validity_weeks,
        )
    
    def _determine_action(self, composite_score: float, strength: Dict,
                          emotion: Dict, strategy: ETFStrategy) -> str:
        """确定交易动作"""
        signal = strength['signal']
        phase = emotion['phase']
        special_rules = strategy.special_rules
        
        # 特殊规则：不参与绝望期抄底
        if special_rules.get('no_despair_buy') and phase == 'despair':
            return 'hold'
        
        # 特殊规则：避免疯狂期追高
        if special_rules.get('avoid_frenzy_chase') and phase == 'frenzy':
            if signal in ['strong_buy', 'buy']:
                return 'hold'
        
        # 根据综合评分判断
        if composite_score >= 0.6:
            return 'strong_buy'
        elif composite_score >= 0.35:
            return 'buy'
        elif composite_score <= -0.6:
            return 'strong_sell'
        elif composite_score <= -0.35:
            return 'sell'
        else:
            return 'hold'
    
    def _calculate_confidence(self, strength: Dict, emotion: Dict,
                              composite_score: float, strategy: ETFStrategy) -> float:
        """计算置信度"""
        confidence = 0.5
        
        signal = strength['signal']
        phase = emotion['phase']
        trend = strength.get('trend', {})
        
        # 信号和情绪一致性加分
        if signal in ['strong_buy', 'buy'] and phase == 'despair':
            confidence += 0.2
        elif signal in ['strong_sell', 'sell'] and phase == 'frenzy':
            confidence += 0.2
        
        # 趋势确认加分
        if trend.get('confirmed'):
            if (signal in ['strong_buy', 'buy'] and trend['direction'] == 'uptrend') or \
               (signal in ['strong_sell', 'sell'] and trend['direction'] == 'downtrend'):
                confidence += 0.15
            else:
                confidence -= 0.15
        
        # 综合评分极端值加分
        if abs(composite_score) > 0.6:
            confidence += 0.1
        
        return max(0.1, min(1.0, confidence))
    
    def _calculate_position_size(self, composite_score: float, confidence: float,
                                 risk_control) -> float:
        """计算建议仓位"""
        # 基础仓位
        if composite_score >= 0.6:
            base_position = risk_control.max_position
        elif composite_score >= 0.35:
            base_position = (risk_control.max_position + risk_control.min_position) / 2
        else:
            base_position = risk_control.min_position
        
        # 根据置信度调整
        position = base_position * (0.7 + 0.3 * confidence)
        
        return round(min(position, risk_control.max_position), 2)
    
    def _build_reasons(self, strength: Dict, emotion: Dict,
                       composite_score: float, strategy: ETFStrategy) -> List[str]:
        """构建信号理由"""
        reasons = []
        
        # 强弱信号
        signal = strength['signal']
        if signal in ['strong_buy', 'buy']:
            reasons.append(f"强弱信号: {signal}")
        elif signal in ['strong_sell', 'sell']:
            reasons.append(f"强弱信号: {signal}")
        
        # 情绪阶段
        phase = emotion['phase']
        if phase == 'despair':
            reasons.append("处于绝望期，逆向买入机会")
        elif phase == 'frenzy':
            reasons.append("处于疯狂期，注意风险")
        
        # 趋势
        trend = strength.get('trend', {})
        if trend.get('confirmed'):
            reasons.append(f"趋势{trend['direction']}已确认")
        
        # 强弱分析理由
        strength_reasons = strength.get('reasons', [])[:2]
        reasons.extend(strength_reasons)
        
        # 综合评分
        reasons.append(f"综合评分: {composite_score:.2f}")
        
        return reasons
    
    def _get_signal_validity(self, action: str) -> int:
        """获取信号有效期"""
        from config import SIGNAL_VALIDITY
        return SIGNAL_VALIDITY.get(action, 2)
    
    def analyze_all_etfs(self, symbols: List[str] = None) -> Dict[str, AnalysisResult]:
        """
        分析所有ETF
        
        Args:
            symbols: 要分析的ETF列表，默认分析所有
            
        Returns:
            分析结果字典
        """
        if symbols is None:
            symbols = list(ETF_POOL.keys())
        
        # 先分析市场环境
        self._analyze_market_regime()
        
        results = {}
        for symbol in symbols:
            result = self.analyze_etf(symbol)
            if result:
                results[symbol] = result
        
        return results
    
    def _analyze_market_regime(self):
        """分析市场环境"""
        # 使用沪深300作为市场基准
        df = self.data_fetcher.get_etf_history('510300', days=120)
        if df.empty:
            self.market_regime = {'regime': 'unknown'}
            return
        
        # 计算近期涨跌幅
        recent_return = (df.iloc[-1]['close'] / df.iloc[-20]['close'] - 1) * 100
        
        # 计算均线位置
        ma20 = df['close'].rolling(20).mean().iloc[-1]
        ma60 = df['close'].rolling(60).mean().iloc[-1]
        current_price = df.iloc[-1]['close']
        
        # 判断市场环境
        if current_price > ma20 > ma60 and recent_return > 5:
            regime = 'bull'
        elif current_price < ma20 < ma60 and recent_return < -5:
            regime = 'bear'
        else:
            regime = 'range'
        
        self.market_regime = {
            'regime': regime,
            'recent_return': recent_return,
            'price_vs_ma20': (current_price / ma20 - 1) * 100,
            'price_vs_ma60': (current_price / ma60 - 1) * 100,
        }
    
    def get_buy_recommendations(self, top_n: int = 5) -> List[AnalysisResult]:
        """
        获取买入推荐
        
        Args:
            top_n: 返回前N个推荐
            
        Returns:
            按综合评分排序的买入推荐列表
        """
        results = self.analyze_all_etfs()
        
        # 过滤出买入信号
        buy_candidates = [
            r for r in results.values()
            if r.trade_signal and r.trade_signal.action in ['strong_buy', 'buy']
        ]
        
        # 按综合评分排序
        buy_candidates.sort(key=lambda x: x.composite_score, reverse=True)
        
        return buy_candidates[:top_n]
    
    def get_sell_recommendations(self, top_n: int = 5) -> List[AnalysisResult]:
        """
        获取卖出推荐
        
        Args:
            top_n: 返回前N个推荐
            
        Returns:
            按综合评分排序的卖出推荐列表
        """
        results = self.analyze_all_etfs()
        
        # 过滤出卖出信号
        sell_candidates = [
            r for r in results.values()
            if r.trade_signal and r.trade_signal.action in ['strong_sell', 'sell']
        ]
        
        # 按综合评分排序（负分越低越应该卖）
        sell_candidates.sort(key=lambda x: x.composite_score)
        
        return sell_candidates[:top_n]
    
    def generate_portfolio(self, total_capital: float = 100000,
                           max_positions: int = 6) -> Dict:
        """
        生成投资组合建议
        
        Args:
            total_capital: 总资金
            max_positions: 最大持仓数
            
        Returns:
            投资组合建议
        """
        results = self.analyze_all_etfs()
        
        # 获取买入推荐
        buy_candidates = [
            r for r in results.values()
            if r.trade_signal and r.trade_signal.action in ['strong_buy', 'buy']
        ]
        buy_candidates.sort(key=lambda x: x.composite_score, reverse=True)
        
        # 选择前N个
        selected = buy_candidates[:max_positions]
        
        # 计算仓位分配
        total_weight = sum(r.trade_signal.position_size for r in selected)
        
        portfolio = {
            'positions': [],
            'total_capital': total_capital,
            'invested_capital': 0,
            'cash_ratio': 0,
            'market_regime': self.market_regime,
        }
        
        for result in selected:
            signal = result.trade_signal
            # 归一化仓位
            weight = signal.position_size / total_weight if total_weight > 0 else 0
            # 留出20%现金
            actual_weight = weight * 0.8
            capital = total_capital * actual_weight
            shares = int(capital / signal.entry_price / 100) * 100  # 整百股
            
            portfolio['positions'].append({
                'symbol': result.symbol,
                'name': result.name,
                'action': signal.action,
                'entry_price': signal.entry_price,
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
                'shares': shares,
                'capital': shares * signal.entry_price,
                'weight': actual_weight,
                'confidence': signal.confidence,
                'reasons': signal.reasons,
            })
            portfolio['invested_capital'] += shares * signal.entry_price
        
        portfolio['cash_ratio'] = 1 - portfolio['invested_capital'] / total_capital
        
        return portfolio
    
    def check_exit_signals(self, holdings: List[Dict]) -> List[Dict]:
        """
        检查持仓的出场信号
        
        Args:
            holdings: 持仓列表，每个元素包含 symbol, entry_price, entry_date
            
        Returns:
            出场信号列表
        """
        exit_signals = []
        
        for holding in holdings:
            symbol = holding['symbol']
            entry_price = holding['entry_price']
            entry_date = holding['entry_date']
            
            # 获取最新数据
            df = self.data_fetcher.get_etf_history(symbol, days=30)
            if df.empty:
                continue
            
            current_price = df.iloc[-1]['close']
            pct_change = (current_price / entry_price - 1) * 100
            
            # 获取策略配置
            strategy = self.strategy_manager.get_strategy(symbol)
            if strategy is None:
                continue
            
            risk_control = strategy.risk_control
            
            # 检查止损
            if pct_change <= risk_control.stop_loss:
                exit_signals.append({
                    'symbol': symbol,
                    'name': strategy.name,
                    'signal': 'stop_loss',
                    'reason': f"触发止损：亏损{abs(pct_change):.1f}%",
                    'current_price': current_price,
                    'pct_change': pct_change,
                })
                continue
            
            # 检查止盈
            if pct_change >= risk_control.take_profit:
                exit_signals.append({
                    'symbol': symbol,
                    'name': strategy.name,
                    'signal': 'take_profit',
                    'reason': f"触发止盈：盈利{pct_change:.1f}%",
                    'current_price': current_price,
                    'pct_change': pct_change,
                })
                continue
            
            # 检查趋势反转
            result = self.analyze_etf(symbol)
            if result and result.trade_signal:
                if result.trade_signal.action in ['strong_sell', 'sell']:
                    exit_signals.append({
                        'symbol': symbol,
                        'name': strategy.name,
                        'signal': 'trend_reversal',
                        'reason': f"趋势反转信号：{result.trade_signal.action}",
                        'current_price': current_price,
                        'pct_change': pct_change,
                    })
        
        return exit_signals


# 全局分析引擎实例
analyzer_engine = AnalyzerEngine(data_fetcher, strategy_manager)
