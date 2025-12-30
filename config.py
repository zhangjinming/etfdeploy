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
    'stop_loss': -5.0,          # 止损线：-5%
    'take_profit': 10.0,        # 止盈线：+10%
    'time_stop_weeks': 8,       # 时间止损：8周
    'time_stop_min_profit': 2.0 # 时间止损最低收益要求
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

# P0优化：绝望期买入确认参数（加严条件，避免过早抄底）
DESPAIR_CONFIRMATION = {
    'rsi_threshold': 25,              # RSI阈值（从30降到25，更保守）
    'volume_shrink_ratio': 0.6,       # 成交量萎缩比例（相对20周均量）
    'require_support': True,          # 是否需要支撑确认
    'min_down_weeks': 3,              # 最少连续下跌周数
    'consecutive_weeks_confirm': 4,   # P0：从2增加到4周确认（关键优化）
    'require_stabilization': True,    # 是否需要企稳信号（如下影线、RSI回升）
    'require_decline_slowdown': True, # P0新增：要求跌幅收窄
    'decline_slowdown_ratio': 0.5,    # P0新增：最近一周跌幅 < 前一周跌幅的50%
    'benchmark_max_drawdown': -10,    # P0新增：基准最大回撤限制（%）
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
