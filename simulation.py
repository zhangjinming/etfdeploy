"""
模拟分析模块

用于模拟历史时间段的ETF策略分析
"""

from typing import List

from strategy import IntegratedETFStrategy
from data_fetcher import get_tuesdays_in_range
from report_generator import MarkdownReportGenerator
from verification import (
    collect_predictions,
    verify_predictions_for_date,
    print_verification_summary
)


# 默认验证周期：1个月、2个月、3个月
DEFAULT_VERIFY_PERIODS = [
    ('1个月', 30),
    ('2个月', 60),
    ('3个月', 90),
]


def simulate_and_verify(start_date: str, end_date: str) -> List[dict]:
    """
    模拟时间段内每周二的分析，并与实际数据对比验证
    
    Args:
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
    
    Returns:
        所有分析结果列表
    """
    tuesdays = get_tuesdays_in_range(start_date, end_date)
    
    if not tuesdays:
        print(f"在 {start_date} 到 {end_date} 期间没有周二")
        return []
    
    print(f"\n{'#' * 80}")
    print(f"# 模拟分析与验证: {start_date} 至 {end_date}")
    print(f"# 共 {len(tuesdays)} 个周二: {', '.join(tuesdays)}")
    print(f"{'#' * 80}\n")
    
    all_results = []
    strategy = IntegratedETFStrategy()
    fetcher = strategy.data_fetcher
    
    for i, tuesday in enumerate(tuesdays, 1):
        print(f"\n{'*' * 80}")
        print(f"* 第 {i}/{len(tuesdays)} 周 - {tuesday} (周二)")
        print(f"{'*' * 80}\n")
        
        strategy.set_simulate_date(tuesday)
        results = strategy.run_full_analysis()
        results['simulate_date'] = tuesday
        results['verification'] = {}
        
        # 收集预测信息
        predictions, verified_symbols = collect_predictions(results)
        results['verified_symbols'] = verified_symbols
        
        # 验证预测
        verification_summary = verify_predictions_for_date(
            fetcher, predictions, tuesday, DEFAULT_VERIFY_PERIODS
        )
        results['verification'] = verification_summary
        all_results.append(results)
        
        print("\n" + "-" * 80)
    
    # 打印汇总报告
    print_verification_summary(all_results)
    
    # 生成Markdown验证报告
    report_gen = MarkdownReportGenerator()
    report_path = report_gen.generate_verification_report(all_results, start_date, end_date)
    
    print("\n" + "=" * 80)
    print("验证完成！")
    print(f"报告已保存至: {report_path}")
    print("=" * 80)
    
    return all_results


def simulate_period(start_date: str, end_date: str) -> List[dict]:
    """
    模拟时间段内每周二的分析（不含验证）
    
    Args:
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
    
    Returns:
        所有分析结果列表
    """
    tuesdays = get_tuesdays_in_range(start_date, end_date)
    
    if not tuesdays:
        print(f"在 {start_date} 到 {end_date} 期间没有周二")
        return []
    
    print(f"\n{'#' * 60}")
    print(f"# 模拟分析: {start_date} 至 {end_date}")
    print(f"# 共 {len(tuesdays)} 个周二: {', '.join(tuesdays)}")
    print(f"{'#' * 60}\n")
    
    all_results = []
    strategy = IntegratedETFStrategy()
    
    for i, tuesday in enumerate(tuesdays, 1):
        print(f"\n{'*' * 60}")
        print(f"* 第 {i}/{len(tuesdays)} 周 - {tuesday} (周二)")
        print(f"{'*' * 60}\n")
        
        strategy.set_simulate_date(tuesday)
        results = strategy.run_full_analysis()
        results['simulate_date'] = tuesday
        all_results.append(results)
        
        print("\n" + "-" * 60)
    
    # 汇总报告
    print(f"\n{'=' * 60}")
    print("模拟分析汇总")
    print("=" * 60)
    
    for result in all_results:
        date = result['simulate_date']
        portfolio = result.get('portfolio_suggestion', {})
        cash_ratio = portfolio.get('cash_ratio', 0) * 100
        net_exposure = portfolio.get('net_exposure', 0) * 100
        
        long_positions = portfolio.get('long_positions', [])
        long_names = [p['name'] for p in long_positions]
        
        print(f"\n{date}:")
        print(f"  现金比例: {cash_ratio:.0f}% | 多头敞口: {net_exposure:.0f}%")
        if long_names:
            print(f"  推荐多头: {', '.join(long_names)}")
        
        # 显示回避建议
        hedge_positions = portfolio.get('hedge_positions', [])
        if hedge_positions:
            hedge_names = [p['name'] for p in hedge_positions]
            print(f"  建议回避: {', '.join(hedge_names)}")
    
    # 为每个结果生成单独的Markdown报告
    report_gen = MarkdownReportGenerator()
    for result in all_results:
        date = result['simulate_date']
        report_gen.generate_single_report(result, f"etf_analysis_{date}")
    
    print("\n" + "=" * 60)
    print("模拟完成！")
    print(f"报告已保存至 reports/ 目录")
    print("=" * 60)
    
    return all_results
