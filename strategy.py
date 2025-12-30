"""综合策略系统（周线级别优化版）"""

from datetime import datetime
from typing import Dict, Optional
import pandas as pd
import numpy as np
from config import (
    ETF_POOL, BENCHMARK_ETF, MARKET_REGIME_PARAMS, 
    DESPAIR_CONFIRMATION, SIGNAL_THRESHOLDS, NO_DESPAIR_BUY_ASSETS,
    VOLATILITY_FILTER, SPECIAL_ASSETS, SPECIAL_ASSET_RULES
)
from data_fetcher import ETFDataFetcher
from analyzers import StrengthWeaknessAnalyzer, EmotionCycleAnalyzer, CapitalFlowAnalyzer, HedgeStrategy


class IntegratedETFStrategy:
    """
    综合策略系统
    整合所有策略，生成最终配置建议
    优化：采用周线级别分析，减少日线噪音
    新增：宏观市场环境过滤器
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
    
    def set_simulate_date(self, date: str):
        """设置模拟日期"""
        self.simulate_date = date
        self.data_fetcher.set_simulate_date(date)
        self.market_regime = None  # 清除缓存
        self.market_volatility = None  # 清除缓存
    
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
        
        Returns:
            验证结果
        """
        result = {
            'valid': True,
            'confidence': 1.0,
            'reasons': [],
            'warnings': []
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
        
        # === P0优化：极端波动率或基准回撤过大时停止抄底 ===
        if volatility.get('stop_despair_buy'):
            result['valid'] = False
            result['confidence'] = 0
            result['reasons'].append(f"系统性风险：{volatility.get('description', '极端波动')}")
            return result
        
        # P0新增：检查基准回撤
        benchmark_drawdown = volatility.get('benchmark_drawdown', 0)
        benchmark_limit = DESPAIR_CONFIRMATION.get('benchmark_max_drawdown', -10)
        if benchmark_drawdown < benchmark_limit:
            result['valid'] = False
            result['confidence'] = 0
            result['reasons'].append(f"基准回撤过大({benchmark_drawdown:.1f}%)，暂停抄底")
            return result
        
        # 高波动率降低置信度
        if volatility.get('level') == 'high':
            result['confidence'] *= 0.6
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
        
        # 检查3：RSI是否足够低（P0：阈值从30降到25）
        rsi = emotion.get('rsi', 50)
        if rsi < DESPAIR_CONFIRMATION['rsi_threshold']:
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
        
        # === P0优化：连续N周确认机制（从2周增加到4周） ===
        if self.use_weekly and len(df) >= 30:
            weekly_df = self._convert_to_weekly(df)
            confirm_weeks = DESPAIR_CONFIRMATION.get('consecutive_weeks_confirm', 4)  # P0：改为4周
            if len(weekly_df) >= confirm_weeks + 1:
                # P0新增：检查跌幅收窄确认
                if DESPAIR_CONFIRMATION.get('require_decline_slowdown', True):
                    latest_change = (weekly_df['close'].iloc[-1] / weekly_df['close'].iloc[-2] - 1) * 100
                    prev_change = (weekly_df['close'].iloc[-2] / weekly_df['close'].iloc[-3] - 1) * 100
                    
                    # 跌幅收窄条件：最近一周跌幅 < 前一周跌幅 * 收窄比例
                    slowdown_ratio = DESPAIR_CONFIRMATION.get('decline_slowdown_ratio', 0.5)
                    
                    if prev_change < 0:  # 前一周是下跌的
                        if latest_change >= 0:
                            # 已经止跌转涨，好信号
                            result['confidence'] *= 1.2
                            result['reasons'].append('止跌转涨，企稳信号明确')
                        elif latest_change > prev_change * slowdown_ratio:
                            # 跌幅收窄
                            result['confidence'] *= 1.1
                            result['reasons'].append(f'跌幅收窄({prev_change:.1f}%→{latest_change:.1f}%)')
                        else:
                            # 跌幅未收窄，继续下跌
                            result['confidence'] *= 0.5
                            result['warnings'].append(f'跌幅未收窄({prev_change:.1f}%→{latest_change:.1f}%)，建议等待')
                    else:
                        # 前一周已经是上涨，检查是否持续企稳
                        if latest_change >= 0:
                            result['reasons'].append('连续企稳，可考虑建仓')
                
                # 检查最近N周是否持续在低位震荡（未继续大幅下跌）
                recent_changes = [
                    (weekly_df['close'].iloc[-i] / weekly_df['close'].iloc[-i-1] - 1) * 100
                    for i in range(1, min(confirm_weeks + 1, len(weekly_df)))
                ]
                # 如果最近几周有单周跌幅超过5%，说明还在恐慌中
                if any(c < -5 for c in recent_changes[:2]):  # 最近2周
                    result['confidence'] *= 0.6
                    result['warnings'].append('近期仍有大幅下跌，恐慌未结束')
        
        # 最终判断
        if result['confidence'] < 0.5:
            result['valid'] = False
            result['reasons'].append('综合置信度过低')
        
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
        
        新增：
        - 市场环境过滤
        - 绝望期验证结果
        """
        # 强弱得分（-5到5映射到-1到1）
        strength_score = strength['score'] / 5
        
        # 情绪阶段得分
        phase = emotion['phase']
        phase_strength = emotion.get('phase_strength', 0.5)
        
        phase_scores = {
            'despair': 1.0,      # 绝望期买入
            'hesitation': 0.0,  # 犹豫期观望
            'frenzy': -1.0,     # 疯狂期卖出
            'unknown': 0.0
        }
        emotion_phase_score = phase_scores.get(phase, 0)
        
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
        
        # 综合评分
        composite = (
            strength_score * 0.40 +
            emotion_phase_score * 0.30 +
            emotion_index_score * 0.15 +
            regime_adjustment * 0.15 +
            despair_bonus * 0.10 / 0.10  # 归一化后的加成
        )
        
        # 确保深度绝望期的ETF能获得足够高的分数（但需要验证通过）
        if phase == 'despair' and despair_bonus > 0.3:
            if despair_validation is None or despair_validation['valid']:
                composite = max(composite, 0.4)  # 保底分数
        
        return composite
