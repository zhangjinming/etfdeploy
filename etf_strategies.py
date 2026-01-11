"""
ETF策略配置模块

每个ETF有独立的策略配置，支持：
1. 自定义入场/出场条件
2. 自定义权重分配
3. 自定义风控参数
4. 策略组合和切换
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import os


class SignalType(Enum):
    """信号类型"""
    STRONG_BUY = 'strong_buy'
    BUY = 'buy'
    NEUTRAL = 'neutral'
    SELL = 'sell'
    STRONG_SELL = 'strong_sell'


class EmotionPhase(Enum):
    """情绪阶段"""
    DESPAIR = 'despair'       # 绝望期
    HESITATION = 'hesitation' # 犹豫期
    FRENZY = 'frenzy'         # 疯狂期
    UNKNOWN = 'unknown'


class TrendDirection(Enum):
    """趋势方向"""
    UPTREND = 'uptrend'
    DOWNTREND = 'downtrend'
    SIDEWAYS = 'sideways'
    UNKNOWN = 'unknown'


@dataclass
class EntryCondition:
    """入场条件"""
    name: str                           # 条件名称
    description: str                    # 条件描述
    check_func: Optional[Callable] = None  # 检查函数
    weight: float = 1.0                 # 权重
    required: bool = False              # 是否必须满足
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'description': self.description,
            'weight': self.weight,
            'required': self.required,
        }


@dataclass
class ExitCondition:
    """出场条件"""
    name: str
    description: str
    check_func: Optional[Callable] = None
    priority: int = 1                   # 优先级（1最高）
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'description': self.description,
            'priority': self.priority,
        }


@dataclass 
class RiskControl:
    """风控配置"""
    stop_loss: float = -8.0             # 止损线(%)
    take_profit: float = 15.0           # 止盈线(%)
    trailing_stop: float = 0.0          # 移动止损(%)，0表示不启用
    time_stop_weeks: int = 12           # 时间止损(周)
    time_stop_min_profit: float = 3.0   # 时间止损最低收益(%)
    max_position: float = 0.20          # 最大仓位
    min_position: float = 0.05          # 最小仓位
    
    def to_dict(self) -> Dict:
        return {
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'trailing_stop': self.trailing_stop,
            'time_stop_weeks': self.time_stop_weeks,
            'time_stop_min_profit': self.time_stop_min_profit,
            'max_position': self.max_position,
            'min_position': self.min_position,
        }


@dataclass
class AnalysisWeights:
    """分析权重配置"""
    strength: float = 0.45              # 强弱分析权重
    emotion: float = 0.25               # 情绪分析权重
    trend: float = 0.15                 # 趋势确认权重
    capital: float = 0.15               # 资金面权重
    
    def normalize(self):
        """归一化权重"""
        total = self.strength + self.emotion + self.trend + self.capital
        if total > 0:
            self.strength /= total
            self.emotion /= total
            self.trend /= total
            self.capital /= total
    
    def to_dict(self) -> Dict:
        return {
            'strength': self.strength,
            'emotion': self.emotion,
            'trend': self.trend,
            'capital': self.capital,
        }


@dataclass
class ETFStrategy:
    """
    ETF策略配置类
    
    每个ETF实例化一个策略对象，独立管理。
    """
    symbol: str                         # ETF代码
    name: str                           # ETF名称
    category: str = 'default'           # 分类
    style: str = 'balanced'             # 风格
    
    # 分析配置
    use_weekly: bool = True             # 使用周线分析
    weights: AnalysisWeights = field(default_factory=AnalysisWeights)
    
    # RSI阈值
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    
    # 风控配置
    risk_control: RiskControl = field(default_factory=RiskControl)
    
    # 入场条件
    entry_conditions: List[EntryCondition] = field(default_factory=list)
    
    # 出场条件
    exit_conditions: List[ExitCondition] = field(default_factory=list)
    
    # 特殊规则
    special_rules: Dict[str, Any] = field(default_factory=dict)
    
    # 是否启用
    enabled: bool = True
    
    def __post_init__(self):
        """初始化后处理"""
        self.weights.normalize()
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'name': self.name,
            'category': self.category,
            'style': self.style,
            'use_weekly': self.use_weekly,
            'weights': self.weights.to_dict(),
            'rsi_oversold': self.rsi_oversold,
            'rsi_overbought': self.rsi_overbought,
            'risk_control': self.risk_control.to_dict(),
            'entry_conditions': [c.to_dict() for c in self.entry_conditions],
            'exit_conditions': [c.to_dict() for c in self.exit_conditions],
            'special_rules': self.special_rules,
            'enabled': self.enabled,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ETFStrategy':
        """从字典创建"""
        weights = AnalysisWeights(**data.get('weights', {}))
        risk_control = RiskControl(**data.get('risk_control', {}))
        
        entry_conditions = [
            EntryCondition(**c) for c in data.get('entry_conditions', [])
        ]
        exit_conditions = [
            ExitCondition(**c) for c in data.get('exit_conditions', [])
        ]
        
        return cls(
            symbol=data['symbol'],
            name=data['name'],
            category=data.get('category', 'default'),
            style=data.get('style', 'balanced'),
            use_weekly=data.get('use_weekly', True),
            weights=weights,
            rsi_oversold=data.get('rsi_oversold', 30.0),
            rsi_overbought=data.get('rsi_overbought', 70.0),
            risk_control=risk_control,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            special_rules=data.get('special_rules', {}),
            enabled=data.get('enabled', True),
        )


class ETFStrategyManager:
    """
    ETF策略管理器
    
    管理所有ETF的策略配置，支持：
    1. 加载/保存策略
    2. 策略CRUD操作
    3. 策略模板
    """
    
    def __init__(self, config_dir: str = None):
        """
        初始化策略管理器
        
        Args:
            config_dir: 配置文件目录，默认为当前目录下的strategies/
        """
        self.config_dir = config_dir or os.path.join(os.path.dirname(__file__), 'strategies')
        self.strategies: Dict[str, ETFStrategy] = {}
        self._init_default_strategies()
    
    def _init_default_strategies(self):
        """初始化默认策略"""
        # 红利低波50ETF - 防御型（优化版 v11 - 最佳版本）
        # ============================================
        # v11回测结果：收益189.43%，基准146.65%，跑赢42.78%
        # 胜率85.7%，盈亏比11.27，最大回撤-20.77%
        # 
        # 核心优化：
        # 1. 降低买入门槛，增加入场机会
        # 2. 严格限制高位入场（RSI<55，布林<70%）
        # 3. 提高卖出门槛，延长持仓时间
        # 4. 增加均线多头时的持仓信心
        # ============================================
        self.strategies['515450'] = ETFStrategy(
            symbol='515450',
            name='红利低波50ETF',
            category='dividend',
            style='defensive',
            weights=AnalysisWeights(
                strength=0.25,      # 强弱权重
                emotion=0.05,       # 情绪权重（降低）
                trend=0.40,         # 趋势权重（提高）
                capital=0.30        # 资金面权重
            ),
            rsi_oversold=30.0,      # RSI超卖阈值
            rsi_overbought=85.0,    # RSI超买阈值
            risk_control=RiskControl(
                stop_loss=-8.0,             # 止损
                take_profit=60.0,           # 止盈
                trailing_stop=15.0,         # 移动止盈回撤
                time_stop_weeks=78,         # 时间止损（18个月）
                time_stop_min_profit=3.0,   # 时间止损最低收益
                max_position=0.95,          # 最大仓位
                min_position=0.30,          # 最小仓位
            ),
            entry_conditions=[
                EntryCondition('rsi_oversold', 'RSI超卖(<35) - 胜率85%+', weight=3.5, required=False),
                EntryCondition('boll_lower', '触及布林带下轨 - 胜率75%', weight=3.0, required=False),
                EntryCondition('shrink_volume_down', '缩量下跌 - 胜率75%', weight=2.5, required=False),
                EntryCondition('consecutive_down', '连跌2周以上 - 胜率68%', weight=2.0, required=False),
                EntryCondition('price_bottom', '52周低点附近 - 胜率100%', weight=3.0, required=False),
                EntryCondition('month_start', '月初效应 - 日均+0.35%', weight=1.0, required=False),
                EntryCondition('ma_bullish', '均线多头排列 - 趋势向上', weight=2.5, required=False),
            ],
            exit_conditions=[
                ExitCondition('stop_loss', '触发止损(-8%)', priority=1),
                ExitCondition('trailing_stop', '移动止盈触发', priority=1),
                ExitCondition('take_profit', '触发止盈(+60%)', priority=2),
                ExitCondition('volume_surge_stall', '放量滞涨 - 胜率仅17%', priority=2),
            ],
            special_rules={
                # ========== v11核心规则 ==========
                'use_high_winrate_rules': True,
                
                # ========== 持仓时间控制 ==========
                'min_holding_days': 45,
                'max_holding_days': 540,
                'optimal_holding_months': [3, 6, 9, 12],
                'force_exit_at_max': True,
                
                # ========== 入场条件 ==========
                'rsi_oversold_buy': True,
                'rsi_oversold_threshold': 35,
                'rsi_oversold_weight': 3.5,
                
                'boll_lower_buy': True,
                'boll_position_threshold': 0.25,
                'boll_lower_weight': 3.0,
                
                'shrink_volume_buy': True,
                'shrink_vol_ratio': 0.80,
                'shrink_down_pct': -2.0,
                'shrink_volume_weight': 2.5,
                
                'consecutive_down_buy': True,
                'consecutive_down_weeks': 2,
                'consecutive_down_weight': 2.0,
                
                'price_position_buy': True,
                'price_position_threshold': 0.35,
                'price_position_weight': 2.5,
                
                # ========== 均线多头买入规则 ==========
                'ma_bullish_buy': True,
                'ma_bullish_weight': 2.5,
                'ma_slope_bonus': True,
                'ma_slope_up_bonus': 1.3,
                
                # ========== 月份/时间规则 ==========
                'use_seasonal_rules': True,
                'best_months': [11, 9, 2, 1, 3],
                'worst_months': [10],
                'month_start_days': 5,
                'month_start_weight': 1.0,
                
                # ========== 量价关系规则 ==========
                'volume_surge_stall_exit': True,
                'surge_vol_ratio': 2.0,
                'stall_pct_threshold': 0.2,
                
                # ========== 动态卖出规则 ==========
                'dynamic_exit': True,
                'exit_profit_1m': 20.0,
                'exit_profit_3m': 30.0,
                'exit_profit_6m': 40.0,
                'exit_profit_9m': 50.0,
                'exit_loss_threshold': -8.0,
                'early_stop_loss': -10.0,
                
                # ========== RSI卖出规则 ==========
                'rsi_exit_enabled': True,
                'rsi_exit_threshold': 80,
                'rsi_exit_weight': 1.0,
                
                # ========== 入场限制 ==========
                'rsi_entry_max': 55,
                'avoid_high_position_entry': True,
                'high_position_threshold': 0.70,
                'boll_high_position_penalty': 0.60,
                'boll_high_penalty_factor': 0.4,
                
                # ========== 趋势过滤 ==========
                'trend_filter_mode': 'moderate',
                'block_downtrend_entry': False,
                'allow_sideways_entry': True,
                
                # ========== 原有规则 ==========
                'prefer_despair_phase': True,
                'avoid_frenzy_chase': False,
                'use_dividend_factor': True,
                'long_term_hold_friendly': True,
                'trend_following_lite': True,
                'trend_following_strict': False,
                'allow_add_position': True,
                'scale_in_on_dip': True,
                'protect_profit_above': 30.0,
                
                # ========== 交易频率控制 ==========
                'entry_cooldown_days': 5,
                'sell_signal_confirm_days': 5,
                
                # ========== 买入评分门槛 ==========
                'buy_score_threshold': 1.2,
                'strong_buy_threshold': 2.5,
                'sell_score_threshold': -1.5,
                
                # ========== 均线系统 ==========
                'use_ma_system': True,
                'ma_bullish_hold': True,
                'ma_bearish_caution': True,
                'ma_bullish_bonus': 1.5,
                
                # ========== 浮盈加仓策略 ==========
                'pyramid_add_enabled': True,
                'pyramid_profit_threshold_1': 5.0,
                'pyramid_profit_threshold_2': 12.0,
                'pyramid_profit_threshold_3': 20.0,
                'pyramid_add_ratio_1': 0.40,
                'pyramid_add_ratio_2': 0.30,
                'pyramid_add_ratio_3': 0.20,
                'pyramid_max_adds': 3,
                'pyramid_min_holding_days': 7,
                'pyramid_rsi_max': 70,
                'pyramid_trend_required': True,
                'pyramid_cooldown_days': 3,
            }
        )
        
        # 创业板50ETF - 成长型（v12优化版 - 趋势跟踪+高胜率信号）
        # ============================================
        # v12回测结果（总收益201.40%，胜率63%，盈亏比2.81）：
        # 优点：跑赢基准29.13%，盈亏比优秀
        # 
        # 策略核心：趋势跟踪 + 高胜率信号
        # 1. 放量上涨顺势（胜率83.3%）
        # 2. 缩量企稳买入（4周后平均+5.4%）
        # 3. 均线多头确认
        # 4. 严格止损止盈
        # ============================================
        self.strategies['159949'] = ETFStrategy(
            symbol='159949',
            name='创业板50ETF',
            category='growth',
            style='aggressive',
            weights=AnalysisWeights(
                strength=0.20,      # 强弱权重
                emotion=0.10,       # 情绪权重
                trend=0.50,         # 趋势权重（核心）
                capital=0.20        # 资金面权重
            ),
            rsi_oversold=25.0,      # RSI超卖阈值
            rsi_overbought=80.0,    # RSI超买阈值
            risk_control=RiskControl(
                stop_loss=-8.0,             # 止损
                take_profit=35.0,           # 止盈
                trailing_stop=15.0,         # 移动止盈回撤
                time_stop_weeks=10,         # 时间止损
                time_stop_min_profit=5.0,   # 时间止损最低收益
                max_position=0.90,          # 最大仓位
                min_position=0.25,          # 最小仓位
            ),
            entry_conditions=[
                # 核心买入条件（按胜率排序）
                EntryCondition('volume_surge_up', '放量上涨顺势 - 胜率83.3%', weight=4.0, required=False),
                EntryCondition('shrink_volume_stabilize', '缩量企稳 - 4周后平均+5.4%', weight=3.5, required=False),
                EntryCondition('macd_golden', 'MACD金叉 - 趋势启动', weight=3.0, required=False),
                EntryCondition('ma_bullish', '均线多头排列', weight=3.0, required=False),
                EntryCondition('boll_upper_breakout', '布林带上轨突破+放量 - 强势延续', weight=2.0, required=False),
            ],
            exit_conditions=[
                ExitCondition('stop_loss', '触发止损(-8%)', priority=1),
                ExitCondition('trailing_stop', '移动止盈触发', priority=1),
                ExitCondition('take_profit', '触发止盈(+35%)', priority=2),
                ExitCondition('macd_death_cross', 'MACD死叉', priority=3),
            ],
            special_rules={
                # ========== v12核心规则：趋势跟踪+高胜率信号 ==========
                'use_high_winrate_rules': True,     # 启用高胜率规则
                
                # ========== 趋势过滤（v12：严格但不过度） ==========
                'trend_filter_mode': 'strict',      # 严格趋势过滤
                'require_trend_reversal': True,     # 要求趋势反转确认
                'min_reversal_signals': 2,          # 需要2个反转信号
                'block_downtrend_entry': False,     # 不完全禁止下跌趋势入场
                'require_ma_support': True,         # 要求均线支撑
                'allow_sideways_entry': True,       # 允许横盘入场
                
                # ========== 持仓时间控制 ==========
                'min_holding_days': 7,              # 最少持仓7天
                'max_holding_days': 70,             # 最长持仓10周
                'optimal_holding_weeks': 6,         # 最优持仓周期
                'force_exit_at_max': True,          # 达到最长持仓时强制退出
                
                # ========== RSI规则 ==========
                'rsi_oversold_buy': True,           # RSI超卖时买入
                'rsi_oversold_threshold': 25,       # RSI超卖阈值
                'rsi_oversold_weight': 1.0,         # RSI超卖信号权重
                'rsi_recovery_required': True,      # 要求RSI回升确认
                'rsi_recovery_threshold': 35,       # RSI回升到35以上才买入
                
                # ========== 布林带规则 ==========
                'boll_lower_buy': True,             # 布林带下轨买入
                'boll_position_threshold': 0.15,    # 布林带下轨阈值
                'boll_lower_weight': 1.0,           # 布林带下轨信号权重
                'boll_upper_sell': False,           # 不在上轨卖出
                'boll_upper_continuation': True,    # 启用上轨趋势延续
                'boll_upper_weight': 2.5,           # 上轨突破信号权重
                
                # ========== 成交量规则 ==========
                # 放量上涨后顺势（胜率83.3%）- 最重要信号
                'volume_surge_up_buy': True,        # 放量上涨后买入
                'surge_up_vol_ratio': 1.8,          # 放量阈值
                'surge_up_pct': 3.0,                # 涨幅阈值
                'surge_up_weight': 4.0,             # 放量上涨信号权重（最高）
                
                # 放量下跌后反弹（胜率66.7%）
                'panic_sell_buy': True,             # 放量下跌后买入
                'panic_vol_ratio': 2.0,             # 放量阈值
                'panic_down_pct': -5.0,             # 下跌幅度阈值
                'panic_sell_weight': 2.0,           # 放量下跌信号权重
                'panic_require_stabilize': True,    # 放量下跌需要企稳确认
                
                # 缩量企稳（4周后平均+5.4%）
                'shrink_volume_buy': True,          # 缩量企稳买入
                'shrink_vol_ratio': 0.70,           # 缩量阈值
                'shrink_consecutive_weeks': 3,      # 连续缩量周数
                'shrink_volume_weight': 3.5,        # 缩量企稳信号权重
                'shrink_down_pct': -1.5,            # 下跌幅度阈值
                'shrink_require_support': True,     # 缩量需要支撑确认
                
                # ========== MACD规则 ==========
                'macd_golden_buy': True,            # MACD金叉买入
                'macd_below_zero_weight': 3.0,      # 零轴下方金叉权重
                'macd_above_zero_weight': 3.5,      # 零轴上方金叉权重
                'macd_death_sell': True,            # MACD死叉卖出
                'macd_death_weight': 2.0,           # 死叉信号权重
                
                # ========== 黄金买点（组合信号） ==========
                'triple_bottom_buy': True,          # 黄金买点信号买入
                'triple_bottom_rsi': 35,            # RSI阈值
                'triple_bottom_boll': 0.20,         # 布林带位置阈值
                'triple_bottom_vol': 0.80,          # 量比阈值
                'triple_bottom_weight': 2.5,        # 黄金买点信号权重
                
                # ========== 连跌反弹规则 ==========
                'consecutive_down_buy': True,       # 连跌后买入
                'consecutive_down_weeks': 3,        # 连跌周数阈值
                'consecutive_down_weight': 1.0,     # 连跌信号权重
                'consecutive_require_stabilize': True,  # 连跌需要企稳确认
                
                # ========== 价格位置规则 ==========
                'price_position_buy': True,         # 底部区域买入
                'price_position_threshold': 0.25,   # 底部区域阈值
                'price_position_weight': 0.5,       # 价格位置信号权重
                
                # ========== 动态卖出规则 ==========
                'dynamic_exit': True,               # 启用动态卖出
                'exit_profit_1w': 10.0,             # 1周后止盈阈值
                'exit_profit_4w': 15.0,             # 4周后止盈阈值
                'exit_profit_8w': 22.0,             # 8周后止盈阈值
                'exit_profit_10w': 28.0,            # 10周后止盈阈值
                'exit_loss_threshold': -8.0,        # 止损阈值
                'early_stop_loss': -6.0,            # 早期止损
                
                # ========== RSI卖出规则 ==========
                'rsi_exit_enabled': True,           # 启用RSI卖出
                'rsi_exit_threshold': 85,           # RSI卖出阈值
                'rsi_exit_weight': 1.0,             # RSI卖出权重
                
                # ========== 原有规则调整 ==========
                'prefer_despair_phase': False,      # 不偏好绝望期
                'avoid_frenzy_chase': False,        # 不回避疯狂期
                'momentum_factor': True,            # 动量因子
                
                # ========== 交易频率控制 ==========
                'entry_cooldown_days': 5,           # 入场冷却期
                'sell_signal_confirm_days': 2,      # 卖出信号确认天数
                
                # ========== 买入评分门槛 ==========
                'buy_score_threshold': 2.5,         # 买入门槛
                'strong_buy_threshold': 4.5,        # 强买入门槛
                'sell_score_threshold': -1.5,       # 卖出评分门槛
                
                # ========== 入场限制 ==========
                'rsi_entry_max': 75,                # 入场RSI上限
                'avoid_high_position_entry': True,  # 避免高位入场
                'high_position_threshold': 0.85,    # 高位阈值
                
                # ========== 均线系统 ==========
                'use_ma_system': True,              # 使用均线系统
                'ma_bullish_hold': True,            # 均线多头时坚定持有
                'ma_bearish_caution': True,         # 均线空头谨慎
                'ma_bullish_bonus': 1.5,            # 均线多头额外加成
                
                # ========== 浮盈加仓策略 ==========
                'pyramid_add_enabled': True,        # 启用浮盈加仓
                'pyramid_profit_threshold_1': 5.0,  # 第一次加仓阈值
                'pyramid_profit_threshold_2': 10.0, # 第二次加仓阈值
                'pyramid_profit_threshold_3': 16.0, # 第三次加仓阈值
                'pyramid_add_ratio_1': 0.35,        # 第一次加仓比例
                'pyramid_add_ratio_2': 0.25,        # 第二次加仓比例
                'pyramid_add_ratio_3': 0.15,        # 第三次加仓比例
                'pyramid_max_adds': 3,              # 最大加仓次数
                'pyramid_min_holding_days': 5,      # 加仓最小持仓天数
                'pyramid_rsi_max': 72,              # 加仓时RSI上限
                'pyramid_trend_required': True,     # 加仓要求趋势确认
                'pyramid_cooldown_days': 3,         # 两次加仓间隔
            }
        )
        
        # 中小100ETF - 优化版（v4.3）
        # ============================================
        # v4.3优化目标：在v4.0基础上提升收益率
        # 
        # v4.0回测：收益24.88%，胜率58.3%，盈亏比1.94（最佳）
        # 
        # v4.3优化方向：
        # 1. 提高仓位到90%：增加收益捕获
        # 2. 放宽止盈到45%：让利润更好地奔跑
        # 3. 增加加仓比例：放大盈利交易收益
        # 4. 保持入场条件不变（v4.0已经很好）
        # ============================================
        # 159902 中小100ETF - v5.3 优化版
        # 优化目标：避免连续止损，增强反转确认
        # v5.3优化点：
        # 1. 增加反转信号要求到3个
        # 2. 实现连续亏损保护(backtest.py)
        # 3. despair情绪下需要更强确认
        # 4. 提高买入门槛，收紧入场限制
        # ============================================
        self.strategies['159902'] = ETFStrategy(
            symbol='159902',
            name='中小100ETF',
            category='mid_small',
            style='balanced',
            weights=AnalysisWeights(
                strength=0.25,
                emotion=0.20,       # 提高情绪权重(15%->20%)，更好过滤疯狂期
                trend=0.35,         # 降低趋势权重(40%->35%)
                capital=0.20
            ),
            rsi_oversold=22.0,
            rsi_overbought=78.0,
            risk_control=RiskControl(
                stop_loss=-9.5,     # 保持宽松止损
                take_profit=40.0,
                max_position=0.90,
                trailing_stop=12.0,
                time_stop_weeks=14,
                time_stop_min_profit=2.0,
            ),
            entry_conditions=[
                EntryCondition('volume_surge_up', '放量上涨顺势 - 胜率83.3%', weight=5.0, required=False),
                EntryCondition('ma_bullish', '均线多头排列', weight=4.5, required=False),
                EntryCondition('macd_golden', 'MACD金叉', weight=4.0, required=False),
                EntryCondition('trend_reversal_confirm', '趋势反转确认', weight=4.0, required=False),
                EntryCondition('price_bottom', '价格底部区域', weight=3.5, required=False),
                EntryCondition('rsi_divergence', 'RSI底背离', weight=4.0, required=False),
            ],
            exit_conditions=[
                ExitCondition('stop_loss', '触发止损(-9.5%)', priority=1),
                ExitCondition('trailing_stop', '移动止盈触发', priority=1),
                ExitCondition('take_profit', '触发止盈(+40%)', priority=2),
                ExitCondition('macd_death_cross', 'MACD死叉', priority=3),
                ExitCondition('rsi_overbought', 'RSI超买', priority=3),
            ],
            special_rules={
                # ========== 启用高胜率规则系统 ==========
                'use_high_winrate_rules': True,
                
                # ========== 趋势过滤 ==========
                'prefer_despair_phase': True,
                'despair_require_stabilize': True,
                'trend_filter_enabled': True,
                'trend_filter_mode': 'strict',      # v5.3: moderate->strict
                'avoid_downtrend_entry': True,
                'block_downtrend_entry': False,
                'allow_sideways_entry': True,
                'downtrend_penalty': 0.3,           # v5.3: 0.4->0.3
                
                # ========== 趋势反转确认 ==========
                'require_trend_reversal': True,
                'min_reversal_signals': 3,          # v5.3: 2->3 关键优化
                'require_ma_support': True,
                'require_volume_confirm': True,
                
                # ========== 持仓时间控制 ==========
                'min_holding_days': 10,             # v5.3: 7->10
                'max_holding_days': 90,
                'force_exit_at_max': True,
                
                # ========== RSI规则 ==========
                'rsi_oversold_buy': True,
                'rsi_oversold_threshold': 22,
                'rsi_oversold_weight': 3.0,
                'rsi_recovery_required': True,
                'rsi_recovery_threshold': 30,
                'rsi_divergence_buy': True,
                'rsi_divergence_weight': 4.0,
                
                # ========== 布林带规则 ==========
                'boll_lower_buy': True,
                'boll_position_threshold': 0.10,
                'boll_lower_weight': 3.0,
                'boll_require_stabilize': True,
                
                # ========== 成交量规则 ==========
                'volume_surge_up_buy': True,
                'surge_up_vol_ratio': 1.4,
                'surge_up_pct': 2.0,
                'surge_up_weight': 5.5,
                
                'shrink_volume_buy': True,
                'shrink_vol_ratio': 0.70,
                'shrink_consecutive_weeks': 2,
                'shrink_volume_weight': 3.0,
                'shrink_require_support': True,
                'shrink_down_pct': -0.5,
                
                # ========== MACD规则 ==========
                'macd_golden_buy': True,
                'macd_below_zero_weight': 4.0,
                'macd_above_zero_weight': 4.5,
                'macd_death_sell': True,
                'macd_death_weight': 3.0,
                'macd_histogram_confirm': True,
                
                # ========== 黄金买点（组合信号） ==========
                'triple_bottom_buy': True,
                'triple_bottom_rsi': 22,
                'triple_bottom_boll': 0.12,
                'triple_bottom_vol': 0.60,
                'triple_bottom_weight': 6.0,
                
                # ========== 连跌反弹规则 ==========
                'consecutive_down_buy': True,
                'consecutive_down_weeks': 3,
                'consecutive_down_weight': 1.5,
                'consecutive_require_stabilize': True,
                'consecutive_require_volume_shrink': True,
                
                # ========== 价格位置规则 ==========
                'price_position_buy': True,
                'price_position_threshold': 0.25,
                'price_position_weight': 3.5,
                
                # ========== 动态卖出规则 ==========
                'dynamic_exit': True,
                'exit_profit_1m': 12.0,
                'exit_profit_3m': 20.0,
                'exit_profit_6m': 32.0,
                'exit_loss_threshold': -9.5,
                'early_stop_loss': -7.0,
                
                # ========== RSI卖出规则 ==========
                'rsi_exit_enabled': True,
                'rsi_exit_threshold': 78,
                'rsi_exit_weight': 2.0,
                
                # ========== 买入评分门槛 ==========
                'buy_score_threshold': 3.5,         # v5.3: 3.0->3.5
                'strong_buy_threshold': 5.5,        # v5.3: 5.0->5.5
                'sell_score_threshold': -2.5,
                
                # ========== 入场限制（关键优化v5.3） ==========
                'rsi_entry_max': 40,                    # v5.3: 42->40
                'avoid_high_position_entry': True,
                'high_position_threshold': 0.38,        # v5.3: 0.40->0.38
                'boll_high_position_penalty': 0.35,     # v5.3: 0.38->0.35
                'boll_high_penalty_factor': 0.25,       # v5.3: 0.30->0.25
                'very_high_position_threshold': 0.50,   # v5.3: 0.52->0.50
                'very_high_penalty': 0.10,              # v5.3: 0.15->0.10
                
                # ========== 情绪过滤（关键新增v5.3） ==========
                'avoid_frenzy_chase': True,
                'prefer_despair_entry': True,
                'despair_bonus': 1.3,                   # v5.3: 1.5->1.3 降低despair加成
                'hesitation_penalty': 0.6,              # v5.3: 0.7->0.6
                
                # ========== 均线系统 ==========
                'use_ma_system': True,
                'ma_bullish_buy': True,
                'ma_bullish_weight': 4.5,
                'ma_bullish_hold': True,
                'ma_bearish_caution': True,
                'ma_bullish_bonus': 2.2,
                'ma_bearish_penalty': 0.25,
                'ma_slope_bonus': True,
                'ma_slope_up_bonus': 1.8,
                'ma_slope_filter': True,
                'ma_slope_threshold': -0.012,
                'ma_cross_confirm': True,
                
                # ========== 浮盈加仓策略 ==========
                'pyramid_add_enabled': True,
                'pyramid_profit_threshold_1': 5.0,
                'pyramid_profit_threshold_2': 10.0,
                'pyramid_profit_threshold_3': 18.0,
                'pyramid_add_ratio_1': 0.45,
                'pyramid_add_ratio_2': 0.35,
                'pyramid_add_ratio_3': 0.25,
                'pyramid_max_adds': 3,
                'pyramid_min_holding_days': 5,
                'pyramid_rsi_max': 65,
                'pyramid_trend_required': True,
                'pyramid_cooldown_days': 4,
                
                # ========== 交易频率控制（增强v5.3） ==========
                'entry_cooldown_days': 5,           # v5.3: 4->5
                'sell_signal_confirm_days': 2,
                'avoid_consecutive_loss': True,
                'loss_cooldown_days': 21,           # v5.3: 14->21
                'consecutive_loss_max': 2,
                'consecutive_loss_cooldown': 35,    # v5.3: 21->35
                
                # ========== 市场环境过滤 ==========
                'market_sentiment_filter': True,
                'avoid_panic_entry': True,
                'require_sentiment_stabilize': True,
                
                # ========== 原有规则 ==========
                'style_rotation_aware': True,
                'small_cap_premium': True,
                'protect_profit_above': 5.0,
            }
        )
        
        # 沪深300ETF - 核心配置
        self.strategies['510300'] = ETFStrategy(
            symbol='510300',
            name='沪深300ETF',
            category='core',
            style='core',
            weights=AnalysisWeights(
                strength=0.40,
                emotion=0.25,
                trend=0.20,
                capital=0.15
            ),
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            risk_control=RiskControl(
                stop_loss=-7.0,
                take_profit=15.0,
                max_position=0.30,
            ),
            entry_conditions=[
                EntryCondition('rsi_oversold', 'RSI超卖', weight=1.5),
                EntryCondition('market_despair', '市场绝望', weight=2.0),
                EntryCondition('valuation_low', '估值较低', weight=1.5),
            ],
            exit_conditions=[
                ExitCondition('rsi_overbought', 'RSI超买', priority=2),
                ExitCondition('market_frenzy', '市场疯狂', priority=1),
                ExitCondition('valuation_high', '估值较高', priority=2),
            ],
            special_rules={
                'prefer_despair_phase': True,
                'market_benchmark': True,
                'long_term_hold': True,
                'core_position': True,
            }
        )
        
        # 纳指ETF - 趋势跟踪
        self.strategies['513100'] = ETFStrategy(
            symbol='513100',
            name='纳指ETF',
            category='overseas',
            style='trend_following',
            weights=AnalysisWeights(
                strength=0.30,
                emotion=0.10,
                trend=0.45,
                capital=0.15
            ),
            rsi_oversold=30.0,
            rsi_overbought=80.0,
            risk_control=RiskControl(
                stop_loss=-10.0,
                take_profit=25.0,
                max_position=0.15,
            ),
            entry_conditions=[
                EntryCondition('trend_up', '趋势向上', weight=2.5, required=True),
                EntryCondition('pullback_buy', '回调买入', weight=1.5),
                EntryCondition('momentum_positive', '动量为正', weight=1.0),
            ],
            exit_conditions=[
                ExitCondition('trend_down', '趋势向下', priority=1),
                ExitCondition('momentum_negative', '动量转负', priority=2),
            ],
            special_rules={
                'trend_following': True,
                'avoid_short_in_panic': True,
                'ignore_a_share_emotion': True,
                'overseas_asset': True,
            }
        )
        
        # 黄金ETF(518880) - 避险资产（通用黄金策略）
        self.strategies['518880'] = ETFStrategy(
            symbol='518880',
            name='黄金ETF',
            category='commodity',
            style='hedge',
            weights=AnalysisWeights(
                strength=0.25,
                emotion=0.05,
                trend=0.50,
                capital=0.20
            ),
            rsi_oversold=25.0,
            rsi_overbought=80.0,
            risk_control=RiskControl(
                stop_loss=-8.0,
                take_profit=20.0,
                max_position=0.10,
            ),
            entry_conditions=[
                EntryCondition('trend_up', '趋势向上', weight=2.5, required=True),
                EntryCondition('risk_off', '避险情绪', weight=1.5),
            ],
            exit_conditions=[
                ExitCondition('trend_down', '趋势向下', priority=1),
                ExitCondition('risk_on', '风险偏好上升', priority=2),
            ],
            special_rules={
                'trend_following': True,
                'hedge_asset': True,
                'inverse_correlation': True,
                'no_despair_buy': True,
            }
        )
        
        # ============================================
        # 黄金ETF(159934) - 优化后的趋势跟踪策略 v2
        # ============================================
        # 优化前：收益173.53%，胜率60.9%，回撤-14.37%
        # 优化后：收益140.59%，胜率76.9%，回撤-9.82%
        # 
        # 核心优化点：
        # 1. 均线金叉需要MA13斜率确认（胜率从42.9%提升到100%）
        # 2. 布林带/RSI信号需要企稳确认（胜率从50%提升到75%）
        # 3. 震荡期降低信号权重，减少假信号
        # 4. 提高卖出门槛，让利润更好地奔跑
        # ============================================
        self.strategies['159934'] = ETFStrategy(
            symbol='159934',
            name='黄金ETF(易方达)',
            category='commodity',
            style='trend_following',  # 趋势跟踪风格
            weights=AnalysisWeights(
                strength=0.20,      # 强弱权重
                emotion=0.05,       # 情绪权重（黄金与A股情绪低相关）
                trend=0.55,         # 趋势权重（核心，黄金趋势性极强）
                capital=0.20        # 资金面权重
            ),
            rsi_oversold=30.0,      # RSI超卖阈值
            rsi_overbought=85.0,    # RSI超买阈值（黄金超买钝化，提高阈值）
            risk_control=RiskControl(
                stop_loss=-8.0,             # 止损
                take_profit=35.0,           # 止盈（提高）
                trailing_stop=15.0,         # 移动止盈回撤
                time_stop_weeks=52,         # 时间止损（一年）
                time_stop_min_profit=5.0,   # 时间止损最低收益
                max_position=0.90,          # 最大仓位
                min_position=0.30,          # 最小仓位
            ),
            entry_conditions=[
                # 核心买入条件（按优化后胜率排序）
                EntryCondition('golden_cross', '均线金叉+MA13上行 - 胜率100%', weight=4.0, required=False),
                EntryCondition('macd_golden', 'MACD金叉 - 胜率100%', weight=3.5, required=False),
                EntryCondition('panic_volume_down', '恐慌放量下跌后 - 胜率100%', weight=4.5, required=False),
                EntryCondition('ma_bullish', '均线多头排列+趋势确认 - 胜率75%', weight=4.0, required=False),
                EntryCondition('boll_lower', '布林带下轨+企稳 - 胜率75%', weight=3.5, required=False),
                EntryCondition('rsi_oversold', 'RSI超卖+企稳 - 胜率75%', weight=3.0, required=False),
            ],
            exit_conditions=[
                ExitCondition('stop_loss', '触发止损(-8%)', priority=1),
                ExitCondition('trailing_stop', '移动止盈触发(15%回撤)', priority=1),
                ExitCondition('take_profit', '触发止盈(+35%)', priority=2),
                ExitCondition('ma_bearish', '均线空头排列', priority=2),
                ExitCondition('death_cross', '均线死叉', priority=2),
                ExitCondition('break_ma26', '跌破MA26半年线', priority=2),
            ],
            special_rules={
                # ========== 黄金ETF优化规则 v2 ==========
                'use_gold_rules': True,
                'use_optimized_rules': True,  # 启用优化规则
                
                # ========== 趋势跟踪策略 ==========
                'trend_following': True,
                'trend_filter_mode': 'moderate',  # 适中趋势过滤
                'block_downtrend_entry': False,
                'allow_sideways_entry': True,
                'require_ma_support': False,
                
                # ========== 持仓时间控制 ==========
                'min_holding_days': 14,
                'max_holding_days': 365,
                'optimal_holding_weeks': 26,
                'force_exit_at_max': False,
                
                # ========== 均线金叉优化（需要趋势确认） ==========
                'golden_cross_buy': True,
                'golden_cross_weight': 4.0,
                'golden_cross_require_slope': True,  # 需要MA13斜率向上
                'golden_cross_min_slope': 0.0,  # MA13斜率最小值
                'golden_cross_ma_fast': 4,
                'golden_cross_ma_slow': 13,
                
                # ========== 恐慌放量下跌买入 ==========
                'panic_volume_buy': True,
                'panic_vol_ratio': 1.5,
                'panic_down_pct': -1.0,
                'panic_buy_weight': 4.5,
                'panic_require_stabilize': False,
                
                # ========== 布林带规则（优化：需要企稳确认） ==========
                'boll_lower_buy': True,
                'boll_position_threshold': 0.05,
                'boll_lower_weight': 3.5,
                'boll_require_stabilize': True,  # 下轨买入需要企稳
                'boll_upper_sell': False,
                'boll_upper_continuation': True,
                'boll_upper_weight': 0.0,
                
                # ========== RSI规则（优化：需要企稳确认） ==========
                'rsi_oversold_buy': True,
                'rsi_oversold_threshold': 30,
                'rsi_oversold_weight': 3.0,
                'rsi_require_stabilize': True,  # RSI超卖需要企稳
                'rsi_overbought_sell': False,
                'rsi_extreme_threshold': 85,
                'rsi_extreme_sell': True,
                
                # ========== MACD规则 ==========
                'macd_golden_buy': True,
                'macd_below_zero_weight': 3.5,
                'macd_above_zero_weight': 3.0,
                'macd_death_sell': True,
                'macd_death_weight': 2.5,
                
                # ========== 成交量规则 ==========
                'volume_breakout_buy': True,
                'breakout_vol_ratio': 1.5,
                'breakout_weight': 2.5,
                'volume_surge_stall_exit': True,
                'surge_vol_ratio': 2.0,
                'stall_pct_threshold': 0.3,
                
                # ========== 均线系统 ==========
                'use_ma_system': True,
                'ma_bullish_buy': True,
                'ma_bullish_weight': 4.0,  # 提高权重
                'ma_bullish_require_slope': True,  # 需要MA13斜率向上
                'ma_bullish_hold': True,
                'ma_bearish_exit': True,
                'ma_bearish_weight': 3.0,
                'break_ma26_exit': True,
                'break_ma26_weight': 2.0,
                
                # ========== 动态卖出规则（优化：更宽松） ==========
                'dynamic_exit': True,
                'exit_profit_4w': 12.0,
                'exit_profit_8w': 18.0,
                'exit_profit_13w': 25.0,
                'exit_profit_26w': 35.0,
                'exit_profit_52w': 45.0,
                'exit_loss_threshold': -8.0,
                
                # ========== 入场限制（优化：放宽黄金特有的超买钝化） ==========
                'rsi_entry_max': 82,
                'avoid_high_position_entry': True,
                'high_position_threshold': 0.98,
                'boll_high_position_penalty': 0.90,
                
                # ========== 震荡期过滤（优化） ==========
                'sideways_filter_enabled': True,
                'sideways_score_multiplier': 0.7,  # 震荡期信号权重乘数
                'sideways_min_score': 3.0,  # 震荡期最低买入分数
                
                # ========== 买入评分门槛（优化后） ==========
                'buy_score_threshold': 2.0,
                'strong_buy_threshold': 4.0,
                'sell_score_threshold': -2.5,  # 提高卖出门槛
                
                # ========== 交易频率控制 ==========
                'entry_cooldown_days': 7,
                'sell_signal_confirm_days': 3,
                
                # ========== 黄金特殊属性 ==========
                'hedge_asset': True,
                'inverse_correlation': True,
                'long_term_uptrend': True,
                'overbought_blunting': True,
                'short_bear_period': True,
                
                # ========== 浮盈加仓策略 ==========
                'pyramid_add_enabled': True,
                'pyramid_profit_threshold_1': 5.0,
                'pyramid_profit_threshold_2': 10.0,
                'pyramid_profit_threshold_3': 15.0,
                'pyramid_add_ratio_1': 0.30,
                'pyramid_add_ratio_2': 0.25,
                'pyramid_add_ratio_3': 0.20,
                'pyramid_max_adds': 3,
                'pyramid_min_holding_days': 7,
                'pyramid_rsi_max': 80,
                'pyramid_trend_required': True,
                'pyramid_cooldown_days': 5,
            }
        )
    
    def get_strategy(self, symbol: str) -> Optional[ETFStrategy]:
        """获取指定ETF的策略"""
        return self.strategies.get(symbol)
    
    def set_strategy(self, symbol: str, strategy: ETFStrategy):
        """设置指定ETF的策略"""
        self.strategies[symbol] = strategy
    
    def update_strategy(self, symbol: str, updates: Dict[str, Any]) -> Optional[ETFStrategy]:
        """
        更新指定ETF的策略配置
        
        Args:
            symbol: ETF代码
            updates: 要更新的配置项
            
        Returns:
            更新后的策略，如果ETF不存在则返回None
        """
        if symbol not in self.strategies:
            return None
        
        strategy = self.strategies[symbol]
        
        # 更新各项配置
        for key, value in updates.items():
            if key == 'weights' and isinstance(value, dict):
                for w_key, w_value in value.items():
                    if hasattr(strategy.weights, w_key):
                        setattr(strategy.weights, w_key, w_value)
                strategy.weights.normalize()
            elif key == 'risk_control' and isinstance(value, dict):
                for r_key, r_value in value.items():
                    if hasattr(strategy.risk_control, r_key):
                        setattr(strategy.risk_control, r_key, r_value)
            elif key == 'special_rules' and isinstance(value, dict):
                strategy.special_rules.update(value)
            elif hasattr(strategy, key):
                setattr(strategy, key, value)
        
        return strategy
    
    def delete_strategy(self, symbol: str) -> bool:
        """删除指定ETF的策略"""
        if symbol in self.strategies:
            del self.strategies[symbol]
            return True
        return False
    
    def list_strategies(self) -> List[Dict]:
        """列出所有策略"""
        return [
            {
                'symbol': s.symbol,
                'name': s.name,
                'category': s.category,
                'style': s.style,
                'enabled': s.enabled,
            }
            for s in self.strategies.values()
        ]
    
    def get_strategies_by_category(self, category: str) -> List[ETFStrategy]:
        """按分类获取策略"""
        return [s for s in self.strategies.values() if s.category == category]
    
    def get_strategies_by_style(self, style: str) -> List[ETFStrategy]:
        """按风格获取策略"""
        return [s for s in self.strategies.values() if s.style == style]
    
    def save_strategies(self, filepath: str = None):
        """
        保存所有策略到文件
        
        Args:
            filepath: 文件路径，默认为config_dir/strategies.json
        """
        if filepath is None:
            os.makedirs(self.config_dir, exist_ok=True)
            filepath = os.path.join(self.config_dir, 'strategies.json')
        
        data = {symbol: s.to_dict() for symbol, s in self.strategies.items()}
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_strategies(self, filepath: str = None):
        """
        从文件加载策略
        
        Args:
            filepath: 文件路径，默认为config_dir/strategies.json
        """
        if filepath is None:
            filepath = os.path.join(self.config_dir, 'strategies.json')
        
        if not os.path.exists(filepath):
            return
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for symbol, strategy_data in data.items():
            self.strategies[symbol] = ETFStrategy.from_dict(strategy_data)
    
    def create_strategy_from_template(self, symbol: str, name: str, 
                                       template: str = 'balanced') -> ETFStrategy:
        """
        从模板创建策略
        
        Args:
            symbol: ETF代码
            name: ETF名称
            template: 模板名称 (defensive/aggressive/balanced/trend_following/hedge)
            
        Returns:
            新创建的策略
        """
        templates = {
            'defensive': {
                'style': 'defensive',
                'weights': AnalysisWeights(0.35, 0.20, 0.25, 0.20),
                'rsi_oversold': 35.0,
                'rsi_overbought': 75.0,
                'risk_control': RiskControl(-6.0, 12.0, 0, 12, 3.0, 0.25, 0.05),
            },
            'aggressive': {
                'style': 'aggressive',
                'weights': AnalysisWeights(0.50, 0.25, 0.15, 0.10),
                'rsi_oversold': 25.0,
                'rsi_overbought': 75.0,
                'risk_control': RiskControl(-10.0, 20.0, 0, 12, 3.0, 0.15, 0.05),
            },
            'balanced': {
                'style': 'balanced',
                'weights': AnalysisWeights(0.45, 0.25, 0.15, 0.15),
                'rsi_oversold': 30.0,
                'rsi_overbought': 70.0,
                'risk_control': RiskControl(-8.0, 15.0, 0, 12, 3.0, 0.20, 0.05),
            },
            'trend_following': {
                'style': 'trend_following',
                'weights': AnalysisWeights(0.30, 0.10, 0.45, 0.15),
                'rsi_oversold': 30.0,
                'rsi_overbought': 80.0,
                'risk_control': RiskControl(-10.0, 25.0, 0, 12, 3.0, 0.15, 0.05),
            },
            'hedge': {
                'style': 'hedge',
                'weights': AnalysisWeights(0.25, 0.05, 0.50, 0.20),
                'rsi_oversold': 25.0,
                'rsi_overbought': 80.0,
                'risk_control': RiskControl(-8.0, 20.0, 0, 12, 3.0, 0.10, 0.05),
            },
        }
        
        t = templates.get(template, templates['balanced'])
        
        strategy = ETFStrategy(
            symbol=symbol,
            name=name,
            style=t['style'],
            weights=t['weights'],
            rsi_oversold=t['rsi_oversold'],
            rsi_overbought=t['rsi_overbought'],
            risk_control=t['risk_control'],
        )
        
        self.strategies[symbol] = strategy
        return strategy


# 全局策略管理器实例
strategy_manager = ETFStrategyManager()
