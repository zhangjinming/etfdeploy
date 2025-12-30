"""
策略四：以变应变对冲战法
核心逻辑：市场没有完美的预测，策略才是关键
优化：结合周线分析，增加情绪和资金面因素
新增：止损止盈机制，特殊资产处理
"""

from typing import Dict, List, Optional
from config import ETF_POOL, LARGE_CAP_ETFS, SMALL_CAP_ETFS, SPECIAL_ASSETS, RISK_PARAMS
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
    """
    
    def __init__(self, data_fetcher, use_weekly: bool = True):
        """
        初始化对冲策略生成器
        
        Args:
            data_fetcher: 数据获取器
            use_weekly: 是否使用周线分析
        """
        self.data_fetcher = data_fetcher
        self.use_weekly = use_weekly
    
    def generate_hedge_portfolio(self) -> Dict:
        """
        生成对冲组合
        
        核心思路：
        1. 周线级别分析减少噪音
        2. 综合强弱信号和情绪阶段
        3. 大小盘对冲、行业分散
        4. 动态调整现金比例
        """
        portfolio = {
            'long_positions': [],
            'hedge_positions': [],
            'cash_ratio': 0.2,  # 基础现金比例
            'analysis_mode': 'weekly' if self.use_weekly else 'daily'
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
            
            # 情绪分析
            emotion_analyzer = EmotionCycleAnalyzer(df, use_weekly=self.use_weekly)
            emotion_result = emotion_analyzer.get_emotion_phase()
            
            # 综合评分
            composite_score = self._calculate_composite_score(strength_result, emotion_result)
            
            etf_analysis[symbol] = {
                'name': ETF_POOL[symbol],
                'strength': strength_result,
                'emotion': emotion_result,
                'composite_score': composite_score,
                'cap_type': 'large' if symbol in LARGE_CAP_ETFS else ('small' if symbol in SMALL_CAP_ETFS else 'sector')
            }
        
        if not etf_analysis:
            return portfolio
        
        # 根据市场整体情绪调整现金比例
        portfolio['cash_ratio'] = self._calculate_cash_ratio(etf_analysis)
        
        # 计算市场环境
        market_regime = self._calculate_market_regime(etf_analysis)
        portfolio['market_regime'] = market_regime
        
        # 排序选择
        sorted_etfs = sorted(
            etf_analysis.items(),
            key=lambda x: x[1]['composite_score'],
            reverse=True
        )
        
        # 选择多头持仓
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
        
        综合考虑：
        - 强弱信号得分（权重40%）
        - 情绪阶段（权重35%）
        - 情绪指数（权重15%）
        - 绝望期深度加成（权重10%）
        
        优化：深度绝望期给予额外加分，体现"行情在绝望中产生"
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
        
        优化：确保按综合得分从高到低选择，高分标的优先入选
        """
        long_positions = []
        selected_caps = {'large': 0, 'small': 0, 'sector': 0}
        max_per_cap = 2  # 每类最多2个
        max_positions = 4  # 最多4个多头
        
        # 确保按综合得分降序排列
        sorted_by_score = sorted(
            sorted_etfs,
            key=lambda x: x[1]['composite_score'],
            reverse=True
        )
        
        # 第一轮：优先选择高分标的（得分>0.35，提高门槛）
        for symbol, analysis in sorted_by_score:
            if len(long_positions) >= max_positions:
                break
            
            composite_score = analysis['composite_score']
            cap_type = analysis['cap_type']
            
            # 只选择得分较高的（提高门槛）
            if composite_score <= 0.35:
                continue
            
            # 控制每类数量
            if selected_caps[cap_type] >= max_per_cap:
                continue
            
            # 计算权重（根据得分动态调整，更保守）
            if composite_score > 0.6:
                weight = 0.25
            elif composite_score > 0.45:
                weight = 0.20
            else:
                weight = 0.15
            
            # 构建理由
            reasons = []
            if analysis['strength']['signal'] in ['strong_buy', 'buy']:
                reasons.append(f"强弱信号:{analysis['strength']['signal']}")
            if analysis['emotion']['phase'] == 'despair':
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
            
            selected_caps[cap_type] += 1
        
        # 第二轮：如果持仓不足，补充得分>0.1的标的（提高门槛）
        if len(long_positions) < max_positions:
            for symbol, analysis in sorted_by_score:
                if len(long_positions) >= max_positions:
                    break
                
                # 跳过已选择的
                if any(p['symbol'] == symbol for p in long_positions):
                    continue
                
                composite_score = analysis['composite_score']
                cap_type = analysis['cap_type']
                
                # 只选择正分的（提高门槛）
                if composite_score <= 0.1:
                    continue
                
                # 控制每类数量
                if selected_caps[cap_type] >= max_per_cap:
                    continue
                
                weight = 0.15  # 补充仓位权重较低
                
                # 构建理由
                reasons = []
                if analysis['strength']['signal'] in ['strong_buy', 'buy']:
                    reasons.append(f"强弱信号:{analysis['strength']['signal']}")
                if analysis['emotion']['phase'] == 'despair':
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
                
                selected_caps[cap_type] += 1
        
        # 按得分降序排列最终结果
        long_positions.sort(key=lambda x: x['composite_score'], reverse=True)
        
        return long_positions
    
    def _select_hedge_positions(self, sorted_etfs: List, etf_analysis: Dict) -> List[Dict]:
        """
        选择谨慎/回避持仓（弱势标的）
        
        说明：这里的"对冲"是指识别出应该回避或减配的标的，
        而非做空。普通投资者可以：
        1. 不配置这些标的
        2. 如已持有，考虑减仓
        3. 作为风险提示参考
        """
        hedge_positions = []
        
        # 从最弱的开始选
        for symbol, analysis in reversed(sorted_etfs):
            if len(hedge_positions) >= 2:  # 最多2个
                break
            
            composite_score = analysis['composite_score']
            
            # 只选择负分的
            if composite_score >= -0.2:
                continue
            
            # 构建理由
            reasons = []
            if analysis['strength']['signal'] in ['strong_sell', 'sell']:
                reasons.append(f"强弱信号:{analysis['strength']['signal']}")
            if analysis['emotion']['phase'] == 'frenzy':
                reasons.append("处于疯狂期")
            reasons.extend(analysis['strength'].get('reasons', [])[:2])
            
            hedge_positions.append({
                'symbol': symbol,
                'name': analysis['name'],
                'weight': 0.1,  # 这里的weight表示风险敞口，建议回避
                'composite_score': composite_score,
                'cap_type': analysis['cap_type'],
                'action': 'avoid',  # 明确操作建议
                'reason': '，'.join(reasons) if reasons else f"综合得分{composite_score:.2f}，建议回避"
            })
        
        return hedge_positions
    
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
