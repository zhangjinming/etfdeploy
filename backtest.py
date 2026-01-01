"""
模拟交易与回测模块

功能：
1. 基于策略信号进行模拟交易
2. 记录详细交易日志
3. 生成回测报告（含图表）
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from strategy import IntegratedETFStrategy
from data_fetcher import get_tuesdays_in_range, ETFDataFetcher
from config import (
    ETF_POOL, RISK_PARAMS, PROFIT_ADD_PARAMS, 
    ETF_SECTORS, SECTOR_LIMITS, CORRELATED_ETF_GROUPS,
    TREND_FILTER_PARAMS, DESPAIR_CONFIRMATION
)


class TradeAction(Enum):
    """交易动作"""
    BUY = "买入"
    SELL = "卖出"
    HOLD = "持有"


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    name: str
    shares: float  # 持有份额
    cost_price: float  # 成本价
    buy_date: str  # 买入日期
    current_price: float = 0.0  # 当前价格
    add_times: int = 0  # 加仓次数
    last_add_date: str = ""  # 上次加仓日期
    highest_price: float = 0.0  # 持仓期间最高价
    partial_sold: bool = False  # 【v2】是否已部分止损
    entry_confirmed: bool = True  # 【v2】是否已确认建仓（分批建仓用）
    pending_shares: float = 0.0  # 【v2】待确认的份额
    
    @property
    def market_value(self) -> float:
        """市值"""
        return self.shares * self.current_price
    
    @property
    def profit_loss(self) -> float:
        """盈亏金额"""
        return self.shares * (self.current_price - self.cost_price)
    
    @property
    def profit_loss_pct(self) -> float:
        """盈亏比例"""
        if self.cost_price == 0:
            return 0.0
        return (self.current_price - self.cost_price) / self.cost_price * 100
    
    @property
    def drawdown_from_high(self) -> float:
        """从最高点回撤比例"""
        if self.highest_price == 0:
            return 0.0
        return (self.current_price - self.highest_price) / self.highest_price * 100


@dataclass
class Trade:
    """交易记录"""
    date: str
    symbol: str
    name: str
    action: TradeAction
    price: float
    shares: float
    amount: float  # 交易金额
    reason: str  # 交易原因
    profit_loss: float = 0.0  # 盈亏（卖出时）
    profit_loss_pct: float = 0.0  # 盈亏比例（卖出时）


@dataclass
class DailySnapshot:
    """每日账户快照"""
    date: str
    cash: float
    positions: Dict[str, Position]
    total_value: float
    daily_return: float = 0.0
    cumulative_return: float = 0.0
    benchmark_return: float = 0.0  # 基准收益率（沪深300）


class BacktestEngine:
    """回测引擎"""
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        max_positions: int = 6,
        position_size: float = None,  # 单个持仓金额，None则平均分配
        commission_rate: float = 0.0003,  # 佣金率 0.03%
        slippage: float = 0.001,  # 滑点 0.1%
    ):
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.position_size = position_size
        self.commission_rate = commission_rate
        self.slippage = slippage
        
        # 账户状态
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        
        # 记录
        self.trades: List[Trade] = []
        self.daily_snapshots: List[DailySnapshot] = []
        self.analysis_results: List[dict] = []
        
        # 策略和数据
        self.strategy = IntegratedETFStrategy()
        self.data_fetcher = self.strategy.data_fetcher
        
        # 【v2】市场环境状态
        self.market_regime = 'unknown'
        
    def reset(self):
        """重置账户"""
        self.cash = self.initial_capital
        self.positions = {}
        self.trades = []
        self.daily_snapshots = []
        self.analysis_results = []
        self.market_regime = 'unknown'
    
    def get_sector_exposure(self) -> Dict[str, float]:
        """【v2】获取各板块持仓占比"""
        total_value = self.get_total_value()
        if total_value == 0:
            return {}
        
        sector_values = {}
        for symbol, pos in self.positions.items():
            sector = ETF_SECTORS.get(symbol, 'other')
            sector_values[sector] = sector_values.get(sector, 0) + pos.market_value
        
        return {k: v / total_value for k, v in sector_values.items()}
    
    def check_sector_limit(self, symbol: str) -> bool:
        """【v2】检查板块仓位是否超限"""
        sector = ETF_SECTORS.get(symbol, 'other')
        limit = SECTOR_LIMITS.get(sector, 0.30)
        
        current_exposure = self.get_sector_exposure()
        current_sector_ratio = current_exposure.get(sector, 0)
        
        # 预估买入后的占比
        buy_amount = self.calculate_buy_amount()
        total_value = self.get_total_value()
        estimated_ratio = (current_sector_ratio * total_value + buy_amount) / (total_value + buy_amount) if total_value > 0 else 0
        
        return estimated_ratio <= limit
    
    def check_correlation_limit(self, symbol: str) -> bool:
        """【v2】检查相关性限制（同组ETF只选1只）"""
        for group in CORRELATED_ETF_GROUPS:
            if symbol in group:
                # 检查是否已持有同组其他ETF
                for held_symbol in self.positions.keys():
                    if held_symbol in group and held_symbol != symbol:
                        return False
        return True
    
    def get_dynamic_max_positions(self) -> int:
        """【v2】根据市场环境动态调整最大持仓数"""
        market_filter = TREND_FILTER_PARAMS.get('market_filter', {})
        if not market_filter.get('enable', False):
            return self.max_positions
        
        if self.market_regime == 'bear':
            return market_filter.get('bear_market_max_positions', 3)
        return self.max_positions
    
    def get_dynamic_trailing_stop(self, peak_profit: float) -> float:
        """【v2】根据盈利幅度获取动态止损距离"""
        dynamic_config = RISK_PARAMS.get('dynamic_trailing_stop', {})
        if not dynamic_config.get('enable', False):
            return RISK_PARAMS.get('trailing_stop_distance', 8.0)
        
        for level in dynamic_config.get('levels', []):
            if level['profit_min'] <= peak_profit < level['profit_max']:
                return level['drawdown_tolerance']
        
        return RISK_PARAMS.get('trailing_stop_distance', 8.0)
        
    def get_position_value(self) -> float:
        """获取持仓总市值"""
        return sum(pos.market_value for pos in self.positions.values())
    
    def get_total_value(self) -> float:
        """获取账户总价值"""
        return self.cash + self.get_position_value()
    
    def get_current_price(self, symbol: str, date: str) -> Optional[float]:
        """获取指定日期的收盘价"""
        self.data_fetcher.set_simulate_date(date)
        df = self.data_fetcher.get_etf_history(symbol, days=10)
        if df.empty:
            return None
        # 获取最新的收盘价
        return df['close'].iloc[-1]
    
    def update_positions_price(self, date: str):
        """更新所有持仓的当前价格"""
        for symbol, pos in self.positions.items():
            price = self.get_current_price(symbol, date)
            if price:
                pos.current_price = price
                # 更新最高价
                if price > pos.highest_price:
                    pos.highest_price = price
    
    def calculate_buy_amount(self) -> float:
        """计算单次买入金额"""
        if self.position_size:
            return min(self.position_size, self.cash)
        
        # 【v2】熊市保持更多现金
        market_filter = TREND_FILTER_PARAMS.get('market_filter', {})
        if market_filter.get('enable', False) and self.market_regime == 'bear':
            min_cash_ratio = market_filter.get('bear_market_cash_ratio', 0.5)
            available_cash = self.cash - self.initial_capital * min_cash_ratio
            if available_cash <= 0:
                return 0
        else:
            available_cash = self.cash
        
        # 平均分配剩余资金到空余仓位
        dynamic_max = self.get_dynamic_max_positions()
        empty_slots = dynamic_max - len(self.positions)
        if empty_slots <= 0:
            return 0
        
        return available_cash / empty_slots
    
    def execute_buy(self, symbol: str, name: str, date: str, reason: str, partial: bool = False) -> Optional[Trade]:
        """执行买入
        
        Args:
            partial: 【v2】是否为分批建仓的首次买入（只买50%）
        """
        # 检查是否已持有
        if symbol in self.positions:
            return None
        
        # 【v2】检查动态仓位限制
        dynamic_max = self.get_dynamic_max_positions()
        if len(self.positions) >= dynamic_max:
            return None
        
        # 【v2】检查板块仓位限制
        if not self.check_sector_limit(symbol):
            return None
        
        # 【v2】检查相关性限制
        if not self.check_correlation_limit(symbol):
            return None
        
        # 获取价格
        price = self.get_current_price(symbol, date)
        if not price:
            return None
        
        # 计算买入金额和份额
        buy_amount = self.calculate_buy_amount()
        
        # 【v2】分批建仓：首次只买50%
        if partial and DESPAIR_CONFIRMATION.get('enable_partial_entry', False):
            buy_amount *= DESPAIR_CONFIRMATION.get('first_entry_ratio', 0.5)
        
        if buy_amount < 100:  # 最小买入金额
            return None
        
        # 考虑滑点和佣金
        actual_price = price * (1 + self.slippage)
        commission = buy_amount * self.commission_rate
        actual_amount = buy_amount - commission
        shares = actual_amount / actual_price
        
        # 更新账户
        self.cash -= buy_amount
        self.positions[symbol] = Position(
            symbol=symbol,
            name=name,
            shares=shares,
            cost_price=actual_price,
            buy_date=date,
            current_price=actual_price,
            add_times=0,
            last_add_date="",
            highest_price=actual_price,
            partial_sold=False,
            entry_confirmed=not partial,  # 分批建仓时首次未确认
            pending_shares=0.0
        )
        
        # 记录交易
        trade = Trade(
            date=date,
            symbol=symbol,
            name=name,
            action=TradeAction.BUY,
            price=actual_price,
            shares=shares,
            amount=buy_amount,
            reason=reason + (" (分批建仓首次)" if partial else "")
        )
        self.trades.append(trade)
        
        return trade
    
    def execute_sell(self, symbol: str, date: str, reason: str, sell_ratio: float = 1.0) -> Optional[Trade]:
        """执行卖出
        
        Args:
            sell_ratio: 【v2】卖出比例，1.0为全部卖出，0.5为卖出一半
        """
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        
        # 获取价格
        price = self.get_current_price(symbol, date)
        if not price:
            return None
        
        # 计算卖出份额
        sell_shares = pos.shares * sell_ratio
        
        # 考虑滑点
        actual_price = price * (1 - self.slippage)
        sell_amount = sell_shares * actual_price
        commission = sell_amount * self.commission_rate
        actual_amount = sell_amount - commission
        
        # 计算盈亏
        profit_loss = actual_amount - (sell_shares * pos.cost_price)
        profit_loss_pct = (actual_price - pos.cost_price) / pos.cost_price * 100
        
        # 更新账户
        self.cash += actual_amount
        
        if sell_ratio >= 1.0:
            # 全部卖出
            del self.positions[symbol]
        else:
            # 部分卖出
            pos.shares -= sell_shares
            pos.partial_sold = True
        
        # 记录交易
        trade = Trade(
            date=date,
            symbol=symbol,
            name=pos.name,
            action=TradeAction.SELL,
            price=actual_price,
            shares=sell_shares,
            amount=actual_amount,
            reason=reason + (f" (卖出{sell_ratio*100:.0f}%)" if sell_ratio < 1.0 else ""),
            profit_loss=profit_loss,
            profit_loss_pct=profit_loss_pct
        )
        self.trades.append(trade)
        
        return trade
    
    def execute_add_position(self, symbol: str, date: str, add_amount: float, reason: str) -> Optional[Trade]:
        """执行浮盈加仓"""
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        
        # 检查现金是否足够
        if self.cash < add_amount:
            add_amount = self.cash
        
        if add_amount < 100:  # 最小加仓金额
            return None
        
        # 获取价格
        price = self.get_current_price(symbol, date)
        if not price:
            return None
        
        # 考虑滑点和佣金
        actual_price = price * (1 + self.slippage)
        commission = add_amount * self.commission_rate
        actual_amount = add_amount - commission
        new_shares = actual_amount / actual_price
        
        # 计算新的平均成本
        total_cost = pos.shares * pos.cost_price + new_shares * actual_price
        total_shares = pos.shares + new_shares
        new_cost_price = total_cost / total_shares
        
        # 更新账户
        self.cash -= add_amount
        pos.shares = total_shares
        pos.cost_price = new_cost_price
        pos.add_times += 1
        pos.last_add_date = date
        pos.current_price = actual_price
        
        # 记录交易
        trade = Trade(
            date=date,
            symbol=symbol,
            name=pos.name,
            action=TradeAction.BUY,
            price=actual_price,
            shares=new_shares,
            amount=add_amount,
            reason=reason
        )
        self.trades.append(trade)
        
        return trade
    
    def check_profit_add(self, date: str, analysis_result: dict) -> List[Trade]:
        """
        检查浮盈加仓条件
        
        加仓条件：
        1. 浮盈超过阈值（10%普通，20%强势）
        2. 持仓时间足够（4周以上）
        3. 趋势确认（价格在均线上方）
        4. 未从高点大幅回撤
        5. 加仓次数未超限
        6. 加仓冷却期已过
        7. 单个持仓不超过总资金25%
        """
        if not PROFIT_ADD_PARAMS.get('enable', False):
            return []
        
        trades_made = []
        current_date = datetime.strptime(date, '%Y-%m-%d')
        total_value = self.get_total_value()
        
        for symbol, pos in list(self.positions.items()):
            # 更新价格
            current_price = self.get_current_price(symbol, date)
            if not current_price:
                continue
            pos.current_price = current_price
            if current_price > pos.highest_price:
                pos.highest_price = current_price
            
            # 检查1：浮盈比例
            profit_pct = pos.profit_loss_pct
            min_profit = PROFIT_ADD_PARAMS['min_profit_pct']
            strong_profit = PROFIT_ADD_PARAMS['strong_profit_pct']
            
            if profit_pct < min_profit:
                continue
            
            # 检查2：持仓时间
            buy_date = datetime.strptime(pos.buy_date, '%Y-%m-%d')
            holding_weeks = (current_date - buy_date).days / 7
            if holding_weeks < PROFIT_ADD_PARAMS['min_holding_weeks']:
                continue
            
            # 检查3：加仓次数
            if pos.add_times >= PROFIT_ADD_PARAMS['max_add_times']:
                continue
            
            # 检查4：加仓冷却期
            if pos.last_add_date:
                last_add = datetime.strptime(pos.last_add_date, '%Y-%m-%d')
                weeks_since_add = (current_date - last_add).days / 7
                if weeks_since_add < PROFIT_ADD_PARAMS['add_cooldown_weeks']:
                    continue
            
            # 检查5：从最高点回撤
            drawdown = pos.drawdown_from_high
            if drawdown < PROFIT_ADD_PARAMS['max_drawdown_from_high']:
                continue
            
            # 检查6：单个持仓占比限制
            max_position_value = total_value * PROFIT_ADD_PARAMS['max_position_ratio']
            if pos.market_value >= max_position_value:
                continue
            
            # 检查7：趋势确认（可选）
            if PROFIT_ADD_PARAMS['require_trend_confirm']:
                self.data_fetcher.set_simulate_date(date)
                df = self.data_fetcher.get_etf_history(symbol, days=100)
                if not df.empty and len(df) >= PROFIT_ADD_PARAMS['trend_ma_period']:
                    ma = df['close'].rolling(PROFIT_ADD_PARAMS['trend_ma_period']).mean().iloc[-1]
                    if PROFIT_ADD_PARAMS['price_above_ma'] and current_price < ma:
                        continue  # 价格在均线下方，不加仓
            
            # 计算加仓金额
            if profit_pct >= strong_profit:
                add_ratio = PROFIT_ADD_PARAMS['add_ratio_strong']
                reason = f"强势浮盈加仓：盈利{profit_pct:.1f}%，趋势向上"
            else:
                add_ratio = PROFIT_ADD_PARAMS['add_ratio_normal']
                reason = f"浮盈加仓：盈利{profit_pct:.1f}%，趋势确认"
            
            # 计算加仓金额，但不超过最大持仓限制
            add_amount = pos.market_value * add_ratio
            remaining_capacity = max_position_value - pos.market_value
            add_amount = min(add_amount, remaining_capacity, self.cash)
            
            if add_amount < 100:
                continue
            
            # 执行加仓
            trade = self.execute_add_position(symbol, date, add_amount, reason)
            if trade:
                trades_made.append(trade)
                print(f"  📈 浮盈加仓 {pos.name}({symbol}): +¥{add_amount:.2f} (第{pos.add_times}次加仓)")
        
        return trades_made
    
    def take_snapshot(self, date: str, benchmark_return: float = 0.0):
        """记录每日快照"""
        self.update_positions_price(date)
        total_value = self.get_total_value()
        
        # 计算收益率
        if self.daily_snapshots:
            prev_value = self.daily_snapshots[-1].total_value
            daily_return = (total_value - prev_value) / prev_value * 100
        else:
            daily_return = 0.0
        
        cumulative_return = (total_value - self.initial_capital) / self.initial_capital * 100
        
        snapshot = DailySnapshot(
            date=date,
            cash=self.cash,
            positions={k: Position(
                symbol=v.symbol,
                name=v.name,
                shares=v.shares,
                cost_price=v.cost_price,
                buy_date=v.buy_date,
                current_price=v.current_price,
                add_times=v.add_times,
                last_add_date=v.last_add_date,
                highest_price=v.highest_price
            ) for k, v in self.positions.items()},
            total_value=total_value,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
            benchmark_return=benchmark_return
        )
        self.daily_snapshots.append(snapshot)
        
        return snapshot
    
    def process_signals(self, date: str, analysis_result: dict):
        """处理策略信号"""
        from datetime import datetime
        
        portfolio = analysis_result.get('portfolio_suggestion', {})
        long_positions = portfolio.get('long_positions', [])
        hedge_positions = portfolio.get('hedge_positions', [])
        
        # 【v2】更新市场环境
        market_regime = analysis_result.get('market_regime', {})
        self.market_regime = market_regime.get('regime', 'unknown')
        
        # 获取推荐买入的ETF代码
        buy_symbols = {p['symbol'] for p in long_positions}
        # 获取建议回避的ETF代码
        avoid_symbols = {p['symbol'] for p in hedge_positions}
        
        trades_made = []
        
        # 最大持仓时间（6个月 ≈ 26周 ≈ 182天）
        max_holding_days = 182
        current_date = datetime.strptime(date, '%Y-%m-%d')
        
        # 【v2】买入缓冲期天数
        buy_buffer_days = RISK_PARAMS.get('buy_buffer_days', 5)
        
        # 1. 先检查持仓时间限制（优先级最高）
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            buy_date = datetime.strptime(pos.buy_date, '%Y-%m-%d')
            holding_days = (current_date - buy_date).days
            
            if holding_days >= max_holding_days:
                # 更新当前价格
                current_price = self.get_current_price(symbol, date)
                if current_price:
                    pos.current_price = current_price
                    pct_change = (current_price - pos.cost_price) / pos.cost_price * 100
                    pct_str = f"+{pct_change:.1f}%" if pct_change >= 0 else f"{pct_change:.1f}%"
                    reason = f"持仓到期：已持有{holding_days}天(约{holding_days//30}个月)，收益{pct_str}"
                    trade = self.execute_sell(symbol, date, reason)
                    if trade:
                        trades_made.append(trade)
                        print(f"  ⏰ 到期卖出 {pos.name}({symbol}): 持有{holding_days}天，收益{pct_str}")
        
        # 2. 检查止损（包含动态移动止损）
        stop_loss_threshold = RISK_PARAMS.get('stop_loss', -5.0)
        enable_trailing = RISK_PARAMS.get('enable_trailing_stop', False)
        trailing_trigger = RISK_PARAMS.get('trailing_stop_trigger', 15.0)
        trailing_min_profit = RISK_PARAMS.get('trailing_stop_min_profit', 8.0)
        
        # 【v2】分批止损配置
        partial_stop = RISK_PARAMS.get('partial_stop_loss', {})
        enable_partial_stop = partial_stop.get('enable', False)
        first_stop_pct = partial_stop.get('first_stop_pct', -5.0)
        first_sell_ratio = partial_stop.get('first_sell_ratio', 0.5)
        second_stop_pct = partial_stop.get('second_stop_pct', -8.0)
        
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            buy_date = datetime.strptime(pos.buy_date, '%Y-%m-%d')
            holding_days = (current_date - buy_date).days
            
            # 更新当前价格
            current_price = self.get_current_price(symbol, date)
            if current_price:
                pos.current_price = current_price
                # 更新最高价
                if current_price > pos.highest_price:
                    pos.highest_price = current_price
                
                # 计算盈亏比例
                pct_change = (current_price - pos.cost_price) / pos.cost_price * 100
                
                # 【v2】买入缓冲期内不止损
                if holding_days < buy_buffer_days:
                    continue
                
                # 【v2】动态移动止损检查
                if enable_trailing and pos.highest_price > 0:
                    # 计算从最高点的回撤
                    peak_profit = (pos.highest_price - pos.cost_price) / pos.cost_price * 100
                    drawdown_from_peak = (current_price - pos.highest_price) / pos.highest_price * 100
                    
                    # 【v2】根据盈利幅度获取动态止损距离
                    trailing_distance = self.get_dynamic_trailing_stop(peak_profit)
                    
                    # 如果曾经盈利超过触发阈值，启用移动止损
                    if peak_profit >= trailing_trigger and drawdown_from_peak <= -trailing_distance:
                        # 检查止损后是否还能保留最低利润
                        if pct_change >= trailing_min_profit:
                            reason = f"移动止损：最高盈利{peak_profit:.1f}%，回撤{abs(drawdown_from_peak):.1f}%"
                            trade = self.execute_sell(symbol, date, reason)
                            if trade:
                                trades_made.append(trade)
                                print(f"  📉 移动止损 {pos.name}({symbol}): 最高+{peak_profit:.1f}%，回撤{drawdown_from_peak:.1f}%")
                            continue
                
                # 【v2】分批止损检查
                if enable_partial_stop and not pos.partial_sold:
                    if pct_change <= first_stop_pct:
                        reason = f"分批止损(首次)：亏损{abs(pct_change):.1f}%"
                        trade = self.execute_sell(symbol, date, reason, sell_ratio=first_sell_ratio)
                        if trade:
                            trades_made.append(trade)
                            print(f"  🛑 分批止损 {pos.name}({symbol}): 卖出{first_sell_ratio*100:.0f}%，亏损{abs(pct_change):.1f}%")
                        continue
                elif enable_partial_stop and pos.partial_sold:
                    # 已部分止损，检查是否需要清仓
                    if pct_change <= second_stop_pct:
                        reason = f"分批止损(清仓)：亏损{abs(pct_change):.1f}%"
                        trade = self.execute_sell(symbol, date, reason)
                        if trade:
                            trades_made.append(trade)
                            print(f"  🛑 清仓止损 {pos.name}({symbol}): 亏损{abs(pct_change):.1f}%")
                        continue
                
                # 检查是否触发固定止损（如果没有启用分批止损）
                if not enable_partial_stop and pct_change <= stop_loss_threshold:
                    reason = f"触发止损：亏损{abs(pct_change):.1f}% > {abs(stop_loss_threshold)}%"
                    trade = self.execute_sell(symbol, date, reason)
                    if trade:
                        trades_made.append(trade)
                        print(f"  🛑 止损卖出 {pos.name}({symbol}): 亏损{abs(pct_change):.1f}%")
        
        # 3. 处理策略建议的卖出（回避信号）- 【v2】熊市时不主动卖出盈利持仓
        for symbol in list(self.positions.keys()):
            if symbol in avoid_symbols:
                pos = self.positions[symbol]
                # 【v2】如果当前盈利且在熊市，不因回避信号卖出
                if self.market_regime == 'bear' and pos.profit_loss_pct > 0:
                    continue
                    
                # 找到回避原因
                reason = "策略建议回避"
                for p in hedge_positions:
                    if p['symbol'] == symbol:
                        reason = p.get('reason', '策略建议回避')
                        break
                
                trade = self.execute_sell(symbol, date, reason)
                if trade:
                    trades_made.append(trade)
        
        # 4. 检查浮盈加仓
        add_trades = self.check_profit_add(date, analysis_result)
        trades_made.extend(add_trades)
        
        # 5. 处理买入 - 【v2】增加板块和相关性检查
        for pos_info in long_positions:
            symbol = pos_info['symbol']
            name = pos_info['name']
            reason = pos_info.get('reason', '策略推荐买入')
            
            # 检查是否已持有
            if symbol in self.positions:
                continue
            
            # 【v2】检查动态仓位限制
            dynamic_max = self.get_dynamic_max_positions()
            if len(self.positions) >= dynamic_max:
                break
            
            # 【v2】检查板块仓位限制
            if not self.check_sector_limit(symbol):
                print(f"  ⚠️ 跳过 {name}({symbol}): 板块仓位已达上限")
                continue
            
            # 【v2】检查相关性限制
            if not self.check_correlation_limit(symbol):
                print(f"  ⚠️ 跳过 {name}({symbol}): 已持有同类ETF")
                continue
            
            # 【v2】判断是否使用分批建仓（绝望期信号）
            use_partial = False
            if DESPAIR_CONFIRMATION.get('enable_partial_entry', False):
                # 检查是否为绝望期买入
                if '绝望期' in reason or 'despair' in reason.lower():
                    use_partial = True
            
            trade = self.execute_buy(symbol, name, date, reason, partial=use_partial)
            if trade:
                trades_made.append(trade)
        
        return trades_made
    
    def get_benchmark_return(self, start_date: str, end_date: str) -> float:
        """获取基准（沪深300）收益率"""
        benchmark_symbol = '510300'
        
        self.data_fetcher.set_simulate_date(start_date)
        df_start = self.data_fetcher.get_etf_history(benchmark_symbol, days=10)
        
        self.data_fetcher.set_simulate_date(end_date)
        df_end = self.data_fetcher.get_etf_history(benchmark_symbol, days=10)
        
        if df_start.empty or df_end.empty:
            return 0.0
        
        start_price = df_start['close'].iloc[-1]
        end_price = df_end['close'].iloc[-1]
        
        return (end_price - start_price) / start_price * 100
    
    def run_backtest(self, start_date: str, end_date: str) -> dict:
        """
        运行回测
        
        Args:
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
        
        Returns:
            回测结果字典
        """
        self.reset()
        
        # 获取交易日（周二）
        # 【测试加速】monthly_only=True: 只取每月第一周的周二，加快回测速度
        # 【正常模式】monthly_only=False: 取所有周二，用于实际回测
        tuesdays = get_tuesdays_in_range(start_date, end_date, monthly_only=True)
        
        if not tuesdays:
            print(f"在 {start_date} 到 {end_date} 期间没有周二")
            return {}
        
        print(f"\n{'=' * 60}")
        print(f"回测期间: {start_date} 至 {end_date}")
        print(f"初始资金: ¥{self.initial_capital:,.2f}")
        print(f"最大持仓: {self.max_positions} 只ETF")
        print(f"交易日数: {len(tuesdays)} 周")
        print(f"{'=' * 60}\n")
        
        # 获取基准起始价格
        benchmark_start_price = None
        self.data_fetcher.set_simulate_date(start_date)
        df_benchmark = self.data_fetcher.get_etf_history('510300', days=10)
        if not df_benchmark.empty:
            benchmark_start_price = df_benchmark['close'].iloc[-1]
        
        for i, tuesday in enumerate(tuesdays, 1):
            print(f"[{i}/{len(tuesdays)}] 分析日期: {tuesday}")
            
            # 运行策略分析
            self.strategy.set_simulate_date(tuesday)
            analysis_result = self.strategy.run_full_analysis()
            analysis_result['date'] = tuesday
            self.analysis_results.append(analysis_result)
            
            # 处理交易信号
            trades = self.process_signals(tuesday, analysis_result)
            
            # 计算基准收益率
            benchmark_return = 0.0
            if benchmark_start_price:
                self.data_fetcher.set_simulate_date(tuesday)
                df_bench = self.data_fetcher.get_etf_history('510300', days=10)
                if not df_bench.empty:
                    current_bench_price = df_bench['close'].iloc[-1]
                    benchmark_return = (current_bench_price - benchmark_start_price) / benchmark_start_price * 100
            
            # 记录快照
            snapshot = self.take_snapshot(tuesday, benchmark_return)
            
            # 打印当日摘要
            if trades:
                for trade in trades:
                    action_str = "🟢 买入" if trade.action == TradeAction.BUY else "🔴 卖出"
                    print(f"  {action_str} {trade.name}({trade.symbol}) @ ¥{trade.price:.3f}")
                    if trade.action == TradeAction.SELL:
                        pnl_str = f"+{trade.profit_loss:.2f}" if trade.profit_loss >= 0 else f"{trade.profit_loss:.2f}"
                        print(f"      盈亏: ¥{pnl_str} ({trade.profit_loss_pct:+.2f}%)")
            
            print(f"  💰 账户总值: ¥{snapshot.total_value:,.2f} ({snapshot.cumulative_return:+.2f}%)")
            print(f"  📊 持仓数: {len(self.positions)}/{self.max_positions}")
            print()
        
        # 生成回测结果
        result = self.generate_backtest_result(start_date, end_date)
        
        return result
    
    def generate_backtest_result(self, start_date: str, end_date: str) -> dict:
        """生成回测结果统计"""
        if not self.daily_snapshots:
            return {}
        
        # 基本统计
        final_value = self.daily_snapshots[-1].total_value
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        benchmark_return = self.get_benchmark_return(start_date, end_date)
        
        # 交易统计
        buy_trades = [t for t in self.trades if t.action == TradeAction.BUY]
        sell_trades = [t for t in self.trades if t.action == TradeAction.SELL]
        
        winning_trades = [t for t in sell_trades if t.profit_loss > 0]
        losing_trades = [t for t in sell_trades if t.profit_loss < 0]
        
        win_rate = len(winning_trades) / len(sell_trades) * 100 if sell_trades else 0
        
        # 计算最大回撤
        max_drawdown = 0.0
        peak_value = self.initial_capital
        for snapshot in self.daily_snapshots:
            if snapshot.total_value > peak_value:
                peak_value = snapshot.total_value
            drawdown = (peak_value - snapshot.total_value) / peak_value * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 计算年化收益率
        days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days
        annual_return = total_return * 365 / days if days > 0 else 0
        
        # 计算夏普比率（假设无风险利率2%）
        returns = [s.daily_return for s in self.daily_snapshots if s.daily_return != 0]
        if returns:
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe_ratio = (avg_return - 2/52) / std_return * np.sqrt(52) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        result = {
            'start_date': start_date,
            'end_date': end_date,
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'annual_return': annual_return,
            'benchmark_return': benchmark_return,
            'excess_return': total_return - benchmark_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'total_trades': len(self.trades),
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'avg_profit': np.mean([t.profit_loss for t in winning_trades]) if winning_trades else 0,
            'avg_loss': np.mean([t.profit_loss for t in losing_trades]) if losing_trades else 0,
            'trades': self.trades,
            'snapshots': self.daily_snapshots,
            'analysis_results': self.analysis_results,
            'final_positions': self.positions
        }
        
        return result


def run_backtest(start_date: str, end_date: str, initial_capital: float = 10000.0) -> dict:
    """
    运行回测的便捷函数
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金
    
    Returns:
        回测结果
    """
    engine = BacktestEngine(
        initial_capital=initial_capital,
        max_positions=6
    )
    
    result = engine.run_backtest(start_date, end_date)
    
    return result
