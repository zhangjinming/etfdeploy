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


if __name__ == "__main__":
    # 默认运行当前日期分析
    # main()
    
    # 模拟并验证历史数据
    simulate_and_verify("2024-03-01", "2024-03-16")
    
    # 仅模拟（不验证）
    # simulate_period("2024-03-01", "2024-03-16")
