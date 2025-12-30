"""
策略二：情绪周期分析
核心逻辑：行情在绝望中产生，犹豫中发展，疯狂中消亡
优化：多维度指标综合评估，周线级别减少噪音
新增：阶段转换确认机制，市场环境过滤
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional


class EmotionCycleAnalyzer:
    """
    情绪周期分析器（周线级别）
    
    绝望：净卖盘衰竭，多头逐渐返场
    犹豫：换手充分，多头接力，行情继续
    疯狂：多数已进场，净买盘衰竭，行情结束
    """
    
    def __init__(self, df: pd.DataFrame, use_weekly: bool = True):
        """
        初始化分析器
        
        Args:
            df: 日线数据
            use_weekly: 是否转换为周线分析
        """
        self.daily_df = df.copy()
        self.use_weekly = use_weekly
        
        if use_weekly and len(df) >= 20:
            self.df = self._convert_to_weekly(df)
        else:
            self.df = df.copy()
        
        self._calculate_emotion_indicators()
    
    def _convert_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        """将日线数据转换为周线数据"""
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
    
    def _calculate_emotion_indicators(self):
        """计算多维度情绪指标"""
        df = self.df
        
        # 1. 换手率指标
        turnover_window = 10 if self.use_weekly else 20
        df['turnover_ma'] = df['turnover'].rolling(turnover_window).mean()
        df['turnover_std'] = df['turnover'].rolling(turnover_window).std()
        df['turnover_zscore'] = (df['turnover'] - df['turnover_ma']) / (df['turnover_std'] + 1e-10)
        
        # 2. 成交额变化率
        df['amount_ma'] = df['amount'].rolling(turnover_window).mean()
        df['amount_ratio'] = df['amount'] / (df['amount_ma'] + 1e-10)
        
        # 3. 波动率指标
        vol_window = 8 if self.use_weekly else 20
        df['volatility'] = df['pct_change'].rolling(vol_window).std()
        df['volatility_ma'] = df['volatility'].rolling(vol_window).mean()
        df['volatility_ratio'] = df['volatility'] / (df['volatility_ma'] + 1e-10)
        
        # 4. RSI (Wilder平滑法，与交易软件一致)
        rsi_period = 6 if self.use_weekly else 14  # 周线6周期≈日线30周期
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        # 使用Wilder平滑（EMA with alpha=1/n）
        avg_gain = gain.ewm(alpha=1/rsi_period, min_periods=rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/rsi_period, min_periods=rsi_period, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 5. 价格位置（相对历史高低点）
        lookback = 26 if self.use_weekly else 120
        df['price_high'] = df['close'].rolling(lookback).max()
        df['price_low'] = df['close'].rolling(lookback).min()
        df['price_position'] = (df['close'] - df['price_low']) / (df['price_high'] - df['price_low'] + 1e-10)
        
        # 6. 连续涨跌统计
        df['up_streak'] = 0
        df['down_streak'] = 0
        df['up_weeks_ratio'] = 0.0  # 近N周上涨比例
        
        up_count = 0
        down_count = 0
        for i in range(len(df)):
            if df.iloc[i]['pct_change'] > 0:
                up_count += 1
                down_count = 0
            elif df.iloc[i]['pct_change'] < 0:
                down_count += 1
                up_count = 0
            else:
                up_count = 0
                down_count = 0
            df.iloc[i, df.columns.get_loc('up_streak')] = up_count
            df.iloc[i, df.columns.get_loc('down_streak')] = down_count
        
        # 近N周上涨比例
        ratio_window = 8 if self.use_weekly else 20
        for i in range(ratio_window, len(df)):
            recent = df.iloc[i-ratio_window:i]['pct_change']
            df.iloc[i, df.columns.get_loc('up_weeks_ratio')] = (recent > 0).sum() / ratio_window
        
        # 7. 动量指标
        mom_period = 4 if self.use_weekly else 10
        df['momentum'] = (df['close'] / df['close'].shift(mom_period) - 1) * 100
        
        # 8. 计算综合情绪指数（多维度加权）
        df['emotion_index'] = self._calculate_composite_emotion(df)
        
        self.df = df
    
    def _calculate_composite_emotion(self, df: pd.DataFrame) -> pd.Series:
        """
        计算综合情绪指数
        
        综合考虑：RSI、价格位置、换手率、波动率、动量
        范围：-1（极度恐惧）到 +1（极度贪婪）
        """
        # RSI归一化 (-1 to 1)
        rsi_norm = (df['rsi'] - 50) / 50
        
        # 价格位置归一化 (-1 to 1)
        price_norm = df['price_position'] * 2 - 1
        
        # 换手率Z分数（截断到-2,2再归一化）
        turnover_norm = df['turnover_zscore'].clip(-2, 2) / 2
        
        # 波动率比率归一化
        volatility_norm = (df['volatility_ratio'].clip(0.5, 2) - 1.25) / 0.75
        
        # 动量归一化
        momentum_norm = (df['momentum'].clip(-20, 20) / 20)
        
        # 上涨周比例归一化
        up_ratio_norm = df['up_weeks_ratio'] * 2 - 1
        
        # 综合加权
        emotion = (
            rsi_norm * 0.25 +           # RSI权重25%
            price_norm * 0.20 +          # 价格位置权重20%
            turnover_norm * 0.15 +       # 换手率权重15%
            volatility_norm * 0.10 +     # 波动率权重10%
            momentum_norm * 0.15 +       # 动量权重15%
            up_ratio_norm * 0.15         # 上涨比例权重15%
        )
        
        return emotion
    
    def get_emotion_phase(self, market_regime: Optional[Dict] = None) -> Dict:
        """
        判断当前情绪阶段
        
        绝望期：情绪指数 < -0.3，RSI<35，价格位置低
        犹豫期：情绪指数 -0.3~0.3，RSI 35-65
        疯狂期：情绪指数 > 0.3，RSI>65，价格位置高
        
        优化：
        - 增加核心指标一致性检查，避免矛盾判定
        - 增加阶段转换确认机制
        - 考虑市场环境因素
        """
        df = self.df
        min_periods = 12 if self.use_weekly else 30
        
        if len(df) < min_periods:
            return {
                'phase': 'unknown',
                'scores': {},
                'suggestion': '数据不足',
                'action': 'hold',
                'emotion_index': 0,
                'rsi': 50,
                'weekly_mode': self.use_weekly
            }
        
        latest = df.iloc[-1]
        recent_n = 4 if self.use_weekly else 10
        recent = df.iloc[-recent_n:]
        
        # 计算各阶段得分
        despair_score = 0
        hesitation_score = 0
        frenzy_score = 0
        
        # 核心指标
        avg_emotion = recent['emotion_index'].mean()
        avg_rsi = recent['rsi'].mean()
        price_pos = latest['price_position']
        
        # 1. 情绪指数分析（核心指标，权重提高）
        if avg_emotion < -0.4:
            despair_score += 5
        elif avg_emotion < -0.2:
            despair_score += 3
            hesitation_score += 1
        elif avg_emotion < 0.2:
            hesitation_score += 5
        elif avg_emotion < 0.4:
            hesitation_score += 2
            frenzy_score += 2
        else:
            frenzy_score += 5
        
        # 2. RSI分析（核心指标，权重提高）
        if avg_rsi < 30:
            despair_score += 4
        elif avg_rsi < 40:
            despair_score += 2
            hesitation_score += 1
        elif avg_rsi < 60:
            hesitation_score += 3
        elif avg_rsi < 70:
            hesitation_score += 2
            frenzy_score += 1
        else:
            frenzy_score += 4
        
        # 3. 价格位置分析
        if price_pos < 0.2:
            despair_score += 2
        elif price_pos < 0.4:
            despair_score += 1
        elif price_pos < 0.6:
            hesitation_score += 2
        elif price_pos < 0.8:
            frenzy_score += 1
        else:
            frenzy_score += 2
        
        # 4. 换手率分析
        turnover_z = latest['turnover_zscore']
        if turnover_z < -1:
            despair_score += 1
        elif turnover_z < 0:
            hesitation_score += 1
        elif turnover_z < 1.5:
            hesitation_score += 1
        else:
            frenzy_score += 1
        
        # 5. 连续涨跌分析
        streak_threshold = 3 if self.use_weekly else 5
        if latest['down_streak'] >= streak_threshold:
            despair_score += 2
        elif latest['up_streak'] >= streak_threshold:
            frenzy_score += 2
        else:
            hesitation_score += 1
        
        # 6. 波动率分析
        if latest['volatility_ratio'] > 1.5:
            frenzy_score += 1
        elif latest['volatility_ratio'] < 0.6:
            despair_score += 1
        
        # 7. 上涨周比例
        up_ratio = latest['up_weeks_ratio']
        if up_ratio < 0.3:
            despair_score += 1
        elif up_ratio > 0.7:
            frenzy_score += 1
        
        # === 核心指标一致性检查（防止矛盾判定）===
        # 如果RSI和情绪指数都在中性区间，强制判定为犹豫期
        if 40 <= avg_rsi <= 65 and -0.2 <= avg_emotion <= 0.2:
            hesitation_score += 3  # 额外加分确保犹豫期
        
        # 如果RSI超卖但被判定为疯狂期，修正
        if avg_rsi < 40 and frenzy_score > despair_score:
            despair_score += 3
            frenzy_score -= 2
        
        # 如果RSI超买但被判定为绝望期，修正
        if avg_rsi > 65 and despair_score > frenzy_score:
            frenzy_score += 3
            despair_score -= 2
        
        # === 新增：阶段转换确认 ===
        phase_transition = self._detect_phase_transition()
        
        # 如果检测到阶段转换，调整得分
        if phase_transition['transitioning']:
            if phase_transition['from_phase'] == 'despair' and phase_transition['to_phase'] == 'hesitation':
                # 绝望→犹豫：需要确认企稳
                if not phase_transition['confirmed']:
                    despair_score += 2  # 保持绝望期判定
            elif phase_transition['from_phase'] == 'hesitation' and phase_transition['to_phase'] == 'frenzy':
                # 犹豫→疯狂：需要确认加速
                if not phase_transition['confirmed']:
                    hesitation_score += 2  # 保持犹豫期判定
        
        # === 新增：市场环境调整 ===
        if market_regime:
            regime = market_regime.get('regime', 'unknown')
            if regime == 'bear':
                # 熊市环境下，提高绝望期判定门槛
                if despair_score > hesitation_score and despair_score - hesitation_score < 3:
                    hesitation_score += 2  # 边界情况偏向犹豫期
            elif regime == 'bull':
                # 牛市环境下，降低疯狂期判定敏感度
                if frenzy_score > hesitation_score and frenzy_score - hesitation_score < 3:
                    hesitation_score += 1  # 边界情况偏向犹豫期
        
        # 判断阶段
        scores = {
            'despair': max(0, despair_score),
            'hesitation': max(0, hesitation_score),
            'frenzy': max(0, frenzy_score)
        }
        phase = max(scores, key=lambda k: scores[k])
        
        # 计算阶段强度
        total_score = sum(scores.values())
        phase_strength = scores[phase] / total_score if total_score > 0 else 0
        
        # 投资建议
        if phase == 'despair':
            if phase_strength > 0.5:
                suggestion = '深度绝望期：可积极分批建仓'
                action = 'strong_buy'
            else:
                suggestion = '绝望期：逐步建仓，分批买入'
                action = 'buy'
        elif phase == 'hesitation':
            suggestion = '犹豫期：持有观望，顺势而为'
            action = 'hold'
        else:
            if phase_strength > 0.5:
                suggestion = '极度疯狂期：应大幅减仓'
                action = 'strong_sell'
            else:
                suggestion = '疯狂期：逐步减仓，锁定利润'
                action = 'sell'
        
        return {
            'phase': phase,
            'phase_strength': phase_strength,
            'scores': scores,
            'suggestion': suggestion,
            'action': action,
            'emotion_index': latest['emotion_index'],
            'avg_emotion': avg_emotion,
            'rsi': latest['rsi'],
            'price_position': price_pos,
            'turnover_zscore': turnover_z,
            'weekly_mode': self.use_weekly,
            'phase_transition': phase_transition
        }
    
    def _detect_phase_transition(self) -> Dict:
        """
        检测情绪阶段转换信号
        
        绝望→犹豫：
        - 连续2周RSI回升
        - 成交量温和放大
        - 价格站上5周均线
        
        犹豫→疯狂：
        - RSI突破70
        - 成交量急剧放大
        - 价格加速上涨
        
        Returns:
            阶段转换信息
        """
        df = self.df
        if len(df) < 8:
            return {'transitioning': False, 'from_phase': None, 'to_phase': None, 'confirmed': False}
        
        recent_period = 4 if self.use_weekly else 10
        recent = df.iloc[-recent_period:]
        prev = df.iloc[-(recent_period*2):-recent_period]
        
        if len(prev) < recent_period:
            return {'transitioning': False, 'from_phase': None, 'to_phase': None, 'confirmed': False}
        
        # 计算指标变化
        recent_rsi = recent['rsi'].mean()
        prev_rsi = prev['rsi'].mean()
        rsi_change = recent_rsi - prev_rsi
        
        recent_vol = recent['volume'].mean()
        prev_vol = prev['volume'].mean()
        vol_change = (recent_vol - prev_vol) / prev_vol if prev_vol > 0 else 0
        
        recent_emotion = recent['emotion_index'].mean()
        prev_emotion = prev['emotion_index'].mean()
        emotion_change = recent_emotion - prev_emotion
        
        # 检测绝望→犹豫转换
        if prev_rsi < 35 and recent_rsi > prev_rsi:
            # RSI从超卖区回升
            confirmed = (
                rsi_change > 5 and  # RSI明显回升
                vol_change > 0 and vol_change < 0.5 and  # 成交量温和放大
                emotion_change > 0.1  # 情绪改善
            )
            return {
                'transitioning': True,
                'from_phase': 'despair',
                'to_phase': 'hesitation',
                'confirmed': confirmed,
                'rsi_change': rsi_change,
                'vol_change': vol_change,
                'emotion_change': emotion_change
            }
        
        # 检测犹豫→疯狂转换
        if 40 < prev_rsi < 65 and recent_rsi > 70:
            # RSI突破超买区
            confirmed = (
                rsi_change > 10 and  # RSI快速上升
                vol_change > 0.5 and  # 成交量大幅放大
                emotion_change > 0.2  # 情绪快速升温
            )
            return {
                'transitioning': True,
                'from_phase': 'hesitation',
                'to_phase': 'frenzy',
                'confirmed': confirmed,
                'rsi_change': rsi_change,
                'vol_change': vol_change,
                'emotion_change': emotion_change
            }
        
        # 检测疯狂→犹豫转换（见顶回落）
        if prev_rsi > 70 and recent_rsi < prev_rsi:
            confirmed = (
                rsi_change < -10 and  # RSI快速下降
                emotion_change < -0.15  # 情绪降温
            )
            return {
                'transitioning': True,
                'from_phase': 'frenzy',
                'to_phase': 'hesitation',
                'confirmed': confirmed,
                'rsi_change': rsi_change,
                'vol_change': vol_change,
                'emotion_change': emotion_change
            }
        
        return {'transitioning': False, 'from_phase': None, 'to_phase': None, 'confirmed': False}
    
    def get_emotion_trend(self) -> Dict:
        """获取情绪趋势（情绪是在改善还是恶化）"""
        df = self.df
        if len(df) < 8:
            return {'trend': 'unknown', 'change': 0}
        
        recent_period = 4 if self.use_weekly else 10
        prev_period = 4 if self.use_weekly else 10
        
        recent_emotion = df['emotion_index'].iloc[-recent_period:].mean()
        prev_emotion = df['emotion_index'].iloc[-(recent_period+prev_period):-recent_period].mean()
        
        change = recent_emotion - prev_emotion
        
        if change > 0.15:
            trend = 'improving_fast'
            description = '情绪快速改善'
        elif change > 0.05:
            trend = 'improving'
            description = '情绪逐步改善'
        elif change < -0.15:
            trend = 'deteriorating_fast'
            description = '情绪快速恶化'
        elif change < -0.05:
            trend = 'deteriorating'
            description = '情绪逐步恶化'
        else:
            trend = 'stable'
            description = '情绪相对稳定'
        
        return {
            'trend': trend,
            'description': description,
            'change': change,
            'recent_emotion': recent_emotion,
            'prev_emotion': prev_emotion
        }
