"""
策略一：强弱分析法
核心逻辑：该涨不涨看跌，该跌不跌看涨
优化：采用周线级别分析，减少日线噪音
新增：趋势确认因子，特殊资产处理
"""

import pandas as pd
import numpy as np
from typing import Dict
from config import SPECIAL_ASSETS


class StrengthWeaknessAnalyzer:
    """
    强弱分析器（周线级别）
    
    当系统受到短期强大冲量（情绪、政策、消息）的打击，
    而价格却没有同向运行，或很快被扭回，
    则说明中长期因素指向相反方向。
    
    新增：趋势确认机制，特殊资产使用趋势跟踪策略
    """
    
    def __init__(self, df: pd.DataFrame, use_weekly: bool = True, symbol: str = None):
        """
        初始化分析器
        
        Args:
            df: 日线数据
            use_weekly: 是否转换为周线分析（默认True）
            symbol: ETF代码，用于识别特殊资产
        """
        self.daily_df = df.copy()
        self.use_weekly = use_weekly
        self.symbol = symbol
        self.is_special_asset = symbol in SPECIAL_ASSETS if symbol else False
        
        if use_weekly and len(df) >= 20:
            self.df = self._convert_to_weekly(df)
        else:
            self.df = df.copy()
        
        self._calculate_indicators()
    
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
        
        # 计算周涨跌幅
        weekly['pct_change'] = weekly['close'].pct_change() * 100
        weekly = weekly.reset_index()
        
        return weekly
    
    def _calculate_indicators(self):
        """计算技术指标"""
        df = self.df
        
        # 均线（周线：4周≈月线，13周≈季线，26周≈半年线）
        if self.use_weekly:
            df['ma_short'] = df['close'].rolling(4).mean()   # 月线
            df['ma_mid'] = df['close'].rolling(13).mean()    # 季线
            df['ma_long'] = df['close'].rolling(26).mean()   # 半年线
        else:
            df['ma_short'] = df['close'].rolling(5).mean()
            df['ma_mid'] = df['close'].rolling(20).mean()
            df['ma_long'] = df['close'].rolling(60).mean()
        
        # 波动率
        window = 10 if self.use_weekly else 20
        df['volatility'] = df['pct_change'].rolling(window).std()
        
        # 成交量均线
        vol_window = 4 if self.use_weekly else 5
        vol_long_window = 13 if self.use_weekly else 20
        df['vol_ma_short'] = df['volume'].rolling(vol_window).mean()
        df['vol_ma_long'] = df['volume'].rolling(vol_long_window).mean()
        
        # RSI（Wilder平滑法，与交易软件一致）
        rsi_period = 6 if self.use_weekly else 14  # 周线6周期≈日线30周期
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/rsi_period, min_periods=rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/rsi_period, min_periods=rsi_period, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD（周线参数调整）
        if self.use_weekly:
            fast, slow, signal = 6, 13, 4
        else:
            fast, slow, signal = 12, 26, 9
        
        exp_fast = df['close'].ewm(span=fast, adjust=False).mean()
        exp_slow = df['close'].ewm(span=slow, adjust=False).mean()
        df['macd'] = exp_fast - exp_slow
        df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # 布林带
        bb_window = 10 if self.use_weekly else 20
        df['bb_mid'] = df['close'].rolling(bb_window).mean()
        df['bb_std'] = df['close'].rolling(bb_window).std()
        df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)
        
        # 动量指标
        mom_period = 4 if self.use_weekly else 10
        df['momentum'] = df['close'] / df['close'].shift(mom_period) - 1
        
        self.df = df
    
    def _check_trend(self) -> Dict:
        """
        检查趋势状态
        
        Returns:
            趋势信息：方向、强度、确认度
        """
        df = self.df
        if len(df) < 10:
            return {'direction': 'unknown', 'strength': 0, 'confirmed': False}
        
        latest = df.iloc[-1]
        
        # 均线排列判断趋势
        ma_short = latest.get('ma_short', 0)
        ma_mid = latest.get('ma_mid', 0)
        ma_long = latest.get('ma_long', 0)
        price = latest['close']
        
        # 计算趋势强度
        if pd.notna(ma_short) and pd.notna(ma_mid) and pd.notna(ma_long):
            # 多头排列：价格 > 短期 > 中期 > 长期
            if price > ma_short > ma_mid > ma_long:
                direction = 'uptrend'
                strength = 1.0
                confirmed = True
            # 弱多头：价格 > 短期 > 中期
            elif price > ma_short > ma_mid:
                direction = 'uptrend'
                strength = 0.6
                confirmed = True
            # 空头排列：价格 < 短期 < 中期 < 长期
            elif price < ma_short < ma_mid < ma_long:
                direction = 'downtrend'
                strength = 1.0
                confirmed = True
            # 弱空头
            elif price < ma_short < ma_mid:
                direction = 'downtrend'
                strength = 0.6
                confirmed = True
            else:
                direction = 'sideways'
                strength = 0.3
                confirmed = False
        else:
            direction = 'unknown'
            strength = 0
            confirmed = False
        
        # 动量确认
        momentum = latest.get('momentum', 0)
        if pd.notna(momentum):
            if direction == 'uptrend' and momentum > 0.05:
                strength = min(1.0, strength + 0.2)
            elif direction == 'downtrend' and momentum < -0.05:
                strength = min(1.0, strength + 0.2)
        
        return {
            'direction': direction,
            'strength': strength,
            'confirmed': confirmed,
            'ma_short': ma_short,
            'ma_mid': ma_mid,
            'ma_long': ma_long
        }
    
    def _analyze_special_asset(self) -> Dict:
        """
        特殊资产分析（趋势跟踪策略）
        
        对于黄金、美股、商品等与A股相关性低的资产，
        使用趋势跟踪而非逆向策略
        """
        df = self.df
        if len(df) < 12:
            return {
                'signal': 'neutral',
                'score': 0,
                'reasons': ['数据不足'],
                'rsi': 50,
                'price_position': 0.5,
                'weekly_mode': self.use_weekly,
                'is_special': True
            }
        
        latest = df.iloc[-1]
        trend = self._check_trend()
        
        score = 0
        reasons = []
        
        # 趋势跟踪核心逻辑
        if trend['direction'] == 'uptrend':
            if trend['confirmed']:
                score += 3
                reasons.append("趋势向上确认")
            else:
                score += 1
                reasons.append("趋势偏多")
            
            # 回调买入机会
            if latest['bb_position'] < 0.4 and latest['rsi'] < 50:
                score += 1
                reasons.append("上升趋势中回调")
                
        elif trend['direction'] == 'downtrend':
            if trend['confirmed']:
                score -= 3
                reasons.append("趋势向下确认")
            else:
                score -= 1
                reasons.append("趋势偏空")
            
            # 反弹卖出机会
            if latest['bb_position'] > 0.6 and latest['rsi'] > 50:
                score -= 1
                reasons.append("下降趋势中反弹")
        else:
            reasons.append("趋势不明")
        
        # 动量确认
        momentum = latest.get('momentum', 0)
        if pd.notna(momentum):
            if momentum > 0.08:
                score += 1
                reasons.append("动量强劲")
            elif momentum < -0.08:
                score -= 1
                reasons.append("动量疲弱")
        
        # 判断信号（特殊资产提高阈值，需要更强趋势确认）
        if score >= 4:
            signal = 'strong_buy'
        elif score >= 2:
            signal = 'buy'
        elif score <= -4:
            signal = 'strong_sell'
        elif score <= -2:
            signal = 'sell'
        else:
            signal = 'neutral'
        
        price_min = df['close'].min()
        price_max = df['close'].max()
        price_position = (latest['close'] - price_min) / (price_max - price_min + 1e-10)
        
        return {
            'signal': signal,
            'score': score,
            'reasons': reasons,
            'rsi': latest['rsi'],
            'price_position': price_position,
            'bb_position': latest['bb_position'],
            'momentum': latest.get('momentum', 0),
            'weekly_mode': self.use_weekly,
            'is_special': True,
            'trend': trend
        }

    def analyze_strength(self) -> Dict:
        """
        分析强弱信号
        
        特殊资产使用趋势跟踪策略
        普通资产使用逆向策略 + 趋势确认
        
        强势信号：
        - 下跌时成交量萎缩（该跌不跌）
        - RSI/MACD底背离
        - 价格在布林带下轨获得支撑
        
        弱势信号：
        - 上涨时成交量萎缩（该涨不涨）
        - RSI/MACD顶背离
        - 价格在布林带上轨遇阻
        """
        # 特殊资产使用趋势跟踪策略
        if self.is_special_asset:
            return self._analyze_special_asset()
        
        df = self.df
        min_periods = 12 if self.use_weekly else 60
        
        if len(df) < min_periods:
            return {
                'signal': 'neutral',
                'score': 0,
                'reasons': ['数据不足'],
                'rsi': 50,
                'price_position': 0.5,
                'weekly_mode': self.use_weekly
            }
        
        latest = df.iloc[-1]
        prev_periods = 3 if self.use_weekly else 5
        prev_n = df.iloc[-(prev_periods+1):-1]
        lookback = 10 if self.use_weekly else 20
        prev_lookback = df.iloc[-(lookback+1):-1]
        
        # 先获取趋势信息
        trend = self._check_trend()
        
        score = 0
        reasons = []
        
        # 1. 价格位置分析
        price_min = df['close'].min()
        price_max = df['close'].max()
        price_position = (latest['close'] - price_min) / (price_max - price_min + 1e-10)
        
        # 2. 该跌不跌分析（强势）
        recent_down = prev_n[prev_n['pct_change'] < 0]
        if len(recent_down) >= 2:
            avg_down_vol = recent_down['volume'].mean()
            if avg_down_vol < latest['vol_ma_long'] * 0.7:
                score += 2
                reasons.append("下跌缩量，卖压减轻")
        
        # 3. 该涨不涨分析（弱势）
        recent_up = prev_n[prev_n['pct_change'] > 0]
        if len(recent_up) >= 2:
            avg_up_vol = recent_up['volume'].mean()
            if avg_up_vol < latest['vol_ma_long'] * 0.7:
                score -= 2
                reasons.append("上涨缩量，买盘不足")
        
        # 4. RSI背离分析
        rsi_divergence_type = None  # 记录背离类型，避免同时出现顶底背离
        if latest['rsi'] < 35:
            # 检查是否底背离：RSI新低但价格未新低
            rsi_min_idx = prev_lookback['rsi'].idxmin()
            if latest['rsi'] < prev_lookback['rsi'].min() * 1.1:
                if latest['close'] > prev_lookback.loc[rsi_min_idx, 'close']:
                    score += 2
                    reasons.append("RSI底背离")
                    rsi_divergence_type = 'bottom'
            else:
                score += 1
                reasons.append("RSI超卖区域")
        elif latest['rsi'] > 70:  # 调整RSI超买阈值从65到70
            # 检查是否顶背离
            rsi_max_idx = prev_lookback['rsi'].idxmax()
            if latest['rsi'] > prev_lookback['rsi'].max() * 0.9:
                if latest['close'] < prev_lookback.loc[rsi_max_idx, 'close']:
                    score -= 2
                    reasons.append("RSI顶背离")
                    rsi_divergence_type = 'top'
            else:
                score -= 1
                reasons.append("RSI超买区域")
        
        # 5. MACD背离分析（避免与RSI背离和布林带位置冲突）
        bb_position = latest['bb_position']
        if len(prev_lookback) >= 5:
            macd_trend = prev_n['macd_hist'].mean() - prev_lookback['macd_hist'].iloc[:prev_periods].mean()
            price_trend = prev_n['close'].mean() - prev_lookback['close'].iloc[:prev_periods].mean()
            
            # 只有当RSI没有相反背离且布林带位置不矛盾时才添加MACD背离
            if macd_trend > 0 and price_trend < 0:
                # 避免RSI顶背离+MACD底背离的矛盾
                # 避免接近布林带上轨+MACD底背离的矛盾
                if rsi_divergence_type != 'top' and bb_position < 0.8:
                    score += 1
                    reasons.append("MACD底背离")
            elif macd_trend < 0 and price_trend > 0:
                # 避免RSI底背离+MACD顶背离的矛盾
                # 避免接近布林带下轨+MACD顶背离的矛盾
                if rsi_divergence_type != 'bottom' and bb_position > 0.2:
                    score -= 1
                    reasons.append("MACD顶背离")
        
        # 6. 均线系统分析
        if pd.notna(latest['ma_long']):
            if latest['close'] > latest['ma_long']:
                if latest['close'] < latest['ma_mid']:
                    score += 1
                    reasons.append("长期均线支撑有效")
            else:
                if latest['close'] > latest['ma_mid']:
                    score -= 1
                    reasons.append("长期均线压力明显")
        
        # 7. 布林带位置
        if latest['bb_position'] < 0.2:
            score += 1
            reasons.append("接近布林带下轨")
        elif latest['bb_position'] > 0.8:
            score -= 1
            reasons.append("接近布林带上轨")
        
        # 8. 动量分析
        if pd.notna(latest['momentum']):
            if latest['momentum'] < -0.1 and price_position > 0.3:
                score += 1
                reasons.append("动量超跌")
            elif latest['momentum'] > 0.15 and price_position < 0.7:
                score -= 1
                reasons.append("动量过热")
        
        # 9. 趋势确认（强化）- 避免逆势操作
        if trend['confirmed']:
            if trend['direction'] == 'uptrend' and score < 0:
                # 上升趋势中的卖出信号需要更强确认
                score += 2
                reasons.append("上升趋势保护(强)")
            elif trend['direction'] == 'downtrend' and score > 0:
                # 下降趋势中的买入信号需要更强确认
                score -= 2
                reasons.append("下降趋势警示(强)")
            elif trend['direction'] == 'uptrend' and score > 0:
                # 上升趋势中的买入信号加强
                score += 1
                reasons.append("顺势做多")
            elif trend['direction'] == 'downtrend' and score < 0:
                # 下降趋势中的卖出信号加强
                score -= 1
                reasons.append("顺势做空")
        
        # 判断信号（提高阈值，减少误判）
        if score >= 5:
            signal = 'strong_buy'
        elif score >= 3:
            signal = 'buy'
        elif score <= -5:
            signal = 'strong_sell'
        elif score <= -3:
            signal = 'sell'
        else:
            signal = 'neutral'
        
        return {
            'signal': signal,
            'score': score,
            'reasons': reasons,
            'rsi': latest['rsi'],
            'price_position': price_position,
            'bb_position': latest['bb_position'],
            'momentum': latest.get('momentum', 0),
            'weekly_mode': self.use_weekly,
            'trend': trend  # 新增趋势信息
        }
    
    def get_daily_confirmation(self) -> Dict:
        """获取日线确认信号（用于入场时机）"""
        if len(self.daily_df) < 20:
            return {'confirmed': False, 'reason': '数据不足'}
        
        df = self.daily_df.copy()
        latest = df.iloc[-1]
        prev_5 = df.iloc[-6:-1]
        
        # 计算日线RSI（Wilder平滑法）
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        df['rsi_daily'] = 100 - (100 / (1 + rs))
        
        daily_rsi = df['rsi_daily'].iloc[-1]
        
        # 日线确认条件
        confirmations = []
        
        # 短期反转信号
        if prev_5['pct_change'].sum() < -3 and latest['pct_change'] > 0:
            confirmations.append("短期下跌后反弹")
        
        if daily_rsi < 30:
            confirmations.append("日线RSI超卖")
        elif daily_rsi > 70:
            confirmations.append("日线RSI超买")
        
        return {
            'confirmed': len(confirmations) > 0,
            'daily_rsi': daily_rsi,
            'signals': confirmations
        }
