"""
ETF配置系统 - 核心配置文件

支持每个ETF单独配置策略，修改一个ETF策略不影响其他ETF。
核心思想：
1. 强弱分析法 - 该涨不涨看跌，该跌不跌看涨
2. 情绪周期分析 - 绝望中产生→犹豫中发展→疯狂中消亡
3. 资金面分析 - 恶炒消耗资金，大盘拉抬性强
4. 对冲战法 - 以变应变，留有余地
5. 分类应对法 - 不同ETF有单独的策略
"""

from typing import Dict, List, Any

# ==================== ETF池定义 ====================
ETF_POOL: Dict[str, str] = {
    # 红利类
    '515450': '红利低波50ETF',
    '515180': '红利ETF',
    
    # 大盘蓝筹
    '510300': '沪深300ETF',
    '510050': '上证50ETF',
    '512800': '银行ETF',
    
    # 创业板/中小盘
    '159949': '创业板50ETF',
    '159902': '中小100ETF',
    '159915': '创业板ETF',
    
    # 科技成长
    '512480': '半导体ETF',
    '515030': '新能源车ETF',
    '159995': '芯片ETF',
    
    # 消费医药
    '512690': '酒ETF',
    '512170': '医疗ETF',
    '159928': '消费ETF',
    
    # 特殊资产（与A股相关性低）
    '159934': '黄金ETF',
    '159941': '纳指ETF',
    '164824': '印度基金LOF',
    '159985': '豆粕ETF',
}

# 大盘股ETF
LARGE_CAP_ETFS: List[str] = [
    '510300', '510050', '512800', '515450', '515180'
]

# 小盘股ETF
SMALL_CAP_ETFS: List[str] = [
    '159949', '159902', '159915', '512480', '515030'
]

# 特殊资产（使用趋势跟踪策略）
SPECIAL_ASSETS: List[str] = [
    '159934',  # 黄金ETF
    '159941',  # 纳指ETF
    '164824',  # 印度基金
    '159985',  # 豆粕ETF
]

# 不参与绝望期抄底的资产（商品类等）
NO_DESPAIR_BUY_ASSETS: List[str] = [
    '159934',  # 黄金
    '159985',  # 豆粕
]

# ==================== 信号阈值配置 ====================
SIGNAL_THRESHOLDS: Dict[str, float] = {
    'strong_buy': 3,      # 强烈买入信号阈值
    'buy': 2,             # 买入信号阈值
    'sell': -2,           # 卖出信号阈值
    'strong_sell': -3,    # 强烈卖出信号阈值
}

# ==================== 风险参数 ====================
RISK_PARAMS: Dict[str, float] = {
    'stop_loss': -8,          # 止损线：-8%
    'take_profit': 15,        # 止盈线：+15%
    'time_stop_weeks': 12,    # 时间止损：12周
    'time_stop_min_profit': 3, # 时间止损最低收益：3%
    'max_single_position': 0.25,  # 单一持仓上限：25%
    'max_sector_exposure': 0.4,   # 单一板块上限：40%
}

# ==================== 特殊资产超买配置 ====================
SPECIAL_ASSET_OVERBOUGHT: Dict[str, Any] = {
    'rsi_extreme': 85,           # 极度超买RSI阈值
    'rsi_high': 75,              # 高位RSI阈值
    'max_score_when_overbought': 1,  # 超买时最大得分限制
}

# ==================== 特殊资产规则 ====================
SPECIAL_ASSET_RULES: Dict[str, Dict[str, Any]] = {
    '513100': {  # 纳指ETF
        'avoid_short_in_panic': True,   # 恐慌期不做空
        'panic_rsi_threshold': 25,      # 恐慌RSI阈值
        'trend_following': True,        # 使用趋势跟踪
    },
    '164824': {  # 印度基金
        'avoid_short_in_panic': True,
        'panic_rsi_threshold': 25,
        'trend_following': True,
    },
    '518880': {  # 黄金ETF
        'avoid_short_in_panic': True,
        'panic_rsi_threshold': 20,
        'trend_following': True,
    },
    '159985': {  # 豆粕ETF
        'avoid_short_in_panic': False,  # 商品类可以做空
        'panic_rsi_threshold': 20,
        'trend_following': True,
    },
}

# ==================== 信号有效期配置 ====================
SIGNAL_VALIDITY: Dict[str, int] = {
    'strong_buy': 4,    # 强买入信号有效4周
    'buy': 3,           # 买入信号有效3周
    'sell': 3,          # 卖出信号有效3周
    'strong_sell': 4,   # 强卖出信号有效4周
    'neutral': 2,       # 中性信号有效2周
}


# ==================== ETF分类策略配置 ====================
class ETFStrategyConfig:
    """
    ETF策略配置类
    
    每个ETF可以有独立的策略配置，修改一个不影响其他。
    """
    
    # 默认策略配置
    DEFAULT_CONFIG: Dict[str, Any] = {
        'use_weekly': True,           # 使用周线分析
        'strength_weight': 0.45,      # 强弱分析权重
        'emotion_weight': 0.25,       # 情绪分析权重
        'trend_weight': 0.15,         # 趋势确认权重
        'capital_weight': 0.15,       # 资金面权重
        'rsi_oversold': 30,           # RSI超卖阈值
        'rsi_overbought': 70,         # RSI超买阈值
        'position_limit': 0.20,       # 默认仓位上限
        'stop_loss': -8,              # 止损线
        'take_profit': 15,            # 止盈线
        'entry_conditions': [],       # 入场条件
        'exit_conditions': [],        # 出场条件
    }
    
    # 红利低波50ETF(515450) - 防御型策略（优化版）
    # 优化说明：
    # 1. 提高仓位上限以增加收益捕获
    # 2. 放宽止损避免假突破
    # 3. 提高止盈让利润奔跑
    # 4. 调整权重突出趋势跟踪
    CONFIG_515450: Dict[str, Any] = {
        'name': '红利低波50ETF',
        'category': 'dividend',       # 分类：红利类
        'style': 'defensive',         # 风格：防御型
        'use_weekly': True,
        'strength_weight': 0.30,      # 降低强弱权重（红利股信号滞后）
        'emotion_weight': 0.15,       # 降低情绪权重（红利股受情绪影响小）
        'trend_weight': 0.35,         # 提高趋势权重（红利股趋势性强）
        'capital_weight': 0.20,       # 保持资金面权重
        'rsi_oversold': 32,           # 略微降低超卖阈值，更早入场
        'rsi_overbought': 78,         # 提高超买阈值，延长持有
        'position_limit': 0.40,       # 提高仓位上限（25%->40%）
        'stop_loss': -8,              # 放宽止损（-6%->-8%）
        'take_profit': 18,            # 提高止盈（12%->18%）
        'trailing_stop': 5,           # 启用5%移动止盈
        'time_stop_weeks': 16,        # 延长时间止损（12->16周）
        'time_stop_min_profit': 2,    # 降低时间止损最低收益要求
        'entry_conditions': [
            'rsi_oversold',           # RSI超卖
            'price_below_ma20',       # 价格低于20周均线
            'dividend_yield_high',    # 股息率较高
            'trend_support',          # 趋势支撑位（新增）
            'volume_shrink',          # 缩量企稳（新增）
        ],
        'exit_conditions': [
            'rsi_overbought',         # RSI超买
            'trend_reversal',         # 趋势反转
            'dividend_yield_low',     # 股息率下降
            'trailing_stop',          # 移动止盈（新增）
        ],
        'special_rules': {
            'prefer_despair_phase': True,    # 偏好绝望期买入
            'avoid_frenzy_chase': True,      # 避免疯狂期追高
            'use_dividend_factor': True,     # 使用股息因子
            'trend_following_lite': True,    # 轻度趋势跟踪（新增）
            'allow_add_position': True,      # 允许加仓（新增）
            'scale_in_on_dip': True,         # 下跌分批建仓（新增）
            'protect_profit_above': 8,       # 盈利8%后启动保护（新增）
        },
    }
    
    # 创业板50ETF(159949) - 成长型策略
    CONFIG_159949: Dict[str, Any] = {
        'name': '创业板50ETF',
        'category': 'growth',         # 分类：成长类
        'style': 'aggressive',        # 风格：进攻型
        'use_weekly': True,
        'strength_weight': 0.50,      # 提高强弱权重（成长股波动大）
        'emotion_weight': 0.25,       # 情绪权重
        'trend_weight': 0.15,         # 趋势权重
        'capital_weight': 0.10,       # 降低资金面权重
        'rsi_oversold': 25,           # 成长股RSI超卖阈值较低
        'rsi_overbought': 75,         # 成长股RSI超买阈值
        'position_limit': 0.15,       # 较低仓位（波动大）
        'stop_loss': -10,             # 较宽止损（波动大）
        'take_profit': 20,            # 较高止盈（成长股涨幅大）
        'entry_conditions': [
            'rsi_oversold',
            'macd_golden_cross',      # MACD金叉
            'volume_breakout',        # 放量突破
        ],
        'exit_conditions': [
            'rsi_overbought',
            'macd_death_cross',       # MACD死叉
            'volume_divergence',      # 量价背离
        ],
        'special_rules': {
            'prefer_despair_phase': True,
            'momentum_factor': True,         # 使用动量因子
            'avoid_bear_market': True,       # 熊市回避
            'sector_rotation_sensitive': True,  # 板块轮动敏感
        },
    }
    
    # 中小100ETF(159902) - 均衡型策略
    CONFIG_159902: Dict[str, Any] = {
        'name': '中小100ETF',
        'category': 'mid_small',      # 分类：中小盘
        'style': 'balanced',          # 风格：均衡型
        'use_weekly': True,
        'strength_weight': 0.45,
        'emotion_weight': 0.25,
        'trend_weight': 0.15,
        'capital_weight': 0.15,
        'rsi_oversold': 28,
        'rsi_overbought': 72,
        'position_limit': 0.18,
        'stop_loss': -9,
        'take_profit': 18,
        'entry_conditions': [
            'rsi_oversold',
            'price_support',          # 价格支撑
            'sector_rotation_favor',  # 板块轮动有利
        ],
        'exit_conditions': [
            'rsi_overbought',
            'price_resistance',       # 价格阻力
            'capital_outflow',        # 资金流出
        ],
        'special_rules': {
            'prefer_despair_phase': True,
            'style_rotation_aware': True,    # 风格轮动感知
            'small_cap_premium': True,       # 小盘溢价因子
        },
    }
    
    # 沪深300ETF(510300) - 核心配置策略
    CONFIG_510300: Dict[str, Any] = {
        'name': '沪深300ETF',
        'category': 'core',           # 分类：核心资产
        'style': 'core',              # 风格：核心配置
        'use_weekly': True,
        'strength_weight': 0.40,
        'emotion_weight': 0.25,
        'trend_weight': 0.20,
        'capital_weight': 0.15,
        'rsi_oversold': 30,
        'rsi_overbought': 70,
        'position_limit': 0.30,       # 核心资产可以较高仓位
        'stop_loss': -7,
        'take_profit': 15,
        'entry_conditions': [
            'rsi_oversold',
            'market_despair',         # 市场绝望
            'valuation_low',          # 估值较低
        ],
        'exit_conditions': [
            'rsi_overbought',
            'market_frenzy',          # 市场疯狂
            'valuation_high',         # 估值较高
        ],
        'special_rules': {
            'prefer_despair_phase': True,
            'market_benchmark': True,        # 作为市场基准
            'long_term_hold': True,          # 适合长期持有
        },
    }
    
    # 纳指ETF(513100) - 趋势跟踪策略
    CONFIG_513100: Dict[str, Any] = {
        'name': '纳指ETF',
        'category': 'overseas',       # 分类：海外资产
        'style': 'trend_following',   # 风格：趋势跟踪
        'use_weekly': True,
        'strength_weight': 0.30,      # 降低强弱权重
        'emotion_weight': 0.10,       # 大幅降低情绪权重（与A股情绪不同）
        'trend_weight': 0.45,         # 大幅提高趋势权重
        'capital_weight': 0.15,
        'rsi_oversold': 30,
        'rsi_overbought': 80,         # 美股可以更超买
        'position_limit': 0.15,       # 海外资产仓位控制
        'stop_loss': -10,
        'take_profit': 25,            # 美股涨幅可以更大
        'entry_conditions': [
            'trend_up_confirmed',     # 趋势向上确认
            'pullback_buy',           # 回调买入
            'momentum_positive',      # 动量为正
        ],
        'exit_conditions': [
            'trend_down_confirmed',   # 趋势向下确认
            'momentum_negative',      # 动量转负
        ],
        'special_rules': {
            'trend_following': True,         # 趋势跟踪
            'avoid_short_in_panic': True,    # 恐慌期不做空
            'ignore_a_share_emotion': True,  # 忽略A股情绪
        },
    }
    
    # 黄金ETF(518880) - 避险资产策略
    CONFIG_518880: Dict[str, Any] = {
        'name': '黄金ETF',
        'category': 'commodity',      # 分类：商品
        'style': 'hedge',             # 风格：对冲避险
        'use_weekly': True,
        'strength_weight': 0.25,
        'emotion_weight': 0.05,       # 几乎不用A股情绪
        'trend_weight': 0.50,         # 黄金趋势性极强
        'capital_weight': 0.20,
        'rsi_oversold': 25,
        'rsi_overbought': 80,
        'position_limit': 0.10,       # 黄金仓位控制
        'stop_loss': -8,
        'take_profit': 20,
        'entry_conditions': [
            'trend_up_confirmed',
            'risk_off_environment',   # 避险环境
            'dollar_weak',            # 美元走弱
        ],
        'exit_conditions': [
            'trend_down_confirmed',
            'risk_on_environment',    # 风险偏好上升
        ],
        'special_rules': {
            'trend_following': True,
            'hedge_asset': True,             # 避险资产
            'inverse_correlation': True,     # 与股市负相关
        },
    }
    
    @classmethod
    def get_config(cls, symbol: str) -> Dict[str, Any]:
        """
        获取指定ETF的策略配置
        
        Args:
            symbol: ETF代码
            
        Returns:
            策略配置字典
        """
        config_map = {
            '515450': cls.CONFIG_515450,
            '159949': cls.CONFIG_159949,
            '159902': cls.CONFIG_159902,
            '510300': cls.CONFIG_510300,
            '513100': cls.CONFIG_513100,
            '518880': cls.CONFIG_518880,
        }
        
        if symbol in config_map:
            # 合并默认配置和特定配置
            config = cls.DEFAULT_CONFIG.copy()
            config.update(config_map[symbol])
            return config
        
        # 返回默认配置
        default = cls.DEFAULT_CONFIG.copy()
        default['name'] = ETF_POOL.get(symbol, symbol)
        return default
    
    @classmethod
    def update_config(cls, symbol: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新指定ETF的策略配置
        
        Args:
            symbol: ETF代码
            updates: 要更新的配置项
            
        Returns:
            更新后的配置
        """
        config = cls.get_config(symbol)
        config.update(updates)
        return config
    
    @classmethod
    def get_all_configs(cls) -> Dict[str, Dict[str, Any]]:
        """获取所有ETF的配置"""
        return {symbol: cls.get_config(symbol) for symbol in ETF_POOL}


# ==================== 策略分类定义 ====================
STRATEGY_CATEGORIES: Dict[str, Dict[str, Any]] = {
    'dividend': {
        'name': '红利类',
        'description': '高股息、低波动，适合防御配置',
        'symbols': ['515450', '515180'],
        'default_weight': 0.25,
        'risk_level': 'low',
    },
    'growth': {
        'name': '成长类',
        'description': '高成长、高波动，适合进攻配置',
        'symbols': ['159949', '159915', '512480', '515030'],
        'default_weight': 0.20,
        'risk_level': 'high',
    },
    'core': {
        'name': '核心资产',
        'description': '宽基指数，适合核心配置',
        'symbols': ['510300', '510050'],
        'default_weight': 0.30,
        'risk_level': 'medium',
    },
    'mid_small': {
        'name': '中小盘',
        'description': '中小市值，弹性较大',
        'symbols': ['159902'],
        'default_weight': 0.10,
        'risk_level': 'medium_high',
    },
    'overseas': {
        'name': '海外资产',
        'description': '分散风险，与A股低相关',
        'symbols': ['513100', '164824'],
        'default_weight': 0.10,
        'risk_level': 'medium',
    },
    'commodity': {
        'name': '商品类',
        'description': '避险资产，对冲通胀',
        'symbols': ['518880', '159985'],
        'default_weight': 0.05,
        'risk_level': 'medium',
    },
}
