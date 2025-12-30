"""综合策略系统（周线级别优化版）"""

from datetime import datetime
from typing import Dict, Optional
from config import ETF_POOL
from data_fetcher import ETFDataFetcher
from analyzers import StrengthWeaknessAnalyzer, EmotionCycleAnalyzer, CapitalFlowAnalyzer, HedgeStrategy


class IntegratedETFStrategy:
    """
    综合策略系统
    整合所有策略，生成最终配置建议
    优化：采用周线级别分析，减少日线噪音
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
    
    def set_simulate_date(self, date: str):
        """设置模拟日期"""
        self.simulate_date = date
        self.data_fetcher.set_simulate_date(date)
    
    def run_full_analysis(self) -> Dict:
        """运行完整分析"""
        mode = "周线" if self.use_weekly else "日线"
        date_display = self.simulate_date if self.simulate_date else datetime.now().strftime('%Y-%m-%d')
        
        print("=" * 60)
        print(f"ETF配置系统（{mode}级别分析）- 分析日期: {date_display}")
        print("=" * 60)
        
        results = {
            'timestamp': self.simulate_date if self.simulate_date else datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'analysis_mode': 'weekly' if self.use_weekly else 'daily',
            'etf_analysis': {},
            'style_analysis': None,
            'market_health': None,
            'portfolio_suggestion': None
        }
        
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
            
            # 周线级别情绪分析
            emotion_analyzer = EmotionCycleAnalyzer(df, use_weekly=self.use_weekly)
            emotion_result = emotion_analyzer.get_emotion_phase()
            emotion_trend = emotion_analyzer.get_emotion_trend()
            
            # 计算综合得分（复用HedgeStrategy的逻辑）
            composite_score = self._calculate_composite_score(strength_result, emotion_result)
            
            results['etf_analysis'][symbol] = {
                'name': name,
                'strength': strength_result,
                'emotion': emotion_result,
                'emotion_trend': emotion_trend,
                'composite_score': composite_score,
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
            print(f"    情绪阶段: {phase_cn.get(emotion_result['phase'], '未知')} (强度:{emotion_result.get('phase_strength', 0):.0%})")
            print(f"    RSI: {strength_result.get('rsi', 0):.1f} | 情绪指数: {emotion_result.get('emotion_index', 0):.2f}")
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
        
        self.hedge_strategy = HedgeStrategy(self.data_fetcher, use_weekly=self.use_weekly)
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
    
    def _calculate_composite_score(self, strength: Dict, emotion: Dict) -> float:
        """
        计算综合评分（与HedgeStrategy保持一致）
        
        综合考虑：
        - 强弱信号得分（权重40%）
        - 情绪阶段（权重35%）
        - 情绪指数（权重15%）
        - 绝望期深度加成（权重10%）
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
        
        # 情绪指数（-1到1）
        emotion_index = emotion.get('emotion_index', 0)
        # 反转：低情绪指数反而是买入机会
        emotion_index_score = -emotion_index
        
        # 深度绝望期加成：RSI极低 + 情绪指数极低 + 绝望期强度高
        despair_bonus = 0
        rsi = emotion.get('rsi', 50)
        if phase == 'despair':
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
            emotion_phase_score * 0.35 +
            emotion_index_score * 0.15 +
            despair_bonus * 0.10 / 0.10  # 归一化后的加成
        )
        
        # 确保深度绝望期的ETF能获得足够高的分数
        if phase == 'despair' and despair_bonus > 0.3:
            composite = max(composite, 0.4)  # 保底分数
        
        return composite
