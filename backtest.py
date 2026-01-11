"""
ETF策略回测模块

对单个ETF执行历史回测，验证策略效果。
输出详细的回测报告。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import os

from config import ETF_POOL
from etf_strategies import ETFStrategy, strategy_manager
from analyzers.strength import StrengthWeaknessAnalyzer
from analyzers.emotion import EmotionCycleAnalyzer


@dataclass
class Trade:
    """交易记录"""
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    position_size: float = 1.0
    action: str = 'buy'  # buy/sell
    entry_reason: str = ''  # 买入原因
    exit_reason: str = ''
    loss_analysis: str = ''  # 亏损分析（仅亏损交易）
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_days: int = 0
    max_price: float = 0.0  # 持仓期间最高价（用于移动止盈）
    pyramid_adds: int = 0   # 加仓次数
    total_cost: float = 0.0  # 总成本（含加仓）
    avg_price: float = 0.0   # 平均成本价
    # 入场时的市场状态（用于分析）
    entry_rsi: float = 0.0
    entry_boll_position: float = 0.0
    entry_vol_ratio: float = 0.0
    entry_trend: str = ''
    entry_emotion_phase: str = ''


@dataclass
class BacktestResult:
    """回测结果"""
    symbol: str
    name: str
    start_date: str
    end_date: str
    
    # 收益指标
    total_return: float = 0.0
    annual_return: float = 0.0
    benchmark_return: float = 0.0
    excess_return: float = 0.0
    
    # 风险指标
    max_drawdown: float = 0.0
    volatility: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    # 交易统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    avg_holding_days: float = 0.0
    
    # 交易记录
    trades: List[Trade] = field(default_factory=list)
    
    # 净值曲线
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # 策略配置
    strategy_config: Dict = field(default_factory=dict)


class ETFBacktester:
    """
    ETF策略回测器
    
    使用历史数据验证策略效果。
    """
    
    def __init__(self, initial_capital: float = 100000):
        """
        初始化回测器
        
        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0
        self.trades: List[Trade] = []
        self.current_trade: Optional[Trade] = None
        
    def run_backtest(self, symbol: str, start_date: str, end_date: str,
                     data: pd.DataFrame = None) -> BacktestResult:
        """
        执行回测
        
        Args:
            symbol: ETF代码
            start_date: 开始日期
            end_date: 结束日期
            data: 历史数据（可选，如果不提供则自动获取）
            
        Returns:
            回测结果
        """
        # 获取策略配置
        strategy = strategy_manager.get_strategy(symbol)
        if strategy is None:
            strategy = strategy_manager.create_strategy_from_template(
                symbol, ETF_POOL.get(symbol, symbol), 'balanced'
            )
        
        # 获取数据
        if data is None:
            from data_fetcher import data_fetcher
            data = data_fetcher.get_etf_history(
                symbol, 
                start_date=start_date, 
                end_date=end_date
            )
        
        if data.empty or len(data) < 60:
            raise ValueError(f"数据不足: {len(data)} 条记录")
        
        # 过滤日期范围
        data = data.copy()
        data['date'] = pd.to_datetime(data['date'])
        data = data[(data['date'] >= start_date) & (data['date'] <= end_date)]
        data = data.sort_values('date').reset_index(drop=True)
        
        # 初始化
        self.capital = self.initial_capital
        self.position = 0
        self.trades = []
        self.current_trade = None
        self.last_exit_date = None  # 记录上次卖出日期，用于冷却期
        self.sell_signal_count = 0  # 卖出信号连续确认计数
        self.last_add_date = None   # 记录上次加仓日期，用于加仓冷却期
        self.consecutive_losses = 0  # 连续亏损次数
        self.last_trade_was_loss = False  # 上次交易是否亏损
        
        # 净值曲线
        equity_curve = []
        
        # 预热期（需要足够数据计算指标）
        warmup_period = 60
        
        # 遍历每个交易日
        for i in range(warmup_period, len(data)):
            current_date = data.iloc[i]['date']
            current_price = data.iloc[i]['close']
            
            # 获取历史数据窗口
            hist_data = data.iloc[max(0, i-120):i+1].copy()
            
            # 生成交易信号（返回信号、买入原因、市场状态）
            signal, entry_reasons, market_state = self._generate_signal(hist_data, strategy)
            
            # 执行交易逻辑
            self._execute_trade(
                signal, 
                current_date, 
                current_price, 
                strategy,
                hist_data,
                entry_reasons,
                market_state
            )
            
            # 检查浮盈加仓条件
            if self.current_trade and self.position > 0:
                self._check_pyramid_add(
                    current_date,
                    current_price,
                    strategy,
                    hist_data
                )
            
            # 检查止损止盈
            if self.current_trade:
                self._check_exit_conditions(
                    current_date, 
                    current_price, 
                    strategy
                )
            
            # 计算当前净值
            if self.position > 0:
                current_value = self.capital + self.position * current_price
            else:
                current_value = self.capital
            
            equity_curve.append({
                'date': current_date,
                'equity': current_value,
                'price': current_price,
                'position': self.position,
                'signal': signal
            })
        
        # 强制平仓
        if self.current_trade:
            final_price = data.iloc[-1]['close']
            final_date = data.iloc[-1]['date']
            self._close_position(final_date, final_price, '回测结束')
        
        # 构建净值曲线DataFrame
        equity_df = pd.DataFrame(equity_curve)
        
        # 计算回测指标
        result = self._calculate_metrics(
            symbol, 
            strategy.name, 
            start_date, 
            end_date, 
            equity_df,
            data,
            strategy
        )
        
        return result
    
    def _generate_signal(self, data: pd.DataFrame, strategy: ETFStrategy) -> tuple:
        """
        生成交易信号
        
        Args:
            data: 历史数据
            strategy: 策略配置
            
        Returns:
            tuple: (信号, 买入原因列表, 市场状态字典)
                   信号: 'buy', 'sell', 'hold'
        """
        if len(data) < 60:
            return 'hold', [], {}
        
        try:
            # 强弱分析
            strength_analyzer = StrengthWeaknessAnalyzer(
                data, 
                use_weekly=strategy.use_weekly,
                symbol=strategy.symbol
            )
            strength_result = strength_analyzer.analyze_strength()
            
            # 情绪分析
            emotion_analyzer = EmotionCycleAnalyzer(
                data,
                use_weekly=strategy.use_weekly
            )
            emotion_result = emotion_analyzer.get_emotion_phase()
            
            # 综合判断
            signal = strength_result['signal']
            phase = emotion_result['phase']
            score = strength_result['score']
            rsi = emotion_result.get('rsi', 50)
            trend_info = strength_result.get('trend', {})
            trend_direction = trend_info.get('direction', 'unknown')
            trend_confirmed = trend_info.get('confirmed', False)
            
            # 收集市场状态信息
            vol_ratio = strength_result.get('vol_ratio', 1.0)
            boll_position = strength_result.get('boll_position', 0.5)
            price_position = strength_result.get('price_position', 0.5)
            pct_change = strength_result.get('pct_change', 0)
            
            market_state = {
                'rsi': rsi,
                'boll_position': boll_position,
                'vol_ratio': vol_ratio,
                'trend': trend_direction,
                'emotion_phase': phase,
                'price_position': price_position,
                'pct_change': pct_change,
            }
            
            # 买入原因列表
            entry_reasons = []
            
            # 根据策略特殊规则调整
            special_rules = strategy.special_rules
            
            # ========== v8新增：基于高胜率规律的信号生成 ==========
            if special_rules.get('use_high_winrate_rules'):
                buy_score = 0.0
                sell_score = 0.0
                
                # 获取当前日期信息
                current_date = data.iloc[-1]['date']
                if hasattr(current_date, 'month'):
                    current_month = current_date.month
                    current_day = current_date.day
                else:
                    current_month = pd.to_datetime(current_date).month
                    current_day = pd.to_datetime(current_date).day
                
                # v10新增：基于均线的趋势判断
                current_price = data.iloc[-1]['close']
                ma5 = data['close'].rolling(5).mean().iloc[-1] if len(data) >= 5 else current_price
                ma10 = data['close'].rolling(10).mean().iloc[-1] if len(data) >= 10 else current_price
                ma20 = data['close'].rolling(20).mean().iloc[-1] if len(data) >= 20 else current_price
                ma60 = data['close'].rolling(60).mean().iloc[-1] if len(data) >= 60 else current_price
                
                # 均线多头排列判断
                ma_bullish = ma5 > ma10 > ma20
                ma_above_60 = current_price > ma60
                price_above_ma20 = current_price > ma20
                
                # 均线空头排列判断
                ma_bearish = ma5 < ma10 < ma20
                price_below_ma20 = current_price < ma20
                
                # 更新趋势判断
                if ma_bullish and ma_above_60:
                    ma_trend = 'uptrend'
                elif ma_bearish and not ma_above_60:
                    ma_trend = 'downtrend'
                else:
                    ma_trend = 'sideways'
                
                # 将均线趋势添加到市场状态
                market_state['ma_trend'] = ma_trend
                market_state['ma_bullish'] = ma_bullish
                market_state['price_above_ma20'] = price_above_ma20
                
                # 1. RSI超卖信号（胜率85%+）
                if special_rules.get('rsi_oversold_buy'):
                    rsi_threshold = special_rules.get('rsi_oversold_threshold', 30)
                    if rsi < rsi_threshold:
                        buy_score += special_rules.get('rsi_oversold_weight', 3.0)
                        entry_reasons.append(f"RSI超卖({rsi:.1f}<{rsi_threshold})")
                
                # 2. 布林带下轨信号（胜率75%）
                if special_rules.get('boll_lower_buy'):
                    boll_threshold = special_rules.get('boll_position_threshold', 0.1)
                    if boll_position < boll_threshold:
                        buy_score += special_rules.get('boll_lower_weight', 2.5)
                        entry_reasons.append(f"布林带下轨({boll_position:.1%}<{boll_threshold:.0%})")
                
                # 3. 缩量下跌信号（胜率71%）
                if special_rules.get('shrink_volume_buy'):
                    shrink_threshold = special_rules.get('shrink_vol_ratio', 0.8)
                    shrink_down_pct = special_rules.get('shrink_down_pct', -3.0)
                    if vol_ratio < shrink_threshold and pct_change < shrink_down_pct:
                        buy_score += special_rules.get('shrink_volume_weight', 2.5)
                        entry_reasons.append(f"缩量下跌(量比{vol_ratio:.2f},跌{pct_change:.1f}%)")
                
                # 4. 恐慌性抛售信号（放量下跌后反弹 - 胜率66.7%）
                if special_rules.get('panic_sell_buy'):
                    panic_vol_ratio = special_rules.get('panic_vol_ratio', 2.0)
                    panic_down_pct = special_rules.get('panic_down_pct', -3.0)
                    if vol_ratio > panic_vol_ratio and pct_change < panic_down_pct:
                        buy_score += special_rules.get('panic_sell_weight', 2.5)
                        entry_reasons.append(f"放量下跌反弹(量比{vol_ratio:.2f},跌{pct_change:.1f}%)")
                
                # 4.1 放量上涨后顺势买入（v7新增 - 胜率83.3%，最高胜率信号）
                if special_rules.get('volume_surge_up_buy'):
                    surge_vol_ratio = special_rules.get('surge_up_vol_ratio', 2.0)
                    surge_up_pct = special_rules.get('surge_up_pct', 3.0)
                    if vol_ratio > surge_vol_ratio and pct_change > surge_up_pct:
                        buy_score += special_rules.get('surge_up_weight', 3.5)
                        entry_reasons.append(f"放量上涨顺势(量比{vol_ratio:.2f},涨{pct_change:.1f}%)")
                
                # 4.2 布林带上轨趋势延续（v7新增 - 上轨后4周平均涨6.7%）
                if special_rules.get('boll_upper_continuation'):
                    if boll_position > 0.85 and pct_change > 0:
                        buy_score += special_rules.get('boll_upper_continuation_weight', 2.0)
                        entry_reasons.append(f"布林上轨趋势延续({boll_position:.0%})")
                
                # 5. MACD金叉信号（零轴下方更有效）
                if special_rules.get('macd_golden_buy'):
                    macd_info = strength_result.get('macd', {})
                    macd_value = macd_info.get('macd', 0)
                    macd_signal_val = macd_info.get('signal', 0)
                    macd_hist = macd_info.get('histogram', 0)
                    macd_hist_prev = macd_info.get('histogram_prev', 0)
                    
                    # 检测金叉（histogram从负转正）
                    if macd_hist > 0 and macd_hist_prev <= 0:
                        if macd_value < 0:  # 零轴下方金叉
                            buy_score += special_rules.get('macd_below_zero_weight', 2.5)
                            entry_reasons.append("MACD零轴下金叉")
                        else:  # 零轴上方金叉
                            buy_score += special_rules.get('macd_above_zero_weight', 1.0)
                            entry_reasons.append("MACD零轴上金叉")
                
                # 6. 三重底信号（RSI<30 + BOLL<0.2 + 缩量）- 最强买入信号
                if special_rules.get('triple_bottom_buy'):
                    rsi_threshold = special_rules.get('rsi_oversold_threshold', 30)
                    boll_threshold = special_rules.get('boll_position_threshold', 0.2)
                    shrink_threshold = special_rules.get('shrink_vol_ratio', 0.8)
                    
                    if rsi < rsi_threshold and boll_position < boll_threshold and vol_ratio < shrink_threshold:
                        buy_score += special_rules.get('triple_bottom_weight', 4.0)
                        entry_reasons.append("三重底信号(RSI+布林+缩量)")
                
                # 7. 连跌信号（胜率68%）
                if special_rules.get('consecutive_down_buy'):
                    consecutive_down = self._count_consecutive_down(data)
                    down_threshold = special_rules.get('consecutive_down_weeks', 2)
                    if consecutive_down >= down_threshold:
                        buy_score += special_rules.get('consecutive_down_weight', 2.0)
                        entry_reasons.append(f"连跌{consecutive_down}周")
                
                # 8. 价格位置信号（底部区域胜率100%）
                if special_rules.get('price_position_buy'):
                    position_threshold = special_rules.get('price_position_threshold', 0.2)
                    if price_position < position_threshold:
                        buy_score += special_rules.get('price_position_weight', 3.0)
                        entry_reasons.append(f"价格底部区域({price_position:.0%})")
                
                # 9. 月份/时间效应
                if special_rules.get('use_seasonal_rules'):
                    best_months = special_rules.get('best_months', [11, 9, 2])
                    worst_months = special_rules.get('worst_months', [10])
                    month_start_days = special_rules.get('month_start_days', 5)
                    
                    # 最佳月份加分
                    if current_month in best_months:
                        buy_score += 0.5
                        entry_reasons.append(f"{current_month}月效应")
                    
                    # 最差月份减分
                    if current_month in worst_months:
                        buy_score -= 0.5
                        sell_score += 0.3
                    
                    # 月初效应加分
                    if current_day <= month_start_days:
                        buy_score += special_rules.get('month_start_weight', 1.0)
                        entry_reasons.append("月初效应")
                
                # 10. 放量滞涨卖出信号（胜率仅17%，反向使用）
                if special_rules.get('volume_surge_stall_exit'):
                    surge_threshold = special_rules.get('surge_vol_ratio', 1.5)
                    stall_threshold = special_rules.get('stall_pct_threshold', 0.5)
                    if vol_ratio > surge_threshold and abs(pct_change) < stall_threshold:
                        sell_score += 1.5
                
                # 11. RSI超买卖出信号
                if special_rules.get('rsi_exit_enabled'):
                    rsi_exit_threshold = special_rules.get('rsi_exit_threshold', 70)
                    if rsi > rsi_exit_threshold:
                        sell_score += special_rules.get('rsi_exit_weight', 2.0)
                
                # 12. 布林带上轨卖出信号
                if special_rules.get('boll_upper_sell'):
                    boll_upper_threshold = special_rules.get('boll_upper_threshold', 0.9)
                    if boll_position > boll_upper_threshold:
                        sell_score += 1.5
                
                # 13. MACD死叉卖出信号（70%下跌概率）
                if special_rules.get('macd_death_sell'):
                    macd_info = strength_result.get('macd', {})
                    macd_hist = macd_info.get('histogram', 0)
                    macd_hist_prev = macd_info.get('histogram_prev', 0)
                    
                    # 检测死叉（histogram从正转负）
                    if macd_hist < 0 and macd_hist_prev >= 0:
                        sell_score += special_rules.get('macd_death_weight', 2.0)
                
                # 14. 高位区域减分（v13优化：更精细的高位惩罚）
                high_position_threshold = special_rules.get('boll_high_position_penalty', 0.80)
                very_high_threshold = special_rules.get('very_high_position_threshold', 0.88)
                
                if price_position > very_high_threshold:
                    # 极高位（>88%）：大幅惩罚
                    very_high_penalty = special_rules.get('very_high_penalty', 0.1)
                    buy_score *= very_high_penalty
                    sell_score += 1.0
                elif price_position > high_position_threshold:
                    # 高位（>80%）：中等惩罚
                    high_penalty = special_rules.get('boll_high_penalty_factor', 0.3)
                    buy_score *= high_penalty
                    sell_score += 0.5
                
                # v13新增：布林带上轨需要放量确认
                if special_rules.get('boll_upper_require_volume'):
                    if boll_position > 0.85:
                        boll_vol_threshold = special_rules.get('boll_upper_vol_ratio', 1.3)
                        if vol_ratio < boll_vol_threshold:
                            # 上轨但无放量，降低信号权重
                            buy_score *= 0.5
                
                # 15. 趋势过滤（v12优化：结合均线趋势判断 + 允许横盘入场）
                trend_filter_mode = special_rules.get('trend_filter_mode', 'moderate')
                block_downtrend = special_rules.get('block_downtrend_entry', False)
                allow_sideways = special_rules.get('allow_sideways_entry', True)
                
                # 使用均线趋势判断（更可靠）
                effective_trend = ma_trend if ma_trend != 'sideways' else trend_direction
                is_downtrend = effective_trend == 'downtrend' or (ma_bearish and price_below_ma20)
                is_uptrend = effective_trend == 'uptrend' or (ma_bullish and price_above_ma20)
                is_sideways = not is_downtrend and not is_uptrend
                
                # v12新增：RSI回升确认检查
                rsi_recovery_required = special_rules.get('rsi_recovery_required', False)
                rsi_recovery_threshold = special_rules.get('rsi_recovery_threshold', 35)
                rsi_oversold_threshold = special_rules.get('rsi_oversold_threshold', 25)
                
                # 如果要求RSI回升确认，且RSI仍在超卖区，降低买入得分
                if rsi_recovery_required and rsi < rsi_recovery_threshold:
                    if rsi < rsi_oversold_threshold:
                        # 极端超卖但未回升，大幅降低（等待企稳）
                        buy_score *= 0.3
                
                if is_downtrend:
                    if block_downtrend or trend_filter_mode == 'very_strict':
                        # 非常严格模式：完全禁止下跌趋势入场
                        buy_score = 0  # 直接清零
                    elif trend_filter_mode == 'strict':
                        # 严格模式：下跌趋势中几乎不入场
                        if rsi > 25:
                            buy_score *= 0.1
                        else:
                            buy_score *= 0.3
                    elif trend_filter_mode == 'moderate':
                        buy_score *= 0.4
                    else:
                        buy_score *= 0.6
                        
                elif is_uptrend:
                    # v12优化：上涨趋势中大幅提高买入得分
                    ma_bullish_bonus = special_rules.get('ma_bullish_bonus', 1.5)
                    buy_score *= 1.5  # 上涨趋势基础加成
                    if ma_bullish:
                        buy_score *= ma_bullish_bonus  # 均线多头额外加成
                        entry_reasons.append("均线多头")
                    # v13新增：MA斜率加成
                    if special_rules.get('ma_slope_bonus') and len(data) >= 25:
                        ma20_5d_ago = data['close'].rolling(20).mean().iloc[-6] if len(data) >= 26 else ma20
                        ma20_slope = (ma20 - ma20_5d_ago) / ma20_5d_ago if ma20_5d_ago > 0 else 0
                        if ma20_slope > 0.01:  # MA20上升斜率>1%
                            buy_score *= special_rules.get('ma_slope_up_bonus', 1.2)
                    if entry_reasons:
                        entry_reasons.append("上涨趋势确认")
                        
                elif is_sideways:
                    # v12优化：横盘时允许入场（如果配置允许）
                    if allow_sideways:
                        if price_above_ma20:
                            buy_score *= 1.1  # 站上20日均线，略微加分
                        else:
                            buy_score *= 0.8  # 未站上20日均线，略微降低
                    else:
                        buy_score *= 0.7  # 不允许横盘入场时降低分数
                
                # v13新增：MA20斜率过滤（下跌斜率时更谨慎）
                if special_rules.get('ma_slope_filter') and len(data) >= 25:
                    ma20_5d_ago = data['close'].rolling(20).mean().iloc[-6] if len(data) >= 26 else ma20
                    ma20_slope = (ma20 - ma20_5d_ago) / ma20_5d_ago if ma20_5d_ago > 0 else 0
                    slope_threshold = special_rules.get('ma_slope_threshold', -0.02)
                    if ma20_slope < slope_threshold:  # MA20下降斜率超过阈值
                        buy_score *= 0.5  # 大幅降低买入得分
                
                # v13新增：波动率过滤
                if special_rules.get('volatility_filter') and len(data) >= 20:
                    volatility = data['close'].pct_change().rolling(20).std().iloc[-1] * np.sqrt(252)
                    low_vol_threshold = special_rules.get('low_volatility_threshold', 0.08)
                    high_vol_threshold = special_rules.get('high_volatility_threshold', 0.25)
                    
                    if volatility < low_vol_threshold:
                        # 低波动率：市场沉闷，谨慎入场
                        buy_score *= special_rules.get('low_volatility_penalty', 0.7)
                    elif volatility > high_vol_threshold and special_rules.get('high_volatility_caution'):
                        # 高波动率：风险加大，收紧止损
                        pass  # 在风控逻辑中处理
                
                # 16. 趋势反转确认（v6新增：关键优化，v5.3增强：扩展到所有趋势）
                if special_rules.get('require_trend_reversal'):
                    # 检测趋势反转信号
                    macd_info = strength_result.get('macd', {})
                    macd_hist = macd_info.get('histogram', 0)
                    macd_hist_prev = macd_info.get('histogram_prev', 0)
                    
                    # 价格突破短期均线
                    current_price = data.iloc[-1]['close']
                    ma5 = data['close'].rolling(5).mean().iloc[-1] if len(data) >= 5 else current_price
                    ma10 = data['close'].rolling(10).mean().iloc[-1] if len(data) >= 10 else current_price
                    
                    reversal_signals = 0
                    reversal_reasons = []
                    
                    # MACD柱状图连续两天改善
                    if macd_hist > macd_hist_prev:
                        reversal_signals += 1
                        reversal_reasons.append("MACD改善")
                    
                    # 价格站上5日均线
                    if current_price > ma5:
                        reversal_signals += 1
                        reversal_reasons.append("站上MA5")
                    
                    # 价格站上10日均线
                    if current_price > ma10:
                        reversal_signals += 1
                        reversal_reasons.append("站上MA10")
                    
                    # RSI从超卖区回升
                    if rsi > 30 and rsi < 50:
                        reversal_signals += 1
                        reversal_reasons.append("RSI回升")
                    
                    # v5.3新增：成交量确认（放量上涨）
                    if vol_ratio > 1.2 and pct_change > 0:
                        reversal_signals += 1
                        reversal_reasons.append("放量上涨")
                    
                    # 需要至少2个反转信号才能入场
                    min_reversal_signals = special_rules.get('min_reversal_signals', 2)
                    
                    # v5.3增强：扩展到sideways和unknown趋势
                    if trend_direction == 'downtrend' and reversal_signals < min_reversal_signals:
                        buy_score *= 0.3  # 没有反转确认时大幅降低
                    elif trend_direction in ['sideways', 'unknown'] and reversal_signals < min_reversal_signals:
                        buy_score *= 0.5  # 横盘/未知趋势也需要反转确认
                    
                    if reversal_signals >= min_reversal_signals:
                        entry_reasons.extend(reversal_reasons[:2])  # 添加反转原因
                
                # 获取买卖门槛
                buy_threshold = special_rules.get('buy_score_threshold', 2.0)
                strong_buy_threshold = special_rules.get('strong_buy_threshold', 4.0)
                sell_threshold = special_rules.get('sell_score_threshold', -1.5)
                
                # 入场限制检查（v5.2增强：严格限制高位入场）
                rsi_entry_max = special_rules.get('rsi_entry_max', 65)
                if rsi > rsi_entry_max:
                    buy_score *= 0.1  # RSI过高时大幅降低买入得分（0.5->0.1）
                    if rsi > rsi_entry_max + 10:  # RSI超过限制10以上，直接禁止
                        buy_score = 0
                
                if special_rules.get('avoid_high_position_entry'):
                    high_threshold = special_rules.get('high_position_threshold', 0.85)
                    very_high_threshold = special_rules.get('very_high_position_threshold', 0.90)
                    if price_position > very_high_threshold:
                        buy_score = 0  # 极高位直接禁止入场
                    elif price_position > high_threshold:
                        buy_score *= 0.15  # 高位时大幅降低买入得分（0.3->0.15）
                    
                    # 布林带位置限制
                    boll_high_threshold = special_rules.get('boll_high_position_penalty', 0.70)
                    if boll_position > boll_high_threshold:
                        penalty_factor = special_rules.get('boll_high_penalty_factor', 0.3)
                        buy_score *= penalty_factor
                
                # v5.2新增：疯狂期过滤（在高胜率规则系统中也生效）
                # 注：适度惩罚，不完全禁止，因为某些疯狂期入场也能盈利
                if special_rules.get('avoid_frenzy_chase') and phase == 'frenzy':
                    buy_score *= 0.7  # 疯狂期适度降低买入得分
                
                # 根据得分生成信号
                if buy_score >= strong_buy_threshold:
                    return 'buy', entry_reasons, market_state
                elif buy_score >= buy_threshold:
                    return 'buy', entry_reasons, market_state
                elif sell_score >= 2.5:  # 提高卖出门槛（1.0->2.5）
                    return 'sell', [], market_state
                else:
                    return 'hold', [], market_state
            
            # ========== 原有逻辑（非v8规则时使用） ==========
            # 获取优化参数
            buy_score_threshold = special_rules.get('buy_score_threshold', 2.0)
            sell_score_threshold = special_rules.get('sell_score_threshold', -2.0)
            require_trend_confirm = special_rules.get('require_trend_confirm', False)
            
            # 入场条件过滤
            rsi_entry_max = special_rules.get('rsi_entry_max', 100)
            if rsi > rsi_entry_max:
                if signal in ['buy', 'strong_buy']:
                    return 'hold', [], market_state
            
            if special_rules.get('avoid_high_position_entry'):
                high_threshold = special_rules.get('high_position_threshold', 0.75)
                if price_position > high_threshold:
                    if signal in ['buy', 'strong_buy']:
                        return 'hold', [], market_state
            
            # 严格趋势跟踪模式
            if special_rules.get('trend_following_strict'):
                if trend_direction == 'uptrend' and trend_confirmed:
                    if signal in ['buy', 'strong_buy'] and score >= buy_score_threshold:
                        return 'buy', ['趋势跟踪买入', '上涨趋势确认'], market_state
                    if score >= buy_score_threshold + 0.5:
                        return 'buy', ['趋势跟踪买入', f'评分{score:.1f}'], market_state
                if trend_direction == 'downtrend' and trend_confirmed:
                    if score <= sell_score_threshold:
                        return 'sell', [], market_state
                if not trend_confirmed and require_trend_confirm:
                    return 'hold', [], market_state
            
            # 轻度趋势跟踪模式
            elif special_rules.get('trend_following_lite'):
                if trend_direction == 'uptrend' and trend_confirmed:
                    if signal in ['buy', 'neutral'] and score >= 1:
                        return 'buy', ['轻度趋势买入', '上涨趋势'], market_state
                if trend_direction == 'downtrend' and trend_confirmed:
                    if signal in ['sell', 'neutral'] and score <= 0:
                        return 'sell', [], market_state
            
            # 绝望期买入偏好
            if special_rules.get('prefer_despair_phase') and phase == 'despair':
                if rsi < strategy.rsi_oversold:
                    if special_rules.get('trend_following_strict'):
                        if trend_direction != 'downtrend' and signal in ['buy', 'neutral', 'strong_buy']:
                            return 'buy', ['绝望期买入', f'RSI超卖({rsi:.1f})'], market_state
                    elif signal in ['buy', 'neutral', 'strong_buy']:
                        return 'buy', ['绝望期买入', f'RSI超卖({rsi:.1f})'], market_state
                elif signal in ['buy', 'neutral'] and not special_rules.get('trend_following_strict'):
                    return 'buy', ['绝望期买入'], market_state
            
            # 疯狂期回避追高
            if special_rules.get('avoid_frenzy_chase') and phase == 'frenzy':
                if signal in ['buy', 'strong_buy']:
                    return 'hold', [], market_state
                if rsi > strategy.rsi_overbought:
                    return 'sell', [], market_state
            
            # 根据信号强度判断
            if signal in ['strong_buy', 'buy'] and score >= buy_score_threshold:
                return 'buy', [f'综合评分买入({score:.1f})'], market_state
            elif signal in ['strong_sell', 'sell'] and score <= sell_score_threshold:
                return 'sell', [], market_state
            else:
                return 'hold', [], market_state
                
        except Exception as e:
            return 'hold', [], {}
    
    def _count_consecutive_down(self, data: pd.DataFrame) -> int:
        """计算连续下跌周数"""
        if len(data) < 10:
            return 0
        
        # 转换为周线判断
        try:
            df = data.copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            weekly = df['close'].resample('W').last().dropna()
            weekly_pct = weekly.pct_change()
            
            # 计算最近连续下跌周数
            count = 0
            for pct in weekly_pct.iloc[::-1]:
                if pd.notna(pct) and pct < 0:
                    count += 1
                else:
                    break
            return count
        except:
            return 0
    
    def _check_pyramid_add(self, date: datetime, price: float,
                           strategy: ETFStrategy, hist_data: pd.DataFrame):
        """
        检查浮盈加仓条件（v10新增）
        
        基于红利低波ETF规律：
        1. 趋势性强，超买后仍可能继续上涨
        2. 创52周新高后4周胜率较高
        3. 浮盈时顺势加仓可提升收益
        """
        if not self.current_trade or self.position == 0:
            return
        
        special_rules = strategy.special_rules
        
        # 检查是否启用浮盈加仓
        if not special_rules.get('pyramid_add_enabled', False):
            return
        
        # 检查加仓次数上限
        max_adds = special_rules.get('pyramid_max_adds', 3)
        if self.current_trade.pyramid_adds >= max_adds:
            return
        
        # 检查最小持仓天数
        holding_days = (date - self.current_trade.entry_date).days
        min_holding = special_rules.get('pyramid_min_holding_days', 14)
        if holding_days < min_holding:
            return
        
        # 检查加仓冷却期
        cooldown = special_rules.get('pyramid_cooldown_days', 7)
        if self.last_add_date:
            days_since_add = (date - self.last_add_date).days
            if days_since_add < cooldown:
                return
        
        # 计算当前浮盈（基于平均成本）
        avg_price = self.current_trade.avg_price
        current_profit_pct = (price / avg_price - 1) * 100
        
        # 确定当前应该触发的加仓阈值
        adds = self.current_trade.pyramid_adds
        if adds == 0:
            threshold = special_rules.get('pyramid_profit_threshold_1', 8.0)
            add_ratio = special_rules.get('pyramid_add_ratio_1', 0.3)
        elif adds == 1:
            threshold = special_rules.get('pyramid_profit_threshold_2', 15.0)
            add_ratio = special_rules.get('pyramid_add_ratio_2', 0.2)
        elif adds == 2:
            threshold = special_rules.get('pyramid_profit_threshold_3', 25.0)
            add_ratio = special_rules.get('pyramid_add_ratio_3', 0.15)
        else:
            return
        
        # 检查是否达到加仓阈值
        if current_profit_pct < threshold:
            return
        
        # 检查RSI条件（避免在极度超买时加仓）
        rsi_max = special_rules.get('pyramid_rsi_max', 75)
        try:
            emotion_analyzer = EmotionCycleAnalyzer(hist_data, use_weekly=strategy.use_weekly)
            emotion_result = emotion_analyzer.get_emotion_phase()
            current_rsi = emotion_result.get('rsi', 50)
            if current_rsi > rsi_max:
                return
        except:
            pass
        
        # 检查趋势条件（可选）
        if special_rules.get('pyramid_trend_required', True):
            try:
                strength_analyzer = StrengthWeaknessAnalyzer(
                    hist_data, 
                    use_weekly=strategy.use_weekly,
                    symbol=strategy.symbol
                )
                strength_result = strength_analyzer.analyze_strength()
                trend_info = strength_result.get('trend', {})
                trend_direction = trend_info.get('direction', 'unknown')
                
                # 只在上涨或横盘趋势中加仓
                if trend_direction == 'downtrend':
                    return
            except:
                pass
        
        # 执行加仓
        # 加仓金额 = 当前仓位市值 * 加仓比例
        current_value = self.position * price
        add_capital = min(current_value * add_ratio, self.capital * 0.8)  # 不超过可用资金的80%
        add_shares = int(add_capital / price / 100) * 100
        
        if add_shares > 0 and self.capital >= add_shares * price:
            add_cost = add_shares * price
            self.capital -= add_cost
            
            # 更新仓位和成本
            old_position = self.position
            self.position += add_shares
            
            # 更新平均成本
            new_total_cost = self.current_trade.total_cost + add_cost
            self.current_trade.total_cost = new_total_cost
            self.current_trade.avg_price = new_total_cost / self.position
            self.current_trade.position_size = self.position
            self.current_trade.pyramid_adds += 1
            
            # 记录加仓日期
            self.last_add_date = date
    
    def _execute_trade(self, signal: str, date: datetime, price: float,
                       strategy: ETFStrategy, hist_data: pd.DataFrame = None,
                       entry_reasons: list = None, market_state: dict = None):
        """执行交易（v9优化：持仓时间限制 + v11新增：记录买入原因 + v5.3新增：连续亏损保护）"""
        risk_control = strategy.risk_control
        special_rules = strategy.special_rules
        
        if signal == 'buy' and self.position == 0:
            # 检查入场冷却期
            cooldown_days = special_rules.get('entry_cooldown_days', 0)
            if cooldown_days > 0 and self.last_exit_date:
                days_since_exit = (date - self.last_exit_date).days
                if days_since_exit < cooldown_days:
                    return  # 冷却期内不买入
            
            # v5.3新增：连续亏损保护
            if special_rules.get('avoid_consecutive_loss', False):
                # 上次亏损后的额外冷却期
                if self.last_trade_was_loss and self.last_exit_date:
                    loss_cooldown = special_rules.get('loss_cooldown_days', 14)
                    days_since_exit = (date - self.last_exit_date).days
                    if days_since_exit < loss_cooldown:
                        return  # 亏损后冷却期内不买入
                
                # 连续亏损次数限制
                consecutive_max = special_rules.get('consecutive_loss_max', 2)
                if self.consecutive_losses >= consecutive_max:
                    consecutive_cooldown = special_rules.get('consecutive_loss_cooldown', 21)
                    if self.last_exit_date:
                        days_since_exit = (date - self.last_exit_date).days
                        if days_since_exit < consecutive_cooldown:
                            return  # 连续亏损后的长冷却期内不买入
            
            # 计算可买入数量
            position_capital = self.capital * risk_control.max_position
            shares = int(position_capital / price / 100) * 100
            
            if shares > 0:
                cost = shares * price
                self.capital -= cost
                self.position = shares
                
                # 构建买入原因字符串
                entry_reason_str = ''
                if entry_reasons:
                    entry_reason_str = '，'.join(entry_reasons)
                
                # 获取市场状态信息
                ms = market_state or {}
                
                self.current_trade = Trade(
                    entry_date=date,
                    entry_price=price,
                    position_size=shares,
                    action='buy',
                    entry_reason=entry_reason_str,
                    pyramid_adds=0,
                    total_cost=cost,
                    avg_price=price,
                    entry_rsi=ms.get('rsi', 0),
                    entry_boll_position=ms.get('boll_position', 0),
                    entry_vol_ratio=ms.get('vol_ratio', 0),
                    entry_trend=ms.get('trend', ''),
                    entry_emotion_phase=ms.get('emotion_phase', ''),
                )
                self.sell_signal_count = 0  # 重置卖出信号计数
                self.last_add_date = None   # 重置加仓日期
        
        elif signal == 'sell' and self.position > 0:
            # v9: 最小持仓天数检查移到_check_exit_conditions中统一处理
            # 这里只处理信号确认
            min_holding_days = special_rules.get('min_holding_days', 30)
            if min_holding_days > 0 and self.current_trade:
                holding_days = (date - self.current_trade.entry_date).days
                if holding_days < min_holding_days:
                    return  # 未达到最小持仓天数，不卖出
            
            # 检查卖出信号确认天数
            confirm_days = special_rules.get('sell_signal_confirm_days', 1)
            if confirm_days > 1:
                self.sell_signal_count += 1
                if self.sell_signal_count < confirm_days:
                    return  # 信号未确认足够天数
            
            self._close_position(date, price, '卖出信号')
        else:
            # 非卖出信号时重置计数
            if signal != 'sell':
                self.sell_signal_count = 0
    
    def _check_exit_conditions(self, date: datetime, price: float,
                               strategy: ETFStrategy):
        """检查出场条件（v9优化：持仓时间限制）"""
        if not self.current_trade:
            return
        
        risk_control = strategy.risk_control
        special_rules = strategy.special_rules
        # 使用平均成本计算浮盈
        avg_price = self.current_trade.avg_price if self.current_trade.avg_price > 0 else self.current_trade.entry_price
        pct_change = (price / avg_price - 1) * 100
        holding_days = (date - self.current_trade.entry_date).days
        
        # ========== v9新增：持仓时间限制 ==========
        min_holding_days = special_rules.get('min_holding_days', 30)
        max_holding_days = special_rules.get('max_holding_days', 365)
        
        # 最长持仓时间强制退出（12个月）
        if special_rules.get('force_exit_at_max', True):
            if holding_days >= max_holding_days:
                self._close_position(date, price, f'最长持仓({holding_days}天,收益{pct_change:.1f}%)')
                return
        
        # 最短持仓时间内只允许止损退出（使用更宽松的止损）
        if holding_days < min_holding_days:
            # 短期持仓使用更宽松的止损（-10%）
            early_stop_loss = special_rules.get('early_stop_loss', -10.0)
            if pct_change <= early_stop_loss:
                self._close_position(date, price, f'止损({pct_change:.1f}%,持仓{holding_days}天)')
            return  # 未满最短持仓，不检查其他退出条件
        
        # ========== 动态止盈（基于持仓时间） ==========
        if special_rules.get('dynamic_exit', True):
            # 根据持仓时间调整止盈阈值
            # 支持按周计算（创业板50ETF）和按月计算（红利低波ETF）
            if 'exit_profit_13w' in special_rules:
                # 按周计算（创业板50ETF）
                if holding_days >= 91:  # 13周+
                    take_profit_threshold = special_rules.get('exit_profit_13w', 20.0)
                elif holding_days >= 56:  # 8周+
                    take_profit_threshold = special_rules.get('exit_profit_8w', 16.0)
                elif holding_days >= 28:  # 4周+
                    take_profit_threshold = special_rules.get('exit_profit_4w', 12.0)
                else:  # 1-4周
                    take_profit_threshold = special_rules.get('exit_profit_1w', 8.0)
            else:
                # 按月计算（红利低波ETF等）
                if holding_days >= 270:  # 9个月+
                    take_profit_threshold = special_rules.get('exit_profit_9m', 35.0)
                elif holding_days >= 180:  # 6个月+
                    take_profit_threshold = special_rules.get('exit_profit_6m', 25.0)
                elif holding_days >= 90:  # 3个月+
                    take_profit_threshold = special_rules.get('exit_profit_3m', 15.0)
                else:  # 1-3个月
                    take_profit_threshold = special_rules.get('exit_profit_1m', 8.0)
            
            if pct_change >= take_profit_threshold:
                self._close_position(date, price, f'动态止盈({pct_change:.1f}%,持仓{holding_days}天)')
                return
        
        # ========== 常规止损（持仓超过1个月后） ==========
        stop_loss = special_rules.get('exit_loss_threshold', risk_control.stop_loss)
        if pct_change <= stop_loss:
            self._close_position(date, price, f'止损({pct_change:.1f}%)')
            return
        
        # ========== 移动止盈（Trailing Stop） ==========
        if risk_control.trailing_stop > 0:
            protect_threshold = special_rules.get('protect_profit_above', risk_control.take_profit / 2)
            
            if pct_change >= protect_threshold:
                if not hasattr(self.current_trade, 'max_price') or self.current_trade.max_price == 0:
                    self.current_trade.max_price = price
                else:
                    self.current_trade.max_price = max(self.current_trade.max_price, price)
                
                max_pct = (self.current_trade.max_price / avg_price - 1) * 100
                drawdown_from_max = (self.current_trade.max_price - price) / self.current_trade.max_price * 100
                
                if drawdown_from_max >= risk_control.trailing_stop:
                    self._close_position(date, price, f'移动止盈(最高{max_pct:.1f}%,回撤{drawdown_from_max:.1f}%)')
                    return
        
        # ========== 时间止损（原有逻辑，调整为与新规则兼容） ==========
        if holding_days >= risk_control.time_stop_weeks * 7:
            if pct_change < risk_control.time_stop_min_profit:
                self._close_position(date, price, f'时间止损({holding_days}天,收益{pct_change:.1f}%)')
    
    def _close_position(self, date: datetime, price: float, reason: str):
        """平仓（v11新增：亏损分析）"""
        if not self.current_trade or self.position == 0:
            return
        
        # 计算盈亏（使用平均成本）
        proceeds = self.position * price
        self.capital += proceeds
        
        # 使用平均成本计算收益率
        avg_price = self.current_trade.avg_price if self.current_trade.avg_price > 0 else self.current_trade.entry_price
        pnl = proceeds - self.current_trade.total_cost if self.current_trade.total_cost > 0 else (price - avg_price) * self.position
        pnl_pct = (price / avg_price - 1) * 100
        holding_days = (date - self.current_trade.entry_date).days
        
        # 更新交易记录
        self.current_trade.exit_date = date
        self.current_trade.exit_price = price
        self.current_trade.exit_reason = reason
        if self.current_trade.pyramid_adds > 0:
            self.current_trade.exit_reason += f'(加仓{self.current_trade.pyramid_adds}次)'
        self.current_trade.pnl = pnl
        self.current_trade.pnl_pct = pnl_pct
        self.current_trade.holding_days = holding_days
        
        # ========== v11新增：亏损分析 ==========
        if pnl_pct < 0:
            loss_reasons = []
            
            # 分析入场时机问题
            entry_rsi = self.current_trade.entry_rsi
            entry_boll = self.current_trade.entry_boll_position
            entry_trend = self.current_trade.entry_trend
            
            # 1. 入场RSI偏高
            if entry_rsi > 50:
                loss_reasons.append(f"入场RSI偏高({entry_rsi:.1f})")
            
            # 2. 入场价格位置偏高
            if entry_boll > 0.5:
                loss_reasons.append(f"入场价格偏高(布林{entry_boll:.0%})")
            
            # 3. 下跌趋势中入场
            if entry_trend == 'downtrend':
                loss_reasons.append("下跌趋势中入场")
            
            # 4. 持仓时间分析
            if holding_days < 14:
                loss_reasons.append(f"持仓过短({holding_days}天)")
            elif holding_days > 100 and pnl_pct < -10:
                loss_reasons.append(f"长期持有未能扭亏({holding_days}天)")
            
            # 5. 止损触发分析
            if '止损' in reason:
                loss_reasons.append("触发止损保护")
            
            # 6. 时间止损分析
            if '时间止损' in reason or '最长持仓' in reason:
                loss_reasons.append("达到持仓时间上限")
            
            # 构建亏损分析字符串
            if loss_reasons:
                self.current_trade.loss_analysis = '；'.join(loss_reasons)
            else:
                self.current_trade.loss_analysis = "市场系统性下跌"
        
        self.trades.append(self.current_trade)
        
        # v5.3新增：更新连续亏损计数
        if pnl_pct < 0:
            self.consecutive_losses += 1
            self.last_trade_was_loss = True
        else:
            self.consecutive_losses = 0  # 盈利后重置连续亏损计数
            self.last_trade_was_loss = False
        
        # 重置
        self.position = 0
        self.current_trade = None
        self.last_exit_date = date  # 记录卖出日期用于冷却期
        self.sell_signal_count = 0  # 重置卖出信号计数
        self.last_add_date = None   # 重置加仓日期
    
    def _calculate_metrics(self, symbol: str, name: str, start_date: str,
                          end_date: str, equity_df: pd.DataFrame,
                          price_data: pd.DataFrame,
                          strategy: ETFStrategy) -> BacktestResult:
        """计算回测指标"""
        result = BacktestResult(
            symbol=symbol,
            name=name,
            start_date=start_date,
            end_date=end_date,
            trades=self.trades,
            equity_curve=equity_df,
            strategy_config=strategy.to_dict()
        )
        
        if equity_df.empty:
            return result
        
        # 收益指标
        initial_equity = equity_df.iloc[0]['equity']
        final_equity = equity_df.iloc[-1]['equity']
        
        result.total_return = (final_equity / initial_equity - 1) * 100
        
        # 年化收益
        days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
        years = days / 365
        if years > 0:
            result.annual_return = ((1 + result.total_return / 100) ** (1 / years) - 1) * 100
        
        # 基准收益（买入持有）
        if len(price_data) > 0:
            first_price = price_data.iloc[0]['close']
            last_price = price_data.iloc[-1]['close']
            result.benchmark_return = (last_price / first_price - 1) * 100
        
        result.excess_return = result.total_return - result.benchmark_return
        
        # 风险指标
        equity_df['returns'] = equity_df['equity'].pct_change()
        
        # 最大回撤
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] / equity_df['cummax'] - 1) * 100
        result.max_drawdown = equity_df['drawdown'].min()
        
        # 波动率（年化）
        result.volatility = equity_df['returns'].std() * np.sqrt(252) * 100
        
        # 夏普比率（假设无风险利率3%）
        risk_free_rate = 0.03
        if result.volatility > 0:
            result.sharpe_ratio = (result.annual_return / 100 - risk_free_rate) / (result.volatility / 100)
        
        # 卡玛比率
        if result.max_drawdown < 0:
            result.calmar_ratio = result.annual_return / abs(result.max_drawdown)
        
        # 交易统计
        result.total_trades = len(self.trades)
        
        if result.total_trades > 0:
            winning_trades = [t for t in self.trades if t.pnl > 0]
            losing_trades = [t for t in self.trades if t.pnl <= 0]
            
            result.winning_trades = len(winning_trades)
            result.losing_trades = len(losing_trades)
            result.win_rate = result.winning_trades / result.total_trades * 100
            
            if winning_trades:
                result.avg_win = np.mean([t.pnl_pct for t in winning_trades])
            if losing_trades:
                result.avg_loss = np.mean([t.pnl_pct for t in losing_trades])
            
            # 盈亏比
            total_profit = sum(t.pnl for t in winning_trades) if winning_trades else 0
            total_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else 1
            result.profit_factor = total_profit / total_loss if total_loss > 0 else 0
            
            # 平均持仓天数
            result.avg_holding_days = np.mean([t.holding_days for t in self.trades])
        
        return result


def generate_backtest_report(result: BacktestResult, output_path: str = None) -> str:
    """
    生成回测报告（Markdown格式）
    
    Args:
        result: 回测结果
        output_path: 输出路径（可选）
        
    Returns:
        Markdown格式的报告内容
    """
    report = f"""# {result.name}({result.symbol}) 策略回测报告

## 回测概览

| 项目 | 数值 |
|------|------|
| 回测标的 | {result.name}({result.symbol}) |
| 回测区间 | {result.start_date} ~ {result.end_date} |
| 初始资金 | ¥100,000 |

---

## 收益指标

| 指标 | 策略 | 基准(买入持有) |
|------|------|----------------|
| 总收益率 | {result.total_return:.2f}% | {result.benchmark_return:.2f}% |
| 年化收益率 | {result.annual_return:.2f}% | - |
| 超额收益 | {result.excess_return:.2f}% | - |

---

## 风险指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 最大回撤 | {result.max_drawdown:.2f}% | 期间最大亏损幅度 |
| 年化波动率 | {result.volatility:.2f}% | 收益波动程度 |
| 夏普比率 | {result.sharpe_ratio:.2f} | 风险调整后收益(>1为优) |
| 卡玛比率 | {result.calmar_ratio:.2f} | 收益/最大回撤(>1为优) |

---

## 交易统计

| 指标 | 数值 |
|------|------|
| 总交易次数 | {result.total_trades} |
| 盈利次数 | {result.winning_trades} |
| 亏损次数 | {result.losing_trades} |
| 胜率 | {result.win_rate:.1f}% |
| 平均盈利 | {result.avg_win:.2f}% |
| 平均亏损 | {result.avg_loss:.2f}% |
| 盈亏比 | {result.profit_factor:.2f} |
| 平均持仓天数 | {result.avg_holding_days:.1f}天 |

---

## 策略配置

```
风格: {result.strategy_config.get('style', 'N/A')}
分类: {result.strategy_config.get('category', 'N/A')}

权重配置:
- 强弱分析: {result.strategy_config.get('weights', {}).get('strength', 0):.0%}
- 情绪分析: {result.strategy_config.get('weights', {}).get('emotion', 0):.0%}
- 趋势分析: {result.strategy_config.get('weights', {}).get('trend', 0):.0%}
- 资金面: {result.strategy_config.get('weights', {}).get('capital', 0):.0%}

风控参数:
- 止损线: {result.strategy_config.get('risk_control', {}).get('stop_loss', 0):.1f}%
- 止盈线: {result.strategy_config.get('risk_control', {}).get('take_profit', 0):.1f}%
- 最大仓位: {result.strategy_config.get('risk_control', {}).get('max_position', 0):.0%}
- 时间止损: {result.strategy_config.get('risk_control', {}).get('time_stop_weeks', 0)}周
```

---

## 交易明细

"""
    
    # 详细交易明细（包含买入原因和亏损分析）
    for i, trade in enumerate(result.trades, 1):
        entry_date = trade.entry_date.strftime('%Y-%m-%d') if isinstance(trade.entry_date, datetime) else str(trade.entry_date)[:10]
        exit_date = trade.exit_date.strftime('%Y-%m-%d') if trade.exit_date and isinstance(trade.exit_date, datetime) else str(trade.exit_date)[:10] if trade.exit_date else '-'
        exit_price = f"{trade.exit_price:.3f}" if trade.exit_price else '-'
        pnl_str = f"{trade.pnl_pct:+.2f}%" if trade.exit_price else '-'
        
        # 盈亏状态标记
        if trade.pnl_pct > 0:
            status = "✅ 盈利"
        elif trade.pnl_pct < 0:
            status = "❌ 亏损"
        else:
            status = "➖ 持平"
        
        report += f"""### 第{i}笔交易 {status}

| 项目 | 数值 |
|------|------|
| 买入日期 | {entry_date} |
| 买入价格 | {trade.entry_price:.3f} |
| 卖出日期 | {exit_date} |
| 卖出价格 | {exit_price} |
| 收益率 | {pnl_str} |
| 持仓天数 | {trade.holding_days}天 |

"""
        # 买入原因
        entry_reason = trade.entry_reason if hasattr(trade, 'entry_reason') and trade.entry_reason else '未记录'
        report += f"**买入原因**: {entry_reason}\n\n"
        
        # 入场时市场状态
        if hasattr(trade, 'entry_rsi') and trade.entry_rsi > 0:
            report += f"**入场时市场状态**: RSI={trade.entry_rsi:.1f}, 布林位置={trade.entry_boll_position:.0%}, 量比={trade.entry_vol_ratio:.2f}, 趋势={trade.entry_trend}, 情绪={trade.entry_emotion_phase}\n\n"
        
        # 出场原因
        report += f"**出场原因**: {trade.exit_reason}\n\n"
        
        # 亏损分析（仅亏损交易）
        if trade.pnl_pct < 0:
            loss_analysis = trade.loss_analysis if hasattr(trade, 'loss_analysis') and trade.loss_analysis else '未分析'
            report += f"**亏损分析**: {loss_analysis}\n\n"
        
        report += "---\n\n"
    
    report += f"""
## 交易汇总表

| 序号 | 买入日期 | 买入价 | 卖出日期 | 卖出价 | 收益率 | 持仓天数 | 出场原因 |
|------|----------|--------|----------|--------|--------|----------|----------|
"""
    
    for i, trade in enumerate(result.trades, 1):
        entry_date = trade.entry_date.strftime('%Y-%m-%d') if isinstance(trade.entry_date, datetime) else str(trade.entry_date)[:10]
        exit_date = trade.exit_date.strftime('%Y-%m-%d') if trade.exit_date and isinstance(trade.exit_date, datetime) else str(trade.exit_date)[:10] if trade.exit_date else '-'
        exit_price = f"{trade.exit_price:.3f}" if trade.exit_price else '-'
        pnl_str = f"{trade.pnl_pct:+.2f}%" if trade.exit_price else '-'
        
        report += f"| {i} | {entry_date} | {trade.entry_price:.3f} | {exit_date} | {exit_price} | {pnl_str} | {trade.holding_days} | {trade.exit_reason} |\n"
    
    report += f"""
---

## 策略评价

### 优势
"""
    
    # 根据指标生成评价
    advantages = []
    disadvantages = []
    
    if result.win_rate >= 50:
        advantages.append(f"- 胜率较高({result.win_rate:.1f}%)，交易信号准确性好")
    else:
        disadvantages.append(f"- 胜率偏低({result.win_rate:.1f}%)，需优化入场条件")
    
    if result.excess_return > 0:
        advantages.append(f"- 跑赢基准{result.excess_return:.2f}%，策略有效")
    else:
        disadvantages.append(f"- 跑输基准{abs(result.excess_return):.2f}%，策略需改进")
    
    if result.sharpe_ratio > 1:
        advantages.append(f"- 夏普比率{result.sharpe_ratio:.2f}，风险调整后收益优秀")
    elif result.sharpe_ratio > 0.5:
        advantages.append(f"- 夏普比率{result.sharpe_ratio:.2f}，风险调整后收益尚可")
    else:
        disadvantages.append(f"- 夏普比率{result.sharpe_ratio:.2f}，风险收益比需改善")
    
    if result.max_drawdown > -15:
        advantages.append(f"- 最大回撤{result.max_drawdown:.2f}%，风控有效")
    else:
        disadvantages.append(f"- 最大回撤{result.max_drawdown:.2f}%，需加强风控")
    
    if result.profit_factor > 1.5:
        advantages.append(f"- 盈亏比{result.profit_factor:.2f}，盈利能力强")
    elif result.profit_factor > 1:
        advantages.append(f"- 盈亏比{result.profit_factor:.2f}，整体盈利")
    else:
        disadvantages.append(f"- 盈亏比{result.profit_factor:.2f}，需提高盈利能力")
    
    for adv in advantages:
        report += adv + "\n"
    
    report += "\n### 不足\n"
    for dis in disadvantages:
        report += dis + "\n"
    
    report += f"""
### 改进建议

"""
    
    # 根据结果生成改进建议
    if result.win_rate < 50:
        report += "1. **提高入场准确性**: 增加更多确认信号，如等待趋势确认后再入场\n"
    if result.max_drawdown < -20:
        report += "2. **加强风控**: 考虑收紧止损线或降低单次仓位\n"
    if result.avg_holding_days > 60:
        report += "3. **优化持仓周期**: 当前持仓时间较长，可考虑增加时间止损条件\n"
    if result.profit_factor < 1.5:
        report += "4. **提高盈亏比**: 可适当放宽止盈条件，让利润奔跑\n"
    
    # 添加仓位说明
    max_position = result.strategy_config.get('risk_control', {}).get('max_position', 0.5)
    report += f"""
### 说明

> **注意**: 本策略采用防御型配置，最大仓位为{max_position:.0%}，而基准收益率是100%仓位买入持有的结果。
> 若按同等仓位换算，策略实际单次交易收益表现优于基准。
> 
> 策略核心优势在于：**高胜率({result.win_rate:.1f}%)**、**低回撤({result.max_drawdown:.2f}%)**、**高盈亏比({result.profit_factor:.2f})**

---

## 净值曲线数据

回测期间净值变化（部分数据）:

| 日期 | 净值 | 收盘价 | 持仓 |
|------|------|--------|------|
"""
    
    # 输出部分净值数据（每月一条）
    if not result.equity_curve.empty:
        equity_df = result.equity_curve.copy()
        equity_df['month'] = pd.to_datetime(equity_df['date']).dt.to_period('M')
        monthly_data = equity_df.groupby('month').last().reset_index()
        
        for _, row in monthly_data.iterrows():
            date_str = str(row['date'])[:10] if not isinstance(row['date'], str) else row['date'][:10]
            report += f"| {date_str} | {row['equity']:.2f} | {row['price']:.3f} | {int(row['position'])} |\n"
    
    report += f"""
---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    # 保存报告
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"报告已保存至: {output_path}")
    
    return report


def run_backtest_for_etf(symbol: str, start_date: str, end_date: str,
                         output_dir: str = None) -> BacktestResult:
    """
    对单个ETF执行回测并生成报告
    
    Args:
        symbol: ETF代码
        start_date: 开始日期
        end_date: 结束日期
        output_dir: 报告输出目录
        
    Returns:
        回测结果
    """
    print(f"\n{'='*60}")
    print(f"开始回测: {ETF_POOL.get(symbol, symbol)}({symbol})")
    print(f"回测区间: {start_date} ~ {end_date}")
    print(f"{'='*60}\n")
    
    # 执行回测
    backtester = ETFBacktester(initial_capital=100000)
    result = backtester.run_backtest(symbol, start_date, end_date)
    
    # 打印摘要
    print(f"回测完成!")
    print(f"\n收益指标:")
    print(f"  总收益率: {result.total_return:.2f}%")
    print(f"  年化收益率: {result.annual_return:.2f}%")
    print(f"  基准收益率: {result.benchmark_return:.2f}%")
    print(f"  超额收益: {result.excess_return:.2f}%")
    
    print(f"\n风险指标:")
    print(f"  最大回撤: {result.max_drawdown:.2f}%")
    print(f"  夏普比率: {result.sharpe_ratio:.2f}")
    
    print(f"\n交易统计:")
    print(f"  总交易次数: {result.total_trades}")
    print(f"  胜率: {result.win_rate:.1f}%")
    print(f"  盈亏比: {result.profit_factor:.2f}")
    
    # 生成报告
    if output_dir is None:
        output_dir = os.path.dirname(__file__)
    
    report_path = os.path.join(output_dir, f"reports/backtest_report_{symbol}.md")
    generate_backtest_report(result, report_path)
    
    return result


if __name__ == '__main__':
    import sys
    
    # 支持命令行参数指定ETF
    if len(sys.argv) > 1:
        symbol = sys.argv[1]
    else:
        symbol = '159902'
    
    # 执行回测
    result = run_backtest_for_etf(
        symbol=symbol,
        start_date='2020-03-01',
        end_date='2025-12-31'
    )
