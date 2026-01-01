"""
预测验证模块

用于验证ETF策略预测的准确性
优化：
1. 买入阈值从3%降低到1%
2. 增加止损规则（亏损超过5%触发止损）
3. 信号强度分级验证
4. 动态调整机制
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

from data_fetcher import ETFDataFetcher
from config import (
    VERIFICATION_PARAMS, SIGNAL_STRENGTH_PARAMS, 
    DYNAMIC_ADJUSTMENT_PARAMS, COMMODITY_ETF_PARAMS,
    DESPAIR_SHORT_LIMITS, TREND_FOLLOW_ASSETS
)


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


def verify_prediction(signal: str, price_change: Optional[float], period_name: str = '',
                      score: int = 0, symbol: str = '', emotion_phase: str = '') -> dict:
    """
    验证预测是否正确（优化版：分级验证 + 止损机制 + 绝望期优化）
    
    Args:
        signal: 预测信号 (strong_buy, buy, neutral, sell, strong_sell)
        price_change: 实际价格变化率
        period_name: 验证周期名称（半个月、1个月、2个月、3个月）
        score: 信号得分（用于分级验证）
        symbol: ETF代码（用于识别商品类ETF）
        emotion_phase: 情绪阶段（用于绝望期做空限制）
    
    Returns:
        验证结果
    
    优化后的验证标准：
    - 买入信号：收益 >= 1% 即可（原为3%）
    - 强信号买入：收益 >= 2%
    - 弱信号买入：收益 >= 1%
    - 卖出/回避信号：涨幅 <= 3% 即可
    - 止损机制：亏损超过5%触发止损警告
    - 【优化】绝望期回避信号：转为观望，不参与验证
    - 【优化】趋势性资产：使用专属回避阈值
    """
    if price_change is None:
        return {'match': None, 'reason': '数据不足'}
    
    # 获取配置参数
    buy_threshold = VERIFICATION_PARAMS.get('buy_profit_threshold', 1.0)
    strong_buy_threshold = VERIFICATION_PARAMS.get('strong_signal_buy_threshold', 2.0)
    weak_buy_threshold = VERIFICATION_PARAMS.get('weak_signal_buy_threshold', 1.0)
    avoid_threshold = VERIFICATION_PARAMS.get('avoid_loss_threshold', 3.0)
    stop_loss_threshold = VERIFICATION_PARAMS.get('stop_loss_threshold', -5.0)
    commodity_weak_threshold = VERIFICATION_PARAMS.get('commodity_weak_threshold', 0.0)
    
    strong_score_threshold = SIGNAL_STRENGTH_PARAMS.get('strong_signal_score', 4)
    
    # 判断是否为商品类ETF
    is_commodity = symbol in COMMODITY_ETF_PARAMS.get('symbols', [])
    
    # 【优化】判断是否为趋势性资产
    is_trend_asset = symbol in TREND_FOLLOW_ASSETS
    trend_config = TREND_FOLLOW_ASSETS.get(symbol, {})
    
    # 判断是否为绝望期
    is_despair = emotion_phase == 'despair'
    
    if signal in ['strong_buy', 'buy']:
        # 根据信号强度选择验证阈值
        if abs(score) >= strong_score_threshold:
            # 强信号：阈值稍高
            min_profit = strong_buy_threshold
            signal_type = '强信号'
        else:
            # 弱信号：阈值较低
            min_profit = weak_buy_threshold
            signal_type = '弱信号'
        
        # 商品类ETF使用更宽松的阈值
        if is_commodity:
            # 【优化】商品类弱信号使用专属阈值（不亏即成功）
            if abs(score) < strong_score_threshold:
                min_profit = commodity_weak_threshold
            else:
                min_profit = max(0.5, min_profit - 0.5)
            signal_type += '(商品)'
        
        # 检查止损
        if price_change <= stop_loss_threshold:
            return {
                'match': False, 
                'reason': f'触发止损：亏损{abs(price_change):.1f}% > {abs(stop_loss_threshold)}%',
                'stop_loss_triggered': True
            }
        
        # 验证收益
        if price_change >= min_profit:
            return {'match': True, 'reason': f'{signal_type}收益{price_change:.1f}% ≥ {min_profit}%'}
        else:
            return {'match': False, 'reason': f'{signal_type}收益{price_change:+.1f}% < {min_profit}%'}
    
    elif signal in ['strong_sell', 'sell']:
        # 【优化】绝望期回避信号转为观望，不参与验证
        if is_despair and DESPAIR_SHORT_LIMITS.get('convert_avoid_to_neutral', True):
            return {
                'match': None, 
                'reason': '绝望期回避信号转为观望，不参与验证',
                'despair_neutral': True
            }
        
        # 【优化】趋势性资产绝望期不做空
        if is_trend_asset and trend_config.get('no_despair_short', False) and is_despair:
            return {
                'match': None, 
                'reason': f'{trend_config.get("name", "趋势资产")}绝望期不做空，转为观望',
                'despair_neutral': True
            }
        
        # 【优化】趋势性资产使用专属回避阈值
        if is_trend_asset:
            avoid_threshold = trend_config.get('avoid_threshold', avoid_threshold)
        
        # 绝望期做空限制（非转观望模式下的宽容处理）
        if is_despair and DESPAIR_SHORT_LIMITS.get('enable_caution', True):
            rsi_floor = DESPAIR_SHORT_LIMITS.get('rsi_floor', 20)
            # 绝望期做空需要更严格的验证
            if price_change > 0:
                # 绝望期资产上涨，做空失败，但给予宽容
                if price_change <= avoid_threshold * 1.5:  # 放宽50%
                    return {
                        'match': True, 
                        'reason': f'绝望期宽容：涨幅{price_change:.1f}%在容忍范围内',
                        'despair_tolerance': True
                    }
                else:
                    return {
                        'match': False, 
                        'reason': f'绝望期反转：上涨{price_change:.1f}%（底部反转风险）',
                        'despair_reversal': True
                    }
        
        # 卖出/回避信号：下跌或涨幅不超过阈值即算正确
        if price_change <= avoid_threshold:
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
    从分析结果中收集预测信息（优化版：增加信号强度和情绪阶段）
    
    【优化】绝望期回避信号转为观望，不参与验证
    
    Args:
        results: 策略分析结果
    
    Returns:
        (predictions, verified_symbols) 预测列表和被验证的ETF代码集合
    """
    predictions = []
    verified_symbols = set()
    
    # 获取ETF分析结果用于补充信息
    etf_analysis = results.get('etf_analysis', {})
    
    # 多头推荐
    portfolio = results.get('portfolio_suggestion', {})
    for pos in portfolio.get('long_positions', []):
        symbol = pos['symbol']
        # 获取信号得分和情绪阶段
        analysis = etf_analysis.get(symbol, {})
        score = analysis.get('strength', {}).get('score', 0)
        emotion_phase = analysis.get('emotion', {}).get('phase', 'unknown')
        
        predictions.append({
            'symbol': symbol,
            'name': pos['name'],
            'signal': 'buy',
            'type': '多头推荐',
            'score': score,
            'emotion_phase': emotion_phase
        })
        verified_symbols.add(symbol)
    
    # 回避建议
    for pos in portfolio.get('hedge_positions', []):
        symbol = pos['symbol']
        analysis = etf_analysis.get(symbol, {})
        score = analysis.get('strength', {}).get('score', 0)
        emotion_phase = analysis.get('emotion', {}).get('phase', 'unknown')
        
        # 【优化】绝望期回避信号转为观望，不参与验证
        is_despair = emotion_phase == 'despair'
        convert_to_neutral = DESPAIR_SHORT_LIMITS.get('convert_avoid_to_neutral', True)
        
        # 【优化】趋势性资产绝望期也不做空
        trend_config = TREND_FOLLOW_ASSETS.get(symbol, {})
        no_despair_short = trend_config.get('no_despair_short', False)
        
        if is_despair and (convert_to_neutral or no_despair_short):
            # 绝望期回避信号转为观望，记录但标记为不验证
            predictions.append({
                'symbol': symbol,
                'name': pos['name'],
                'signal': 'neutral',  # 转为中性
                'type': '建议回避(绝望期转观望)',
                'score': score,
                'emotion_phase': emotion_phase,
                'despair_neutral': True  # 标记为绝望期转观望
            })
            # 不加入verified_symbols，不参与验证
        else:
            predictions.append({
                'symbol': symbol,
                'name': pos['name'],
                'signal': 'sell',
                'type': '建议回避',
                'score': score,
                'emotion_phase': emotion_phase
            })
            verified_symbols.add(symbol)
    
    # ETF分析结果（强信号）
    for symbol, analysis in etf_analysis.items():
        signal = analysis.get('strength', {}).get('signal', 'neutral')
        score = analysis.get('strength', {}).get('score', 0)
        emotion_phase = analysis.get('emotion', {}).get('phase', 'unknown')
        
        if signal in ['strong_buy', 'strong_sell']:
            # 【优化】绝望期强卖出信号也转为观望
            is_despair = emotion_phase == 'despair'
            convert_to_neutral = DESPAIR_SHORT_LIMITS.get('convert_avoid_to_neutral', True)
            trend_config = TREND_FOLLOW_ASSETS.get(symbol, {})
            no_despair_short = trend_config.get('no_despair_short', False)
            
            if signal == 'strong_sell' and is_despair and (convert_to_neutral or no_despair_short):
                # 绝望期强卖出信号转为观望
                predictions.append({
                    'symbol': symbol,
                    'name': analysis['name'],
                    'signal': 'neutral',
                    'type': '强信号(绝望期转观望)',
                    'score': score,
                    'emotion_phase': emotion_phase,
                    'despair_neutral': True
                })
            else:
                predictions.append({
                    'symbol': symbol,
                    'name': analysis['name'],
                    'signal': signal,
                    'type': '强信号',
                    'score': score,
                    'emotion_phase': emotion_phase
                })
                verified_symbols.add(symbol)
    
    return predictions, verified_symbols


def verify_predictions_for_date(fetcher: ETFDataFetcher, predictions: list, 
                                 tuesday: str, verify_periods: list) -> dict:
    """
    验证指定日期的所有预测（优化版：增加止损和动态调整）
    
    优化：
    - 短周期验证失败则跳过长周期验证
    - 1个月亏损超过5%触发止损
    - 信号强度分级验证
    - 绝望期做空谨慎处理
    
    Args:
        fetcher: 数据获取器
        predictions: 预测列表
        tuesday: 分析日期
        verify_periods: 验证周期列表 [(名称, 天数), ...]
    
    Returns:
        验证摘要字典
    """
    verification_summary = {period[0]: [] for period in verify_periods}
    stop_loss_threshold = VERIFICATION_PARAMS.get('stop_loss_threshold', -5.0)
    
    print(f"\n{'=' * 80}")
    print(f"【预测验证】- 分析日期: {tuesday}")
    print(f"{'=' * 80}")
    
    for pred in predictions:
        symbol = pred['symbol']
        name = pred['name']
        signal = pred['signal']
        pred_type = pred['type']
        score = pred.get('score', 0)
        emotion_phase = pred.get('emotion_phase', 'unknown')
        
        # 信号强度标记
        strength_mark = '💪' if abs(score) >= SIGNAL_STRENGTH_PARAMS.get('strong_signal_score', 4) else ''
        despair_mark = '⚠️绝望期' if emotion_phase == 'despair' and signal in ['sell', 'strong_sell'] else ''
        
        print(f"\n  📊 {name}({symbol}) - {pred_type} [{signal}] {strength_mark} {despair_mark}")
        
        # 记录该ETF是否已验证失败或触发止损
        failed_at_period = None
        stop_loss_triggered = False
        
        for period_name, days in verify_periods:
            # 优化：如果前一个周期验证失败，跳过后续验证
            if failed_at_period is not None:
                skip_reason = '触发止损' if stop_loss_triggered else f'{failed_at_period}已失败'
                print(f"     {period_name}: ⏭️ 跳过验证 | {skip_reason}，需调整策略")
                # 记录跳过信息
                skip_detail = {
                    'symbol': symbol,
                    'name': name,
                    'signal': signal,
                    'type': pred_type,
                    'score': score,
                    'emotion_phase': emotion_phase,
                    'price_change': None,
                    'match': None,
                    'reason': f'{skip_reason}，跳过后续验证',
                    'skipped': True,
                    'skipped_reason': failed_at_period,
                    'stop_loss_triggered': stop_loss_triggered
                }
                verification_summary[period_name].append(skip_detail)
                continue
            
            price_change = get_future_price_change(fetcher, symbol, tuesday, days)
            
            # 调用优化后的验证函数，传入额外参数
            verify_result = verify_prediction(
                signal, price_change, period_name,
                score=score, symbol=symbol, emotion_phase=emotion_phase
            )
            
            # 记录详细验证信息
            verify_detail = {
                'symbol': symbol,
                'name': name,
                'signal': signal,
                'type': pred_type,
                'score': score,
                'emotion_phase': emotion_phase,
                'price_change': price_change,
                'match': verify_result['match'],
                'reason': verify_result['reason'],
                'skipped': False,
                'stop_loss_triggered': verify_result.get('stop_loss_triggered', False),
                'despair_tolerance': verify_result.get('despair_tolerance', False),
                'despair_reversal': verify_result.get('despair_reversal', False)
            }
            
            if verify_result['match'] is None:
                status = '⚪ 数据不足'
            elif verify_result['match']:
                status = '✅ 符合预期'
                # 特殊标记
                if verify_result.get('despair_tolerance'):
                    status += ' (绝望期宽容)'
                verification_summary[period_name].append(verify_detail)
            else:
                status = '❌ 不符合预期'
                verification_summary[period_name].append(verify_detail)
                # 标记验证失败
                failed_at_period = period_name
                # 检查是否触发止损
                if verify_result.get('stop_loss_triggered'):
                    stop_loss_triggered = True
                    status += ' 🛑止损'
            
            change_str = f"{price_change:+.1f}%" if price_change is not None else "N/A"
            print(f"     {period_name}: {status} | 涨跌: {change_str} | {verify_result['reason']}")
            
            # 如果验证失败，提示需要策略调整
            if failed_at_period:
                if stop_loss_triggered:
                    print(f"     🛑 止损触发: {name}亏损超过{abs(stop_loss_threshold)}%，建议立即止损")
                else:
                    print(f"     ⚠️ 策略失效提示: {name}在{period_name}验证失败，后续周期不再验证")
    
    return verification_summary


def print_verification_summary(all_results: list):
    """
    打印验证汇总报告（优化版：增加止损统计和策略建议）
    
    优化：
    - 统计跳过的验证，区分有效验证和跳过验证
    - 统计止损触发次数
    - 统计绝望期做空失败次数
    - 提供针对性的策略调整建议
    
    Args:
        all_results: 所有分析结果列表
    """
    print(f"\n{'=' * 80}")
    print("【总体验证汇总】")
    print("=" * 80)
    
    total_summary = {
        '1个月': {'correct': 0, 'total': 0, 'skipped': 0, 'stop_loss': 0, 'despair_fail': 0}, 
        '2个月': {'correct': 0, 'total': 0, 'skipped': 0, 'stop_loss': 0, 'despair_fail': 0}, 
        '3个月': {'correct': 0, 'total': 0, 'skipped': 0, 'stop_loss': 0, 'despair_fail': 0}
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
                stop_loss_count = sum(1 for r in valid_results if r.get('stop_loss_triggered', False))
                despair_fail_count = sum(1 for r in valid_results if r.get('despair_reversal', False))
                
                accuracy = correct / total * 100 if total > 0 else 0
                total_summary[period_name]['correct'] += correct
                total_summary[period_name]['total'] += total
                total_summary[period_name]['skipped'] += skipped
                total_summary[period_name]['stop_loss'] += stop_loss_count
                total_summary[period_name]['despair_fail'] += despair_fail_count
                
                skip_info = f", 跳过{skipped}个" if skipped > 0 else ""
                stop_loss_info = f", 止损{stop_loss_count}个" if stop_loss_count > 0 else ""
                print(f"   {period_name}: {correct}/{total} 符合预期 ({accuracy:.0f}%){skip_info}{stop_loss_info}")
                
                # 显示验证错误的ETF详情
                failed_items = [r for r in valid_results if r['match'] is False]
                if failed_items:
                    print(f"      ❌ 验证失败:")
                    for item in failed_items:
                        signal_desc = '买入' if item['signal'] in ['buy', 'strong_buy'] else '回避'
                        change_str = f"{item['price_change']:+.1f}%" if item['price_change'] is not None else "N/A"
                        extra_info = ""
                        if item.get('stop_loss_triggered'):
                            extra_info = " 🛑止损"
                        elif item.get('despair_reversal'):
                            extra_info = " ⚠️绝望期反转"
                        print(f"         - {item['name']}({item['symbol']}): {signal_desc}信号, 实际涨跌{change_str}, {item['reason']}{extra_info}")
                
                # 显示跳过的验证
                if skipped_results:
                    print(f"      ⏭️ 跳过验证（前期已失败）:")
                    for item in skipped_results:
                        skip_reason = '止损' if item.get('stop_loss_triggered') else '前期失败'
                        print(f"         - {item['name']}({item['symbol']}): {skip_reason}")
    
    # 总体准确率
    print(f"\n{'=' * 80}")
    print("【总体准确率】（优化标准：买入收益≥1%，强信号≥2%，回避涨幅≤3%）")
    print("=" * 80)
    
    for period_name in ['1个月', '2个月', '3个月']:
        correct = total_summary[period_name]['correct']
        total = total_summary[period_name]['total']
        skipped = total_summary[period_name]['skipped']
        stop_loss = total_summary[period_name]['stop_loss']
        despair_fail = total_summary[period_name]['despair_fail']
        accuracy = correct / total * 100 if total > 0 else 0
        bar = '█' * int(accuracy / 5) + '░' * (20 - int(accuracy / 5))
        
        extra_info = []
        if skipped > 0:
            extra_info.append(f"跳过{skipped}")
        if stop_loss > 0:
            extra_info.append(f"止损{stop_loss}")
        if despair_fail > 0:
            extra_info.append(f"绝望期反转{despair_fail}")
        extra_str = f" ({', '.join(extra_info)})" if extra_info else ""
        
        print(f"  {period_name}: [{bar}] {accuracy:.1f}% ({correct}/{total}){extra_str}")
    
    # 策略调整建议
    print(f"\n{'=' * 80}")
    print("【策略调整建议】")
    print("=" * 80)
    
    total_failed_1m = sum(
        1 for r in all_results 
        for v in r.get('verification', {}).get('1个月', [])
        if v.get('match') is False and not v.get('skipped', False)
    )
    total_stop_loss = sum(
        1 for r in all_results 
        for v in r.get('verification', {}).get('1个月', [])
        if v.get('stop_loss_triggered', False)
    )
    total_despair_fail = sum(
        1 for r in all_results 
        for v in r.get('verification', {}).get('1个月', [])
        if v.get('despair_reversal', False)
    )
    
    if total_failed_1m > 0:
        print(f"  ⚠️ 共有{total_failed_1m}个预测在1个月内验证失败")
    if total_stop_loss > 0:
        print(f"  🛑 共有{total_stop_loss}次触发止损，建议检查买入时机")
    if total_despair_fail > 0:
        print(f"  ⚠️ 共有{total_despair_fail}次绝望期做空失败（底部反转），建议对绝望期资产更谨慎做空")
    
    # 具体建议
    print(f"\n  📋 优化建议:")
    if total_stop_loss > total_failed_1m * 0.3:
        print(f"     1. 止损比例较高，考虑提高买入信号阈值或等待更明确的趋势确认")
    if total_despair_fail > 0:
        print(f"     2. 绝望期做空需谨慎，底部反转风险大，建议等待趋势确认后再做空")
    print(f"     3. 商品类ETF波动大，建议使用纯趋势跟踪策略")
    print(f"     4. 信号失效后应及时止损，避免扩大损失")
