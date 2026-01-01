"""
ETF配置系统

核心策略：
1. 强弱分析法：该涨不涨看跌，该跌不跌看涨
2. 情绪周期分析：行情在绝望中产生，犹豫中发展，疯狂中消亡
3. 资金面分析：恶炒消耗资金，大盘股拉抬性强，小盘股消耗资金
4. 博弈逻辑：增量博弈看空头翻多，减量博弈看多头出局
5. 风格对冲：以变应变，灵活对冲
"""

from strategy import IntegratedETFStrategy
from report_generator import MarkdownReportGenerator
from simulation import simulate_and_verify, simulate_period
from backtest import BacktestEngine, run_backtest
from backtest_report import generate_backtest_report


def main():
    """主函数 - 当前日期分析"""
    strategy = IntegratedETFStrategy()
    results = strategy.run_full_analysis()
    
    # 生成Markdown报告
    report_gen = MarkdownReportGenerator()
    report_path = report_gen.generate_single_report(results)
    
    print("\n" + "=" * 60)
    print("分析完成！")
    print(f"报告已保存至: {report_path}")
    print("=" * 60)
    
    return results


def run_full_backtest(start_date: str, end_date: str, initial_capital: float = 10000.0):
    """
    运行完整回测并生成报告
    
    Args:
        start_date: 开始日期 'YYYY-MM-DD'
        end_date: 结束日期 'YYYY-MM-DD'
        initial_capital: 初始资金
    """
    print("\n" + "=" * 60)
    print("🚀 开始回测...")
    print("=" * 60)
    
    # 运行回测
    result = run_backtest(start_date, end_date, initial_capital)
    
    if not result:
        print("回测失败！")
        return None
    
    # 生成报告
    report_path = generate_backtest_report(result)
    
    # 打印回测摘要
    print("\n" + "=" * 60)
    print("📊 回测完成！")
    print("=" * 60)
    print(f"  回测期间: {start_date} 至 {end_date}")
    print(f"  初始资金: ¥{result['initial_capital']:,.2f}")
    print(f"  最终资金: ¥{result['final_value']:,.2f}")
    print(f"  总收益率: {result['total_return']:+.2f}%")
    print(f"  年化收益率: {result['annual_return']:+.2f}%")
    print(f"  基准收益率: {result['benchmark_return']:+.2f}%")
    print(f"  超额收益: {result['excess_return']:+.2f}%")
    print(f"  最大回撤: {result['max_drawdown']:.2f}%")
    print(f"  胜率: {result['win_rate']:.1f}%")
    print(f"  总交易次数: {result['total_trades']}")
    print("=" * 60)
    print(f"📄 报告已保存至: {report_path}")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    # 默认运行当前日期分析
    # main()
    
    # 模拟并验证历史数据
    simulate_and_verify("2022-01-01", "2022-12-30")
    
    # 仅模拟（不验证）
    # simulate_period("2024-03-01", "2024-03-16")
    
    # 运行回测
    #run_full_backtest("2020-01-01", "2020-12-30", initial_capital=10000.0)
