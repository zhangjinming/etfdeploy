"""
预测验证模块

用于验证ETF策略预测的准确性
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

from data_fetcher import ETFDataFetcher


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


def verify_prediction(signal: str, price_change: Optional[float], period_name: str = '') -> dict:
    """
    验证预测是否正确（严格标准）
    
    Args:
        signal: 预测信号 (strong_buy, buy, neutral, sell, strong_sell)
        price_change: 实际价格变化率
        period_name: 验证周期名称（半个月、1个月、2个月、3个月）
    
    Returns:
        验证结果
    
    验证标准：
    - 买入信号（buy/strong_buy）：必须收益 >= 3% 才算正确
    - 卖出信号（sell/strong_sell）：必须下跌 >= 3% 才算正确
    - 回避信号（sell用于回避）：不上涨超过3%即可
    """
    if price_change is None:
        return {'match': None, 'reason': '数据不足'}
    
    # 严格验证标准：买入必须有3%以上收益
    min_profit = 3.0  # 最低收益要求
    
    if signal in ['strong_buy', 'buy']:
        # 买入信号：必须收益 >= 3%
        if price_change >= min_profit:
            return {'match': True, 'reason': f'收益{price_change:.1f}% ≥ {min_profit}%'}
        else:
            return {'match': False, 'reason': f'收益{price_change:+.1f}% < {min_profit}%'}
    
    elif signal in ['strong_sell', 'sell']:
        # 卖出/回避信号：下跌或涨幅不超过3%即算正确（成功回避）
        if price_change <= min_profit:
            if price_change < 0:
                return {'match': True, 'reason': f'成功回避，下跌{abs(price_change):.1f}%'}
            else:
                return {'match': True, 'reason': f'成功回避，仅涨{price_change:.1f}%'}
        else:
            return {'match': False, 'reason': f'回避失败，上涨{price_change:.1f}%'}
    
    else:  # neutral
        # 中性信号不参与验证
        return {'match': None, 'reason': '中性信号不验证'}


def collect_predictions(results: dict) -> tuple:
    """
    从分析结果中收集预测信息
    
    Args:
        results: 策略分析结果
    
    Returns:
        (predictions, verified_symbols) 预测列表和被验证的ETF代码集合
    """
    predictions = []
    verified_symbols = set()
    
    # 多头推荐
    portfolio = results.get('portfolio_suggestion', {})
    for pos in portfolio.get('long_positions', []):
        predictions.append({
            'symbol': pos['symbol'],
            'name': pos['name'],
            'signal': 'buy',
            'type': '多头推荐'
        })
        verified_symbols.add(pos['symbol'])
    
    # 回避建议
    for pos in portfolio.get('hedge_positions', []):
        predictions.append({
            'symbol': pos['symbol'],
            'name': pos['name'],
            'signal': 'sell',
            'type': '建议回避'
        })
        verified_symbols.add(pos['symbol'])
    
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
            verified_symbols.add(symbol)
    
    return predictions, verified_symbols


def verify_predictions_for_date(fetcher: ETFDataFetcher, predictions: list, 
                                 tuesday: str, verify_periods: list) -> dict:
    """
    验证指定日期的所有预测
    
    优化：短周期验证失败则跳过长周期验证
    - 1个月验证失败 → 跳过2个月、3个月验证
    - 2个月验证失败 → 跳过3个月验证
    
    Args:
        fetcher: 数据获取器
        predictions: 预测列表
        tuesday: 分析日期
        verify_periods: 验证周期列表 [(名称, 天数), ...]
    
    Returns:
        验证摘要字典
    """
    verification_summary = {period[0]: [] for period in verify_periods}
    
    print(f"\n{'=' * 80}")
    print(f"【预测验证】- 分析日期: {tuesday}")
    print(f"{'=' * 80}")
    
    for pred in predictions:
        symbol = pred['symbol']
        name = pred['name']
        signal = pred['signal']
        pred_type = pred['type']
        
        print(f"\n  📊 {name}({symbol}) - {pred_type} [{signal}]")
        
        # 记录该ETF是否已验证失败，失败后跳过后续周期
        failed_at_period = None
        
        for period_name, days in verify_periods:
            # 优化：如果前一个周期验证失败，跳过后续验证
            if failed_at_period is not None:
                print(f"     {period_name}: ⏭️ 跳过验证 | {failed_at_period}已失败，需调整策略")
                # 记录跳过信息
                skip_detail = {
                    'symbol': symbol,
                    'name': name,
                    'signal': signal,
                    'type': pred_type,
                    'price_change': None,
                    'match': None,
                    'reason': f'{failed_at_period}验证失败，跳过后续验证',
                    'skipped': True,
                    'skipped_reason': failed_at_period
                }
                verification_summary[period_name].append(skip_detail)
                continue
            
            price_change = get_future_price_change(fetcher, symbol, tuesday, days)
            verify_result = verify_prediction(signal, price_change)
            
            # 记录详细验证信息
            verify_detail = {
                'symbol': symbol,
                'name': name,
                'signal': signal,
                'type': pred_type,
                'price_change': price_change,
                'match': verify_result['match'],
                'reason': verify_result['reason'],
                'skipped': False
            }
            
            if verify_result['match'] is None:
                status = '⚪ 数据不足'
            elif verify_result['match']:
                status = '✅ 符合预期'
                verification_summary[period_name].append(verify_detail)
            else:
                status = '❌ 不符合预期'
                verification_summary[period_name].append(verify_detail)
                # 标记验证失败，后续周期将跳过
                failed_at_period = period_name
            
            change_str = f"{price_change:+.1f}%" if price_change is not None else "N/A"
            print(f"     {period_name}: {status} | 涨跌: {change_str} | {verify_result['reason']}")
            
            # 如果验证失败，提示需要策略调整
            if failed_at_period:
                print(f"     ⚠️ 策略失效提示: {name}在{period_name}验证失败，后续周期不再验证，建议调整策略")
    
    return verification_summary


def print_verification_summary(all_results: list):
    """
    打印验证汇总报告
    
    优化：统计跳过的验证，区分有效验证和跳过验证
    
    Args:
        all_results: 所有分析结果列表
    """
    print(f"\n{'=' * 80}")
    print("【总体验证汇总】")
    print("=" * 80)
    
    total_summary = {
        '1个月': {'correct': 0, 'total': 0, 'skipped': 0}, 
        '2个月': {'correct': 0, 'total': 0, 'skipped': 0}, 
        '3个月': {'correct': 0, 'total': 0, 'skipped': 0}
    }
    
    for result in all_results:
        date = result['simulate_date']
        verification = result.get('verification', {})
        
        print(f"\n📅 {date}:")
        
        for period_name in ['1个月', '2个月', '3个月']:
            results_list = verification.get(period_name, [])
            if results_list:
                # 区分有效验证和跳过的验证
                valid_results = [r for r in results_list if not r.get('skipped', False)]
                skipped_results = [r for r in results_list if r.get('skipped', False)]
                
                correct = sum(1 for r in valid_results if r['match'])
                total = len(valid_results)
                skipped = len(skipped_results)
                
                accuracy = correct / total * 100 if total > 0 else 0
                total_summary[period_name]['correct'] += correct
                total_summary[period_name]['total'] += total
                total_summary[period_name]['skipped'] += skipped
                
                skip_info = f", 跳过{skipped}个" if skipped > 0 else ""
                print(f"   {period_name}: {correct}/{total} 符合预期 ({accuracy:.0f}%){skip_info}")
                
                # 显示验证错误的ETF详情
                failed_items = [r for r in valid_results if r['match'] is False]
                if failed_items:
                    print(f"      ❌ 验证失败:")
                    for item in failed_items:
                        signal_desc = '买入' if item['signal'] in ['buy', 'strong_buy'] else '回避'
                        change_str = f"{item['price_change']:+.1f}%" if item['price_change'] is not None else "N/A"
                        print(f"         - {item['name']}({item['symbol']}): {signal_desc}信号, 实际涨跌{change_str}, {item['reason']}")
                
                # 显示跳过的验证
                if skipped_results:
                    print(f"      ⏭️ 跳过验证（前期已失败）:")
                    for item in skipped_results:
                        print(f"         - {item['name']}({item['symbol']}): {item.get('skipped_reason', '前期')}失败")
    
    # 总体准确率
    print(f"\n{'=' * 80}")
    print("【总体准确率】（严格标准：买入收益≥3%，回避涨幅≤3%）")
    print("=" * 80)
    
    for period_name in ['1个月', '2个月', '3个月']:
        correct = total_summary[period_name]['correct']
        total = total_summary[period_name]['total']
        skipped = total_summary[period_name]['skipped']
        accuracy = correct / total * 100 if total > 0 else 0
        bar = '█' * int(accuracy / 5) + '░' * (20 - int(accuracy / 5))
        skip_info = f" (跳过{skipped})" if skipped > 0 else ""
        print(f"  {period_name}: [{bar}] {accuracy:.1f}% ({correct}/{total}){skip_info}")
    
    # 新增：策略调整建议
    total_failed_1m = sum(
        1 for r in all_results 
        for v in r.get('verification', {}).get('1个月', [])
        if v.get('match') is False and not v.get('skipped', False)
    )
    if total_failed_1m > 0:
        print(f"\n⚠️ 策略调整建议: 共有{total_failed_1m}个预测在1个月内验证失败，建议复盘调整策略参数")
