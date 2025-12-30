"""
策略四：以变应变对冲战法
核心逻辑：市场没有完美的预测，策略才是关键
优化：结合周线分析，增加情绪和资金面因素
新增：止损止盈机制，特殊资产处理，信号时效性
"""

from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
from config import (
    ETF_POOL, LARGE_CAP_ETFS, SMALL_CAP_ETFS, SPECIAL_ASSETS, 
    RISK_PARAMS, SIGNAL_VALIDITY, SIGNAL_THRESHOLDS, NO_DESPAIR_BUY_ASSETS,
    SPECIAL_ASSET_RULES
)
from .strength import StrengthWeaknessAnalyzer
from .emotion import EmotionCycleAnalyzer


class HedgeStrategy:
    """
    对冲策略生成器（周线级别）
    
    核心原则：
    1. 市场没有完美的预测，策略才是关键
    2. 将可能走势列出，以不同策略应对
    3. 对冲保护，赚取风格强弱的利润
    4. 留有余地，仓位不可用足
    5. 新增：止损止盈纪律
    6. 新增：信号时效性管理
    """
    
    def __init__(self, data_fetcher, use_weekly: bool = True, market_regime: Dict = None):
        """
        初始化对冲策略生成器
        
        Args:
            data_fetcher: 数据获取器
            use_weekly: 是否使用周线分析
            market_regime: 市场环境信息
        """
        self.data_fetcher = data_fetcher
        self.use_weekly = use_weekly
        self.market_regime = market_regime
        self.signal_history = {}  # 记录信号历史，用于时效性管理
    
    def generate_hedge_portfolio(self) -> Dict:
        """
        生成对冲组合
        
        核心思路：
        1. 周线级别分析减少噪音
        2. 综合强弱信号和情绪阶段
        3. 大小盘对冲、行业分散
        4. 动态调整现金比例
        5. 新增：信号置信度过滤
        6. 新增：市场环境调整
        """
        portfolio = {
            'long_positions': [],
            'hedge_positions': [],
            'cash_ratio': 0.2,  # 基础现金比例
            'analysis_mode': 'weekly' if self.use_weekly else 'daily',
            'market_regime': self.market_regime
        }
        
        # 分析各ETF
        etf_analysis = {}
        min_data_len = 60 if not self.use_weekly else 30
        
        for symbol in ETF_POOL:
            df = self.data_fetcher.get_etf_history(symbol)
            if df.empty or len(df) < min_data_len:
                continue
            
            # 强弱分析（传入symbol用于识别特殊资产）
            strength_analyzer = StrengthWeaknessAnalyzer(df, use_weekly=self.use_weekly, symbol=symbol)
            strength_result = strength_analyzer.analyze_strength()
            
            # 情绪分析（传入市场环境）
            emotion_analyzer = EmotionCycleAnalyzer(df, use_weekly=self.use_weekly)
            emotion_result = emotion_analyzer.get_emotion_phase(market_regime=self.market_regime)
            
            # 综合评分
            composite_score = self._calculate_composite_score(strength_result, emotion_result)
            
            # === P0优化：综合得分为nan时标记为无效 ===
            score_valid = not (np.isnan(composite_score) if isinstance(composite_score, float) else False)
            
            # 计算信号置信度
            signal_confidence = self._calculate_signal_confidence(strength_result, emotion_result)
            
            etf_analysis[symbol] = {
                'name': ETF_POOL[symbol],
                'strength': strength_result,
                'emotion': emotion_result,
                'composite_score': composite_score,
                'score_valid': score_valid,  # 新增：标记得分是否有效
                'signal_confidence': signal_confidence,
                'cap_type': 'large' if symbol in LARGE_CAP_ETFS else ('small' if symbol in SMALL_CAP_ETFS else 'sector')
            }
        
        if not etf_analysis:
            return portfolio
        
        # 根据市场整体情绪调整现金比例
        portfolio['cash_ratio'] = self._calculate_cash_ratio(etf_analysis)
        
        # 计算市场环境
        market_regime_calc = self._calculate_market_regime(etf_analysis)
        portfolio['market_regime_calc'] = market_regime_calc
        
        # 排序选择
        sorted_etfs = sorted(
            etf_analysis.items(),
            key=lambda x: x[1]['composite_score'],
            reverse=True
        )
        
        # 选择多头持仓（增加置信度过滤）
        long_positions = self._select_long_positions(sorted_etfs, etf_analysis)
        portfolio['long_positions'] = long_positions
        
        # 选择谨慎/回避持仓
        hedge_positions = self._select_hedge_positions(sorted_etfs, etf_analysis)
        portfolio['hedge_positions'] = hedge_positions
        
        # 计算总权重（只计算多头，对冲仓位是回避建议，不计入实际持仓）
        total_long_weight = sum(p['weight'] for p in long_positions)
        cash_ratio = portfolio['cash_ratio']
        
        # 可用仓位 = 1 - 现金比例
        available_weight = 1 - cash_ratio
        
        # 如果多头仓位超过可用仓位，按比例缩减
        if total_long_weight > available_weight and total_long_weight > 0:
            scale_factor = available_weight / total_long_weight
            for pos in long_positions:
                pos['weight'] = round(pos['weight'] * scale_factor, 2)
            total_long_weight = sum(p['weight'] for p in long_positions)
        
        portfolio['total_long_weight'] = total_long_weight
        # 净敞口 = 多头仓位（对冲仓位是回避建议，不是做空）
        portfolio['net_exposure'] = total_long_weight
        # 保留对冲标的数量作为风险提示
        portfolio['risk_alerts_count'] = len(hedge_positions)
        
        return portfolio
    
    def _calculate_composite_score(self, strength: Dict, emotion: Dict) -> float:
        """
        计算综合评分
        
        优化v2：
        - 降低情绪阶段权重（35%→25%），提高强弱信号权重（40%→45%）
        - 疯狂期不再一刀切惩罚，区分"强势疯狂"和"衰竭疯狂"
        - 增加趋势确认因子
        
        优化v3：
        - P2：商品类资产使用纯趋势得分，不使用情绪周期
        
        综合考虑：
        - 强弱信号得分（权重45%）
        - 情绪阶段（权重25%）
        - 情绪指数（权重15%）
        - 趋势确认加成（权重15%）
        """
        # 强弱得分（-5到5映射到-1到1）
        strength_score = strength['score'] / 5
        
        # 获取趋势信息
        trend_info = strength.get('trend', {})
        trend_direction = trend_info.get('direction', 'unknown')
        trend_confirmed = trend_info.get('confirmed', False)
        
        # === P2优化：商品类资产使用纯趋势得分 ===
        symbol = strength.get('symbol', '')
        if symbol in NO_DESPAIR_BUY_ASSETS:
            # 商品类资产：纯趋势跟踪，不使用情绪周期
            trend_bonus = 0
            if trend_direction == 'uptrend':
                trend_bonus = 0.6 if trend_confirmed else 0.3
            elif trend_direction == 'downtrend':
                trend_bonus = -0.6 if trend_confirmed else -0.3
            
            # 简化得分：强弱信号 + 趋势
            composite = strength_score * 0.6 + trend_bonus * 0.4
            
            # 市场环境调整
            if self.market_regime:
                regime = self.market_regime.get('regime', 'unknown')
                if regime == 'bear' and composite > 0:
                    composite *= 0.7
                elif regime == 'bull' and composite < 0:
                    composite *= 0.8
            
            return composite
        
        # 情绪阶段得分（优化：疯狂期惩罚力度降低）
        phase = emotion['phase']
        phase_strength = emotion.get('phase_strength', 0.5)
        rsi = emotion.get('rsi', 50)
        
        # 动态计算情绪阶段得分
        if phase == 'despair':
            emotion_phase_score = 1.0  # 绝望期买入
        elif phase == 'hesitation':
            emotion_phase_score = 0.0  # 犹豫期观望
        elif phase == 'frenzy':
            # 优化：疯狂期根据趋势方向调整惩罚力度
            if trend_direction == 'uptrend' and trend_confirmed:
                # 强势疯狂：趋势向上确认，轻微惩罚
                emotion_phase_score = -0.3
            elif trend_direction == 'downtrend' and trend_confirmed:
                # 衰竭疯狂：趋势向下确认，重度惩罚
                emotion_phase_score = -1.0
            else:
                # 普通疯狂：中度惩罚
                emotion_phase_score = -0.6
        else:
            emotion_phase_score = 0.0
        
        # 情绪指数（-1到1）
        emotion_index = emotion.get('emotion_index', 0)
        # 反转：低情绪指数反而是买入机会
        emotion_index_score = -emotion_index
        
        # 趋势确认加成/惩罚
        trend_bonus = 0
        if trend_direction == 'uptrend':
            if trend_confirmed:
                trend_bonus = 0.4  # 上升趋势确认，强加成
            else:
                trend_bonus = 0.15  # 上升趋势未确认，轻加成
        elif trend_direction == 'downtrend':
            if trend_confirmed:
                trend_bonus = -0.4  # 下降趋势确认，强惩罚
            else:
                trend_bonus = -0.15  # 下降趋势未确认，轻惩罚
        
        # 深度绝望期额外加成
        despair_bonus = 0
        if phase == 'despair':
            if rsi < 25:
                despair_bonus += 0.25
            elif rsi < 35:
                despair_bonus += 0.12
            
            if emotion_index < -0.5:
                despair_bonus += 0.15
            elif emotion_index < -0.3:
                despair_bonus += 0.08
            
            if phase_strength > 0.7:
                despair_bonus += 0.1
        
        # 综合评分（优化权重分配）
        composite = (
            strength_score * 0.45 +           # 强弱信号（提高权重）
            emotion_phase_score * 0.25 +      # 情绪阶段（降低权重）
            emotion_index_score * 0.15 +      # 情绪指数
            trend_bonus * 0.15 +              # 趋势确认（新增）
            despair_bonus                      # 绝望期加成
        )
        
        # 市场环境调整
        if self.market_regime:
            regime = self.market_regime.get('regime', 'unknown')
            if regime == 'bear':
                # 熊市环境：降低买入信号得分
                if composite > 0:
                    composite *= 0.7
            elif regime == 'bull':
                # 牛市环境：降低卖出信号惩罚
                if composite < 0:
                    composite *= 0.8
        
        # 确保深度绝望期的ETF能获得足够高的分数（但熊市除外）
        if phase == 'despair' and despair_bonus > 0.3:
            if self.market_regime is None or self.market_regime.get('regime') != 'bear':
                composite = max(composite, 0.4)
        
        return composite
    
    def _calculate_signal_confidence(self, strength: Dict, emotion: Dict) -> float:
        """
        计算信号综合置信度
        
        高置信度条件：
        1. 强弱信号和情绪阶段一致
        2. 趋势确认
        3. 多个技术指标共振
        
        Returns:
            置信度 0-1
        """
        confidence = 0.5  # 基础置信度
        
        signal = strength['signal']
        phase = emotion['phase']
        trend = strength.get('trend', {})
        strength_confidence = strength.get('confidence', 'medium')
        
        # 信号和情绪一致性
        if signal in ['strong_buy', 'buy'] and phase == 'despair':
            confidence += 0.2
        elif signal in ['strong_sell', 'sell'] and phase == 'frenzy':
            confidence += 0.2
        elif signal == 'neutral' and phase == 'hesitation':
            confidence += 0.1
        
        # 趋势确认
        if trend.get('confirmed'):
            if (signal in ['strong_buy', 'buy'] and trend['direction'] == 'uptrend') or \
               (signal in ['strong_sell', 'sell'] and trend['direction'] == 'downtrend'):
                confidence += 0.15
            elif (signal in ['strong_buy', 'buy'] and trend['direction'] == 'downtrend') or \
                 (signal in ['strong_sell', 'sell'] and trend['direction'] == 'uptrend'):
                confidence -= 0.2  # 逆势信号降低置信度
        
        # 强弱分析自身置信度
        if strength_confidence == 'high':
            confidence += 0.1
        elif strength_confidence == 'low':
            confidence -= 0.1
        
        # 市场环境调整
        if self.market_regime:
            regime = self.market_regime.get('regime', 'unknown')
            if regime == 'bear' and signal in ['strong_buy', 'buy']:
                confidence -= 0.15  # 熊市买入信号降低置信度
            elif regime == 'bull' and signal in ['strong_sell', 'sell']:
                confidence -= 0.1  # 牛市卖出信号降低置信度
        
        return max(0.1, min(1.0, confidence))
    
    def _calculate_cash_ratio(self, etf_analysis: Dict) -> float:
        """
        根据市场整体情绪计算现金比例
        
        绝望期：降低现金比例（10%）
        犹豫期：正常现金比例（20%）
        疯狂期：提高现金比例（30-40%）
        """
        # 统计各阶段ETF数量
        phase_counts = {'despair': 0, 'hesitation': 0, 'frenzy': 0}
        
        for symbol, analysis in etf_analysis.items():
            phase = analysis['emotion']['phase']
            if phase in phase_counts:
                phase_counts[phase] += 1
        
        total = sum(phase_counts.values())
        if total == 0:
            return 0.2
        
        # 计算各阶段比例
        despair_ratio = phase_counts['despair'] / total
        frenzy_ratio = phase_counts['frenzy'] / total
        
        # 动态调整现金比例
        if frenzy_ratio > 0.5:
            cash_ratio = 0.4  # 多数疯狂，大幅提高现金
        elif frenzy_ratio > 0.3:
            cash_ratio = 0.3  # 部分疯狂，提高现金
        elif despair_ratio > 0.5:
            cash_ratio = 0.1  # 多数绝望，降低现金
        elif despair_ratio > 0.3:
            cash_ratio = 0.15  # 部分绝望，稍降现金
        else:
            cash_ratio = 0.2  # 正常
        
        return cash_ratio
    
    def _calculate_market_regime(self, etf_analysis: Dict) -> str:
        """
        判断市场环境：牛市/熊市/震荡
        
        用于调整信号强度和仓位
        """
        if not etf_analysis:
            return 'range'
        
        # 计算平均综合得分
        avg_score = sum(a['composite_score'] for a in etf_analysis.values()) / len(etf_analysis)
        
        # 统计买卖信号数量
        buy_count = sum(1 for a in etf_analysis.values() 
                       if a['strength']['signal'] in ['strong_buy', 'buy'])
        sell_count = sum(1 for a in etf_analysis.values() 
                        if a['strength']['signal'] in ['strong_sell', 'sell'])
        total = len(etf_analysis)
        
        # 综合判断
        if avg_score > 0.25 and buy_count / total > 0.4:
            return 'bull'
        elif avg_score < -0.25 and sell_count / total > 0.4:
            return 'bear'
        return 'range'
    
    def _select_long_positions(self, sorted_etfs: List, etf_analysis: Dict) -> List[Dict]:
        """
        选择多头持仓
        
        优化：
        - 增加置信度过滤
        - 市场环境调整门槛
        - P0：过滤nan得分
        - P0：禁止特定资产绝望期抄底
        """
        long_positions = []
        max_positions = 6  # 最多6个多头
        
        # 根据市场环境调整门槛
        if self.market_regime and self.market_regime.get('regime') == 'bear':
            min_score = 0.45  # 熊市提高门槛
            min_confidence = 0.5  # 熊市要求更高置信度
        else:
            min_score = 0.35  # 正常门槛
            min_confidence = 0.4  # 正常置信度要求
        
        # 按综合得分降序排列
        sorted_by_score = sorted(
            sorted_etfs,
            key=lambda x: x[1]['composite_score'] if x[1].get('score_valid', True) else -999,
            reverse=True
        )
        
        # 选择得分最高的前N个（得分>门槛 且 置信度>门槛）
        for symbol, analysis in sorted_by_score:
            if len(long_positions) >= max_positions:
                break
            
            # === P0优化：跳过nan得分 ===
            if not analysis.get('score_valid', True):
                continue
            
            composite_score = analysis['composite_score']
            signal_confidence = analysis.get('signal_confidence', 0.5)
            cap_type = analysis['cap_type']
            phase = analysis['emotion']['phase']
            
            # === P0优化：禁止特定资产绝望期抄底 ===
            if symbol in NO_DESPAIR_BUY_ASSETS and phase == 'despair':
                continue  # 这些资产不参与绝望期推荐
            
            # 只选择得分超过门槛的
            if composite_score <= min_score:
                continue
            
            # 置信度过滤
            if signal_confidence < min_confidence:
                continue
            
            # 计算权重（根据得分和置信度动态调整）
            base_weight = 0.15
            if composite_score > 0.6:
                base_weight = 0.25
            elif composite_score > 0.45:
                base_weight = 0.20
            
            # 置信度调整权重
            weight = base_weight * (0.7 + 0.3 * signal_confidence)
            
            # 构建理由
            reasons = []
            if analysis['strength']['signal'] in ['strong_buy', 'buy']:
                reasons.append(f"强弱信号:{analysis['strength']['signal']}")
            if phase == 'despair':
                reasons.append("处于绝望期")
            reasons.extend(analysis['strength'].get('reasons', [])[:2])
            
            long_positions.append({
                'symbol': symbol,
                'name': analysis['name'],
                'weight': weight,
                'composite_score': composite_score,
                'cap_type': cap_type,
                'reason': '，'.join(reasons) if reasons else f"综合得分{composite_score:.2f}"
            })
        
        return long_positions
    
    def _select_hedge_positions(self, sorted_etfs: List, etf_analysis: Dict) -> List[Dict]:
        """
        选择谨慎/回避持仓（弱势标的）
        
        优化v2：区分"强势疯狂"和"衰竭疯狂"
        - 强势疯狂：趋势强劲+高RSI，可能继续上涨，不应回避
        - 衰竭疯狂：趋势衰竭+高RSI+量能萎缩，才应回避
        
        优化v3：
        - P0：过滤nan得分，不参与回避推荐
        - P0：趋势性资产（纳指/印度ETF）恐慌期不发卖出信号
        - P1：牛市环境下"上涨缩量"不作为回避理由
        
        说明：这里的"对冲"是指识别出应该回避或减配的标的，
        而非做空。普通投资者可以：
        1. 不配置这些标的
        2. 如已持有，考虑减仓
        3. 作为风险提示参考
        """
        hedge_positions = []
        
        # 长期趋势强劲的品种列表（红利、银行等防御性品种）
        # 这些品种即使处于疯狂期，也可能继续上涨，需要更严格的回避条件
        defensive_symbols = {'515450', '512800', '515180'}  # 红利低波50、银行ETF、红利ETF
        
        # 判断是否为牛市环境
        is_bull_market = self.market_regime and self.market_regime.get('regime') == 'bull'
        
        # 从最弱的开始选
        for symbol, analysis in reversed(sorted_etfs):
            if len(hedge_positions) >= 2:  # 最多2个
                break
            
            # === P0优化：跳过nan得分 ===
            if not analysis.get('score_valid', True):
                continue
            
            composite_score = analysis['composite_score']
            emotion = analysis['emotion']
            strength = analysis['strength']
            phase = emotion['phase']
            rsi = emotion.get('rsi', 50)
            
            # === P0优化：趋势性资产恐慌期保护 ===
            if symbol in SPECIAL_ASSET_RULES:
                asset_rules = SPECIAL_ASSET_RULES[symbol]
                if asset_rules.get('avoid_short_in_panic', False):
                    panic_threshold = asset_rules.get('panic_rsi_threshold', 25)
                    # 如果RSI低于恐慌阈值，不发回避信号（可能是V型反转机会）
                    if rsi < panic_threshold:
                        continue
                    # 如果处于绝望期，也不发回避信号
                    if phase == 'despair':
                        continue
            
            # 基础门槛：只选择负分的
            if composite_score >= -0.2:
                continue
            
            # === P1优化：牛市环境下"上涨缩量"不作为回避理由 ===
            reasons_list = strength.get('reasons', [])
            if is_bull_market:
                # 如果唯一的负面理由是"上涨缩量"，则跳过
                negative_reasons = [r for r in reasons_list if '缩量' in r or '买盘不足' in r]
                other_negative_reasons = [r for r in reasons_list if r not in negative_reasons and 
                                         ('顶背离' in r or '超买' in r or '卖出' in r)]
                if negative_reasons and not other_negative_reasons:
                    # 只有缩量相关的负面理由，牛市中跳过
                    continue
            
            # === 优化：区分强势疯狂 vs 衰竭疯狂 ===
            if phase == 'frenzy':
                # 检查是否为"强势疯狂"（趋势强劲，不应回避）
                trend_info = strength.get('trend', {})
                trend_direction = trend_info.get('direction', 'unknown')
                trend_confirmed = trend_info.get('confirmed', False)
                
                # 条件1：趋势向上且已确认 = 强势疯狂，跳过回避
                if trend_direction == 'uptrend' and trend_confirmed:
                    continue
                
                # 条件2：防御性品种（红利/银行）需要更严格的回避条件
                if symbol in defensive_symbols:
                    # RSI需要极端超买(>85)且有明确卖出信号才回避
                    if rsi < 85 or strength['signal'] not in ['strong_sell', 'sell']:
                        continue
                
                # 条件3：RSI在70-80之间，且没有明确卖出信号，可能是正常上涨
                if 65 < rsi < 80 and strength['signal'] not in ['strong_sell', 'sell']:
                    continue
            
            # === 优化：绝望期买入信号不应被回避 ===
            # 如果处于绝望期且有买入信号，这是机会不是风险
            if phase == 'despair' and strength['signal'] in ['strong_buy', 'buy']:
                continue
            
            # 构建理由
            reasons = []
            if strength['signal'] in ['strong_sell', 'sell']:
                reasons.append(f"强弱信号:{strength['signal']}")
            if phase == 'frenzy':
                # 细化疯狂期描述
                if rsi > 85:
                    reasons.append("极度超买(RSI>85)")
                else:
                    reasons.append("处于疯狂期")
            reasons.extend(strength.get('reasons', [])[:2])
            
            # 计算回避置信度（用于排序和展示）
            avoid_confidence = self._calculate_avoid_confidence(analysis)
            
            hedge_positions.append({
                'symbol': symbol,
                'name': analysis['name'],
                'weight': 0.1,  # 这里的weight表示风险敞口，建议回避
                'composite_score': composite_score,
                'cap_type': analysis['cap_type'],
                'action': 'avoid',  # 明确操作建议
                'avoid_confidence': avoid_confidence,
                'reason': '，'.join(reasons) if reasons else f"综合得分{composite_score:.2f}，建议回避"
            })
        
        # 按回避置信度排序，优先展示高置信度的
        hedge_positions.sort(key=lambda x: x.get('avoid_confidence', 0), reverse=True)
        
        return hedge_positions
    
    def _calculate_avoid_confidence(self, analysis: Dict) -> float:
        """
        计算回避信号的置信度
        
        高置信度回避条件：
        1. 明确的卖出信号 + 疯狂期
        2. RSI极端超买(>85)
        3. 趋势向下确认
        4. 近期涨幅过大(>20%)
        
        低置信度（不应回避）：
        1. 趋势向上确认
        2. 防御性品种正常波动
        3. 绝望期抄底机会
        """
        confidence = 0.0
        
        emotion = analysis['emotion']
        strength = analysis['strength']
        phase = emotion['phase']
        rsi = emotion.get('rsi', 50)
        
        # 卖出信号加分
        if strength['signal'] == 'strong_sell':
            confidence += 0.4
        elif strength['signal'] == 'sell':
            confidence += 0.25
        
        # 疯狂期加分（但需要配合其他条件）
        if phase == 'frenzy':
            confidence += 0.2
            # RSI极端超买额外加分
            if rsi > 85:
                confidence += 0.3
            elif rsi > 80:
                confidence += 0.15
        
        # 趋势向下确认加分
        trend_info = strength.get('trend', {})
        if trend_info.get('direction') == 'downtrend' and trend_info.get('confirmed'):
            confidence += 0.3
        
        # 趋势向上确认减分（强势不应回避）
        if trend_info.get('direction') == 'uptrend' and trend_info.get('confirmed'):
            confidence -= 0.4
        
        return max(0, min(1, confidence))
    
    def generate_scenario_strategies(self) -> Dict:
        """
        生成情景策略
        
        核心思想：将可能走势列出，以不同策略应对
        """
        base_portfolio = self.generate_hedge_portfolio()
        
        scenarios = {
            'base': {
                'description': '基准情景',
                'portfolio': base_portfolio
            },
            'bullish': {
                'description': '乐观情景：市场继续上涨',
                'action': '可适度增加多头仓位，减少现金',
                'adjustment': {
                    'cash_ratio': max(0.1, base_portfolio['cash_ratio'] - 0.1),
                    'long_weight_multiplier': 1.2
                }
            },
            'bearish': {
                'description': '悲观情景：市场下跌',
                'action': '增加现金比例，保持对冲',
                'adjustment': {
                    'cash_ratio': min(0.5, base_portfolio['cash_ratio'] + 0.15),
                    'long_weight_multiplier': 0.7
                }
            },
            'volatile': {
                'description': '震荡情景：市场大幅波动',
                'action': '降低总仓位，增加对冲比例',
                'adjustment': {
                    'cash_ratio': min(0.4, base_portfolio['cash_ratio'] + 0.1),
                    'hedge_weight_multiplier': 1.5
                }
            }
        }
        
        return scenarios
    
    def check_exit_signal(self, symbol: str, entry_price: float, 
                          entry_date: str, current_date: str = None) -> Dict:
        """
        检查止损止盈信号
        
        Args:
            symbol: ETF代码
            entry_price: 入场价格
            entry_date: 入场日期 (YYYY-MM-DD)
            current_date: 当前日期，默认使用最新数据
        
        Returns:
            出场信号和原因
        """
        from datetime import datetime
        
        df = self.data_fetcher.get_etf_history(symbol)
        if df.empty:
            return {'exit': False, 'reason': '数据不足'}
        
        # 获取当前价格
        if current_date:
            df_filtered = df[df['date'] <= current_date]
            if df_filtered.empty:
                return {'exit': False, 'reason': '数据不足'}
            current_price = df_filtered.iloc[-1]['close']
            current_dt = datetime.strptime(current_date, '%Y-%m-%d')
        else:
            current_price = df.iloc[-1]['close']
            current_dt = df.iloc[-1]['date']
        
        # 计算收益率
        pct_change = (current_price / entry_price - 1) * 100
        
        # 计算持有时间（周）
        entry_dt = datetime.strptime(entry_date, '%Y-%m-%d')
        holding_days = (current_dt - entry_dt).days
        holding_weeks = holding_days / 7
        
        # 止损检查
        if pct_change <= RISK_PARAMS['stop_loss']:
            return {
                'exit': True,
                'signal': 'stop_loss',
                'reason': f"触发止损：亏损{abs(pct_change):.1f}%",
                'pct_change': pct_change,
                'holding_weeks': holding_weeks
            }
        
        # 止盈检查
        if pct_change >= RISK_PARAMS['take_profit']:
            return {
                'exit': True,
                'signal': 'take_profit',
                'reason': f"触发止盈：盈利{pct_change:.1f}%",
                'pct_change': pct_change,
                'holding_weeks': holding_weeks
            }
        
        # 时间止损检查
        if holding_weeks >= RISK_PARAMS['time_stop_weeks']:
            if pct_change < RISK_PARAMS['time_stop_min_profit']:
                return {
                    'exit': True,
                    'signal': 'time_stop',
                    'reason': f"时间止损：持有{holding_weeks:.0f}周，收益{pct_change:+.1f}%不达标",
                    'pct_change': pct_change,
                    'holding_weeks': holding_weeks
                }
        
        # 趋势反转检查（针对特殊资产）
        if symbol in SPECIAL_ASSETS:
            strength_analyzer = StrengthWeaknessAnalyzer(
                df, use_weekly=self.use_weekly, symbol=symbol
            )
            result = strength_analyzer.analyze_strength()
            trend = result.get('trend', {})
            
            # 如果持有多头但趋势转空
            if trend.get('direction') == 'downtrend' and trend.get('confirmed'):
                return {
                    'exit': True,
                    'signal': 'trend_reversal',
                    'reason': f"趋势反转：确认下降趋势",
                    'pct_change': pct_change,
                    'holding_weeks': holding_weeks
                }
        
        return {
            'exit': False,
            'reason': '继续持有',
            'pct_change': pct_change,
            'holding_weeks': holding_weeks
        }
    
    def get_position_advice(self, symbol: str) -> Dict:
        """
        获取单个标的的持仓建议
        
        综合分析后给出：建仓/加仓/减仓/清仓建议
        """
        df = self.data_fetcher.get_etf_history(symbol)
        if df.empty:
            return {'action': 'hold', 'reason': '数据不足'}
        
        # 强弱分析
        strength_analyzer = StrengthWeaknessAnalyzer(
            df, use_weekly=self.use_weekly, symbol=symbol
        )
        strength_result = strength_analyzer.analyze_strength()
        
        # 情绪分析
        emotion_analyzer = EmotionCycleAnalyzer(df, use_weekly=self.use_weekly)
        emotion_result = emotion_analyzer.get_emotion_phase()
        
        signal = strength_result['signal']
        phase = emotion_result['phase']
        score = strength_result['score']
        
        # 综合判断
        if signal == 'strong_buy' and phase == 'despair':
            action = 'strong_buy'
            advice = '强烈建议建仓/加仓'
        elif signal in ['strong_buy', 'buy'] and phase in ['despair', 'hesitation']:
            action = 'buy'
            advice = '可以建仓/加仓'
        elif signal == 'strong_sell' and phase == 'frenzy':
            action = 'strong_sell'
            advice = '强烈建议减仓/清仓'
        elif signal in ['strong_sell', 'sell'] and phase in ['frenzy', 'hesitation']:
            action = 'sell'
            advice = '建议减仓'
        else:
            action = 'hold'
            advice = '持有观望'
        
        return {
            'symbol': symbol,
            'name': ETF_POOL.get(symbol, symbol),
            'action': action,
            'advice': advice,
            'signal': signal,
            'phase': phase,
            'score': score,
            'is_special': symbol in SPECIAL_ASSETS
        }
