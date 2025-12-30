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
    '510170': '大宗商品ETF',
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

# 特殊资产类别（需要趋势跟踪而非逆向策略）
SPECIAL_ASSETS = {
    '159934': {'type': 'gold', 'name': '黄金ETF', 'strategy': 'trend_follow'},      # 避险资产
    '159941': {'type': 'us_stock', 'name': '纳指ETF', 'strategy': 'trend_follow'},  # 美股联动
    '164824': {'type': 'foreign', 'name': '印度ETF', 'strategy': 'trend_follow'},   # 海外市场
    '159985': {'type': 'commodity', 'name': '豆粕ETF', 'strategy': 'trend_follow'}, # 商品
    '160723': {'type': 'commodity', 'name': '原油ETF', 'strategy': 'trend_follow'}, # 商品
    '510170': {'type': 'commodity', 'name': '大宗商品ETF', 'strategy': 'trend_follow'},
}

# 止损止盈参数
RISK_PARAMS = {
    'stop_loss': -5.0,          # 止损线：-5%
    'take_profit': 10.0,        # 止盈线：+10%
    'time_stop_weeks': 8,       # 时间止损：8周
    'time_stop_min_profit': 2.0 # 时间止损最低收益要求
}
