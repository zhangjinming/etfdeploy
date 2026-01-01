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

# 【优化v6】趋势性资产配置 - 降低入场门槛，加快响应
TREND_FOLLOW_ASSETS = {
    '160723': {  # 原油ETF
        'name': '嘉实原油ETF',
        'trend_weight': 0.90,           # 【优化v6】趋势权重从0.95降到0.90
        'emotion_weight': 0.10,         # 【优化v6】情绪权重从0.05提高到0.10
        'avoid_threshold': 8.0,         # 【优化v6】回避验证阈值从10%降到8%
        'no_despair_short': True,       # 绝望期不做空
        'min_trend_weeks': 4,           # 【优化v6】趋势确认从8周减少到4周（加快入场）
        'priority_weight': 0.3,         # 【优化v6】优先配置权重从0.2提高到0.3
        'require_uptrend_to_buy': True, # 只在上涨趋势中买入
    },
    '159985': {  # 豆粕ETF
        'name': '豆粕ETF',
        'trend_weight': 0.85,           # 【优化v6】趋势权重从0.88降到0.85
        'emotion_weight': 0.15,         # 【优化v6】情绪权重从0.12提高到0.15
        'avoid_threshold': 6.0,         # 【优化v6】回避验证阈值从8%降到6%
        'no_despair_short': True,
        'min_trend_weeks': 3,           # 【优化v6】趋势确认从6周减少到3周（加快入场）
        'priority_weight': 0.4,         # 【优化v6】优先配置权重从0.3提高到0.4
        'require_uptrend_to_buy': True, # 只在上涨趋势中买入
    },
    '159934': {  # 黄金ETF - 【核心优化v6】黄金是最稳定的趋势资产
        'name': '黄金ETF',
        'trend_weight': 0.70,           # 【优化v6】趋势权重从0.80降到0.70（更平衡）
        'emotion_weight': 0.30,         # 【优化v6】情绪权重从0.20提高到0.30
        'avoid_threshold': 2.0,         # 【优化v6】回避验证阈值从3%降到2%
        'no_despair_short': True,       # 黄金绝望期不做空
        'min_trend_weeks': 1,           # 【优化v6】趋势确认从2周减少到1周（黄金更快入场）
        'priority_weight': 2.2,         # 【优化v6】优先配置权重从2.0提高到2.2
        'is_safe_haven': True,          # 避险资产标记
        'always_consider': True,        # 始终考虑配置
        'require_uptrend_to_buy': False, # 黄金可以在震荡中买入
    },
    '159941': {  # 纳指ETF - 【优化v6】降低入场门槛
        'name': '纳指ETF',
        'trend_weight': 0.70,           # 【优化v6】趋势权重从0.75降到0.70
        'emotion_weight': 0.30,         # 【优化v6】情绪权重从0.25提高到0.30
        'avoid_threshold': 8.0,         # 【优化v6】回避验证阈值从10%降到8%
        'no_despair_short': True,       # 纳指绝望期不做空
        'min_trend_weeks': 2,           # 【优化v6】趋势确认从5周减少到2周（大幅加快入场）
        'priority_weight': 2.0,         # 【优化v6】优先配置权重从1.8提高到2.0
        'is_global_trend': True,        # 全球趋势资产标记
        'always_consider': True,        # 始终考虑配置
        'require_uptrend_to_buy': False, # 【优化v6】允许在震荡中买入（原为True）
        'min_ma_slope': 0.1,            # 【优化v6】均线斜率从0.3%降到0.1%
    },
    '164824': {  # 印度ETF - 【优化v6】降低入场门槛
        'name': '印度ETF',
        'trend_weight': 0.70,           # 【优化v6】趋势权重从0.75降到0.70
        'emotion_weight': 0.30,         # 【优化v6】情绪权重从0.25提高到0.30
        'avoid_threshold': 6.0,         # 【优化v6】回避验证阈值从8%降到6%
        'no_despair_short': True,
        'min_trend_weeks': 3,           # 【优化v6】趋势确认从6周减少到3周（加快入场）
        'priority_weight': 1.2,         # 【优化v6】优先配置权重从1.0提高到1.2
        'is_global_trend': True,        # 全球趋势资产标记
        'require_uptrend_to_buy': False, # 【优化v6】允许在震荡中买入（原为True）
        'min_ma_slope': 0.2,            # 【优化v6】均线斜率从0.5%降到0.2%
    },
}

# 【新增v5】趋势资产优先配置参数 - 增强趋势资产权重
TREND_PRIORITY_CONFIG = {
    'enable': True,                    # 启用趋势资产优先配置
    'min_trend_score': 0.15,           # 【优化v5】最低趋势得分阈值从0.20降到0.15
    'max_trend_allocation': 0.50,      # 【优化v5】趋势资产最大配置比例从60%降到50%（平衡）
    'safe_haven_boost': 1.6,           # 【优化v5】避险资产（黄金）加成系数从1.8降到1.6
    'global_trend_boost': 1.5,         # 【优化v5】全球趋势资产加成从1.6降到1.5
    'bear_market_trend_boost': 2.0,    # 【优化v5】熊市环境下趋势资产加成从2.5降到2.0
    'bull_market_trend_boost': 1.2,    # 【新增v5】牛市环境下趋势资产加成
    'prefer_uptrend': True,            # 优先选择上涨趋势资产
    'uptrend_confirmed_boost': 1.8,    # 【优化v5】上涨趋势确认后的加成从2.0降到1.8
    'downtrend_penalty': 0.2,          # 【优化v5】下跌趋势的惩罚系数从0.1提高到0.2
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

# 波动率过滤参数（用于识别系统性风险）- 【优化v4】
VOLATILITY_FILTER = {
    'extreme_vol_threshold': 4.0,   # 【优化v4】周波动率>4.0%视为极端波动（从4.5%降低）
    'high_vol_threshold': 2.0,      # 【优化v4】周波动率>2.0%视为高波动（从2.5%降低）
    'vol_lookback_weeks': 4,        # 波动率计算回溯周数
    'stop_despair_buy_vol': 3.0,    # 【优化v4】波动率超过此值停止绝望期抄底（从3.5%降低）
    'max_consecutive_drops': 2,     # 【优化v4】连续下跌超过2周视为系统性风险（从3周减少）
    'benchmark_drawdown_limit': -6, # 【优化v4】基准回撤超过-6%停止抄底（从-8%收紧）
}

# 止损止盈参数 - 【优化v5】市场环境自适应止损
RISK_PARAMS = {
    'stop_loss': -10.0,         # 【优化v5】默认止损从-8%放宽到-10%，减少频繁止损
    'take_profit': 20.0,        # 【优化v5】止盈线从18%提高到20%
    'time_stop_weeks': 26,      # 时间止损（约6个月）
    'time_stop_min_profit': 5.0, # 时间止损最低收益5%
    
    # 动态移动止损参数（优化）
    'enable_trailing_stop': True,     # 启用移动止损
    'trailing_stop_trigger': 20.0,    # 【优化v5】盈利20%后启用移动止损（从18%提高）
    'trailing_stop_distance': 12.0,   # 移动止损距离12%
    'trailing_stop_min_profit': 10.0, # 【优化v5】止损后至少保留10%利润（从8%提高）
    
    # 动态止损分级（放宽回撤容忍度）- 【优化v5】
    'dynamic_trailing_stop': {
        'enable': True,
        'levels': [
            {'profit_min': 20.0, 'profit_max': 35.0, 'drawdown_tolerance': 12.0},  # 【优化v5】
            {'profit_min': 35.0, 'profit_max': 50.0, 'drawdown_tolerance': 15.0},  # 【优化v5】
            {'profit_min': 50.0, 'profit_max': 75.0, 'drawdown_tolerance': 18.0},  # 【优化v5】
            {'profit_min': 75.0, 'profit_max': 999.0, 'drawdown_tolerance': 22.0}, # 【优化v5】
        ],
    },
    
    # 买入缓冲期（增加缓冲）- 【优化v5】
    'buy_buffer_days': 10,            # 【优化v5】买入后10个交易日不止损（从7天增加）
    
    # 【优化v5】市场环境自适应止损
    'bear_market_stop_loss': -8.0,    # 【优化v5】熊市止损线收紧到-8%（保守）
    'bear_market_buffer_days': 12,    # 【优化v5】熊市买入缓冲期12天
    'bull_market_stop_loss': -12.0,   # 【优化v5】牛市止损线放宽到-12%（更宽容）
    'bull_market_buffer_days': 7,     # 【优化v5】牛市买入缓冲期7天（可更快反应）
    
    # 【关闭】分批止损 - 实测会降低胜率
    'partial_stop_loss': {
        'enable': False,
        'first_stop_pct': -5.0,
        'first_sell_ratio': 0.5,
        'second_stop_pct': -8.0,
        'second_sell_ratio': 1.0,
    },
}

# 【优化v6】牛市适应性参数 - 进一步增强牛市环境下的策略表现
BULL_MARKET_PARAMS = {
    'enable': True,                       # 启用牛市适应性策略
    'enable_momentum_follow': True,       # 牛市启用动量跟踪
    'momentum_threshold': 0.08,           # 【优化v6】动量阈值从12%降到8%（更容易触发）
    'reduce_despair_weight': 0.7,         # 【优化v6】绝望期权重从60%提高到70%（牛市回调也是机会）
    'increase_trend_weight': 1.5,         # 【优化v6】趋势权重从140%提高到150%
    'rsi_oversold_threshold': 45,         # 【优化v6】牛市RSI<45即可视为超卖（从40提高）
    'min_bounce_threshold': 3.0,          # 【优化v6】牛市反弹确认阈值从5%降到3%
    'confidence_boost': 1.4,              # 【优化v6】牛市信号置信度加成从1.3提高到1.4
    'max_positions_boost': 1,             # 【新增v6】牛市可额外增加1个持仓
    'cash_ratio_reduction': 0.10,         # 【新增v6】牛市现金比例额外降低10%
}

# 【新增v4】止损冷却机制参数 - 避免同一标的反复止损
STOP_LOSS_COOLDOWN = {
    'enable': True,                   # 启用冷却机制
    'same_etf_cooldown_weeks': 12,    # 【优化v4】同一ETF止损后12周内不再买入（从8周增加）
    'sector_cooldown_weeks': 6,       # 【优化v4】同板块止损后6周内限制买入（从4周增加）
    'max_sector_stop_loss': 2,        # 同板块连续止损次数超过此值触发板块冷却
    'cooldown_decay': True,           # 冷却期递减（首次12周，第二次18周...）
    'decay_factor': 1.5,              # 递减因子
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

# 信号阈值参数（优化v5后降低阈值，牛市适应）
SIGNAL_THRESHOLDS = {
    'strong_buy': 5,            # 【优化v5】强买入阈值从6降到5（牛市适应）
    'buy': 4,                   # 【优化v5】买入阈值从5降到4
    'sell': -5,                 # 卖出阈值-5
    'strong_sell': -6,          # 强卖出阈值-6
}

# 信号有效期（周数）
SIGNAL_VALIDITY = {
    'strong_buy': 4,            # 强买入信号4周有效
    'buy': 2,                   # 买入信号2周有效
    'strong_sell': 4,           # 强卖出信号4周有效
    'sell': 2,                  # 卖出信号2周有效
    'neutral': 1,               # 中性信号1周有效
}

# 市场环境参数 - 【优化v6】加快响应速度
MARKET_REGIME_PARAMS = {
    'ma_period': 10,            # 【优化v6】判断趋势的均线周期从20周缩短到10周（加快响应）
    'slope_threshold': 0.3,     # 【优化v6】均线斜率阈值从0.5%降到0.3%（更敏感）
    'bull_threshold': 0.015,    # 【优化v6】牛市判定从0.02降到0.015（更容易判定为牛市）
    'bear_threshold': -0.025,   # 【优化v6】熊市判定从-0.02调整到-0.025（更难判定为熊市）
}

# 【优化v6】持仓到期机制 - 改为趋势跟踪止盈，取消固定周期
TIME_STOP_PARAMS = {
    'enable': False,                  # 【优化v6】关闭固定周期卖出，改用趋势跟踪止盈
    'max_holding_weeks': 52,          # 【优化v6】最大持仓周数延长到52周（1年），实际由趋势决定
    'min_profit_to_extend': 10.0,     # 【优化v6】盈利>10%可延长持有（降低门槛）
    'extend_weeks': 12,               # 【优化v6】延长持有周数从8周增加到12周
    'trend_override': True,           # 趋势向上时不强制卖出
    'momentum_override': True,        # 动量强劲时不强制卖出
    'momentum_threshold': 0.08,       # 【优化v6】动量阈值从10%降到8%（更容易延期）
    'force_sell_loss_threshold': -8.0, # 【优化v6】亏损阈值从-5%放宽到-8%
}

# 【新增v6】趋势跟踪止盈参数 - 替代固定周期卖出
TREND_STOP_PARAMS = {
    'enable': True,                   # 启用趋势跟踪止盈
    'trend_ma_period': 10,            # 趋势判断均线周期（周线）
    'trend_confirm_weeks': 2,         # 趋势确认周数
    'sell_on_trend_break': True,      # 趋势破位时卖出
    'trend_break_threshold': -0.02,   # 趋势破位阈值（价格低于均线2%）
    'require_volume_confirm': False,  # 不强制要求成交量确认
    'min_holding_weeks': 4,           # 最少持仓4周才能趋势止盈
    'profit_lock_threshold': 15.0,    # 盈利>15%时启用趋势保护
    'profit_lock_ma_period': 5,       # 盈利保护使用5周均线
}

# 趋势过滤器参数 - 用于熊市减少抄底频率 - 【优化v5】牛市适应
# 趋势过滤器参数 - 用于熊市减少抄底频率 - 【优化v5】牛市适应
TREND_FILTER_PARAMS = {
    # 多周期均线配置
    'short_ma': 5,              # 短期均线（5周）
    'mid_ma': 10,               # 中期均线（10周）
    'long_ma': 20,              # 长期均线（20周）
    
    # 趋势判定条件
    'strong_downtrend_conditions': {
        'ma_alignment': True,           # 均线空头排列
        'price_below_all_ma': True,     # 价格在所有均线下方
        'slope_threshold': -0.6,        # 【优化v5】长期均线斜率阈值从-0.8放宽到-0.6
    },
    
    # 熊市抄底限制 - 【优化v5】适度放宽
    'bear_market_restrictions': {
        'enable': True,                 # 启用熊市抄底限制
        'min_rsi': 15,                  # 【优化v5】熊市抄底最低RSI从12提高到15
        'require_ma_support': True,     # 要求均线支撑信号
        'require_volume_dry': True,     # 要求成交量枯竭
        'volume_dry_ratio': 0.35,       # 【优化v5】成交量萎缩从30%提高到35%
        'max_weekly_signals': 2,        # 【优化v5】每周最多2个抄底信号（从1增加）
        'cooldown_weeks': 4,            # 【优化v5】冷却期从8周减少到4周
        'require_ma_cross': True,       # 要求短期均线上穿中期均线
    },
    
    # 趋势反转确认 - 【优化v5】适度放宽
    'reversal_confirmation': {
        'require_higher_low': True,     # 要求形成更高的低点
        'require_ma_cross': True,       # 要求短期均线上穿中期均线
        'min_bounce_pct': 8.0,          # 【优化v5】最小反弹幅度从10%降到8%
        'confirm_weeks': 3,             # 【优化v5】反转确认从5周减少到3周
    },
    
    # 趋势强度分级
    'trend_strength_levels': {
        'strong_trend_threshold': 0.7,
        'weak_trend_threshold': 0.3,
        'trend_follow_min_strength': 0.5,
    },
    
    # 大盘环境过滤 - 【优化v6】牛市提高仓位上限
    'market_filter': {
        'enable': True,                       # 启用大盘过滤
        'bear_market_max_positions': 4,       # 熊市最多持仓4只
        'bear_market_cash_ratio': 0.35,       # 【优化v6】熊市保持35%现金（从40%降低）
        'bull_market_max_positions': 6,       # 【优化v6】牛市最多持仓6只
        'bull_market_cash_ratio': 0.15,       # 【优化v6】牛市保持15%现金（从20%降低，提高仓位）
        'require_benchmark_above_ma': False,
        'benchmark_ma_period': 10,            # 【优化v6】基准均线周期从20周缩短到10周
    },
}

# 【优化v6】绝望期买入确认参数 - 放宽条件，牛市适应性增强
DESPAIR_CONFIRMATION = {
    'rsi_threshold': 32,              # 【优化v6】RSI阈值从25提高到32（更容易触发）
    'volume_shrink_ratio': 0.50,      # 【优化v6】成交量萎缩比例从45%提高到50%（放宽）
    'require_support': True,          # 是否需要支撑确认
    'min_down_weeks': 3,              # 【优化v6】最少连续下跌周数从4周减少到3周
    'consecutive_weeks_confirm': 3,   # 【优化v6】确认周数从4周减少到3周（更快确认）
    'require_stabilization': True,    # 是否需要企稳信号
    'require_decline_slowdown': True, # 要求跌幅收窄
    'decline_slowdown_ratio': 0.50,   # 【优化v6】跌幅收窄比例从0.40提高到0.50（放宽）
    'benchmark_max_drawdown': -10,    # 【优化v6】基准最大回撤从-8%放宽到-10%
    
    # 二次确认机制 - 【优化v6】放宽
    'require_price_stabilization': True,  # 要求价格企稳
    'stabilization_weeks': 2,             # 【优化v6】价格企稳确认从3周减少到2周
    'require_rsi_divergence': False,      # 【优化v6】不强制要求RSI底背离（原为True）
    
    # 反弹确认 - 【优化v6】进一步放宽
    'require_bounce_confirm': True,       # 要求从低点反弹确认
    'min_bounce_from_low': 4.0,           # 【优化v6】从最低点反弹从5%降到4%
    'require_higher_low': False,          # 【优化v6】不强制要求更高低点（原为True）
    'higher_low_margin': 0.5,             # 【优化v6】更高低点需高于前低0.5%（从1%降低）
    
    # 【优化v6】周线阳线确认进一步放宽
    'require_weekly_positive': True,      # 要求周线收阳
    'min_weekly_positive_count': 1,       # 【优化v6】近4周至少1周收阳（从2周减少）
    
    # 【优化v6】成交量放大确认放宽
    'require_volume_confirm': False,      # 【优化v6】不强制要求放量确认（原为True）
    'volume_surge_ratio': 1.10,           # 【优化v6】反弹时成交量需放大10%（从15%降低）
    'require_positive_close': False,      # 【优化v6】不强制要求收阳（原为True）
    
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
