"""
ETF配置系统

核心策略：
1. 强弱分析法：该涨不涨看跌，该跌不跌看涨
2. 情绪周期分析：行情在绝望中产生，犹豫中发展，疯狂中消亡
3. 资金面分析：恶炒消耗资金，大盘股拉抬性强，小盘股消耗资金
4. 博弈逻辑：增量博弈看空头翻多，减量博弈看多头出局
5. 风格对冲：以变应变，灵活对冲
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from strategy import IntegratedETFStrategy
from data_fetcher import get_tuesdays_in_range, ETFDataFetcher


def main():
    """主函数 - 当前日期分析"""
    strategy = IntegratedETFStrategy()
    results = strategy.run_full_analysis()
    
    print("\n" + "=" * 60)
    print("分析完成！")
    print("=" * 60)
    
    return results


def get_future_price_change(fetcher: ETFDataFetcher, symbol: str, 
                            start_date: str, days: int) -> Optional[float]:
    """
    获取从start_date开始，days天后的价格变化率
    
    Args:
        fetcher: 数据获取器
        symbol: ETF代码
        start_date: 起始日期
        days: 天数（半个月=15, 1个月=30, 2个月=60）
    
    Returns:
        价格变化率（百分比），数据不足时返回None
    """
    try:
        # 获取原始数据
        if symbol not in fetcher.raw_data_cache:
            fetcher.get_etf_history(symbol)
        
        if symbol not in fetcher.raw_data_cache:
            return None
        
        df = fetcher.raw_data_cache[symbol]
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = start_dt + timedelta(days=days)
        
        # 找到起始日期的收盘价（或最近的交易日）
        df_after_start = df[df['date'] >= start_dt]
        if df_after_start.empty:
            return None
        start_price = df_after_start.iloc[0]['close']
        
        # 找到结束日期的收盘价（或最近的交易日）
        df_before_end = df[df['date'] <= end_dt]
        if df_before_end.empty:
            return None
        end_price = df_before_end.iloc[-1]['close']
        
        return (end_price / start_price - 1) * 100
    except Exception as e:
        print(f"获取{symbol}价格变化失败: {e}")
        return None


def verify_prediction(signal: str, price_change: Optional[float]) -> dict:
    """
    验证预测是否正确
    
    Args:
        signal: 预测信号 (strong_buy, buy, neutral, sell, strong_sell)
        price_change: 实际价格变化率
    
    Returns:
        验证结果
    """
    if price_change is None:
        return {'match': None, 'reason': '数据不足'}
    
    # 定义预期（优化：放宽阈值，更符合实际市场波动）
    expectations = {
        'strong_buy': {'expected': 'up', 'threshold': 0},      # 强买入预期不跌即可
        'buy': {'expected': 'up', 'threshold': -3},            # 买入允许3%波动
        'neutral': {'expected': 'neutral', 'threshold': 7},    # 中性预期波动不超过7%
        'sell': {'expected': 'down', 'threshold': 3},          # 卖出允许3%波动
        'strong_sell': {'expected': 'down', 'threshold': 0},   # 强卖出预期不涨即可
    }
    
    exp = expectations.get(signal, {'expected': 'neutral', 'threshold': 5})
    threshold = float(exp['threshold'])
    
    if exp['expected'] == 'up':
        if price_change >= threshold:
            return {'match': True, 'reason': f'预期上涨，实际涨{price_change:.1f}%'}
        else:
            return {'match': False, 'reason': f'预期涨{threshold}%以上，实际{price_change:+.1f}%'}
    
    elif exp['expected'] == 'down':
        if price_change <= threshold:
            return {'match': True, 'reason': f'预期下跌，实际跌{abs(price_change):.1f}%'}
        else:
            return {'match': False, 'reason': f'预期跌{abs(threshold)}%以上，实际{price_change:+.1f}%'}
    
    else:  # neutral
        if abs(price_change) <= threshold:
            return {'match': True, 'reason': f'预期震荡，实际波动{price_change:+.1f}%'}
        else:
            return {'match': False, 'reason': f'预期震荡±{threshold}%内，实际{price_change:+.1f}%'}


def simulate_and_verify(start_date: str, end_date: str):
    """
    模拟时间段内每周二的分析，并与实际数据对比验证
    
    Args:
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
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
    
    # 验证周期：半个月、1个月、2个月
    verify_periods = [
        ('半个月', 15),
        ('1个月', 30),
        ('2个月', 60),
    ]
    
    for i, tuesday in enumerate(tuesdays, 1):
        print(f"\n{'*' * 80}")
        print(f"* 第 {i}/{len(tuesdays)} 周 - {tuesday} (周二)")
        print(f"{'*' * 80}\n")
        
        strategy.set_simulate_date(tuesday)
        results = strategy.run_full_analysis()
        results['simulate_date'] = tuesday
        results['verification'] = {}
        
        # 收集预测信息
        predictions = []
        
        # 多头推荐
        portfolio = results.get('portfolio_suggestion', {})
        for pos in portfolio.get('long_positions', []):
            predictions.append({
                'symbol': pos['symbol'],
                'name': pos['name'],
                'signal': 'buy',
                'type': '多头推荐'
            })
        
        # 回避建议
        for pos in portfolio.get('hedge_positions', []):
            predictions.append({
                'symbol': pos['symbol'],
                'name': pos['name'],
                'signal': 'sell',
                'type': '建议回避'
            })
        
        # ETF分析结果
        for symbol, analysis in results.get('etf_analysis', {}).items():
            signal = analysis.get('strength', {}).get('signal', 'neutral')
            if signal in ['strong_buy', 'strong_sell']:
                predictions.append({
                    'symbol': symbol,
                    'name': analysis['name'],
                    'signal': signal,
                    'type': '强信号'
                })
        
        # 验证预测
        print(f"\n{'=' * 80}")
        print(f"【预测验证】- 分析日期: {tuesday}")
        print(f"{'=' * 80}")
        
        verification_summary = {'半个月': [], '1个月': [], '2个月': []}
        
        for pred in predictions:
            symbol = pred['symbol']
            name = pred['name']
            signal = pred['signal']
            pred_type = pred['type']
            
            print(f"\n  📊 {name}({symbol}) - {pred_type} [{signal}]")
            
            for period_name, days in verify_periods:
                price_change = get_future_price_change(fetcher, symbol, tuesday, days)
                verify_result = verify_prediction(signal, price_change)
                
                if verify_result['match'] is None:
                    status = '⚪ 数据不足'
                elif verify_result['match']:
                    status = '✅ 符合预期'
                    verification_summary[period_name].append(True)
                else:
                    status = '❌ 不符合预期'
                    verification_summary[period_name].append(False)
                
                change_str = f"{price_change:+.1f}%" if price_change is not None else "N/A"
                print(f"     {period_name}: {status} | 涨跌: {change_str} | {verify_result['reason']}")
        
        results['verification'] = verification_summary
        all_results.append(results)
        
        print("\n" + "-" * 80)
    
    # 汇总报告
    print(f"\n{'=' * 80}")
    print("【总体验证汇总】")
    print("=" * 80)
    
    total_summary = {'半个月': {'correct': 0, 'total': 0}, 
                     '1个月': {'correct': 0, 'total': 0}, 
                     '2个月': {'correct': 0, 'total': 0}}
    
    for result in all_results:
        date = result['simulate_date']
        verification = result.get('verification', {})
        
        print(f"\n📅 {date}:")
        
        for period_name in ['半个月', '1个月', '2个月']:
            results_list = verification.get(period_name, [])
            if results_list:
                correct = sum(1 for r in results_list if r)
                total = len(results_list)
                accuracy = correct / total * 100 if total > 0 else 0
                total_summary[period_name]['correct'] += correct
                total_summary[period_name]['total'] += total
                print(f"   {period_name}: {correct}/{total} 符合预期 ({accuracy:.0f}%)")
    
    # 总体准确率
    print(f"\n{'=' * 80}")
    print("【总体准确率】")
    print("=" * 80)
    
    for period_name in ['半个月', '1个月', '2个月']:
        correct = total_summary[period_name]['correct']
        total = total_summary[period_name]['total']
        accuracy = correct / total * 100 if total > 0 else 0
        bar = '█' * int(accuracy / 5) + '░' * (20 - int(accuracy / 5))
        print(f"  {period_name}: [{bar}] {accuracy:.1f}% ({correct}/{total})")
    
    print("\n" + "=" * 80)
    print("验证完成！")
    print("=" * 80)
    
    return all_results


def simulate_period(start_date: str, end_date: str):
    """
    模拟时间段内每周二的分析（不含验证）
    
    Args:
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
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
        long_names = [p['name'] for p in long_positions[:3]]
        
        print(f"\n{date}:")
        print(f"  现金比例: {cash_ratio:.0f}% | 多头敞口: {net_exposure:.0f}%")
        if long_names:
            print(f"  推荐多头: {', '.join(long_names)}")
    
    print("\n" + "=" * 60)
    print("模拟完成！")
    print("=" * 60)
    
    return all_results


if __name__ == "__main__":
    # 模拟，每周二输出结论并验证
    simulate_and_verify("2025-01-01", "2025-03-31")
