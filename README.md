# ETF投资策略系统

ETF配置策略系统。

## 核心策略

| 策略 | 核心逻辑 | 模块 |
|------|----------|------|
| 强弱分析法 | 该涨不涨看跌，该跌不跌看涨 | `analyzers/strength.py` |
| 情绪周期分析 | 绝望中产生→犹豫中发展→疯狂中消亡 | `analyzers/emotion.py` |
| 资金面分析 | 恶炒消耗资金，大盘拉抬性强 | `analyzers/capital.py` |
| 对冲战法 | 以变应变，留有余地 | `analyzers/hedge.py` |

## 项目结构

```
etf_deploy/
├── main.py              # 入口文件
├── config.py            # ETF配置常量
├── data_fetcher.py      # 数据获取模块
├── strategy.py          # 综合策略系统
├── analyzers/           # 分析器模块
│   ├── strength.py      # 强弱分析
│   ├── emotion.py       # 情绪周期
│   ├── capital.py       # 资金面分析
│   └── hedge.py         # 对冲策略
└── tests/               # 测试用例
```

## 安装

```bash
pip install akshare pandas numpy pytest
```

## 使用

```bash
python main.py
```

或在代码中调用：

```python
from strategy import IntegratedETFStrategy

strategy = IntegratedETFStrategy()
results = strategy.run_full_analysis()
```

## 运行测试

```bash
python -m pytest tests/ -v
```

## ETF池

覆盖宽基指数和主要行业：

- **宽基**: 沪深300、中证500、上证50、创业板、中证1000
- **行业**: 白酒、光伏、半导体、医药、证券、银行、红利、纳指

## 核心理念

1. **该涨不涨看跌，该跌不跌看涨** - 价格与预期背离时反向操作
2. **行情在绝望中产生，犹豫中发展，疯狂中消亡** - 逆向情绪周期
3. **恶炒消耗资金** - 小盘股消耗资金约是大盘股的5倍
4. **留有余地** - 仓位不可用足，保持现金比例
5. **策略比预测更重要** - 以变应变，灵活对冲

## 免责声明

本系统仅供学习研究，不构成投资建议。投资有风险，入市需谨慎。
参考文档
https://zhuanlan.zhihu.com/p/698623272