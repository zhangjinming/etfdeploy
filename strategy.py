"""综合策略系统（周线级别优化版）"""

from datetime import datetime
from typing import Dict, Optional
import pandas as pd
import numpy as np
from config import (
    ETF_POOL, BENCHMARK_ETF, MARKET_REGIME_PARAMS, 
    DESPAIR_CONFIRMATION, SIGNAL_THRESHOLDS, NO_DESPAIR_BUY_ASSETS,
    VOLATILITY_FILTER, SPECIAL_ASSETS, SPECIAL_ASSET_RULES,
    COMMODITY_ETF_PARAMS, DESPAIR_SHORT_LIMITS, SIGNAL_STRENGTH_PARAMS,
    TREND_FOLLOW_ASSETS, TREND_FILTER_PARAMS, BULL_MARKET_PARAMS
)
from data_fetcher import ETFDataFetcher
from analyzers import StrengthWeaknessAnalyzer, EmotionCycleAnalyzer, CapitalFlowAnalyzer, HedgeStrategy


class IntegratedETFStrategy:
    """
    综合策略系统
    整合所有策略，生成最终配置建议
    优化：采用周线级别分析，减少日线噪音
    新增：宏观市场环境过滤器
    新增：趋势过滤器，熊市减少抄底频率
    """
    
    def __init__(self, use_weekly: bool = True, simulate_date: Optional[str] = None):
        """
        初始化策略系统
        
        Args:
            use_weekly: 是否使用周线分析（默认True）
            simulate_date: 模拟日期，格式 'YYYY-MM-DD'，为None时使用当前日期
        """
        self.data_fetcher = ETFDataFetcher(simulate_date=simulate_date)
        self.use_weekly = use_weekly
        self.simulate_date = simulate_date
        self.capital_analyzer = None
        self.hedge_strategy = None
        self.market_regime = None  # 缓存市场环境
        self.market_volatility = None  # 缓存市场波动率
        self.trend_filter_cache = {}  # 【新增】趋势过滤器缓存
        self.despair_signal_count = 0  # 【新增】当周绝望期信号计数
        self.despair_cooldown = {}  # 【新增】ETF抄底冷却记录
    
    def set_simulate_date(self, date: str):
        """设置模拟日期"""
        self.simulate_date = date
        self.data_fetcher.set_simulate_date(date)
        self.market_regime = None  # 清除缓存
        self.market_volatility = None  # 清除缓存
        self.trend_filter_cache = {}  # 【新增】清除趋势过滤器缓存
        self.despair_signal_count = 0  # 【新增】重置信号计数
    
    def get_trend_filter(self, symbol: str, df: pd.DataFrame) -> Dict:
        """
        【新增】趋势过滤器 - 判断个股/ETF的中期趋势状态
        
        用于熊市环境下过滤抄底信号，减少逆势操作
        
        Args:
            symbol: ETF代码
            df: 日线数据
            
        Returns:
            趋势过滤结果，包含：
            - trend_state: 趋势状态 (strong_down/down/neutral/up/strong_up)
            - allow_despair_buy: 是否允许绝望期抄底
            - confidence_factor: 置信度调整因子
            - reasons: 判断原因
        """
        # 检查缓存
        if symbol in self.trend_filter_cache:
            return self.trend_filter_cache[symbol]
        
        result = {
            'trend_state': 'neutral',
            'allow_despair_buy': True,
            'confidence_factor': 1.0,
            'reasons': [],
            'ma_alignment': 'neutral',
            'price_position': 'neutral',
            'reversal_signal': False
        }
        
        if df.empty or len(df) < 100:
            self.trend_filter_cache[symbol] = result
            return result
        
        # 转换为周线
        weekly_df = self._convert_to_weekly(df) if self.use_weekly else df
        
        if len(weekly_df) < TREND_FILTER_PARAMS['long_ma'] + 5:
            self.trend_filter_cache[symbol] = result
            return result
        
        # 计算多周期均线
        short_period = TREND_FILTER_PARAMS['short_ma']
        mid_period = TREND_FILTER_PARAMS['mid_ma']
        long_period = TREND_FILTER_PARAMS['long_ma']
        
        weekly_df['ma_short'] = weekly_df['close'].rolling(short_period).mean()
        weekly_df['ma_mid'] = weekly_df['close'].rolling(mid_period).mean()
        weekly_df['ma_long'] = weekly_df['close'].rolling(long_period).mean()
        
        latest = weekly_df.iloc[-1]
        prev_week = weekly_df.iloc[-2] if len(weekly_df) >= 2 else latest
        
        price = latest['close']
        ma_short = latest['ma_short']
        ma_mid = latest['ma_mid']
        ma_long = latest['ma_long']
        
        # 1. 判断均线排列
        if ma_short < ma_mid < ma_long:
            result['ma_alignment'] = 'bearish'  # 空头排列
            result['reasons'].append('均线空头排列(短<中<长)')
        elif ma_short > ma_mid > ma_long:
            result['ma_alignment'] = 'bullish'  # 多头排列
            result['reasons'].append('均线多头排列(短>中>长)')
        else:
            result['ma_alignment'] = 'mixed'
            result['reasons'].append('均线交织')
        
        # 2. 判断价格相对均线位置
        below_all = price < ma_short and price < ma_mid and price < ma_long
        above_all = price > ma_short and price > ma_mid and price > ma_long
        
        if below_all:
            result['price_position'] = 'below_all'
            result['reasons'].append('价格在所有均线下方')
        elif above_all:
            result['price_position'] = 'above_all'
            result['reasons'].append('价格在所有均线上方')
        else:
            result['price_position'] = 'mixed'
        
        # 3. 计算长期均线斜率
        if len(weekly_df) >= long_period + 5:
            ma_long_prev = weekly_df['ma_long'].iloc[-5]
            ma_slope = (ma_long - ma_long_prev) / ma_long_prev * 100 if ma_long_prev > 0 else 0
        else:
            ma_slope = 0
        
        # 4. 综合判断趋势状态
        strong_down_conditions = TREND_FILTER_PARAMS['strong_downtrend_conditions']
        slope_threshold = strong_down_conditions['slope_threshold']
        
        # 强下跌趋势：空头排列 + 价格在所有均线下方 + 均线向下
        if (result['ma_alignment'] == 'bearish' and 
            result['price_position'] == 'below_all' and 
            ma_slope < slope_threshold):
            result['trend_state'] = 'strong_down'
            result['allow_despair_buy'] = False
            result['confidence_factor'] = 0.3
            result['reasons'].append(f'强下跌趋势(斜率{ma_slope:.2f}%)')
        
        # 下跌趋势：空头排列或价格在均线下方
        elif result['ma_alignment'] == 'bearish' or result['price_position'] == 'below_all':
            result['trend_state'] = 'down'
            result['confidence_factor'] = 0.5
            result['reasons'].append('下跌趋势')
        
        # 上涨趋势
        elif result['ma_alignment'] == 'bullish' and result['price_position'] == 'above_all':
            result['trend_state'] = 'strong_up'
            result['confidence_factor'] = 1.2
            result['reasons'].append('强上涨趋势')
        
        elif result['ma_alignment'] == 'bullish' or result['price_position'] == 'above_all':
            result['trend_state'] = 'up'
            result['confidence_factor'] = 1.1
            result['reasons'].append('上涨趋势')
        
        # 5. 检查反转信号
        reversal_config = TREND_FILTER_PARAMS['reversal_confirmation']
        
        # 检查是否形成更高的低点
        if len(weekly_df) >= 8:
            recent_lows = weekly_df['low'].iloc[-8:]
            min_idx = recent_lows.idxmin()
            min_pos = recent_lows.index.get_loc(min_idx)
            
            # 如果最低点不在最近2周，且最近价格高于最低点
            if min_pos < len(recent_lows) - 2:
                bounce_pct = (price / recent_lows.min() - 1) * 100
                if bounce_pct >= reversal_config['min_bounce_pct']:
                    result['reversal_signal'] = True
                    result['reasons'].append(f'反弹{bounce_pct:.1f}%，可能见底')
                    # 有反转信号时，适当提高置信度
                    if result['trend_state'] in ['down', 'strong_down']:
                        result['confidence_factor'] = min(result['confidence_factor'] + 0.2, 0.7)
        
        # 检查短期均线是否上穿中期均线（金叉）
        if len(weekly_df) >= 3:
            prev_ma_short = weekly_df['ma_short'].iloc[-2]
            prev_ma_mid = weekly_df['ma_mid'].iloc[-2]
            
            if prev_ma_short < prev_ma_mid and ma_short > ma_mid:
                result['reversal_signal'] = True
                result['reasons'].append('短期均线金叉')
                result['confidence_factor'] = min(result['confidence_factor'] + 0.15, 0.8)
        
        self.trend_filter_cache[symbol] = result
        return result
    
    def get_market_volatility(self) -> Dict:
        """
        计算市场整体波动率，用于识别系统性风险
        
        P0优化：增加基准回撤检测
        
        Returns:
            波动率信息，包含是否处于极端波动状态
        """
        if self.market_volatility is not None:
            return self.market_volatility
        
        df = self.data_fetcher.get_etf_history(BENCHMARK_ETF)
        if df.empty or len(df) < 60:
            self.market_volatility = {
                'level': 'unknown',
                'weekly_vol': 0,
                'is_extreme': False,
                'stop_despair_buy': False,
                'consecutive_drops': 0,
                'benchmark_drawdown': 0
            }
            return self.market_volatility
        
        # 转换为周线
        if self.use_weekly:
            df = self._convert_to_weekly(df)
        
        if len(df) < VOLATILITY_FILTER['vol_lookback_weeks'] + 2:
            self.market_volatility = {
                'level': 'unknown',
                'weekly_vol': 0,
                'is_extreme': False,
                'stop_despair_buy': False,
                'consecutive_drops': 0,
                'benchmark_drawdown': 0
            }
            return self.market_volatility
        
        # 计算近N周波动率
        lookback = VOLATILITY_FILTER['vol_lookback_weeks']
        recent_returns = df['pct_change'].iloc[-lookback:]
        weekly_vol = recent_returns.std()
        
        # 计算连续下跌周数
        consecutive_drops = 0
        for i in range(1, min(10, len(df))):
            if df['pct_change'].iloc[-i] < 0:
                consecutive_drops += 1
            else:
                break
        
        # P0优化：计算基准近期回撤
        benchmark_drawdown = 0
        if len(df) >= 8:
            recent_high = df['high'].iloc[-8:].max()
            current_close = df['close'].iloc[-1]
            benchmark_drawdown = (current_close / recent_high - 1) * 100
        
        # 判断波动率级别
        if weekly_vol > VOLATILITY_FILTER['extreme_vol_threshold']:
            level = 'extreme'
            is_extreme = True
        elif weekly_vol > VOLATILITY_FILTER['high_vol_threshold']:
            level = 'high'
            is_extreme = False
        else:
            level = 'normal'
            is_extreme = False
        
        # P0优化：判断是否停止绝望期抄底（增加回撤条件）
        benchmark_limit = VOLATILITY_FILTER.get('benchmark_drawdown_limit', -10)
        stop_despair_buy = (
            weekly_vol > VOLATILITY_FILTER['stop_despair_buy_vol'] or
            consecutive_drops >= VOLATILITY_FILTER['max_consecutive_drops'] or
            benchmark_drawdown < benchmark_limit  # P0新增：基准回撤过大
        )
        
        self.market_volatility = {
            'level': level,
            'weekly_vol': weekly_vol,
            'is_extreme': is_extreme,
            'stop_despair_buy': stop_despair_buy,
            'consecutive_drops': consecutive_drops,
            'benchmark_drawdown': benchmark_drawdown,
            'description': f"周波动率{weekly_vol:.2f}%，连续下跌{consecutive_drops}周，基准回撤{benchmark_drawdown:.1f}%"
        }
        
        return self.market_volatility
    
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
    
    def get_market_regime(self) -> Dict:
        """
        判断整体市场环境：牛市/熊市/震荡
        
        基于沪深300判断：
        - 价格在20周均线上方且均线向上 → 牛市
        - 价格在20周均线下方且均线向下 → 熊市
        - 其他 → 震荡
        
        Returns:
            市场环境信息
        """
        if self.market_regime is not None:
            return self.market_regime
        
        df = self.data_fetcher.get_etf_history(BENCHMARK_ETF)
        if df.empty or len(df) < 100:
            self.market_regime = {
                'regime': 'unknown',
                'description': '数据不足',
                'strength': 0,
                'ma_position': 0,
                'ma_slope': 0
            }
            return self.market_regime
        
        # 转换为周线
        if self.use_weekly:
            df = self._convert_to_weekly(df)
        
        if len(df) < MARKET_REGIME_PARAMS['ma_period'] + 5:
            self.market_regime = {
                'regime': 'unknown',
                'description': '数据不足',
                'strength': 0,
                'ma_position': 0,
                'ma_slope': 0
            }
            return self.market_regime
        
        # 计算均线
        ma_period = MARKET_REGIME_PARAMS['ma_period']
        df['ma'] = df['close'].rolling(ma_period).mean()
        
        latest = df.iloc[-1]
        prev = df.iloc[-5]  # 5周前
        
        # 计算均线斜率（5周变化率）
        ma_slope = (latest['ma'] - prev['ma']) / prev['ma'] * 100 if prev['ma'] > 0 else 0
        
        # 价格相对均线位置
        ma_position = (latest['close'] - latest['ma']) / latest['ma'] if latest['ma'] > 0 else 0
        
        # 判断市场环境
        bull_threshold = MARKET_REGIME_PARAMS['bull_threshold']
        bear_threshold = MARKET_REGIME_PARAMS['bear_threshold']
        slope_threshold = MARKET_REGIME_PARAMS['slope_threshold']
        
        if ma_position > bull_threshold and ma_slope > slope_threshold:
            regime = 'bull'
            description = '牛市环境：价格在均线上方且均线向上'
            strength = min(1.0, (ma_position + ma_slope / 10) / 0.1)
        elif ma_position < bear_threshold and ma_slope < -slope_threshold:
            regime = 'bear'
            description = '熊市环境：价格在均线下方且均线向下'
            strength = min(1.0, abs(ma_position + ma_slope / 10) / 0.1)
        else:
            regime = 'range'
            description = '震荡环境：趋势不明确'
            strength = 0.5
        
        self.market_regime = {
            'regime': regime,
            'description': description,
            'strength': strength,
            'ma_position': ma_position,
            'ma_slope': ma_slope,
            'benchmark_price': latest['close'],
            'benchmark_ma': latest['ma']
        }
        
        return self.market_regime
    
    def _validate_despair_buy(self, symbol: str, emotion: Dict, strength: Dict, df: pd.DataFrame) -> Dict:
        """
        验证绝望期买入信号
        
        P0优化：加严确认条件
        1. 趋势未确认向下（避免下跌中继抄底）
        2. 成交量萎缩到近期最低（恐慌盘出尽）
        3. 出现企稳信号（下影线/RSI底背离）
        4. 大盘环境非系统性熊市
        5. 禁止特定资产（原油等）绝望期抄底
        6. 极端波动率时停止抄底
        7. P0新增：连续4周确认机制（从2周增加）
        8. P0新增：要求跌幅收窄确认
        9. P0新增：基准回撤限制
        10. 【新增】趋势过滤器：熊市减少抄底频率
        11. 【新增v5】牛市适应性：降低抄底门槛
        
        Returns:
            验证结果
        """
        result = {
            'valid': True,
            'confidence': 1.0,
            'reasons': [],
            'warnings': [],
            'trend_filter': None  # 【新增】趋势过滤结果
        }
        
        # === P0优化：禁止特定资产绝望期抄底 ===
        if symbol in NO_DESPAIR_BUY_ASSETS:
            result['valid'] = False
            result['confidence'] = 0
            result['reasons'].append(f'{NO_DESPAIR_BUY_ASSETS[symbol]}不适合绝望期抄底，仅使用趋势跟踪')
            return result
        
        # 获取市场环境和波动率
        market = self.get_market_regime()
        volatility = self.get_market_volatility()
        
        # === 【新增v5】牛市适应性处理 ===
        is_bull_market = market['regime'] == 'bull'
        bull_params = BULL_MARKET_PARAMS if BULL_MARKET_PARAMS.get('enable', False) else {}
        
        # === P0优化：极端波动率或基准回撤过大时停止抄底 ===
        if volatility.get('stop_despair_buy'):
            # 【优化v5】牛市环境下放宽限制
            if not is_bull_market:
                result['valid'] = False
                result['confidence'] = 0
                result['reasons'].append(f"系统性风险：{volatility.get('description', '极端波动')}")
                return result
            else:
                result['warnings'].append(f"牛市环境，放宽波动率限制")
                result['confidence'] *= 0.8
        
        # P0新增：检查基准回撤
        benchmark_drawdown = volatility.get('benchmark_drawdown', 0)
        benchmark_limit = DESPAIR_CONFIRMATION.get('benchmark_max_drawdown', -10)
        
        # 【优化v5】牛市环境下放宽基准回撤限制
        if is_bull_market:
            benchmark_limit = benchmark_limit * 1.5  # 牛市放宽50%
        
        if benchmark_drawdown < benchmark_limit:
            result['valid'] = False
            result['confidence'] = 0
            result['reasons'].append(f"基准回撤过大({benchmark_drawdown:.1f}%)，暂停抄底")
            return result
        
        # === 【新增】趋势过滤器检查 ===
        trend_filter = self.get_trend_filter(symbol, df)
        result['trend_filter'] = trend_filter
        
        bear_restrictions = TREND_FILTER_PARAMS['bear_market_restrictions']
        
        # 【优化v5】牛市环境下的特殊处理
        if is_bull_market and bull_params:
            # 牛市中回调即是机会，降低绝望期抄底门槛
            result['confidence'] *= bull_params.get('confidence_boost', 1.3)
            
            # 牛市RSI阈值放宽
            rsi = emotion.get('rsi', 50)
            bull_rsi_threshold = bull_params.get('rsi_oversold_threshold', 40)
            if rsi < bull_rsi_threshold:
                result['confidence'] *= 1.2
                result['reasons'].append(f'牛市回调机会(RSI={rsi:.1f}<{bull_rsi_threshold})')
            
            # 牛市中趋势向下也可以考虑抄底（回调买入）
            if trend_filter['trend_state'] in ['down']:
                result['confidence'] *= 0.9  # 轻微惩罚
                result['warnings'].append('牛市回调，可考虑逢低买入')
            elif trend_filter['trend_state'] == 'strong_down':
                result['confidence'] *= 0.6  # 较大惩罚
                result['warnings'].append('牛市深度回调，谨慎抄底')
        
        # 熊市环境下应用趋势过滤
        elif market['regime'] == 'bear' and bear_restrictions['enable']:
            # 强下跌趋势：禁止抄底
            if not trend_filter['allow_despair_buy']:
                result['valid'] = False
                result['confidence'] = 0
                result['reasons'].append(f"趋势过滤：{', '.join(trend_filter['reasons'][:2])}")
                return result
            
            # 下跌趋势：大幅降低置信度
            if trend_filter['trend_state'] in ['down', 'strong_down']:
                result['confidence'] *= trend_filter['confidence_factor']
                result['warnings'].append(f"趋势向下，抄底风险高")
            
            # 熊市抄底需要更严格的RSI条件
            rsi = emotion.get('rsi', 50)
            min_rsi = bear_restrictions['min_rsi']
            if rsi > min_rsi:
                result['confidence'] *= 0.5
                result['warnings'].append(f"熊市抄底要求RSI<{min_rsi}，当前{rsi:.1f}")
            
            # 检查成交量是否枯竭
            if bear_restrictions['require_volume_dry'] and self.use_weekly and len(df) >= 30:
                weekly_df = self._convert_to_weekly(df)
                if len(weekly_df) >= 20:
                    recent_vol = weekly_df['volume'].iloc[-1]
                    vol_ma = weekly_df['volume'].iloc[-20:].mean()
                    vol_ratio = recent_vol / vol_ma if vol_ma > 0 else 1
                    
                    volume_dry_ratio = bear_restrictions['volume_dry_ratio']
                    if vol_ratio > volume_dry_ratio:
                        result['confidence'] *= 0.6
                        result['warnings'].append(f"成交量未枯竭({vol_ratio:.0%})，恐慌可能未结束")
                    else:
                        result['reasons'].append(f"成交量枯竭({vol_ratio:.0%})，恐慌盘出尽")
            
            # 检查是否有反转信号
            if not trend_filter['reversal_signal']:
                result['confidence'] *= 0.7
                result['warnings'].append("未出现反转信号，建议等待")
            else:
                result['reasons'].append("出现反转信号")
            
            # 【新增】熊市抄底信号数量限制
            max_signals = bear_restrictions['max_weekly_signals']
            if self.despair_signal_count >= max_signals:
                result['valid'] = False
                result['confidence'] = 0
                result['reasons'].append(f"本周抄底信号已达上限({max_signals}个)")
                return result
            
            # 【新增】冷却期检查
            cooldown_weeks = bear_restrictions['cooldown_weeks']
            if symbol in self.despair_cooldown:
                weeks_since = self.despair_cooldown[symbol]
                if weeks_since < cooldown_weeks:
                    result['valid'] = False
                    result['confidence'] = 0
                    result['reasons'].append(f"{symbol}抄底冷却中，还需{cooldown_weeks - weeks_since}周")
                    return result
        
        # 高波动率降低置信度
        if volatility.get('level') == 'high':
            # 【优化v5】牛市环境下减轻惩罚
            penalty = 0.7 if is_bull_market else 0.6
            result['confidence'] *= penalty
            result['warnings'].append(f"高波动环境({volatility.get('weekly_vol', 0):.1f}%)，抄底需谨慎")
        
        # 检查1：熊市环境下降低置信度
        if market['regime'] == 'bear':
            result['confidence'] *= 0.5
            result['warnings'].append('熊市环境，绝望期信号需谨慎')
            
            # 熊市中趋势向下确认的，不建议抄底
            trend = strength.get('trend', {})
            if trend.get('direction') == 'downtrend' and trend.get('confirmed'):
                result['valid'] = False
                result['reasons'].append('熊市+下降趋势确认，不宜抄底')
                return result
        
        # 检查2：成交量是否萎缩
        if self.use_weekly and len(df) >= 20:
            weekly_df = self._convert_to_weekly(df)
            if len(weekly_df) >= 20:
                recent_vol = weekly_df['volume'].iloc[-1]
                vol_ma = weekly_df['volume'].iloc[-20:].mean()
                vol_ratio = recent_vol / vol_ma if vol_ma > 0 else 1
                
                if vol_ratio < DESPAIR_CONFIRMATION['volume_shrink_ratio']:
                    result['confidence'] *= 1.2  # 成交量萎缩是好信号
                    result['reasons'].append(f'成交量萎缩至均量{vol_ratio:.0%}')
                elif vol_ratio > 1.5:
                    result['confidence'] *= 0.8
                    result['warnings'].append('成交量仍较大，可能未到恐慌尾声')
        
        # 检查3：RSI是否足够低
        rsi = emotion.get('rsi', 50)
        rsi_threshold = DESPAIR_CONFIRMATION['rsi_threshold']
        # 【优化v5】牛市环境下放宽RSI阈值
        if is_bull_market and bull_params:
            rsi_threshold = bull_params.get('rsi_oversold_threshold', rsi_threshold)
        
        if rsi < rsi_threshold:
            result['confidence'] *= 1.1
            result['reasons'].append(f'RSI={rsi:.1f}，深度超卖')
        elif rsi > 40:
            result['confidence'] *= 0.7
            result['warnings'].append(f'RSI={rsi:.1f}，超卖程度不足')
        
        # 检查4：是否有支撑信号（下影线）
        if len(df) >= 5:
            latest = df.iloc[-1]
            body = abs(latest['close'] - latest['open'])
            lower_shadow = min(latest['open'], latest['close']) - latest['low']
            if lower_shadow > body * 1.5:
                result['confidence'] *= 1.15
                result['reasons'].append('出现长下影线，底部支撑')
        
        # 【胜率优化】检查5：价格企稳确认（不创新低）
        if DESPAIR_CONFIRMATION.get('require_price_stabilization', True) and self.use_weekly and len(df) >= 30:
            weekly_df = self._convert_to_weekly(df)
            stabilization_weeks = DESPAIR_CONFIRMATION.get('stabilization_weeks', 3)
            if len(weekly_df) >= stabilization_weeks + 4:
                # 检查最近N周是否创新低
                recent_lows = weekly_df['low'].iloc[-stabilization_weeks:]
                prior_low = weekly_df['low'].iloc[-stabilization_weeks-4:-stabilization_weeks].min()
                current_low = recent_lows.min()
                
                if current_low < prior_low * 0.98:  # 创新低（允许2%误差）
                    result['confidence'] *= 0.5
                    result['warnings'].append('近期创新低，底部未确认')
                else:
                    result['confidence'] *= 1.15
                    result['reasons'].append('价格企稳，未创新低')
        
        # 【胜率优化】检查6：RSI底背离确认
        if DESPAIR_CONFIRMATION.get('require_rsi_divergence', False) and self.use_weekly and len(df) >= 60:
            weekly_df = self._convert_to_weekly(df)
            if len(weekly_df) >= 20:
                # 计算RSI
                delta = weekly_df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi_series = 100 - (100 / (1 + rs))
                
                if len(rsi_series) >= 10:
                    # 检查价格创新低但RSI未创新低（底背离）
                    price_recent = weekly_df['close'].iloc[-5:]
                    price_prior = weekly_df['close'].iloc[-10:-5]
                    rsi_recent = rsi_series.iloc[-5:]
                    rsi_prior = rsi_series.iloc[-10:-5]
                    
                    price_new_low = price_recent.min() < price_prior.min()
                    rsi_higher_low = rsi_recent.min() > rsi_prior.min()
                    
                    if price_new_low and rsi_higher_low:
                        result['confidence'] *= 1.3
                        result['reasons'].append('RSI底背离，反转信号强')
                    elif not price_new_low and rsi_recent.iloc[-1] > 30:
                        result['confidence'] *= 1.1
                        result['reasons'].append('RSI回升，动能改善')
        
        # 【优化v5】检查7：反弹确认（牛市适应性调整）
        if DESPAIR_CONFIRMATION.get('require_bounce_confirm', True) and self.use_weekly and len(df) >= 30:
            weekly_df = self._convert_to_weekly(df)
            if len(weekly_df) >= 10:
                # 计算从近期最低点的反弹幅度
                recent_low = weekly_df['low'].iloc[-10:].min()
                current_price = weekly_df['close'].iloc[-1]
                bounce_pct = (current_price / recent_low - 1) * 100
                
                # 【优化v5】牛市环境下降低反弹确认阈值
                min_bounce = DESPAIR_CONFIRMATION.get('min_bounce_from_low', 5.0)
                if is_bull_market and bull_params:
                    min_bounce = bull_params.get('min_bounce_threshold', min_bounce)
                
                if bounce_pct >= min_bounce:
                    result['confidence'] *= 1.3
                    result['reasons'].append(f'从低点反弹{bounce_pct:.1f}%，企稳信号')
                elif bounce_pct < 2:
                    # 【优化v5】牛市环境下减轻惩罚
                    penalty = 0.5 if is_bull_market else 0.3
                    result['confidence'] *= penalty
                    result['warnings'].append('反弹幅度不足，不宜抄底')
        
        # 【优化v5】检查8：更高低点确认
        if DESPAIR_CONFIRMATION.get('require_higher_low', True) and self.use_weekly and len(df) >= 40:
            weekly_df = self._convert_to_weekly(df)
            if len(weekly_df) >= 12:
                # 检查是否形成更高的低点
                recent_low = weekly_df['low'].iloc[-4:].min()
                prior_low = weekly_df['low'].iloc[-8:-4].min()
                
                higher_low_margin = DESPAIR_CONFIRMATION.get('higher_low_margin', 1.0) / 100
                if recent_low > prior_low * (1 + higher_low_margin):  # 最近低点高于之前低点
                    result['confidence'] *= 1.35
                    result['reasons'].append('形成更高低点，底部确认')
                elif recent_low < prior_low * 0.98:  # 创新低（收紧到2%）
                    # 【优化v5】牛市环境下减轻惩罚
                    penalty = 0.5 if is_bull_market else 0.3
                    result['confidence'] *= penalty
                    result['warnings'].append('未形成更高低点，底部未确认')
        
        # 【优化v5】检查9：周线阳线确认
        if DESPAIR_CONFIRMATION.get('require_weekly_positive', True) and self.use_weekly and len(df) >= 30:
            weekly_df = self._convert_to_weekly(df)
            if len(weekly_df) >= 4:
                # 检查近4周收阳周数
                min_positive_count = DESPAIR_CONFIRMATION.get('min_weekly_positive_count', 2)
                recent_4_weeks = weekly_df.iloc[-4:]
                positive_weeks = sum(1 for i in range(len(recent_4_weeks)) 
                                    if recent_4_weeks['close'].iloc[i] > recent_4_weeks['open'].iloc[i])
                
                if positive_weeks >= min_positive_count:
                    result['confidence'] *= 1.25
                    result['reasons'].append(f'近4周有{positive_weeks}周收阳，企稳信号')
                elif positive_weeks <= 1:
                    # 【优化v5】牛市环境下减轻惩罚
                    penalty = 0.5 if is_bull_market else 0.3
                    result['confidence'] *= penalty
                    result['warnings'].append('近4周收阳不足，下跌动能强')
                else:
                    result['confidence'] *= 0.7
                    result['warnings'].append(f'近4周仅{positive_weeks}周收阳，企稳不足')
        
        # 【优化v5】检查10：放量阳线确认
        if DESPAIR_CONFIRMATION.get('require_volume_confirm', True) and self.use_weekly and len(df) >= 30:
            weekly_df = self._convert_to_weekly(df)
            if len(weekly_df) >= 5:
                # 检查最近一周是否放量收阳
                latest_vol = weekly_df['volume'].iloc[-1]
                vol_ma = weekly_df['volume'].iloc[-5:-1].mean()
                vol_ratio = latest_vol / vol_ma if vol_ma > 0 else 1
                
                is_positive = weekly_df['close'].iloc[-1] > weekly_df['open'].iloc[-1]
                volume_surge = DESPAIR_CONFIRMATION.get('volume_surge_ratio', 1.15)
                
                if is_positive and vol_ratio >= volume_surge:
                    result['confidence'] *= 1.3  # 放量阳线，强企稳信号
                    result['reasons'].append(f'放量阳线(量比{vol_ratio:.1f}x)，资金入场')
                elif not is_positive:
                    result['confidence'] *= 0.7
                    result['warnings'].append('最近一周收阴，企稳不足')
        
        # === 【优化v5】连续N周确认机制 ===
        if self.use_weekly and len(df) >= 30:
            weekly_df = self._convert_to_weekly(df)
            confirm_weeks = DESPAIR_CONFIRMATION.get('consecutive_weeks_confirm', 4)
            if len(weekly_df) >= confirm_weeks + 1:
                # 检查跌幅收窄确认
                if DESPAIR_CONFIRMATION.get('require_decline_slowdown', True):
                    latest_change = (weekly_df['close'].iloc[-1] / weekly_df['close'].iloc[-2] - 1) * 100
                    prev_change = (weekly_df['close'].iloc[-2] / weekly_df['close'].iloc[-3] - 1) * 100
                    
                    slowdown_ratio = DESPAIR_CONFIRMATION.get('decline_slowdown_ratio', 0.40)
                    
                    if prev_change < 0:  # 前一周是下跌的
                        if latest_change >= 0:
                            # 已经止跌转涨，好信号
                            result['confidence'] *= 1.35
                            result['reasons'].append('止跌转涨，企稳信号明确')
                        elif latest_change > prev_change * slowdown_ratio:
                            # 跌幅收窄
                            result['confidence'] *= 1.15
                            result['reasons'].append(f'跌幅收窄({prev_change:.1f}%→{latest_change:.1f}%)')
                        else:
                            # 跌幅未收窄，继续下跌
                            # 【优化v5】牛市环境下减轻惩罚
                            penalty = 0.5 if is_bull_market else 0.3
                            result['confidence'] *= penalty
                            result['warnings'].append(f'跌幅未收窄({prev_change:.1f}%→{latest_change:.1f}%)，建议等待')
                    else:
                        # 前一周已经是上涨，检查是否持续企稳
                        if latest_change >= 0:
                            result['confidence'] *= 1.15
                            result['reasons'].append('连续企稳，可考虑建仓')
                
                # 检查最近N周是否持续在低位震荡（未继续大幅下跌）
                recent_changes = [
                    (weekly_df['close'].iloc[-i] / weekly_df['close'].iloc[-i-1] - 1) * 100
                    for i in range(1, min(confirm_weeks + 1, len(weekly_df)))
                ]
                # 【优化v5】如果最近几周有单周跌幅超过4%，说明还在恐慌中
                if any(c < -4 for c in recent_changes[:2]):  # 最近2周
                    # 【优化v5】牛市环境下减轻惩罚
                    penalty = 0.5 if is_bull_market else 0.3
                    result['confidence'] *= penalty
                    result['warnings'].append('近期仍有大幅下跌，恐慌未结束')
        
        # 【优化v5】最终判断（牛市环境下降低置信度门槛）
        confidence_threshold = 0.65 if is_bull_market else 0.75
        if result['confidence'] < confidence_threshold:
            result['valid'] = False
            result['reasons'].append('综合置信度过低')
        
        # 【新增】如果验证通过，更新信号计数
        if result['valid'] and market['regime'] == 'bear':
            self.despair_signal_count += 1
            self.despair_cooldown[symbol] = 0  # 重置冷却
        
        return result
    
    def run_full_analysis(self) -> Dict:
        """运行完整分析"""
        mode = "周线" if self.use_weekly else "日线"
        date_display = self.simulate_date if self.simulate_date else datetime.now().strftime('%Y-%m-%d')
        
        print("=" * 60)
        print(f"ETF配置系统（{mode}级别分析）- 分析日期: {date_display}")
        print("=" * 60)
        
        # 0. 首先获取市场环境和波动率
        market_regime = self.get_market_regime()
        market_volatility = self.get_market_volatility()
        
        # 【新增】重置趋势过滤器状态
        self.trend_filter_cache = {}
        self.despair_signal_count = 0
        
        results = {
            'timestamp': self.simulate_date if self.simulate_date else datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'analysis_mode': 'weekly' if self.use_weekly else 'daily',
            'market_regime': market_regime,
            'market_volatility': market_volatility,
            'etf_analysis': {},
            'style_analysis': None,
            'market_health': None,
            'portfolio_suggestion': None
        }
        
        # 显示市场环境
        regime_emoji = {'bull': '🐂', 'bear': '🐻', 'range': '📊', 'unknown': '❓'}
        vol_emoji = {'extreme': '🔥', 'high': '⚠️', 'normal': '✅', 'unknown': '❓'}
        
        print(f"\n【零、市场环境判断】")
        print("-" * 50)
        print(f"  {regime_emoji.get(market_regime['regime'], '❓')} {market_regime['description']}")
        if market_regime['regime'] != 'unknown':
            print(f"  均线位置: {market_regime['ma_position']:.2%} | 均线斜率: {market_regime['ma_slope']:.2f}%")
            if market_regime['regime'] == 'bear':
                print(f"  ⚠️ 熊市环境下，绝望期信号需要更多确认，避免抄底陷阱")
                print(f"  📉 趋势过滤器已启用：每周最多{TREND_FILTER_PARAMS['bear_market_restrictions']['max_weekly_signals']}个抄底信号")
        
        # 显示波动率
        print(f"\n  {vol_emoji.get(market_volatility['level'], '❓')} 波动率: {market_volatility.get('description', '未知')}")
        if market_volatility.get('stop_despair_buy'):
            print(f"  🚫 系统性风险警告：暂停所有绝望期抄底信号！")
        
        # 1. 分析各ETF
        print("\n【一、强弱分析】")
        print("-" * 50)
        
        for symbol, name in ETF_POOL.items():
            df = self.data_fetcher.get_etf_history(symbol)
            if df.empty:
                print(f"  {name}({symbol}): 数据获取失败")
                continue
            
            # 周线级别强弱分析（传入symbol用于识别特殊资产）
            strength_analyzer = StrengthWeaknessAnalyzer(df, use_weekly=self.use_weekly, symbol=symbol)
            strength_result = strength_analyzer.analyze_strength()
            
            # 周线级别情绪分析（传入市场环境）
            emotion_analyzer = EmotionCycleAnalyzer(df, use_weekly=self.use_weekly)
            emotion_result = emotion_analyzer.get_emotion_phase(market_regime=market_regime)
            emotion_trend = emotion_analyzer.get_emotion_trend()
            
            # 绝望期买入验证
            despair_validation = None
            if emotion_result['phase'] == 'despair':
                despair_validation = self._validate_despair_buy(symbol, emotion_result, strength_result, df)
                if not despair_validation['valid']:
                    # 绝望期信号被否决，调整情绪结果
                    emotion_result['phase_adjusted'] = True
                    emotion_result['adjustment_reason'] = despair_validation['reasons']
            
            # 计算综合得分（复用HedgeStrategy的逻辑，加入市场环境因子）
            # 将symbol添加到strength_result中，用于识别特殊资产
            strength_result['symbol'] = symbol
            composite_score = self._calculate_composite_score(
                strength_result, emotion_result, 
                market_regime=market_regime,
                despair_validation=despair_validation
            )
            
            results['etf_analysis'][symbol] = {
                'name': name,
                'strength': strength_result,
                'emotion': emotion_result,
                'emotion_trend': emotion_trend,
                'composite_score': composite_score,
                'despair_validation': despair_validation,
                'latest_price': df.iloc[-1]['close'],
                'pct_change_1m': (df.iloc[-1]['close'] / df.iloc[-30]['close'] - 1) * 100 if len(df) >= 30 else 0
            }
            
            signal_emoji = {
                'strong_buy': '🟢🟢', 'buy': '🟢', 'neutral': '⚪',
                'sell': '🔴', 'strong_sell': '🔴🔴'
            }
            phase_cn = {'despair': '绝望期', 'hesitation': '犹豫期', 'frenzy': '疯狂期', 'unknown': '未知'}
            
            print(f"  {name}({symbol}):")
            print(f"    强弱信号: {signal_emoji.get(strength_result['signal'], '⚪')} {strength_result['signal']} (得分:{strength_result['score']})")
            
            # 显示情绪阶段（如果被调整则标注）
            phase_display = phase_cn.get(emotion_result['phase'], '未知')
            if emotion_result.get('phase_adjusted'):
                phase_display += " ⚠️(需确认)"
            print(f"    情绪阶段: {phase_display} (强度:{emotion_result.get('phase_strength', 0):.0%})")
            print(f"    RSI: {strength_result.get('rsi', 0):.1f} | 情绪指数: {emotion_result.get('emotion_index', 0):.2f}")
            
            # 【新增】显示趋势过滤信息（仅在熊市且有绝望期验证时）
            if despair_validation and despair_validation.get('trend_filter'):
                tf = despair_validation['trend_filter']
                trend_state_cn = {
                    'strong_down': '📉强下跌', 'down': '📉下跌', 
                    'neutral': '➖震荡', 'up': '📈上涨', 'strong_up': '📈强上涨'
                }
                print(f"    趋势状态: {trend_state_cn.get(tf['trend_state'], '未知')} | 置信因子: {tf['confidence_factor']:.1f}")
                if tf['reversal_signal']:
                    print(f"    🔄 检测到反转信号")
            
            if despair_validation and despair_validation['warnings']:
                print(f"    ⚠️ 警告: {', '.join(despair_validation['warnings'][:2])}")
            
            if emotion_trend.get('trend') != 'unknown':
                print(f"    情绪趋势: {emotion_trend.get('description', '')}")
            if strength_result.get('reasons'):
                print(f"    原因: {', '.join(strength_result['reasons'][:3])}")
        
        # 2. 资金面分析
        print("\n【二、资金面分析】")
        print("-" * 50)
        
        self.capital_analyzer = CapitalFlowAnalyzer(self.data_fetcher, use_weekly=self.use_weekly)
        style_result = self.capital_analyzer.analyze_style_rotation()
        results['style_analysis'] = style_result
        
        if 'error' not in style_result:
            style_cn = {
                'large_cap_dominant': '大盘股占优',
                'small_cap_dominant': '小盘股占优',
                'balanced': '风格均衡'
            }
            trend_cn = {
                'rotating_to_large': '→大盘',
                'rotating_to_small': '→小盘',
                'stable': '稳定'
            }
            print(f"  当前风格: {style_cn.get(style_result['style'], '未知')} ({trend_cn.get(style_result.get('style_trend', 'stable'), '')})")
            print(f"  大盘股收益: {style_result['large_cap_return']:.2f}% | 小盘股收益: {style_result['small_cap_return']:.2f}%")
            print(f"  风格差异: {style_result['style_diff']:.2f}% | 资金效率比: {style_result.get('efficiency_ratio', 0):.1f}x")
            print(f"  建议: {style_result['suggestion']}")
            if style_result.get('trend_suggestion'):
                print(f"  趋势: {style_result['trend_suggestion']}")
        
        # 3. 市场健康度
        market_health = self.capital_analyzer.get_market_health()
        results['market_health'] = market_health
        
        health_emoji = {'excellent': '🟢', 'good': '🟡', 'fair': '🟠', 'poor': '🔴', 'unknown': '⚪'}
        health_cn = {'excellent': '优秀', 'good': '良好', 'fair': '一般', 'poor': '较差', 'unknown': '未知'}
        
        print(f"\n  市场健康度: {health_emoji.get(market_health['health'], '⚪')} {health_cn.get(market_health['health'], '未知')} ({market_health['score']}/{market_health['max_score']})")
        if market_health.get('factors'):
            print(f"  因素: {', '.join(market_health['factors'][:3])}")
        
        # 4. 生成对冲组合
        print("\n【三、对冲策略】")
        print("-" * 50)
        
        self.hedge_strategy = HedgeStrategy(self.data_fetcher, use_weekly=self.use_weekly, market_regime=market_regime)
        portfolio = self.hedge_strategy.generate_hedge_portfolio()
        results['portfolio_suggestion'] = portfolio
        
        print(f"  现金比例: {portfolio['cash_ratio']*100:.0f}%（留有余地）")
        print(f"  多头敞口: {portfolio.get('net_exposure', 0)*100:.0f}%")
        
        if portfolio['long_positions']:
            print("\n  多头配置:")
            for pos in portfolio['long_positions']:
                print(f"    - {pos['name']}({pos['symbol']}): {pos['weight']*100:.0f}% | {pos['reason']}")
        else:
            print("\n  多头配置: 无强势标的")
        
        if portfolio['hedge_positions']:
            print("\n  风险提示（建议回避）:")
            for pos in portfolio['hedge_positions']:
                print(f"    - {pos['name']}({pos['symbol']}): {pos['reason']}")
        
        # 5. 综合建议
        print("\n【四、综合配置建议】")
        print("-" * 50)
        self._generate_final_suggestion(results)
        
        return results
    
    def _generate_final_suggestion(self, results: Dict):
        """生成最终建议"""
        buy_signals = []
        sell_signals = []
        despair_etfs = []
        frenzy_etfs = []
        improving_etfs = []
        
        for symbol, analysis in results['etf_analysis'].items():
            if analysis['strength']['signal'] in ['strong_buy', 'buy']:
                buy_signals.append(analysis['name'])
            elif analysis['strength']['signal'] in ['strong_sell', 'sell']:
                sell_signals.append(analysis['name'])
            
            if analysis['emotion']['phase'] == 'despair':
                despair_etfs.append(analysis['name'])
            elif analysis['emotion']['phase'] == 'frenzy':
                frenzy_etfs.append(analysis['name'])
            
            # 情绪改善中的
            if analysis.get('emotion_trend', {}).get('trend') in ['improving', 'improving_fast']:
                improving_etfs.append(analysis['name'])
        
        print("\n  📊 市场状态总结:")
        buy_display = ', '.join(buy_signals) if buy_signals else '无'
        sell_display = ', '.join(sell_signals) if sell_signals else '无'
        print(f"    - 超跌反弹机会(买入信号): {len(buy_signals)}个 {buy_display}")
        print(f"    - 超涨回调风险(卖出信号): {len(sell_signals)}个 {sell_display}")
        
        if despair_etfs:
            print(f"    - 绝望期(可建仓): {', '.join(despair_etfs[:4])}")
        if frenzy_etfs:
            print(f"    - 疯狂期(注意风险): {', '.join(frenzy_etfs[:4])}")
        if improving_etfs:
            print(f"    - 情绪改善中: {', '.join(improving_etfs[:4])}")
        
        # 风格建议
        style = results.get('style_analysis', {})
        if style and 'allocation' in style:
            print(f"\n  📈 风格配置建议:")
            print(f"    - 大盘股: {style['allocation']['large_cap']*100:.0f}%")
            print(f"    - 小盘股: {style['allocation']['small_cap']*100:.0f}%")
        
        # 市场健康度建议
        health = results.get('market_health', {})
        if health.get('suggestion'):
            print(f"\n  🏥 市场健康建议: {health['suggestion']}")
        
        # 核心理念
        print("\n  💡 核心理念提醒:")
        print("    1. 该涨不涨看跌，该跌不跌看涨")
        print("    2. 行情在绝望中产生，犹豫中发展，疯狂中消亡")
        print("    3. 恶炒消耗资金，价值白马领涨才有持续性")
        print("    4. 留有余地，仓位不可用足")
        print("    5. 策略比预测更重要，以变应变")
    
    def _calculate_composite_score(self, strength: Dict, emotion: Dict, 
                                     market_regime: Dict = None,
                                     despair_validation: Dict = None) -> float:
        """
        计算综合评分（优化版）
        
        综合考虑：
        - 强弱信号得分（权重40%）
        - 情绪阶段（权重30%）
        - 情绪指数（权重15%）
        - 市场环境调整（权重15%）
        
        优化：
        - 市场环境过滤
        - 绝望期验证结果
        - 【优化】趋势性资产使用TREND_FOLLOW_ASSETS配置
        - 【优化】绝望期只做多不做空
        - 信号强度分级
        """
        # 强弱得分（-5到5映射到-1到1）
        strength_score = strength['score'] / 5
        
        # 获取趋势信息
        trend_info = strength.get('trend', {})
        trend_direction = trend_info.get('direction', 'unknown')
        trend_confirmed = trend_info.get('confirmed', False)
        
        # 获取symbol
        symbol = strength.get('symbol', '')
        
        # 获取情绪阶段
        phase = emotion['phase']
        is_despair = phase == 'despair'
        
        # === 【优化】趋势性资产使用专属配置 ===
        if symbol in TREND_FOLLOW_ASSETS:
            trend_config = TREND_FOLLOW_ASSETS[symbol]
            trend_weight = trend_config.get('trend_weight', 0.7)
            emotion_weight = trend_config.get('emotion_weight', 0.3)
            no_despair_short = trend_config.get('no_despair_short', True)
            
            trend_bonus = 0
            if trend_direction == 'uptrend':
                trend_bonus = 0.6 if trend_confirmed else 0.3
            elif trend_direction == 'downtrend':
                # 【优化】绝望期不给负分（不做空）
                if is_despair and no_despair_short:
                    trend_bonus = 0  # 绝望期下跌趋势不做空，给0分（观望）
                else:
                    trend_bonus = -0.6 if trend_confirmed else -0.3
            
            # 简化得分：强弱信号 + 趋势
            composite = strength_score * emotion_weight + trend_bonus * trend_weight
            
            # 【优化】绝望期限制负分（只做多不做空）
            if is_despair and no_despair_short and composite < 0:
                composite = 0  # 绝望期不产生负分
            
            # 市场环境调整
            if market_regime:
                regime = market_regime.get('regime', 'unknown')
                if regime == 'bear' and composite > 0:
                    composite *= 0.7
                elif regime == 'bull' and composite < 0:
                    composite *= 0.8
            
            return composite
        
        # === 商品类ETF特殊处理（非TREND_FOLLOW_ASSETS中的商品） ===
        commodity_symbols = COMMODITY_ETF_PARAMS.get('symbols', [])
        if symbol in commodity_symbols or symbol in NO_DESPAIR_BUY_ASSETS:
            # 商品类资产：纯趋势跟踪，不使用情绪周期
            trend_weight = COMMODITY_ETF_PARAMS.get('trend_weight', 0.7)
            emotion_weight = COMMODITY_ETF_PARAMS.get('emotion_weight', 0.3)
            
            trend_bonus = 0
            if trend_direction == 'uptrend':
                trend_bonus = 0.6 if trend_confirmed else 0.3
            elif trend_direction == 'downtrend':
                # 【优化】绝望期不做空
                if is_despair and DESPAIR_SHORT_LIMITS.get('convert_avoid_to_neutral', True):
                    trend_bonus = 0
                else:
                    trend_bonus = -0.6 if trend_confirmed else -0.3
            
            # 简化得分：强弱信号 + 趋势（商品更依赖趋势）
            composite = strength_score * (1 - trend_weight) + trend_bonus * trend_weight
            
            # 【优化】绝望期限制负分
            if is_despair and composite < 0:
                composite = 0
            
            # 市场环境调整
            if market_regime:
                regime = market_regime.get('regime', 'unknown')
                if regime == 'bear' and composite > 0:
                    composite *= 0.7
                elif regime == 'bull' and composite < 0:
                    composite *= 0.8
            
            return composite
        
        # === 普通资产处理 ===
        # 情绪阶段得分
        phase_strength = emotion.get('phase_strength', 0.5)
        
        phase_scores = {
            'despair': 1.0,      # 绝望期买入
            'hesitation': 0.0,  # 犹豫期观望
            'frenzy': -1.0,     # 疯狂期卖出
            'unknown': 0.0
        }
        emotion_phase_score = phase_scores.get(phase, 0)
        
        # === 【优化】绝望期只做多不做空 ===
        if is_despair and DESPAIR_SHORT_LIMITS.get('convert_avoid_to_neutral', True):
            # 绝望期不应该产生负的情绪阶段得分
            if emotion_phase_score < 0:
                emotion_phase_score = 0
            # 强弱信号如果是负的，也限制为0（不做空）
            if strength_score < 0:
                strength_score = 0
        
        # 如果绝望期验证失败，大幅降低情绪阶段得分
        if despair_validation and not despair_validation['valid']:
            emotion_phase_score = 0.2  # 降低到接近犹豫期
        elif despair_validation:
            # 根据置信度调整
            emotion_phase_score *= despair_validation['confidence']
        
        # 情绪指数（-1到1）
        emotion_index = emotion.get('emotion_index', 0)
        # 反转：低情绪指数反而是买入机会
        emotion_index_score = -emotion_index
        
        # 市场环境调整
        regime_adjustment = 0
        if market_regime:
            regime = market_regime.get('regime', 'unknown')
            if regime == 'bear':
                # 熊市环境：降低买入信号，增强卖出信号
                if emotion_phase_score > 0:
                    regime_adjustment = -0.3  # 降低绝望期买入得分
                elif emotion_phase_score < 0:
                    regime_adjustment = -0.1  # 增强疯狂期卖出
            elif regime == 'bull':
                # 牛市环境：增强买入信号，降低卖出信号
                if emotion_phase_score > 0:
                    regime_adjustment = 0.1  # 增强绝望期买入
                elif emotion_phase_score < 0:
                    regime_adjustment = 0.2  # 降低疯狂期卖出惩罚
        
        # 深度绝望期加成：RSI极低 + 情绪指数极低 + 绝望期强度高
        despair_bonus = 0
        rsi = emotion.get('rsi', 50)
        if phase == 'despair':
            # 只有在非熊市或验证通过时才给予加成
            if (market_regime is None or market_regime.get('regime') != 'bear') or \
               (despair_validation and despair_validation['valid'] and despair_validation['confidence'] > 0.7):
                # RSI越低加成越多
                if rsi < 25:
                    despair_bonus += 0.3
                elif rsi < 35:
                    despair_bonus += 0.15
                
                # 情绪指数越低加成越多
                if emotion_index < -0.5:
                    despair_bonus += 0.2
                elif emotion_index < -0.3:
                    despair_bonus += 0.1
                
                # 绝望期强度加成
                if phase_strength > 0.7:
                    despair_bonus += 0.15
        
        # === 信号强度分级 ===
        signal_score = abs(strength['score'])
        strong_threshold = SIGNAL_STRENGTH_PARAMS.get('strong_signal_score', 4)
        if signal_score >= strong_threshold:
            # 强信号：增加权重
            strength_weight = SIGNAL_STRENGTH_PARAMS.get('strong_signal_weight', 1.5)
        else:
            # 弱信号：降低权重
            strength_weight = SIGNAL_STRENGTH_PARAMS.get('weak_signal_weight', 0.8)
        
        # 综合评分（应用信号强度权重）
        composite = (
            strength_score * 0.40 * strength_weight +
            emotion_phase_score * 0.30 +
            emotion_index_score * 0.15 +
            regime_adjustment * 0.15 +
            despair_bonus * 0.10 / 0.10  # 归一化后的加成
        )
        
        # 【优化】绝望期限制负分（只做多不做空）
        if is_despair and DESPAIR_SHORT_LIMITS.get('convert_avoid_to_neutral', True):
            if composite < 0:
                composite = 0
        
        # 确保深度绝望期的ETF能获得足够高的分数（但需要验证通过）
        if phase == 'despair' and despair_bonus > 0.3:
            if despair_validation is None or despair_validation['valid']:
                composite = max(composite, 0.4)  # 保底分数
        
        return composite
