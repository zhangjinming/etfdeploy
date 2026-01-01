"""ETF配置常量"""

# 核心ETF池 - 覆盖主要风格
ETF_POOL: dict[str, str] = {
    # 宽基指数
    '510300': '沪深300ETF',
    '510050': '上证50ETF',
    '159915': '创业板ETF',
    '159949': '创业板50ETF',
    '588390': '科创创业50ETF',
    '159902': '中小100ETF',
    '512100': '中证1000ETF',
    '515450': '红利低波50ETF',
    '159740': '恒生科技ETF',
    # 行业ETF
    '512690': '白酒ETF',
    '515790': '光伏ETF',
    '512480': '半导体ETF',
    '512010': '医药ETF',
    '512880': '证券ETF',
    '512800': '银行ETF',
    '515180': '红利ETF',
    '512400': '有色ETF',
    '159941': '纳指ETF',
    '164824': '印度ETF',
    # 商品
    '159934': '黄金ETF',
    '159985': '豆粕ETF',
    '160723': '嘉实原油ETF',
}

# 大盘vs小盘分类
LARGE_CAP_ETFS = ['510300', '510050', '512800', '515180']
SMALL_CAP_ETFS = ['159902', '159915', '512100']

# 基准ETF（用于判断市场环境）
BENCHMARK_ETF = '510300'  # 沪深300作为基准

# 特殊资产类别（需要趋势跟踪而非逆向策略）
SPECIAL_ASSETS = {
    '159934': {'type': 'gold', 'name': '黄金ETF', 'strategy': 'trend_follow'},      # 避险资产
    '159941': {'type': 'us_stock', 'name': '纳指ETF', 'strategy': 'trend_follow'},  # 美股联动
    '164824': {'type': 'foreign', 'name': '印度ETF', 'strategy': 'trend_follow'},   # 海外市场
    '159985': {'type': 'commodity', 'name': '豆粕ETF', 'strategy': 'trend_follow'}, # 商品
    '160723': {'type': 'commodity', 'name': '原油ETF', 'strategy': 'trend_follow'}, # 商品
}

# 禁止绝望期抄底的资产（趋势性极强，抄底风险大）
# 这些资产只使用趋势跟踪策略，不参与绝望期抄底推荐
NO_DESPAIR_BUY_ASSETS = {
    '160723': '嘉实原油ETF',   # 原油趋势性极强，2020年负油价教训
    '159985': '豆粕ETF',       # 农产品受供需影响大
    '159934': '黄金ETF',       # 【优化】黄金趋势性强，绝望期抄底风险大
}

# 【优化】趋势性资产配置（这些资产使用纯趋势跟踪，不使用逆向策略）
TREND_FOLLOW_ASSETS = {
    '160723': {  # 原油ETF
        'name': '嘉实原油ETF',
        'trend_weight': 0.9,           # 趋势权重极高
        'emotion_weight': 0.1,         # 情绪权重极低
        'avoid_threshold': 5.0,        # 回避验证阈值提高到5%
        'no_despair_short': True,      # 绝望期不做空
        'min_trend_weeks': 4,          # 趋势确认需要4周
    },
    '159985': {  # 豆粕ETF
        'name': '豆粕ETF',
        'trend_weight': 0.8,
        'emotion_weight': 0.2,
        'avoid_threshold': 4.0,
        'no_despair_short': True,
        'min_trend_weeks': 3,
    },
    '159934': {  # 黄金ETF
        'name': '黄金ETF',
        'trend_weight': 0.75,
        'emotion_weight': 0.25,
        'avoid_threshold': 4.0,
        'no_despair_short': True,      # 【优化】黄金绝望期不做空
        'min_trend_weeks': 3,
    },
    '159941': {  # 纳指ETF
        'name': '纳指ETF',
        'trend_weight': 0.7,
        'emotion_weight': 0.3,
        'avoid_threshold': 5.0,        # 【优化】纳指回避阈值提高
        'no_despair_short': True,      # 【优化】纳指绝望期不做空
        'min_trend_weeks': 3,
    },
    '164824': {  # 印度ETF
        'name': '印度ETF',
        'trend_weight': 0.7,
        'emotion_weight': 0.3,
        'avoid_threshold': 4.0,
        'no_despair_short': True,
        'min_trend_weeks': 3,
    },
}

# P0优化：特殊资产规则（趋势性资产在恐慌期的特殊处理）
SPECIAL_ASSET_RULES = {
    '159941': {  # 纳指ETF
        'strategy': 'trend_follow',
        'avoid_short_in_panic': True,       # 恐慌期不发卖出信号
        'panic_rsi_threshold': 25,          # RSI<25视为恐慌
        'min_trend_confirm_weeks': 3,       # 趋势确认需要3周
        'weight_factor': 1.0,               # 权重因子
    },
    '164824': {  # 印度ETF
        'strategy': 'trend_follow',
        'avoid_short_in_panic': True,
        'panic_rsi_threshold': 25,
        'min_trend_confirm_weeks': 3,
        'weight_factor': 0.7,               # 降低权重，海外市场不确定性大
    },
    '159934': {  # 黄金ETF
        'strategy': 'trend_follow',
        'avoid_short_in_panic': False,      # 黄金是避险资产，不需要恐慌保护
        'panic_rsi_threshold': 25,
        'min_trend_confirm_weeks': 2,
        'weight_factor': 1.0,
    },
    '160723': {  # 原油ETF
        'strategy': 'trend_follow',
        'avoid_short_in_panic': False,      # 原油趋势性强，不做恐慌保护
        'panic_rsi_threshold': 20,
        'min_trend_confirm_weeks': 4,
        'weight_factor': 0.5,               # 大幅降低权重
    },
}

# 波动率过滤参数（用于识别系统性风险）
VOLATILITY_FILTER = {
    'extreme_vol_threshold': 5.0,   # 周波动率>5%视为极端波动
    'high_vol_threshold': 3.0,      # 周波动率>3%视为高波动
    'vol_lookback_weeks': 4,        # 波动率计算回溯周数
    'stop_despair_buy_vol': 4.0,    # 波动率超过此值停止绝望期抄底
    'max_consecutive_drops': 4,     # 连续下跌超过此周数视为系统性风险
    'benchmark_drawdown_limit': -10, # P0新增：基准回撤超过此值停止抄底
}

# 止损止盈参数
RISK_PARAMS = {
    'stop_loss': -5.0,          # 止损线：-5%（1个月内亏损超过5%触发止损）
    'take_profit': 15.0,        # 止盈线：15%
    'time_stop_weeks': 26,      # 时间止损（约6个月）
    'time_stop_min_profit': 3.0, # 时间止损最低收益
    
    # 动态移动止损参数（保留原版本）
    'enable_trailing_stop': True,     # 启用移动止损
    'trailing_stop_trigger': 12.0,    # 盈利12%后启用移动止损
    'trailing_stop_distance': 8.0,    # 移动止损距离8%
    'trailing_stop_min_profit': 5.0,  # 止损后至少保留5%利润
    
    # 动态止损分级（保留但使用更宽松的设置）
    'dynamic_trailing_stop': {
        'enable': True,
        'levels': [
            {'profit_min': 12.0, 'profit_max': 25.0, 'drawdown_tolerance': 8.0},
            {'profit_min': 25.0, 'profit_max': 40.0, 'drawdown_tolerance': 10.0},
            {'profit_min': 40.0, 'profit_max': 60.0, 'drawdown_tolerance': 12.0},
            {'profit_min': 60.0, 'profit_max': 999.0, 'drawdown_tolerance': 15.0},
        ],
    },
    
    # 买入缓冲期（保留，有助于避免频繁止损）
    'buy_buffer_days': 3,             # 买入后3个交易日不止损（从5天减少）
    
    # 【关闭】分批止损 - 实测会降低胜率
    'partial_stop_loss': {
        'enable': False,              # 关闭分批止损
        'first_stop_pct': -5.0,
        'first_sell_ratio': 0.5,
        'second_stop_pct': -8.0,
        'second_sell_ratio': 1.0,
    },
}

# 浮盈加仓策略参数（还原到原版本）
PROFIT_ADD_PARAMS = {
    'enable': True,                     # 是否启用浮盈加仓
    
    # 加仓触发条件
    'min_profit_pct': 25.0,             # 最低浮盈比例25%
    'strong_profit_pct': 40.0,          # 强势浮盈比例40%
    'min_holding_weeks': 8,             # 最少持仓周数8周
    
    # 加仓比例
    'add_ratio_normal': 0.25,           # 普通加仓25%
    'add_ratio_strong': 0.4,            # 强势加仓40%
    'max_position_ratio': 0.25,         # 单个持仓最大占比25%
    
    # 加仓次数限制
    'max_add_times': 1,                 # 单个标的最多加仓次数
    'add_cooldown_weeks': 8,            # 加仓冷却期8周
    
    # 趋势确认
    'require_trend_confirm': True,      # 加仓需要趋势确认
    'trend_ma_period': 10,              # 趋势判断均线周期
    'price_above_ma': True,             # 价格需在均线上方
    
    # 回撤保护
    'max_drawdown_from_high': -2.0,     # 从最高点回撤不超过-2%
    'profit_protection': True,          # 启用浮盈保护
    'protection_stop_loss': 0.7,        # 保护止损70%已有浮盈
}

# 【胜率优化v2】板块分类（用于仓位集中度控制）
ETF_SECTORS = {
    # 宽基指数
    '510300': 'broad_market',
    '510050': 'broad_market',
    '159915': 'growth',
    '159949': 'growth',
    '588390': 'growth',
    '159902': 'small_cap',
    '512100': 'small_cap',
    '515450': 'dividend',
    '159740': 'hk_tech',
    # 行业ETF
    '512690': 'consumer',
    '515790': 'new_energy',
    '512480': 'tech',
    '512010': 'healthcare',
    '512880': 'finance',
    '512800': 'finance',
    '515180': 'dividend',
    '512400': 'cyclical',
    '159941': 'us_market',
    '164824': 'foreign',
    # 商品
    '159934': 'commodity',
    '159985': 'commodity',
    '160723': 'commodity',
}

# 【胜率优化v2】板块仓位限制
SECTOR_LIMITS = {
    'growth': 0.35,          # 成长板块最多35%
    'finance': 0.30,         # 金融板块最多30%
    'tech': 0.25,            # 科技板块最多25%
    'commodity': 0.20,       # 商品板块最多20%
    'consumer': 0.25,        # 消费板块最多25%
    'new_energy': 0.20,      # 新能源板块最多20%
    'healthcare': 0.20,      # 医药板块最多20%
    'cyclical': 0.20,        # 周期板块最多20%
    'broad_market': 0.40,    # 宽基指数最多40%
    'small_cap': 0.30,       # 小盘股最多30%
    'dividend': 0.30,        # 红利板块最多30%
    'hk_tech': 0.20,         # 港股科技最多20%
    'us_market': 0.15,       # 美股最多15%
    'foreign': 0.15,         # 海外市场最多15%
}

# 【胜率优化v2】相关性高的ETF组（同组内只选1只）
CORRELATED_ETF_GROUPS = [
    ['159915', '159949', '588390'],  # 创业板相关
    ['510300', '510050'],            # 大盘蓝筹
    ['512880', '512800'],            # 金融板块
    ['159902', '512100'],            # 中小盘
]

# 验证参数（优化后降低阈值）
VERIFICATION_PARAMS = {
    'buy_profit_threshold': 1.0,      # 买入验证阈值：收益≥1%即可（原为3%）
    'avoid_loss_threshold': 3.0,      # 回避验证阈值：涨幅≤3%即可
    'stop_loss_threshold': -5.0,      # 止损阈值：亏损超过5%触发止损
    'strong_signal_buy_threshold': 2.0,  # 强信号买入阈值：收益≥2%
    'weak_signal_buy_threshold': 1.0,    # 弱信号买入阈值：收益≥1%
    'commodity_weak_threshold': 0.0,     # 【优化】商品类弱信号阈值：不亏即成功
    'despair_avoid_max_period': 1,       # 【优化】绝望期回避只验证1个月
}

# 信号强度分级参数
SIGNAL_STRENGTH_PARAMS = {
    'strong_signal_score': 4,         # 强信号得分阈值（得分≥4为强信号）
    'weak_signal_score': 2,           # 弱信号得分阈值（得分2-3为弱信号）
    'strong_signal_weight': 1.5,      # 强信号权重系数
    'weak_signal_weight': 0.8,        # 弱信号权重系数
}

# 动态调整参数
DYNAMIC_ADJUSTMENT_PARAMS = {
    'enable_stop_loss': True,         # 启用止损机制
    'enable_signal_downgrade': True,  # 启用信号降级机制
    'consecutive_fail_threshold': 2,  # 连续失败次数阈值，超过则降级
    'recovery_weeks': 4,              # 信号恢复需要的周数
}

# 商品类ETF特殊参数
COMMODITY_ETF_PARAMS = {
    'symbols': ['159985', '160723', '159934'],  # 商品类ETF代码
    'volatility_factor': 1.5,         # 波动率系数（商品波动大）
    'trend_weight': 0.7,              # 趋势权重（商品更依赖趋势）
    'emotion_weight': 0.3,            # 情绪权重（降低情绪周期影响）
    'min_trend_weeks': 3,             # 最小趋势确认周数
    'avoid_despair_buy': True,        # 避免绝望期抄底
}

# 绝望期做空限制参数
DESPAIR_SHORT_LIMITS = {
    'enable_caution': True,           # 启用绝望期做空谨慎模式
    'convert_avoid_to_neutral': True, # 【优化】绝望期回避信号转为观望（不做空）
    'min_downtrend_weeks': 6,         # 最少下跌周数才能做空
    'require_volume_confirm': True,   # 需要成交量确认
    'max_short_score': -3,            # 绝望期最大做空得分限制
    'rsi_floor': 20,                  # RSI地板值，低于此值不做空
}

# 信号阈值参数（优化后提高阈值减少噪音）
SIGNAL_THRESHOLDS = {
    'strong_buy': 5,            # 强买入阈值（原为4）
    'buy': 4,                   # 买入阈值（原为3）
    'sell': -4,                 # 卖出阈值（原为-3）
    'strong_sell': -5,          # 强卖出阈值（原为-4）
}

# 信号有效期（周数）
SIGNAL_VALIDITY = {
    'strong_buy': 4,            # 强买入信号4周有效
    'buy': 2,                   # 买入信号2周有效
    'strong_sell': 4,           # 强卖出信号4周有效
    'sell': 2,                  # 卖出信号2周有效
    'neutral': 1,               # 中性信号1周有效
}

# 市场环境参数
MARKET_REGIME_PARAMS = {
    'ma_period': 20,            # 判断趋势的均线周期（周线）
    'slope_threshold': 0.5,     # 均线斜率阈值（%）
    'bull_threshold': 0.02,     # 牛市判定：价格高于均线的比例
    'bear_threshold': -0.02,    # 熊市判定：价格低于均线的比例
}

# 趋势过滤器参数 - 用于熊市减少抄底频率
TREND_FILTER_PARAMS = {
    # 多周期均线配置
    'short_ma': 5,              # 短期均线（5周）
    'mid_ma': 10,               # 中期均线（10周）
    'long_ma': 20,              # 长期均线（20周）
    
    # 趋势判定条件
    'strong_downtrend_conditions': {
        'ma_alignment': True,           # 均线空头排列
        'price_below_all_ma': True,     # 价格在所有均线下方
        'slope_threshold': -1.5,        # 长期均线斜率阈值
    },
    
    # 熊市抄底限制（还原到原版本）
    'bear_market_restrictions': {
        'enable': True,                 # 启用熊市抄底限制
        'min_rsi': 18,                  # 熊市抄底最低RSI
        'require_ma_support': True,     # 要求均线支撑信号
        'require_volume_dry': True,     # 要求成交量枯竭
        'volume_dry_ratio': 0.4,        # 成交量萎缩40%
        'max_weekly_signals': 2,        # 每周最多2个抄底信号（放宽）
        'cooldown_weeks': 4,            # 冷却期4周
        'require_ma_cross': True,       # 要求短期均线上穿中期均线
    },
    
    # 趋势反转确认
    'reversal_confirmation': {
        'require_higher_low': True,     # 要求形成更高的低点
        'require_ma_cross': True,       # 要求短期均线上穿中期均线
        'min_bounce_pct': 5.0,          # 最小反弹幅度5%
        'confirm_weeks': 3,             # 反转确认3周
    },
    
    # 趋势强度分级
    'trend_strength_levels': {
        'strong_trend_threshold': 0.7,
        'weak_trend_threshold': 0.3,
        'trend_follow_min_strength': 0.5,
    },
    
    # 大盘环境过滤（放宽限制）
    'market_filter': {
        'enable': False,                      # 【关闭】大盘过滤（过于严格）
        'bear_market_max_positions': 6,       # 熊市最多持仓6只（不限制）
        'bear_market_cash_ratio': 0.3,        # 熊市保持30%现金
        'require_benchmark_above_ma': False,
        'benchmark_ma_period': 20,
    },
}

# P0优化：绝望期买入确认参数
DESPAIR_CONFIRMATION = {
    'rsi_threshold': 22,              # RSI阈值22
    'volume_shrink_ratio': 0.5,       # 成交量萎缩比例50%
    'require_support': True,          # 是否需要支撑确认
    'min_down_weeks': 4,              # 最少连续下跌周数4周
    'consecutive_weeks_confirm': 5,   # 5周确认
    'require_stabilization': True,    # 是否需要企稳信号
    'require_decline_slowdown': True, # 要求跌幅收窄
    'decline_slowdown_ratio': 0.4,    # 跌幅收窄比例
    'benchmark_max_drawdown': -8,     # 基准最大回撤-8%
    
    # 二次确认机制
    'require_price_stabilization': True,  # 要求价格企稳
    'stabilization_weeks': 3,             # 价格企稳确认3周
    'require_rsi_divergence': True,       # 要求RSI底背离
    
    # 反弹确认
    'require_bounce_confirm': True,       # 要求从低点反弹确认
    'min_bounce_from_low': 3.0,           # 从最低点至少反弹3%
    'require_higher_low': True,           # 要求形成更高的低点
    
    # 放量阳线确认
    'require_volume_confirm': False,      # 【关闭】放量阳线确认（过于严格）
    'volume_surge_ratio': 1.3,
    'require_positive_close': False,
    
    # 【关闭】分批建仓 - 实测会降低胜率
    'enable_partial_entry': False,        # 关闭分批建仓
    'first_entry_ratio': 1.0,             # 一次性建仓100%
    'confirm_entry_ratio': 0.0,
    'confirm_days': 5,
}

# 疯狂期卖出确认参数
FRENZY_CONFIRMATION = {
    'rsi_threshold': 75,        # RSI阈值
    'volume_surge_ratio': 1.5,  # 成交量放大比例
    'price_position': 0.85,     # 价格位置阈值
}

# 特殊资产超买阈值
SPECIAL_ASSET_OVERBOUGHT = {
    'rsi_extreme': 85,          # 极度超买RSI
    'rsi_high': 75,             # 高位RSI
    'max_score_when_overbought': 1,  # 超买时最大得分
}
