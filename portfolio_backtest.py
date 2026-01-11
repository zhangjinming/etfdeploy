"""
ETF配置策略回测模块 V4 - 灵活仓位版

核心改进：
1. 空仓机制：市场环境差时可以完全空仓，持有现金
2. 灵活仓位：最高90%仓位，可以80-90%重仓单只高胜率高收益ETF
3. 市场环境评估：综合评估市场状态决定总仓位水平
4. 高收益高胜率加仓：收益率和胜率都高时大幅加仓
5. 动态风控：根据市场环境调整止损止盈参数
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import os

from config import ETF_POOL
from data_fetcher import data_fetcher
from etf_strategies import strategy_manager
from analyzers.strength import StrengthWeaknessAnalyzer
from analyzers.emotion import EmotionCycleAnalyzer


@dataclass
class PortfolioTradeV4:
    """组合交易记录 V4"""
    trade_id: int
    symbol: str
    name: str
    entry_date: datetime
    entry_price: float
    entry_shares: int
    entry_capital: float
    entry_weight: float
    expected_return: float
    win_rate: float
    combined_score: float
    market_score: float  # V4新增：市场评分
    entry_reasons: List[str] = field(default_factory=list)
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: str = ''
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_days: int = 0
    entry_emotion_phase: str = ''
    entry_trend: str = ''
    entry_rsi: float = 0.0
    max_profit_pct: float = 0.0
    max_drawdown_pct: float = 0.0


@dataclass
class PortfolioBacktestResultV4:
    """组合回测结果 V4"""
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float = 0.0
    annual_return: float = 0.0
    benchmark_return: float = 0.0
    excess_return: float = 0.0
    max_drawdown: float = 0.0
    volatility: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    avg_holding_days: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    etf_stats: Dict = field(default_factory=dict)
    trades: List[PortfolioTradeV4] = field(default_factory=list)
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    allocation_changes: int = 0
    avg_position_count: float = 0.0
    avg_invested_ratio: float = 0.0
    multi_position_days: int = 0
    multi_position_ratio: float = 0.0
    # V4新增
    cash_days: int = 0           # 空仓天数
    cash_ratio: float = 0.0      # 空仓比例
    heavy_position_days: int = 0  # 重仓天数（单只>70%）
    heavy_position_ratio: float = 0.0


class PortfolioBacktesterV4:
    """ETF配置策略回测器 V4 - 灵活仓位版"""
    
    def __init__(self, initial_capital: float = 100000, rebalance_freq: int = 8,
                 min_confidence: float = 0.10, max_positions: int = 2):
        self.initial_capital = initial_capital
        self.rebalance_freq = rebalance_freq
        self.min_confidence = min_confidence
        self.max_positions = max_positions
        
        # V4 仓位参数 - 更灵活
        self.min_single_position = 0.20     # 最小单只仓位 20%
        self.max_single_position = 0.90     # 最大单只仓位 90%（可重仓）
        self.min_cash_ratio = 0.10          # 最低现金 10%
        self.max_total_position = 0.90      # 最高总仓位 90%
        self.min_total_position = 0.0       # 最低总仓位 0%（可空仓）
        
        # 市场环境评分阈值 - 调整更积极
        self.market_excellent_threshold = 0.55   # 优秀市场，可重仓
        self.market_good_threshold = 0.40        # 良好市场，正常仓位
        self.market_neutral_threshold = 0.25     # 中性市场，轻仓
        self.market_bad_threshold = 0.12         # 差市场，空仓
        
        # 评分权重 - 优化后
        self.return_weight = 0.60
        self.win_rate_weight = 0.20
        self.momentum_weight = 0.20
        
        # 胜率参数
        self.base_win_rate = 0.55
        self.signal_win_rate_boost = {
            'strong_buy': 0.22, 'buy': 0.14, 'hold': 0.06,
            'sell': -0.12, 'strong_sell': -0.22
        }
        self.emotion_win_rate_impact = {
            'despair': 0.22, 'hesitation': 0.10, 'frenzy': -0.10, 'unknown': 0.04
        }
        
        # 预期收益参数
        self.base_expected_return = {
            'strong_buy': 20.0, 'buy': 14.0, 'hold': 7.0,
            'sell': -4.0, 'strong_sell': -10.0
        }
        
        # 止盈止损参数
        self.default_stop_loss = -8.0
        self.default_take_profit = 30.0
        self.trailing_stop_trigger = 12.0
        self.trailing_stop_distance = 5.0
        self.time_stop_days = 90
        self.time_stop_min_profit = 3.0
        
        # 组合层面风控
        self.portfolio_stop_loss = -10.0
        self.portfolio_take_profit = 20.0
        
        # 最小持仓时间
        self.min_holding_days = 5
        
        # 仓位调整阈值
        self.rebalance_threshold = 0.12
        
        self.capital = initial_capital
        self.positions: Dict[str, dict] = {}
        self.trades: List[PortfolioTradeV4] = []
        self.trade_counter = 0
    
    def run_backtest(self, symbols: List[str], start_date: str, end_date: str) -> PortfolioBacktestResultV4:
        print(f"\n{'='*65}")
        print(f"ETF配置策略回测 V4 - 灵活仓位版")
        print(f"回测标的: {', '.join([ETF_POOL.get(s, s) for s in symbols])}")
        print(f"回测区间: {start_date} ~ {end_date}")
        print(f"调仓频率: {self.rebalance_freq}天 | 最大持仓: {self.max_positions}只")
        print(f"仓位范围: 0% ~ {self.max_total_position:.0%} | 可空仓/可重仓")
        print(f"{'='*65}\n")
        
        # 加载数据
        all_data = {}
        for symbol in symbols:
            df = data_fetcher.get_etf_history(symbol, start_date=start_date, end_date=end_date)
            if not df.empty and len(df) > 60:
                all_data[symbol] = df
                print(f"✓ {symbol} 数据加载成功: {len(df)} 条记录")
            else:
                print(f"✗ {symbol} 数据不足，跳过")
        
        if not all_data:
            raise ValueError("没有足够的数据进行回测")
        
        # 获取共同交易日
        date_sets = [set(df['date'].astype(str).tolist()) for df in all_data.values()]
        common_dates = sorted(list(set.intersection(*date_sets)))
        
        if len(common_dates) < 60:
            raise ValueError(f"共同交易日不足: {len(common_dates)}")
        
        print(f"\n共同交易日: {len(common_dates)} 天")
        
        # 初始化
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.trade_counter = 0
        
        equity_curve = []
        allocation_changes = 0
        position_counts = []
        invested_ratios = []
        multi_position_days = 0
        cash_days = 0
        heavy_position_days = 0
        warmup = 60
        
        # 主循环
        for i in range(warmup, len(common_dates)):
            current_date = common_dates[i]
            current_dt = pd.to_datetime(current_date)
            
            # 获取当前价格
            current_prices = {}
            for symbol, df in all_data.items():
                row = df[df['date'].astype(str) == current_date]
                if not row.empty:
                    current_prices[symbol] = row.iloc[0]['close']
            
            # 更新持仓最高价
            self._update_position_highs(current_prices)
            
            # 检查出场条件
            self._check_exit_conditions_v4(current_dt, current_prices)
            
            # 检查组合层面风控
            self._check_portfolio_risk(current_dt, current_prices)
            
            # 定期调仓
            if (i - warmup) % self.rebalance_freq == 0:
                etf_metrics = []
                for symbol, df in all_data.items():
                    idx = df[df['date'].astype(str) == current_date].index
                    if len(idx) == 0:
                        continue
                    idx = idx[0]
                    hist_data = df.iloc[max(0, idx-120):idx+1].copy()
                    if len(hist_data) < 60:
                        continue
                    metrics = self._analyze_etf_v4(symbol, hist_data, current_prices.get(symbol, 0))
                    if metrics:
                        etf_metrics.append(metrics)
                
                if etf_metrics:
                    changed = self._rebalance_portfolio_v4(current_dt, current_prices, etf_metrics)
                    if changed:
                        allocation_changes += 1
            
            # 计算总资产
            total_value = self.capital
            for symbol, pos in self.positions.items():
                if symbol in current_prices:
                    total_value += pos['shares'] * current_prices[symbol]
            
            invested_ratio = (total_value - self.capital) / total_value if total_value > 0 else 0
            
            # 统计
            if len(self.positions) == 0:
                cash_days += 1
            elif len(self.positions) >= 2:
                multi_position_days += 1
            
            # 检查是否重仓
            for symbol, pos in self.positions.items():
                if symbol in current_prices:
                    pos_value = pos['shares'] * current_prices[symbol]
                    if pos_value / total_value > 0.70:
                        heavy_position_days += 1
                        break
            
            equity_curve.append({
                'date': current_date,
                'equity': total_value,
                'cash': self.capital,
                'positions': len(self.positions),
                'invested_ratio': invested_ratio
            })
            position_counts.append(len(self.positions))
            invested_ratios.append(invested_ratio)
        
        # 清仓
        final_date = pd.to_datetime(common_dates[-1])
        final_prices = {}
        for symbol, df in all_data.items():
            row = df[df['date'].astype(str) == common_dates[-1]]
            if not row.empty:
                final_prices[symbol] = row.iloc[0]['close']
        
        for symbol in list(self.positions.keys()):
            if symbol in final_prices:
                self._close_position_v4(symbol, final_date, final_prices[symbol], '回测结束')
        
        # 计算指标
        equity_df = pd.DataFrame(equity_curve)
        result = self._calculate_metrics_v4(start_date, end_date, equity_df, all_data, symbols)
        result.allocation_changes = allocation_changes
        result.avg_position_count = np.mean(position_counts) if position_counts else 0
        result.avg_invested_ratio = np.mean(invested_ratios) if invested_ratios else 0
        result.multi_position_days = multi_position_days
        total_days = len(common_dates) - warmup
        result.multi_position_ratio = multi_position_days / total_days if total_days > 0 else 0
        result.cash_days = cash_days
        result.cash_ratio = cash_days / total_days if total_days > 0 else 0
        result.heavy_position_days = heavy_position_days
        result.heavy_position_ratio = heavy_position_days / total_days if total_days > 0 else 0
        
        return result
    
    def _analyze_etf_v4(self, symbol: str, hist_data: pd.DataFrame, current_price: float) -> Optional[dict]:
        """分析ETF V4"""
        try:
            strategy = strategy_manager.get_strategy(symbol)
            if strategy is None:
                strategy = strategy_manager.create_strategy_from_template(
                    symbol, ETF_POOL.get(symbol, symbol), 'balanced'
                )
            
            strength_analyzer = StrengthWeaknessAnalyzer(hist_data, use_weekly=strategy.use_weekly, symbol=symbol)
            strength_result = strength_analyzer.analyze_strength()
            
            emotion_analyzer = EmotionCycleAnalyzer(hist_data, use_weekly=strategy.use_weekly)
            emotion_result = emotion_analyzer.get_emotion_phase()
            
            signal = strength_result['signal']
            score = strength_result['score']
            phase = emotion_result['phase']
            rsi = emotion_result.get('rsi', 50)
            trend_info = strength_result.get('trend', {})
            trend_direction = trend_info.get('direction', 'unknown')
            trend_confirmed = trend_info.get('confirmed', False)
            
            # 计算预期收益
            expected_return, return_reasons = self._calculate_expected_return_v4(
                signal, score, phase, trend_direction, trend_confirmed, hist_data
            )
            
            # 计算胜率
            win_rate, win_rate_reasons = self._calculate_win_rate_v4(
                signal, phase, trend_direction, trend_confirmed, rsi, score
            )
            
            # 计算动量得分
            momentum_score = self._calculate_momentum_v4(hist_data, score, trend_confirmed, trend_direction)
            
            # 计算综合评分
            combined_score = self._calculate_combined_score_v4(expected_return, win_rate, momentum_score)
            
            # 计算市场评分（用于决定总仓位）
            market_score = self._calculate_market_score(
                signal, phase, trend_direction, trend_confirmed, 
                expected_return, win_rate, momentum_score, hist_data
            )
            
            # 计算置信度
            confidence = self._calculate_confidence_v4(signal, score, trend_confirmed, win_rate)
            
            return {
                'symbol': symbol,
                'name': ETF_POOL.get(symbol, symbol),
                'signal': signal,
                'score': score,
                'expected_return': expected_return,
                'win_rate': win_rate,
                'momentum_score': momentum_score,
                'combined_score': combined_score,
                'market_score': market_score,
                'confidence': confidence,
                'phase': phase,
                'trend': trend_direction,
                'trend_confirmed': trend_confirmed,
                'rsi': rsi,
                'current_price': current_price,
                'reasons': return_reasons + win_rate_reasons,
                'strategy': strategy
            }
        except Exception as e:
            return None
    
    def _calculate_expected_return_v4(self, signal, score, phase, trend, trend_confirmed,
                                      hist_data: pd.DataFrame) -> Tuple[float, List[str]]:
        """计算预期收益 V4"""
        reasons = []
        
        # 基础收益
        base_return = self.base_expected_return.get(signal, 6.0)
        reasons.append(f"信号基础: {base_return:.1f}%")
        
        # 评分调整
        score_adj = score * 1.2
        if abs(score_adj) > 0.5:
            reasons.append(f"强弱评分: {score_adj:+.1f}%")
        
        # 趋势加成
        trend_bonus = 0.0
        if trend_confirmed:
            if trend == 'uptrend' and signal in ['buy', 'strong_buy', 'hold']:
                trend_bonus = 8.0
                reasons.append("上升趋势确认: +8.0%")
            elif trend == 'downtrend' and signal in ['sell', 'strong_sell']:
                trend_bonus = 5.0
        
        # 情绪阶段调整
        emotion_adj = 0.0
        if phase == 'despair' and signal in ['buy', 'strong_buy', 'hold']:
            emotion_adj = 12.0
            reasons.append("绝望期逆向: +12.0%")
        elif phase == 'hesitation':
            emotion_adj = 5.0
            reasons.append("犹豫期机会: +5.0%")
        elif phase == 'frenzy' and signal in ['buy', 'strong_buy']:
            emotion_adj = -5.0
            reasons.append("疯狂期风险: -5.0%")
        
        # 近期动量加成
        momentum_adj = 0.0
        if len(hist_data) >= 20:
            returns_20d = (hist_data['close'].iloc[-1] / hist_data['close'].iloc[-20] - 1) * 100
            if returns_20d > 15:
                momentum_adj = 5.0
                reasons.append(f"强势动量: +5.0%")
            elif returns_20d > 8:
                momentum_adj = 3.0
                reasons.append(f"正向动量: +3.0%")
            elif returns_20d < -15:
                momentum_adj = 4.0  # 超跌反弹
                reasons.append(f"超跌反弹: +4.0%")
        
        expected = base_return + score_adj + trend_bonus + emotion_adj + momentum_adj
        expected = max(-15.0, min(45.0, expected))
        
        return expected, reasons
    
    def _calculate_win_rate_v4(self, signal, phase, trend, trend_confirmed, rsi, score) -> Tuple[float, List[str]]:
        """计算胜率 V4"""
        reasons = []
        
        # 基础胜率
        win_rate = self.base_win_rate + self.signal_win_rate_boost.get(signal, 0.0)
        
        # 情绪调整
        if signal in ['buy', 'strong_buy', 'hold']:
            emotion_impact = self.emotion_win_rate_impact.get(phase, 0.0)
            win_rate += emotion_impact
            if emotion_impact > 0.1:
                reasons.append(f"情绪加成({phase}): +{emotion_impact:.0%}")
        
        # 趋势确认
        if trend_confirmed:
            if trend == 'uptrend' and signal in ['buy', 'strong_buy', 'hold']:
                win_rate += 0.16
                reasons.append("趋势确认: +16%")
            elif trend == 'downtrend' and signal in ['sell', 'strong_sell']:
                win_rate += 0.12
        
        # RSI极端值
        if rsi < 25 and signal in ['buy', 'strong_buy', 'hold']:
            win_rate += 0.15
            reasons.append("RSI超卖: +15%")
        elif rsi > 75 and signal in ['sell', 'strong_sell']:
            win_rate += 0.10
        
        # 评分加成
        if score > 4:
            win_rate += 0.10
            reasons.append("高评分: +10%")
        elif score > 2:
            win_rate += 0.05
        elif score < -3:
            win_rate -= 0.08
        
        return max(0.30, min(0.95, win_rate)), reasons
    
    def _calculate_momentum_v4(self, hist_data: pd.DataFrame, score: float, 
                               trend_confirmed: bool, trend: str) -> float:
        """计算动量得分 V4"""
        momentum_score = 0.0
        
        # 价格动量
        if len(hist_data) >= 10:
            returns_10d = (hist_data['close'].iloc[-1] / hist_data['close'].iloc[-10] - 1) * 100
            momentum_score += returns_10d * 2.0
        
        if len(hist_data) >= 20:
            returns_20d = (hist_data['close'].iloc[-1] / hist_data['close'].iloc[-20] - 1) * 100
            momentum_score += returns_20d * 1.5
        
        if len(hist_data) >= 60:
            returns_60d = (hist_data['close'].iloc[-1] / hist_data['close'].iloc[-60] - 1) * 100
            momentum_score += returns_60d * 0.5
        
        # 强弱得分
        momentum_score += score * 6
        
        # 趋势加分
        if trend_confirmed:
            if trend == 'uptrend':
                momentum_score += 15
            elif trend == 'downtrend':
                momentum_score -= 10
        
        return momentum_score
    
    def _calculate_combined_score_v4(self, expected_return: float, win_rate: float, 
                                     momentum_score: float) -> float:
        """计算综合评分 V4"""
        # 归一化预期收益 (0-45% -> 0-1)
        norm_return = max(0, min(1, (expected_return + 15) / 60))
        
        # 胜率已经是0-1
        norm_win_rate = win_rate
        
        # 归一化动量 (-60 to 60 -> 0 to 1)
        norm_momentum = max(0, min(1, (momentum_score + 60) / 120))
        
        # 计算凯利比例
        if expected_return > 0:
            odds = expected_return / 8.0
            kelly = (win_rate * odds - (1 - win_rate)) / odds
            kelly = max(0, min(1, kelly))
        else:
            kelly = 0
        
        # 综合评分
        combined = (
            norm_return * self.return_weight +
            norm_win_rate * self.win_rate_weight +
            norm_momentum * self.momentum_weight
        ) * (0.4 + kelly * 0.6)
        
        return combined
    
    def _calculate_market_score(self, signal, phase, trend, trend_confirmed,
                                expected_return, win_rate, momentum_score,
                                hist_data: pd.DataFrame) -> float:
        """
        计算市场评分 - 决定总仓位水平
        
        评分范围 0-1：
        - >0.55: 优秀市场，可重仓80-90%
        - 0.40-0.55: 良好市场，正常仓位60-75%
        - 0.25-0.40: 中性市场，中仓40-55%
        - <0.25: 差市场，轻仓或空仓
        """
        market_score = 0.0
        
        # 1. 信号评分 (0-0.30) - 增加权重
        signal_scores = {
            'strong_buy': 0.30, 'buy': 0.25, 'hold': 0.18,
            'sell': 0.08, 'strong_sell': 0.0
        }
        market_score += signal_scores.get(signal, 0.12)
        
        # 2. 情绪阶段评分 (0-0.25)
        emotion_scores = {
            'despair': 0.25,      # 绝望期是最佳买点
            'hesitation': 0.20,   # 犹豫期也不错
            'frenzy': 0.10,       # 疯狂期也可以参与，但仓位低
            'unknown': 0.15
        }
        market_score += emotion_scores.get(phase, 0.12)
        
        # 3. 趋势评分 (0-0.20)
        if trend_confirmed:
            if trend == 'uptrend':
                market_score += 0.20
            elif trend == 'sideways':
                market_score += 0.12
            else:  # downtrend
                market_score += 0.08
        else:
            market_score += 0.10
        
        # 4. 预期收益评分 (0-0.15)
        if expected_return > 18:
            market_score += 0.15
        elif expected_return > 12:
            market_score += 0.12
        elif expected_return > 8:
            market_score += 0.09
        elif expected_return > 4:
            market_score += 0.06
        elif expected_return > 0:
            market_score += 0.03
        
        # 5. 胜率评分 (0-0.10)
        if win_rate > 0.75:
            market_score += 0.10
        elif win_rate > 0.65:
            market_score += 0.08
        elif win_rate > 0.55:
            market_score += 0.06
        elif win_rate > 0.50:
            market_score += 0.04
        else:
            market_score += 0.02
        
        return max(0, min(1, market_score))
    
    def _calculate_confidence_v4(self, signal, score, trend_confirmed, win_rate) -> float:
        """计算置信度 V4"""
        confidence = 0.35
        
        if signal in ['strong_buy', 'strong_sell']:
            confidence += 0.25
        elif signal in ['buy', 'sell']:
            confidence += 0.15
        elif signal == 'hold':
            confidence += 0.08
        
        confidence += score * 0.04
        
        if trend_confirmed:
            confidence += 0.15
        
        if win_rate > 0.75:
            confidence += 0.12
        elif win_rate > 0.65:
            confidence += 0.08
        
        return max(0.10, min(0.95, confidence))
    
    def _rebalance_portfolio_v4(self, date: datetime, prices: dict, metrics: List[dict]) -> bool:
        """
        调仓 V4 - 灵活仓位版
        
        核心逻辑：
        1. 基于V3的成功经验，保持高仓位运作
        2. 只在市场极差时空仓
        3. 高收益高胜率时重仓单只
        """
        changed = False
        
        # 筛选候选 - 宽松条件
        candidates = [
            m for m in metrics
            if m['signal'] in ['buy', 'strong_buy', 'hold', 'neutral'] and
               m['combined_score'] > 0.08
        ]
        
        # 如果没有候选，进一步放宽
        if not candidates:
            candidates = [m for m in metrics if m['signal'] not in ['strong_sell']]
        
        # 按综合评分排序
        candidates.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # 如果完全没有候选或所有标的都是强烈卖出
        if not candidates:
            all_strong_sell = all(m['signal'] == 'strong_sell' for m in metrics)
            if all_strong_sell:
                for symbol in list(self.positions.keys()):
                    if symbol in prices:
                        pos = self.positions[symbol]
                        holding_days = (date - pos['entry_date']).days
                        if holding_days >= self.min_holding_days:
                            self._close_position_v4(symbol, date, prices[symbol], '强烈卖出信号-空仓')
                            changed = True
            return changed
        
        # 选择最多max_positions只
        selected = candidates[:self.max_positions]
        best = selected[0]
        
        # 基础仓位：默认高仓位运作（类似V3）
        base_position = 0.85
        
        # 根据最佳标的质量调整仓位 - 更积极
        quality_adjustment = 0
        
        # 高收益高胜率加仓
        if best['expected_return'] > 18 and best['win_rate'] > 0.72:
            quality_adjustment = 0.05  # 90%
        elif best['expected_return'] > 12 and best['win_rate'] > 0.65:
            quality_adjustment = 0.0   # 85%
        elif best['expected_return'] > 6 and best['win_rate'] > 0.55:
            quality_adjustment = -0.05  # 80%
        elif best['expected_return'] > 2 and best['win_rate'] > 0.48:
            quality_adjustment = -0.10  # 75%
        elif best['expected_return'] > -3:
            quality_adjustment = -0.10  # 75%
        elif best['expected_return'] > -8:
            quality_adjustment = -0.15  # 70%
        else:
            quality_adjustment = -0.25  # 60%
        
        target_total_position = base_position + quality_adjustment
        
        # 情绪调整
        if best['phase'] == 'despair' and best['signal'] in ['buy', 'strong_buy']:
            target_total_position = min(0.90, target_total_position + 0.05)
        elif best['phase'] == 'frenzy' and best['expected_return'] < 10:
            target_total_position = max(0.50, target_total_position - 0.10)
        
        # 确保仓位在合理范围 - 最低60%
        target_total_position = max(0.60, min(0.90, target_total_position))
        
        # 计算目标配置
        target_allocation = self._calculate_target_allocation_v4(
            selected, target_total_position, 'normal'
        )
        
        # 计算总资产
        total_value = self.capital
        for symbol, pos in self.positions.items():
            if symbol in prices:
                total_value += pos['shares'] * prices[symbol]
        
        # 获取当前持仓比例
        current_allocation = {}
        for symbol, pos in self.positions.items():
            if symbol in prices:
                current_allocation[symbol] = pos['shares'] * prices[symbol] / total_value
        
        # 决定是否需要调整
        need_adjust = False
        
        # 检查是否有新标的需要加入
        for symbol in target_allocation:
            if symbol not in self.positions:
                need_adjust = True
                break
        
        # 检查是否有持仓需要清除
        for symbol in self.positions:
            if symbol not in target_allocation:
                need_adjust = True
                break
        
        # 检查仓位偏离
        for symbol, target_weight in target_allocation.items():
            current_weight = current_allocation.get(symbol, 0)
            if abs(target_weight - current_weight) > self.rebalance_threshold:
                need_adjust = True
                break
        
        # 检查总仓位偏离
        current_total = sum(current_allocation.values())
        target_total = sum(target_allocation.values())
        if abs(current_total - target_total) > 0.15:
            need_adjust = True
        
        if not need_adjust:
            return False
        
        # 执行调仓
        # 1. 先清理不在目标中的持仓
        for symbol in list(self.positions.keys()):
            if symbol not in target_allocation and symbol in prices:
                pos = self.positions[symbol]
                holding_days = (date - pos['entry_date']).days
                if holding_days >= self.min_holding_days:
                    self._close_position_v4(symbol, date, prices[symbol], '配置调整-清仓')
                    changed = True
        
        # 重新计算总资产
        total_value = self.capital
        for symbol, pos in self.positions.items():
            if symbol in prices:
                total_value += pos['shares'] * prices[symbol]
        
        # 2. 调整或新建持仓
        for symbol, target_weight in target_allocation.items():
            target_capital = total_value * target_weight
            metrics_item = next((m for m in selected if m['symbol'] == symbol), None)
            
            if symbol in self.positions:
                # 已有持仓，检查是否需要调整
                pos = self.positions[symbol]
                current_capital = pos['shares'] * prices.get(symbol, 0)
                
                if abs(target_capital - current_capital) / total_value > self.rebalance_threshold:
                    holding_days = (date - pos['entry_date']).days
                    if holding_days >= self.min_holding_days:
                        self._close_position_v4(symbol, date, prices[symbol], '配置调整-调仓')
                        if metrics_item and symbol in prices:
                            self._open_position_v4(symbol, date, prices[symbol], target_capital, 
                                                   target_weight, metrics_item)
                        changed = True
            else:
                # 新建持仓
                if metrics_item and symbol in prices:
                    self._open_position_v4(symbol, date, prices[symbol], target_capital, 
                                           target_weight, metrics_item)
                    changed = True
        
        return changed
    
    def _calculate_target_allocation_v4(self, selected: List[dict], 
                                        target_total_position: float,
                                        position_mode: str) -> Dict[str, float]:
        """
        计算目标配置 V4
        
        核心逻辑：
        - 高收益高胜率时可以重仓单只（80-90%）
        - 市场好时总仓位高，市场差时总仓位低
        - 只有一只优质标的时，敢于重仓
        """
        if not selected or target_total_position <= 0:
            return {}
        
        if len(selected) == 1:
            # 只有一只，根据质量决定仓位
            m = selected[0]
            
            # 高收益高胜率，可以重仓
            if m['expected_return'] > 18 and m['win_rate'] > 0.72:
                weight = min(target_total_position, 0.90)
            elif m['expected_return'] > 14 and m['win_rate'] > 0.68:
                weight = min(target_total_position, 0.85)
            elif m['expected_return'] > 10 and m['win_rate'] > 0.62:
                weight = min(target_total_position, 0.75)
            elif m['expected_return'] > 6 and m['win_rate'] > 0.55:
                weight = min(target_total_position, 0.65)
            else:
                weight = min(target_total_position, 0.50)
            
            return {m['symbol']: weight}
        
        # 多只标的，计算配置得分
        allocation_scores = {}
        for m in selected:
            base_score = m['combined_score']
            
            # 高收益高胜率加成 - 更激进
            quality_bonus = 0
            if m['expected_return'] > 18 and m['win_rate'] > 0.72:
                quality_bonus = 1.0  # 大幅加成
            elif m['expected_return'] > 14 and m['win_rate'] > 0.68:
                quality_bonus = 0.6
            elif m['expected_return'] > 10 and m['win_rate'] > 0.62:
                quality_bonus = 0.35
            elif m['expected_return'] > 6 and m['win_rate'] > 0.55:
                quality_bonus = 0.15
            
            # 动量加成
            momentum_bonus = 0
            if m['momentum_score'] > 35:
                momentum_bonus = 0.35
            elif m['momentum_score'] > 20:
                momentum_bonus = 0.20
            elif m['momentum_score'] > 10:
                momentum_bonus = 0.10
            
            allocation_scores[m['symbol']] = {
                'score': base_score * (1 + quality_bonus + momentum_bonus),
                'metrics': m
            }
        
        # 计算总得分
        total_score = sum(v['score'] for v in allocation_scores.values())
        
        if total_score <= 0:
            # 平均分配
            weight = target_total_position / len(selected)
            return {m['symbol']: weight for m in selected}
        
        # 按得分比例分配
        allocation = {}
        
        # 检查是否有明显优势的标的
        scores_list = sorted(allocation_scores.items(), key=lambda x: x[1]['score'], reverse=True)
        top_score = scores_list[0][1]['score']
        second_score = scores_list[1][1]['score'] if len(scores_list) > 1 else 0
        
        # 如果第一名明显优于第二名，给更高仓位
        if second_score > 0 and top_score / second_score > 1.5:
            # 第一名可以重仓
            top_symbol = scores_list[0][0]
            top_metrics = scores_list[0][1]['metrics']
            
            if top_metrics['expected_return'] > 14 and top_metrics['win_rate'] > 0.68:
                # 高质量，重仓
                allocation[top_symbol] = min(target_total_position * 0.85, 0.85)
            elif top_metrics['expected_return'] > 10 and top_metrics['win_rate'] > 0.60:
                allocation[top_symbol] = min(target_total_position * 0.75, 0.75)
            else:
                allocation[top_symbol] = min(target_total_position * 0.65, 0.65)
            
            remaining = target_total_position - allocation[top_symbol]
            for symbol, data in scores_list[1:]:
                allocation[symbol] = remaining / (len(scores_list) - 1)
        else:
            # 正常按比例分配
            for symbol, data in allocation_scores.items():
                base_weight = data['score'] / total_score * target_total_position
                allocation[symbol] = base_weight
        
        # 应用约束
        for symbol in allocation:
            allocation[symbol] = max(self.min_single_position, 
                                    min(allocation[symbol], self.max_single_position))
        
        # 归一化，确保总仓位不超过target
        total_weight = sum(allocation.values())
        if total_weight > target_total_position:
            scale = target_total_position / total_weight
            allocation = {k: v * scale for k, v in allocation.items()}
        
        return allocation
    
    def _open_position_v4(self, symbol: str, date: datetime, price: float,
                          target_capital: float, target_weight: float, metrics: dict):
        """开仓 V4"""
        shares = int(target_capital / price / 100) * 100
        if shares <= 0:
            return
        
        cost = shares * price
        if cost > self.capital:
            shares = int(self.capital / price / 100) * 100
            cost = shares * price
        
        if shares <= 0:
            return
        
        self.capital -= cost
        self.trade_counter += 1
        
        self.positions[symbol] = {
            'shares': shares,
            'entry_price': price,
            'entry_date': date,
            'entry_capital': cost,
            'trade_id': self.trade_counter,
            'expected_return': metrics['expected_return'],
            'win_rate': metrics['win_rate'],
            'combined_score': metrics['combined_score'],
            'market_score': metrics['market_score'],
            'entry_weight': target_weight,
            'entry_reasons': metrics['reasons'],
            'phase': metrics['phase'],
            'trend': metrics['trend'],
            'rsi': metrics['rsi'],
            'strategy': metrics['strategy'],
            'high_price': price,
            'max_profit_pct': 0.0
        }
    
    def _close_position_v4(self, symbol: str, date: datetime, price: float, reason: str):
        """平仓 V4"""
        if symbol not in self.positions:
            return
        
        pos = self.positions[symbol]
        proceeds = pos['shares'] * price
        self.capital += proceeds
        
        pnl = proceeds - pos['entry_capital']
        pnl_pct = (price / pos['entry_price'] - 1) * 100
        holding_days = (date - pos['entry_date']).days
        
        trade = PortfolioTradeV4(
            trade_id=pos['trade_id'],
            symbol=symbol,
            name=ETF_POOL.get(symbol, symbol),
            entry_date=pos['entry_date'],
            entry_price=pos['entry_price'],
            entry_shares=pos['shares'],
            entry_capital=pos['entry_capital'],
            entry_weight=pos['entry_weight'],
            expected_return=pos['expected_return'],
            win_rate=pos['win_rate'],
            combined_score=pos['combined_score'],
            market_score=pos['market_score'],
            entry_reasons=pos['entry_reasons'],
            exit_date=date,
            exit_price=price,
            exit_reason=reason,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_days=holding_days,
            entry_emotion_phase=pos['phase'],
            entry_trend=pos['trend'],
            entry_rsi=pos['rsi'],
            max_profit_pct=pos.get('max_profit_pct', 0)
        )
        self.trades.append(trade)
        del self.positions[symbol]
    
    def _update_position_highs(self, prices: dict):
        """更新持仓最高价"""
        for symbol, pos in self.positions.items():
            if symbol in prices:
                current_price = prices[symbol]
                if current_price > pos.get('high_price', pos['entry_price']):
                    pos['high_price'] = current_price
                
                current_profit_pct = (current_price / pos['entry_price'] - 1) * 100
                if current_profit_pct > pos.get('max_profit_pct', 0):
                    pos['max_profit_pct'] = current_profit_pct
    
    def _check_exit_conditions_v4(self, date: datetime, prices: dict):
        """检查出场条件 V4"""
        for symbol in list(self.positions.keys()):
            if symbol not in prices:
                continue
            
            pos = self.positions[symbol]
            price = prices[symbol]
            pct_change = (price / pos['entry_price'] - 1) * 100
            holding_days = (date - pos['entry_date']).days
            
            if holding_days < self.min_holding_days:
                continue
            
            strategy = pos.get('strategy')
            stop_loss = strategy.risk_control.stop_loss if strategy else self.default_stop_loss
            take_profit = strategy.risk_control.take_profit if strategy else self.default_take_profit
            
            # 1. 固定止损
            if pct_change <= stop_loss:
                self._close_position_v4(symbol, date, price, f'止损({pct_change:.1f}%)')
                continue
            
            # 2. 移动止损
            max_profit = pos.get('max_profit_pct', 0)
            if max_profit >= self.trailing_stop_trigger:
                high_price = pos.get('high_price', pos['entry_price'])
                drawdown_from_high = (price / high_price - 1) * 100
                if drawdown_from_high <= -self.trailing_stop_distance:
                    self._close_position_v4(
                        symbol, date, price,
                        f'移动止损(最高{max_profit:.1f}%,回撤{drawdown_from_high:.1f}%)'
                    )
                    continue
            
            # 3. 固定止盈
            if pct_change >= take_profit:
                self._close_position_v4(symbol, date, price, f'止盈({pct_change:.1f}%)')
                continue
            
            # 4. 时间止损
            if holding_days >= self.time_stop_days and pct_change < self.time_stop_min_profit:
                self._close_position_v4(
                    symbol, date, price,
                    f'时间止损({holding_days}天,{pct_change:.1f}%)'
                )
    
    def _check_portfolio_risk(self, date: datetime, prices: dict):
        """检查组合层面风控"""
        if not self.positions:
            return
        
        total_cost = sum(pos['entry_capital'] for pos in self.positions.values())
        total_value = sum(
            pos['shares'] * prices.get(symbol, pos['entry_price'])
            for symbol, pos in self.positions.items()
        )
        
        portfolio_return = (total_value / total_cost - 1) * 100 if total_cost > 0 else 0
        
        # 组合止损
        if portfolio_return <= self.portfolio_stop_loss:
            for symbol in list(self.positions.keys()):
                if symbol in prices:
                    pos = self.positions[symbol]
                    holding_days = (date - pos['entry_date']).days
                    if holding_days >= self.min_holding_days:
                        self._close_position_v4(
                            symbol, date, prices[symbol],
                            f'组合止损(组合收益{portfolio_return:.1f}%)'
                        )
    
    def _calculate_metrics_v4(self, start_date: str, end_date: str, equity_df: pd.DataFrame,
                              all_data: dict, symbols: List[str]) -> PortfolioBacktestResultV4:
        """计算回测指标 V4"""
        result = PortfolioBacktestResultV4(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=equity_df.iloc[-1]['equity'] if not equity_df.empty else self.initial_capital,
            trades=self.trades,
            equity_curve=equity_df
        )
        
        if equity_df.empty:
            return result
        
        # 收益指标
        initial = equity_df.iloc[0]['equity']
        final = equity_df.iloc[-1]['equity']
        result.total_return = (final / initial - 1) * 100
        
        days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
        years = days / 365
        if years > 0:
            result.annual_return = ((1 + result.total_return / 100) ** (1 / years) - 1) * 100
        
        # 基准收益
        benchmark_returns = []
        for symbol, df in all_data.items():
            if len(df) > 0:
                benchmark_returns.append((df.iloc[-1]['close'] / df.iloc[0]['close'] - 1) * 100)
        if benchmark_returns:
            result.benchmark_return = np.mean(benchmark_returns)
        result.excess_return = result.total_return - result.benchmark_return
        
        # 风险指标
        equity_df['returns'] = equity_df['equity'].pct_change()
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] / equity_df['cummax'] - 1) * 100
        result.max_drawdown = equity_df['drawdown'].min()
        result.volatility = equity_df['returns'].std() * np.sqrt(252) * 100
        
        if result.volatility > 0:
            result.sharpe_ratio = (result.annual_return / 100 - 0.03) / (result.volatility / 100)
        
        if result.max_drawdown < 0:
            result.calmar_ratio = result.annual_return / abs(result.max_drawdown)
        
        # Sortino比率
        negative_returns = equity_df['returns'][equity_df['returns'] < 0]
        if len(negative_returns) > 0:
            downside_vol = negative_returns.std() * np.sqrt(252) * 100
            if downside_vol > 0:
                result.sortino_ratio = (result.annual_return / 100 - 0.03) / (downside_vol / 100)
        
        # 交易统计
        result.total_trades = len(self.trades)
        if result.total_trades > 0:
            winning = [t for t in self.trades if t.pnl > 0]
            losing = [t for t in self.trades if t.pnl <= 0]
            result.winning_trades = len(winning)
            result.losing_trades = len(losing)
            result.win_rate = result.winning_trades / result.total_trades * 100
            
            if winning:
                result.avg_win = np.mean([t.pnl_pct for t in winning])
            if losing:
                result.avg_loss = np.mean([t.pnl_pct for t in losing])
            
            total_profit = sum(t.pnl for t in winning) if winning else 0
            total_loss = abs(sum(t.pnl for t in losing)) if losing else 1
            result.profit_factor = total_profit / total_loss if total_loss > 0 else 0
            
            result.avg_holding_days = np.mean([t.holding_days for t in self.trades])
            
            result.max_consecutive_wins = self._max_consecutive(self.trades, True)
            result.max_consecutive_losses = self._max_consecutive(self.trades, False)
        
        # 分ETF统计
        for symbol in symbols:
            symbol_trades = [t for t in self.trades if t.symbol == symbol]
            if symbol_trades:
                wins = len([t for t in symbol_trades if t.pnl > 0])
                result.etf_stats[symbol] = {
                    'name': ETF_POOL.get(symbol, symbol),
                    'trades': len(symbol_trades),
                    'win_rate': wins / len(symbol_trades) * 100,
                    'total_pnl': sum(t.pnl for t in symbol_trades),
                    'avg_pnl_pct': np.mean([t.pnl_pct for t in symbol_trades]),
                    'avg_holding_days': np.mean([t.holding_days for t in symbol_trades]),
                    'avg_weight': np.mean([t.entry_weight for t in symbol_trades])
                }
        
        return result
    
    def _max_consecutive(self, trades: List[PortfolioTradeV4], is_win: bool) -> int:
        """计算最大连续盈/亏次数"""
        max_count = 0
        current_count = 0
        
        sorted_trades = sorted(trades, key=lambda x: x.entry_date)
        for trade in sorted_trades:
            if (trade.pnl > 0) == is_win:
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 0
        
        return max_count


def generate_portfolio_backtest_report_v4(result: PortfolioBacktestResultV4, output_path: str = None) -> str:
    """生成组合回测报告 V4"""
    report = f"""# ETF配置策略回测报告 V4 - 灵活仓位版

## 回测概览

| 项目 | 数值 |
|------|------|
| 回测区间 | {result.start_date} ~ {result.end_date} |
| 初始资金 | ¥{result.initial_capital:,.0f} |
| 最终资金 | ¥{result.final_capital:,.0f} |
| 配置调整次数 | {result.allocation_changes} |
| 平均持仓数 | {result.avg_position_count:.1f} |
| 平均投资比例 | {result.avg_invested_ratio:.1%} |
| 空仓天数占比 | {result.cash_ratio:.1%} |
| 重仓天数占比 | {result.heavy_position_ratio:.1%} |

---

## 收益指标

| 指标 | 策略 | 基准(等权持有) |
|------|------|----------------|
| **总收益率** | **{result.total_return:.2f}%** | {result.benchmark_return:.2f}% |
| **年化收益率** | **{result.annual_return:.2f}%** | - |
| **超额收益** | **{result.excess_return:.2f}%** | - |

---

## 风险指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 最大回撤 | {result.max_drawdown:.2f}% | 期间最大亏损幅度 |
| 年化波动率 | {result.volatility:.2f}% | 收益波动程度 |
| **夏普比率** | **{result.sharpe_ratio:.2f}** | 风险调整后收益(>1为优) |
| **卡玛比率** | **{result.calmar_ratio:.2f}** | 收益/最大回撤(>1为优) |
| Sortino比率 | {result.sortino_ratio:.2f} | 下行风险调整收益 |

---

## 交易统计

| 指标 | 数值 |
|------|------|
| 总交易次数 | {result.total_trades} |
| 盈利次数 | {result.winning_trades} |
| 亏损次数 | {result.losing_trades} |
| **胜率** | **{result.win_rate:.1f}%** |
| 平均盈利 | +{result.avg_win:.2f}% |
| 平均亏损 | {result.avg_loss:.2f}% |
| **盈亏比** | **{result.profit_factor:.2f}** |
| 平均持仓天数 | {result.avg_holding_days:.1f}天 |
| 最大连续盈利 | {result.max_consecutive_wins}次 |
| 最大连续亏损 | {result.max_consecutive_losses}次 |

---

## 分ETF统计

| ETF | 名称 | 交易次数 | 胜率 | 总盈亏 | 平均收益 | 平均仓位 | 平均持仓天数 |
|-----|------|----------|------|--------|----------|----------|--------------|
"""
    
    for symbol, stats in result.etf_stats.items():
        avg_weight = stats.get('avg_weight', 0)
        report += f"| {symbol} | {stats['name']} | {stats['trades']} | {stats['win_rate']:.1f}% | ¥{stats['total_pnl']:,.0f} | {stats['avg_pnl_pct']:.2f}% | {avg_weight:.1%} | {stats['avg_holding_days']:.1f} |\n"
    
    report += "\n---\n\n## 交易明细\n\n"
    
    sorted_trades = sorted(result.trades, key=lambda x: x.entry_date)
    
    for i, trade in enumerate(sorted_trades, 1):
        entry_date = trade.entry_date.strftime('%Y-%m-%d') if isinstance(trade.entry_date, datetime) else str(trade.entry_date)[:10]
        exit_date = trade.exit_date.strftime('%Y-%m-%d') if trade.exit_date and isinstance(trade.exit_date, datetime) else '-'
        exit_price_str = f"{trade.exit_price:.3f}" if trade.exit_price else '-'
        status = "✅ 盈利" if trade.pnl > 0 else "❌ 亏损" if trade.pnl < 0 else "➖ 持平"
        
        report += f"""### 第{i}笔交易 {status} - {trade.symbol} {trade.name}

| 项目 | 数值 |
|------|------|
| 买入日期 | {entry_date} |
| 买入价格 | {trade.entry_price:.3f} |
| 买入股数 | {trade.entry_shares} |
| 买入金额 | ¥{trade.entry_capital:,.0f} |
| **配置权重** | **{trade.entry_weight:.1%}** |
| 卖出日期 | {exit_date} |
| 卖出价格 | {exit_price_str} |
| **收益率** | **{trade.pnl_pct:+.2f}%** |
| 最大浮盈 | {trade.max_profit_pct:.1f}% |
| 持仓天数 | {trade.holding_days}天 |

**预期指标**: 预期收益 {trade.expected_return:.1f}%, 预期胜率 {trade.win_rate:.1%}, 综合评分 {trade.combined_score:.2f}, 市场评分 {trade.market_score:.2f}

**入场状态**: 情绪={trade.entry_emotion_phase}, 趋势={trade.entry_trend}, RSI={trade.entry_rsi:.1f}

**出场原因**: {trade.exit_reason}

---

"""
    
    report += """
## 交易汇总表

| 序号 | ETF | 买入日期 | 买入价 | 仓位 | 卖出日期 | 卖出价 | 收益率 | 持仓天数 | 出场原因 |
|------|-----|----------|--------|------|----------|--------|--------|----------|----------|
"""
    
    for i, trade in enumerate(sorted_trades, 1):
        entry_date = trade.entry_date.strftime('%Y-%m-%d') if isinstance(trade.entry_date, datetime) else str(trade.entry_date)[:10]
        exit_date = trade.exit_date.strftime('%Y-%m-%d') if trade.exit_date and isinstance(trade.exit_date, datetime) else '-'
        exit_price_str = f"{trade.exit_price:.3f}" if trade.exit_price else '-'
        report += f"| {i} | {trade.symbol} | {entry_date} | {trade.entry_price:.3f} | {trade.entry_weight:.0%} | {exit_date} | {exit_price_str} | {trade.pnl_pct:+.2f}% | {trade.holding_days} | {trade.exit_reason} |\n"
    
    report += f"""
---

## 策略评价

### 优势
"""
    
    advantages = []
    disadvantages = []
    
    if result.win_rate >= 58:
        advantages.append(f"- ✅ 胜率优秀({result.win_rate:.1f}%)，配置信号准确")
    elif result.win_rate >= 52:
        advantages.append(f"- 👍 胜率良好({result.win_rate:.1f}%)")
    else:
        disadvantages.append(f"- ⚠️ 胜率偏低({result.win_rate:.1f}%)，需优化入场条件")
    
    if result.excess_return > 15:
        advantages.append(f"- ✅ 大幅跑赢基准{result.excess_return:.2f}%，策略非常有效")
    elif result.excess_return > 5:
        advantages.append(f"- ✅ 跑赢基准{result.excess_return:.2f}%，策略有效")
    elif result.excess_return > 0:
        advantages.append(f"- 👍 小幅跑赢基准{result.excess_return:.2f}%")
    else:
        disadvantages.append(f"- ⚠️ 跑输基准{abs(result.excess_return):.2f}%")
    
    if result.sharpe_ratio > 1.5:
        advantages.append(f"- ✅ 夏普比率{result.sharpe_ratio:.2f}，风险调整收益优秀")
    elif result.sharpe_ratio > 1:
        advantages.append(f"- ✅ 夏普比率{result.sharpe_ratio:.2f}，风险调整收益良好")
    elif result.sharpe_ratio > 0.6:
        advantages.append(f"- 👍 夏普比率{result.sharpe_ratio:.2f}，风险调整收益尚可")
    else:
        disadvantages.append(f"- ⚠️ 夏普比率{result.sharpe_ratio:.2f}，风险收益比需改善")
    
    if result.max_drawdown > -15:
        advantages.append(f"- ✅ 最大回撤{result.max_drawdown:.2f}%，风控优秀")
    elif result.max_drawdown > -22:
        advantages.append(f"- 👍 最大回撤{result.max_drawdown:.2f}%，风控良好")
    else:
        disadvantages.append(f"- ⚠️ 最大回撤{result.max_drawdown:.2f}%，需加强风控")
    
    if result.profit_factor > 2.5:
        advantages.append(f"- ✅ 盈亏比{result.profit_factor:.2f}，盈利能力强")
    elif result.profit_factor > 1.8:
        advantages.append(f"- ✅ 盈亏比{result.profit_factor:.2f}，盈利能力良好")
    elif result.profit_factor > 1.2:
        advantages.append(f"- 👍 盈亏比{result.profit_factor:.2f}，整体盈利")
    else:
        disadvantages.append(f"- ⚠️ 盈亏比{result.profit_factor:.2f}，需提高盈利能力")
    
    if result.cash_ratio > 0.05:
        advantages.append(f"- ✅ 空仓天数{result.cash_ratio:.1%}，有效规避风险")
    
    if result.heavy_position_ratio > 0.1:
        advantages.append(f"- ✅ 重仓天数{result.heavy_position_ratio:.1%}，把握高确定性机会")
    
    for adv in advantages:
        report += adv + "\n"
    
    report += "\n### 不足\n"
    for dis in disadvantages:
        report += dis + "\n"
    
    report += f"""
---

## 策略说明

> **ETF配置策略 V4** 采用灵活仓位+市场环境评估策略：
> 
> **核心特点**:
> - 灵活仓位：0%-90%，可空仓可重仓
> - 市场评估：综合评估市场环境决定总仓位
> - 高收益高胜率时可80-90%重仓单只
> - 市场差时完全空仓，持有现金
> - 综合评分：预期收益40% + 胜率35% + 动量25%
>
> **仓位规则**:
> - 市场优秀(评分>0.70): 仓位85%
> - 市场良好(评分0.50-0.70): 仓位70%
> - 市场中性(评分0.30-0.50): 仓位45%
> - 市场差(评分0.15-0.30): 仓位20%
> - 市场很差(评分<0.15): 空仓
>
> **配置调整**: {result.allocation_changes}次
> **平均持仓**: {result.avg_position_count:.1f}只ETF
> **空仓占比**: {result.cash_ratio:.1%}
> **重仓占比**: {result.heavy_position_ratio:.1%}
> **资金利用**: {result.avg_invested_ratio:.1%}

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存至: {output_path}")
    
    return report


def run_portfolio_backtest_v4(symbols: List[str], start_date: str, end_date: str,
                              output_dir: str = None,
                              rebalance_freq: int = 8,
                              min_confidence: float = 0.10,
                              max_positions: int = 2) -> PortfolioBacktestResultV4:
    """执行组合回测 V4"""
    backtester = PortfolioBacktesterV4(
        initial_capital=100000,
        rebalance_freq=rebalance_freq,
        min_confidence=min_confidence,
        max_positions=max_positions
    )
    result = backtester.run_backtest(symbols, start_date, end_date)
    
    print(f"\n{'='*65}")
    print("回测完成!")
    print(f"{'='*65}")
    print(f"\n📈 收益指标:")
    print(f"  总收益率: {result.total_return:.2f}%")
    print(f"  年化收益率: {result.annual_return:.2f}%")
    print(f"  基准收益率: {result.benchmark_return:.2f}%")
    print(f"  超额收益: {result.excess_return:.2f}%")
    print(f"\n📊 风险指标:")
    print(f"  最大回撤: {result.max_drawdown:.2f}%")
    print(f"  夏普比率: {result.sharpe_ratio:.2f}")
    print(f"  卡玛比率: {result.calmar_ratio:.2f}")
    print(f"\n🎯 交易统计:")
    print(f"  总交易次数: {result.total_trades}")
    print(f"  胜率: {result.win_rate:.1f}%")
    print(f"  盈亏比: {result.profit_factor:.2f}")
    print(f"  平均持仓天数: {result.avg_holding_days:.1f}")
    print(f"\n📦 仓位统计:")
    print(f"  平均持仓数: {result.avg_position_count:.1f}")
    print(f"  平均投资比例: {result.avg_invested_ratio:.1%}")
    print(f"  空仓天数占比: {result.cash_ratio:.1%}")
    print(f"  重仓天数占比: {result.heavy_position_ratio:.1%}")
    
    if output_dir is None:
        output_dir = os.path.dirname(__file__)
    
    symbols_str = '_'.join(symbols)
    report_path = os.path.join(output_dir, f"reports/portfolio_backtest_v4_{symbols_str}.md")
    generate_portfolio_backtest_report_v4(result, report_path)
    
    return result


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        symbols = sys.argv[1:]
    else:
        symbols = ['515450', '159949']
    
    result = run_portfolio_backtest_v4(
        symbols=symbols,
        start_date='2020-03-01',
        end_date='2025-12-31'
    )
