"""
ETF配置策略 V2 - 优化版智能仓位分配器

优化改进：
1. 降低信号门槛，增加持仓机会
2. 引入动量轮动策略，追踪强势ETF
3. 优化持仓周期，减少频繁调仓
4. 加入趋势跟踪，顺势而为
5. 改进止盈止损机制，让利润奔跑

核心策略：
- 动量轮动：选择近期表现最强的ETF
- 趋势跟踪：顺势持有，逆势减仓
- 风险平价：根据波动率调整仓位
- 凯利公式：根据胜率优化仓位

作者：ETF配置系统 V2
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import numpy as np
import pandas as pd

from analyzer_engine import analyzer_engine, AnalysisResult
from etf_strategies import strategy_manager
from config import STRATEGY_CATEGORIES


@dataclass
class ETFAllocationV2:
    """单个ETF的配置结果 V2"""
    symbol: str
    name: str
    
    # 预期收益和胜率
    expected_return: float
    win_rate: float
    risk_adjusted_return: float
    
    # 动量指标
    momentum_score: float       # 动量得分
    momentum_rank: int          # 动量排名
    trend_strength: float       # 趋势强度
    
    # 分配结果
    raw_weight: float
    adjusted_weight: float
    position_size: float
    capital_allocated: float
    shares: int
    
    # 交易参数
    entry_price: float
    stop_loss: float
    take_profit: float
    trailing_stop: float        # 移动止损
    
    # 评分细节
    signal_score: float
    timing_score: float
    confidence: float
    
    # 分析理由
    reasons: List[str] = field(default_factory=list)


@dataclass
class PortfolioAllocationV2:
    """投资组合配置结果 V2"""
    allocations: List[ETFAllocationV2]
    total_capital: float
    invested_capital: float
    cash_reserve: float
    cash_ratio: float
    
    # 组合指标
    portfolio_expected_return: float
    portfolio_win_rate: float
    portfolio_momentum: float      # 组合动量
    diversification_score: float
    
    # 市场环境
    market_regime: str
    market_trend: str              # 市场趋势
    allocation_strategy: str
    
    # 生成时间
    generated_at: datetime = field(default_factory=datetime.now)


class PortfolioAllocatorV2:
    """
    ETF配置策略 V2 - 优化版智能仓位分配器
    
    核心改进：
    1. 动量轮动：追踪强势ETF
    2. 趋势跟踪：顺势持有
    3. 降低门槛：增加持仓机会
    4. 优化止盈：让利润奔跑
    """
    
    def __init__(self):
        # 配置参数 - 放宽限制
        self.min_position = 0.15        # 最小仓位 15%（提高）
        self.max_position = 0.60        # 最大仓位 60%（提高）
        self.min_cash_ratio = 0.05      # 最低现金比例 5%（降低）
        self.max_cash_ratio = 0.40      # 最高现金比例 40%（降低）
        
        # 动量参数
        self.momentum_period = 20       # 动量计算周期
        self.momentum_weight = 0.40     # 动量在配置中的权重
        
        # 信号门槛 - 大幅降低
        self.min_confidence = 0.20      # 最低置信度 20%（大幅降低）
        self.min_signal_score = -2      # 允许轻微负分信号
        
        # 胜率计算参数 - 更乐观
        self.base_win_rate = 0.55       # 基础胜率提高到55%
        self.signal_win_rate_boost = {
            'strong_buy': 0.20,
            'buy': 0.12,
            'hold': 0.05,              # hold也给小幅提升
            'sell': -0.10,
            'strong_sell': -0.20
        }
        
        # 情绪阶段影响 - 更重视逆向
        self.emotion_win_rate_impact = {
            'despair': 0.20,           # 绝望期买入胜率更高
            'hesitation': 0.08,        # 犹豫期也有机会
            'frenzy': -0.15,           # 疯狂期惩罚降低
            'unknown': 0.03
        }
        
        # 预期收益参数 - 更积极
        self.base_expected_return = {
            'strong_buy': 18.0,
            'buy': 12.0,
            'hold': 6.0,               # hold也有正预期
            'sell': -3.0,
            'strong_sell': -8.0
        }
        
        # 动量加成
        self.momentum_return_boost = {
            'strong': 5.0,             # 强动量+5%
            'moderate': 2.5,           # 中等动量+2.5%
            'weak': 0.0,
            'negative': -2.0           # 负动量-2%
        }
        
        # 趋势跟踪参数
        self.trend_follow_weight = 0.30  # 趋势跟踪权重
        
    def calculate_momentum_score(self, result: AnalysisResult, hist_data: pd.DataFrame = None) -> Tuple[float, str]:
        """
        计算动量得分
        
        基于：
        1. 近期价格涨幅
        2. 相对强弱
        3. 成交量配合
        """
        momentum_score = 0.0
        
        # 从分析结果获取动量信息
        if result.strength_score is not None:
            # 强弱得分直接反映动量
            momentum_score = result.strength_score * 10
        
        # 趋势确认加分
        if result.trend_confirmed:
            if result.trend_direction == 'uptrend':
                momentum_score += 20
            elif result.trend_direction == 'downtrend':
                momentum_score -= 15
        
        # 情绪阶段调整
        if result.emotion_phase == 'frenzy':
            momentum_score += 10  # 疯狂期动量强
        elif result.emotion_phase == 'despair':
            momentum_score -= 5   # 绝望期动量弱但可能反转
        
        # 综合评分加成
        momentum_score += result.composite_score * 15
        
        # 分类动量
        if momentum_score > 30:
            momentum_class = 'strong'
        elif momentum_score > 10:
            momentum_class = 'moderate'
        elif momentum_score > -10:
            momentum_class = 'weak'
        else:
            momentum_class = 'negative'
        
        return momentum_score, momentum_class
    
    def calculate_expected_return_v2(self, result: AnalysisResult, momentum_class: str) -> Tuple[float, List[str]]:
        """
        计算预期收益率 V2
        
        改进：
        1. 加入动量加成
        2. 更积极的基础预期
        3. 趋势跟踪加成
        """
        reasons = []
        
        if result.trade_signal is None:
            # 即使没有明确信号，也给予基础预期
            return 5.0, ["无明确信号，给予基础预期"]
        
        signal = result.trade_signal
        
        # 1. 基础预期收益
        base_return = self.base_expected_return.get(signal.action, 5.0)
        reasons.append(f"信号基础: {base_return:.1f}%")
        
        # 2. 动量加成
        momentum_boost = self.momentum_return_boost.get(momentum_class, 0.0)
        if momentum_boost != 0:
            reasons.append(f"动量加成({momentum_class}): {momentum_boost:+.1f}%")
        
        # 3. 综合评分调整 (-1 到 1 映射到 -8% 到 +8%)
        score_adjustment = result.composite_score * 8
        reasons.append(f"综合评分: {score_adjustment:+.1f}%")
        
        # 4. 趋势确认加成 - 更大的加成
        trend_bonus = 0.0
        if result.trend_confirmed:
            if result.trend_direction == 'uptrend':
                trend_bonus = 5.0
                reasons.append("上升趋势确认: +5.0%")
            elif result.trend_direction == 'downtrend' and signal.action in ['sell', 'strong_sell']:
                trend_bonus = 3.0
        
        # 5. 情绪阶段调整 - 逆向投资加成更大
        emotion_adjustment = 0.0
        if result.emotion_phase == 'despair':
            emotion_adjustment = 8.0  # 绝望期买入预期收益更高
            reasons.append("绝望期逆向加成: +8.0%")
        elif result.emotion_phase == 'frenzy' and signal.action in ['buy', 'strong_buy']:
            emotion_adjustment = -3.0  # 疯狂期惩罚降低
            reasons.append("疯狂期风险: -3.0%")
        elif result.emotion_phase == 'hesitation':
            emotion_adjustment = 3.0  # 犹豫期有机会
            reasons.append("犹豫期机会: +3.0%")
        
        # 6. 使用策略的止盈目标作为参考
        strategy_target = 0.0
        if signal.take_profit > 0 and signal.entry_price > 0:
            strategy_target = (signal.take_profit / signal.entry_price - 1) * 100
            strategy_weight = 0.25
        else:
            strategy_weight = 0.0
        
        # 计算最终预期收益
        calculated_return = base_return + momentum_boost + score_adjustment + trend_bonus + emotion_adjustment
        
        if strategy_weight > 0:
            expected_return = calculated_return * (1 - strategy_weight) + strategy_target * strategy_weight
        else:
            expected_return = calculated_return
        
        # 限制范围 - 放宽上限
        expected_return = max(-15.0, min(35.0, expected_return))
        
        return expected_return, reasons
    
    def calculate_win_rate_v2(self, result: AnalysisResult, momentum_class: str) -> Tuple[float, List[str]]:
        """
        计算胜率 V2
        
        改进：
        1. 更高的基础胜率
        2. 动量因素
        3. 更乐观的调整
        """
        reasons = []
        
        if result.trade_signal is None:
            return 0.50, ["无信号，使用基础胜率"]
        
        signal = result.trade_signal
        
        # 1. 基础胜率 - 提高到55%
        win_rate = self.base_win_rate
        reasons.append(f"基础胜率: {win_rate:.0%}")
        
        # 2. 信号强度调整
        signal_boost = self.signal_win_rate_boost.get(signal.action, 0.0)
        win_rate += signal_boost
        if signal_boost != 0:
            reasons.append(f"信号强度: {signal_boost:+.0%}")
        
        # 3. 动量加成
        momentum_win_boost = {
            'strong': 0.12,
            'moderate': 0.06,
            'weak': 0.0,
            'negative': -0.05
        }
        momentum_boost = momentum_win_boost.get(momentum_class, 0.0)
        win_rate += momentum_boost
        if momentum_boost != 0:
            reasons.append(f"动量因素: {momentum_boost:+.0%}")
        
        # 4. 情绪阶段调整
        emotion_impact = self.emotion_win_rate_impact.get(result.emotion_phase, 0.0)
        if signal.action in ['buy', 'strong_buy', 'hold']:
            win_rate += emotion_impact
            if emotion_impact != 0:
                reasons.append(f"情绪阶段({result.emotion_phase}): {emotion_impact:+.0%}")
        
        # 5. 趋势确认加成 - 更大的加成
        if result.trend_confirmed:
            if (result.trend_direction == 'uptrend' and signal.action in ['buy', 'strong_buy', 'hold']) or \
               (result.trend_direction == 'downtrend' and signal.action in ['sell', 'strong_sell']):
                win_rate += 0.12
                reasons.append("趋势确认: +12%")
        
        # 6. 置信度调整 - 更温和
        confidence_factor = signal.confidence
        confidence_adjustment = (confidence_factor - 0.4) * 0.15
        win_rate += confidence_adjustment
        
        # 7. 特殊高胜率信号检测
        # RSI超卖
        if result.strength_score < -3:
            win_rate += 0.10
            reasons.append("超卖信号: +10%")
        
        # 限制胜率范围 - 放宽上限
        win_rate = max(0.30, min(0.92, win_rate))
        
        return win_rate, reasons
    
    def calculate_risk_adjusted_return_v2(self, expected_return: float, win_rate: float, 
                                          momentum_score: float) -> float:
        """
        计算风险调整后收益 V2
        
        改进：
        1. 加入动量因素
        2. 更合理的凯利公式应用
        """
        if win_rate <= 0:
            return -abs(expected_return)
        
        # 基础风险调整收益
        base_rar = expected_return * win_rate
        
        # 动量加成
        if momentum_score > 20:
            base_rar *= 1.15
        elif momentum_score > 0:
            base_rar *= 1.05
        
        # 胜率加成因子 - 更激进
        if win_rate > 0.70:
            win_rate_bonus = (win_rate - 0.70) * 2.5
            base_rar *= (1 + win_rate_bonus)
        elif win_rate > 0.60:
            win_rate_bonus = (win_rate - 0.60) * 1.5
            base_rar *= (1 + win_rate_bonus)
        
        # 低胜率惩罚 - 更温和
        if win_rate < 0.40:
            low_win_penalty = (0.40 - win_rate) * 1.0
            base_rar *= (1 - low_win_penalty)
        
        return base_rar
    
    def calculate_allocation_weights_v2(
        self, 
        etf_metrics: List[Dict],
        market_regime: str = 'range'
    ) -> List[Dict]:
        """
        计算配置权重 V2
        
        改进：
        1. 动量轮动策略
        2. 更积极的仓位分配
        3. 趋势跟踪加权
        """
        if not etf_metrics:
            return []
        
        # 1. 放宽筛选条件 - 允许hold信号和负分信号
        valid_etfs = [
            m for m in etf_metrics 
            if m['risk_adjusted_return'] > -5 and  # 允许小幅负值
               m['signal_action'] in ['buy', 'strong_buy', 'hold']  # 允许hold
        ]
        
        if not valid_etfs:
            # 如果没有符合条件的，选择最好的那个
            etf_metrics.sort(key=lambda x: x['risk_adjusted_return'], reverse=True)
            if etf_metrics and etf_metrics[0]['risk_adjusted_return'] > -10:
                valid_etfs = [etf_metrics[0]]
        
        if not valid_etfs:
            return []
        
        # 2. 按动量排名
        valid_etfs.sort(key=lambda x: x['momentum_score'], reverse=True)
        for i, m in enumerate(valid_etfs):
            m['momentum_rank'] = i + 1
        
        # 3. 计算综合得分（风险调整收益 + 动量）
        for m in valid_etfs:
            # 归一化风险调整收益
            max_rar = max(abs(e['risk_adjusted_return']) for e in valid_etfs) or 1
            norm_rar = (m['risk_adjusted_return'] + 10) / (max_rar + 10)  # 移动到正数
            
            # 归一化动量
            max_momentum = max(abs(e['momentum_score']) for e in valid_etfs) or 1
            norm_momentum = (m['momentum_score'] + 50) / (max_momentum + 50)
            
            # 综合得分
            m['composite_allocation_score'] = (
                norm_rar * (1 - self.momentum_weight) + 
                norm_momentum * self.momentum_weight
            )
        
        # 4. 计算原始权重
        total_score = sum(m['composite_allocation_score'] for m in valid_etfs)
        
        for m in valid_etfs:
            m['raw_weight'] = m['composite_allocation_score'] / total_score if total_score > 0 else 0
        
        # 5. 应用约束 - 更宽松
        for m in valid_etfs:
            m['adjusted_weight'] = max(self.min_position, min(m['raw_weight'], self.max_position))
        
        # 6. 归一化
        total_adjusted = sum(m['adjusted_weight'] for m in valid_etfs)
        if total_adjusted > 0:
            for m in valid_etfs:
                m['adjusted_weight'] /= total_adjusted
        
        # 7. 市场环境调整 - 更积极
        if market_regime == 'bear':
            # 熊市只小幅降低仓位
            for m in valid_etfs:
                m['adjusted_weight'] *= 0.85
        elif market_regime == 'bull':
            # 牛市更激进
            for m in valid_etfs:
                m['adjusted_weight'] *= 1.15
                m['adjusted_weight'] = min(m['adjusted_weight'], self.max_position)
        
        return valid_etfs
    
    def allocate(
        self,
        total_capital: float = 100000,
        max_positions: int = 4,
        symbols: List[str] = None,
        min_confidence: float = None
    ) -> PortfolioAllocationV2:
        """
        执行智能仓位分配 V2
        """
        if min_confidence is None:
            min_confidence = self.min_confidence
        
        # 1. 获取所有ETF的分析结果
        if symbols:
            results = {s: analyzer_engine.analyze_etf(s) for s in symbols}
            results = {k: v for k, v in results.items() if v is not None}
        else:
            results = analyzer_engine.analyze_all_etfs()
        
        if not results:
            return self._empty_allocation(total_capital)
        
        # 2. 计算每个ETF的指标
        etf_metrics = []
        for symbol, result in results.items():
            # 计算动量
            momentum_score, momentum_class = self.calculate_momentum_score(result)
            
            # 计算预期收益和胜率
            expected_return, return_reasons = self.calculate_expected_return_v2(result, momentum_class)
            win_rate, win_rate_reasons = self.calculate_win_rate_v2(result, momentum_class)
            risk_adjusted_return = self.calculate_risk_adjusted_return_v2(expected_return, win_rate, momentum_score)
            
            # 计算置信度
            signal = result.trade_signal
            confidence = signal.confidence if signal else 0.3
            
            # 放宽置信度过滤
            if confidence < min_confidence and risk_adjusted_return < 5:
                continue
            
            etf_metrics.append({
                'symbol': symbol,
                'name': result.name,
                'expected_return': expected_return,
                'win_rate': win_rate,
                'risk_adjusted_return': risk_adjusted_return,
                'momentum_score': momentum_score,
                'momentum_class': momentum_class,
                'signal_action': signal.action if signal else 'hold',
                'signal_score': result.strength_score,
                'timing_score': result.composite_score,
                'confidence': confidence,
                'entry_price': signal.entry_price if signal else 0,
                'stop_loss': signal.stop_loss if signal else 0,
                'take_profit': signal.take_profit if signal else 0,
                'reasons': return_reasons + win_rate_reasons,
                'result': result
            })
        
        # 3. 获取市场环境
        market_regime = self._detect_market_regime(results)
        market_trend = self._detect_market_trend(results)
        
        # 4. 计算配置权重
        weighted_etfs = self.calculate_allocation_weights_v2(etf_metrics, market_regime)
        
        # 5. 选择最优的N个
        weighted_etfs.sort(key=lambda x: x['risk_adjusted_return'], reverse=True)
        selected_etfs = weighted_etfs[:max_positions]
        
        # 6. 确定现金比例 - 更低
        cash_ratio = self._calculate_cash_ratio_v2(selected_etfs, market_regime, market_trend)
        
        # 7. 分配资金
        allocations = []
        total_invested = 0
        
        for i, etf in enumerate(selected_etfs):
            position_size = etf['adjusted_weight'] * (1 - cash_ratio)
            capital_for_etf = total_capital * position_size
            
            entry_price = etf['entry_price']
            if entry_price > 0:
                shares = int(capital_for_etf / entry_price / 100) * 100
                actual_capital = shares * entry_price
            else:
                shares = 0
                actual_capital = 0
            
            if shares > 0:
                # 计算移动止损
                trailing_stop = entry_price * 0.92  # 8%移动止损
                
                allocation = ETFAllocationV2(
                    symbol=etf['symbol'],
                    name=etf['name'],
                    expected_return=etf['expected_return'],
                    win_rate=etf['win_rate'],
                    risk_adjusted_return=etf['risk_adjusted_return'],
                    momentum_score=etf['momentum_score'],
                    momentum_rank=i + 1,
                    trend_strength=etf['timing_score'],
                    raw_weight=etf['raw_weight'],
                    adjusted_weight=etf['adjusted_weight'],
                    position_size=actual_capital / total_capital,
                    capital_allocated=actual_capital,
                    shares=shares,
                    entry_price=entry_price,
                    stop_loss=etf['stop_loss'],
                    take_profit=etf['take_profit'],
                    trailing_stop=trailing_stop,
                    signal_score=etf['signal_score'],
                    timing_score=etf['timing_score'],
                    confidence=etf['confidence'],
                    reasons=etf['reasons']
                )
                allocations.append(allocation)
                total_invested += actual_capital
        
        # 8. 计算组合指标
        if allocations:
            portfolio_return = sum(a.expected_return * a.position_size for a in allocations)
            total_position = sum(a.position_size for a in allocations)
            portfolio_win_rate = sum(a.win_rate * a.position_size for a in allocations) / max(total_position, 0.01)
            portfolio_momentum = sum(a.momentum_score * a.position_size for a in allocations) / max(total_position, 0.01)
        else:
            portfolio_return = 0
            portfolio_win_rate = 0
            portfolio_momentum = 0
        
        diversification = self._calculate_diversification(allocations)
        allocation_strategy = self._determine_strategy_name_v2(allocations, market_regime, market_trend)
        
        return PortfolioAllocationV2(
            allocations=allocations,
            total_capital=total_capital,
            invested_capital=total_invested,
            cash_reserve=total_capital - total_invested,
            cash_ratio=(total_capital - total_invested) / total_capital,
            portfolio_expected_return=portfolio_return,
            portfolio_win_rate=portfolio_win_rate,
            portfolio_momentum=portfolio_momentum,
            diversification_score=diversification,
            market_regime=market_regime,
            market_trend=market_trend,
            allocation_strategy=allocation_strategy
        )
    
    def _detect_market_regime(self, results: Dict[str, AnalysisResult]) -> str:
        """检测市场环境"""
        if not results:
            return 'range'
        
        bullish_count = 0
        bearish_count = 0
        
        for result in results.values():
            if result.trend_direction == 'uptrend' and result.trend_confirmed:
                bullish_count += 1
            elif result.trend_direction == 'downtrend' and result.trend_confirmed:
                bearish_count += 1
            
            if result.emotion_phase == 'frenzy':
                bullish_count += 0.5
            elif result.emotion_phase == 'despair':
                bearish_count += 0.5
        
        total = len(results)
        if bullish_count / total > 0.5:  # 降低阈值
            return 'bull'
        elif bearish_count / total > 0.5:
            return 'bear'
        else:
            return 'range'
    
    def _detect_market_trend(self, results: Dict[str, AnalysisResult]) -> str:
        """检测市场趋势"""
        if not results:
            return 'sideways'
        
        uptrend_count = sum(1 for r in results.values() if r.trend_direction == 'uptrend')
        downtrend_count = sum(1 for r in results.values() if r.trend_direction == 'downtrend')
        
        total = len(results)
        if uptrend_count / total > 0.5:
            return 'up'
        elif downtrend_count / total > 0.5:
            return 'down'
        else:
            return 'sideways'
    
    def _calculate_cash_ratio_v2(self, etfs: List[Dict], market_regime: str, market_trend: str) -> float:
        """计算现金比例 V2 - 更低的现金比例"""
        if not etfs:
            return self.max_cash_ratio
        
        # 基础现金比例 - 降低
        base_cash = self.min_cash_ratio
        
        # 市场环境调整 - 更温和
        if market_regime == 'bear':
            base_cash += 0.10
        elif market_regime == 'bull':
            base_cash -= 0.02
        
        # 趋势调整
        if market_trend == 'up':
            base_cash -= 0.03
        elif market_trend == 'down':
            base_cash += 0.05
        
        # 信号质量调整 - 更温和
        avg_confidence = sum(e['confidence'] for e in etfs) / len(etfs)
        if avg_confidence < 0.4:
            base_cash += 0.05
        elif avg_confidence > 0.7:
            base_cash -= 0.03
        
        # 动量调整
        avg_momentum = sum(e.get('momentum_score', 0) for e in etfs) / len(etfs)
        if avg_momentum > 20:
            base_cash -= 0.03
        elif avg_momentum < -10:
            base_cash += 0.05
        
        return max(self.min_cash_ratio, min(self.max_cash_ratio, base_cash))
    
    def _calculate_diversification(self, allocations: List[ETFAllocationV2]) -> float:
        """计算分散化得分"""
        if not allocations:
            return 0.0
        
        n = len(allocations)
        count_score = min(n / 3, 1.0) * 40
        
        weights = [a.position_size for a in allocations]
        hhi = sum(w ** 2 for w in weights) if weights else 0
        concentration_score = (1 - hhi) * 40
        
        # 动量分散度
        momentum_scores = [a.momentum_score for a in allocations]
        if len(momentum_scores) > 1:
            momentum_std = np.std(momentum_scores)
            momentum_diversity = min(momentum_std / 20, 1.0) * 20
        else:
            momentum_diversity = 10
        
        return count_score + concentration_score + momentum_diversity
    
    def _determine_strategy_name_v2(self, allocations: List[ETFAllocationV2], 
                                    market_regime: str, market_trend: str) -> str:
        """确定配置策略名称 V2"""
        if not allocations:
            return "观望策略"
        
        avg_win_rate = sum(a.win_rate for a in allocations) / len(allocations)
        avg_return = sum(a.expected_return for a in allocations) / len(allocations)
        avg_momentum = sum(a.momentum_score for a in allocations) / len(allocations)
        
        if avg_momentum > 25 and avg_return > 12:
            return "动量追涨策略"
        elif avg_win_rate > 0.70 and avg_return > 10:
            return "高胜率进攻策略"
        elif avg_win_rate > 0.65:
            return "稳健配置策略"
        elif market_trend == 'up' and avg_momentum > 10:
            return "趋势跟踪策略"
        elif market_regime == 'bear':
            return "熊市防守策略"
        elif market_regime == 'bull':
            return "牛市进取策略"
        else:
            return "均衡轮动策略"
    
    def _empty_allocation(self, total_capital: float) -> PortfolioAllocationV2:
        """返回空配置"""
        return PortfolioAllocationV2(
            allocations=[],
            total_capital=total_capital,
            invested_capital=0,
            cash_reserve=total_capital,
            cash_ratio=1.0,
            portfolio_expected_return=0,
            portfolio_win_rate=0,
            portfolio_momentum=0,
            diversification_score=0,
            market_regime='unknown',
            market_trend='sideways',
            allocation_strategy='全现金观望'
        )
    
    def compare_etfs(self, symbols: List[str]) -> Dict:
        """对比多个ETF的配置价值"""
        comparison = []
        
        for symbol in symbols:
            result = analyzer_engine.analyze_etf(symbol)
            if result is None:
                continue
            
            momentum_score, momentum_class = self.calculate_momentum_score(result)
            expected_return, return_reasons = self.calculate_expected_return_v2(result, momentum_class)
            win_rate, win_rate_reasons = self.calculate_win_rate_v2(result, momentum_class)
            risk_adjusted_return = self.calculate_risk_adjusted_return_v2(expected_return, win_rate, momentum_score)
            
            comparison.append({
                'symbol': symbol,
                'name': result.name,
                'expected_return': expected_return,
                'win_rate': win_rate,
                'risk_adjusted_return': risk_adjusted_return,
                'momentum_score': momentum_score,
                'momentum_class': momentum_class,
                'signal': result.trade_signal.action if result.trade_signal else 'none',
                'confidence': result.trade_signal.confidence if result.trade_signal else 0,
                'emotion_phase': result.emotion_phase,
                'composite_score': result.composite_score,
                'reasons': return_reasons + win_rate_reasons,
                'recommendation': self._get_recommendation_v2(risk_adjusted_return, win_rate, momentum_score)
            })
        
        comparison.sort(key=lambda x: x['risk_adjusted_return'], reverse=True)
        
        return {
            'comparison': comparison,
            'best_choice': comparison[0] if comparison else None,
            'ranking': [c['symbol'] for c in comparison]
        }
    
    def _get_recommendation_v2(self, rar: float, win_rate: float, momentum: float) -> str:
        """获取配置建议 V2"""
        if rar > 10 and win_rate > 0.65 and momentum > 15:
            return "🔥 强烈推荐"
        elif rar > 6 and win_rate > 0.58:
            return "✅ 推荐配置"
        elif rar > 3 or (win_rate > 0.55 and momentum > 0):
            return "👍 可以配置"
        elif rar > 0:
            return "⚠️ 谨慎配置"
        else:
            return "❌ 暂不推荐"


# 全局实例
portfolio_allocator_v2 = PortfolioAllocatorV2()


def print_allocation_report_v2(allocation: PortfolioAllocationV2):
    """打印配置报告 V2"""
    print("\n" + "=" * 75)
    print("       ETF智能配置报告 V2 - 动量轮动策略")
    print("=" * 75)
    print(f"生成时间: {allocation.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"市场环境: {allocation.market_regime} | 市场趋势: {allocation.market_trend}")
    print(f"配置策略: {allocation.allocation_strategy}")
    
    print("\n" + "-" * 75)
    print("📊 配置汇总")
    print("-" * 75)
    print(f"总资金: {allocation.total_capital:,.0f}")
    print(f"投资资金: {allocation.invested_capital:,.0f} ({(1-allocation.cash_ratio):.1%})")
    print(f"现金储备: {allocation.cash_reserve:,.0f} ({allocation.cash_ratio:.1%})")
    print(f"组合预期收益: {allocation.portfolio_expected_return:.2f}%")
    print(f"组合综合胜率: {allocation.portfolio_win_rate:.1%}")
    print(f"组合动量得分: {allocation.portfolio_momentum:.1f}")
    print(f"分散化得分: {allocation.diversification_score:.1f}/100")
    
    if allocation.allocations:
        print("\n" + "-" * 75)
        print("💼 持仓配置明细")
        print("-" * 75)
        print(f"{'代码':<10} {'名称':<12} {'预期收益':<10} {'胜率':<8} {'动量':<8} {'仓位':<8} {'资金':<12}")
        print("-" * 75)
        
        for a in allocation.allocations:
            print(f"{a.symbol:<10} {a.name:<12} {a.expected_return:>+7.1f}% {a.win_rate:>6.1%} "
                  f"{a.momentum_score:>+6.1f} {a.position_size:>6.1%} {a.capital_allocated:>10,.0f}")
        
        print("\n" + "-" * 75)
        print("🎯 交易参数")
        print("-" * 75)
        for a in allocation.allocations:
            print(f"\n{a.symbol} - {a.name} (动量排名#{a.momentum_rank}):")
            print(f"  入场价: {a.entry_price:.3f}")
            print(f"  止损: {a.stop_loss:.3f} ({(a.stop_loss/a.entry_price-1)*100:+.1f}%)")
            print(f"  止盈: {a.take_profit:.3f} ({(a.take_profit/a.entry_price-1)*100:+.1f}%)")
            print(f"  移动止损: {a.trailing_stop:.3f} ({(a.trailing_stop/a.entry_price-1)*100:+.1f}%)")
            print(f"  配置理由: {', '.join(a.reasons[:4])}")
    else:
        print("\n⚠️ 当前无推荐配置，建议保持观望")
    
    print("\n" + "=" * 75)


def compare_and_print_v2(symbols: List[str]):
    """对比ETF并打印结果 V2"""
    result = portfolio_allocator_v2.compare_etfs(symbols)
    
    print("\n" + "=" * 75)
    print("       ETF配置价值对比 V2")
    print("=" * 75)
    
    print(f"\n{'排名':<4} {'代码':<10} {'名称':<12} {'预期收益':<10} {'胜率':<8} {'动量':<8} {'建议':<15}")
    print("-" * 75)
    
    for i, c in enumerate(result['comparison'], 1):
        print(f"{i:<4} {c['symbol']:<10} {c['name']:<12} {c['expected_return']:>+7.1f}% "
              f"{c['win_rate']:>6.1%} {c['momentum_score']:>+6.1f} {c['recommendation']:<15}")
    
    if result['best_choice']:
        best = result['best_choice']
        print(f"\n🏆 最佳配置选择: {best['symbol']} - {best['name']}")
        print(f"   预期收益: {best['expected_return']:+.1f}% | 胜率: {best['win_rate']:.1%} | 动量: {best['momentum_score']:+.1f}")
        print(f"   情绪阶段: {best['emotion_phase']} | 动量分类: {best['momentum_class']}")
    
    print("\n" + "=" * 75)
    
    return result


# 便捷函数
def quick_allocate_v2(capital: float = 100000) -> PortfolioAllocationV2:
    """快速生成配置 V2"""
    allocation = portfolio_allocator_v2.allocate(total_capital=capital)
    print_allocation_report_v2(allocation)
    return allocation


def allocate_specific_v2(symbols: List[str], capital: float = 100000) -> PortfolioAllocationV2:
    """对指定ETF进行配置 V2"""
    allocation = portfolio_allocator_v2.allocate(total_capital=capital, symbols=symbols)
    print_allocation_report_v2(allocation)
    return allocation


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'compare':
            symbols = sys.argv[2:] if len(sys.argv) > 2 else ['515450', '159949']
            compare_and_print_v2(symbols)
        elif sys.argv[1] == 'allocate':
            capital = float(sys.argv[2]) if len(sys.argv) > 2 else 100000
            quick_allocate_v2(capital)
        else:
            symbols = sys.argv[1:]
            allocate_specific_v2(symbols)
    else:
        print("\n📈 对比 红利低波50ETF vs 创业板50ETF (V2)")
        compare_and_print_v2(['515450', '159949'])
        
        print("\n📊 生成智能配置方案 (V2)")
        quick_allocate_v2(100000)
