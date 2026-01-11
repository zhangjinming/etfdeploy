"""
ETF配置系统 - 主入口

使用示例和命令行接口

核心功能：
1. 分析单个ETF
2. 分析所有ETF并生成推荐
3. 生成投资组合
4. 检查持仓出场信号
5. 管理ETF策略配置
"""

import argparse
import json
from typing import List, Dict, Optional
from datetime import datetime

from config import ETF_POOL, ETFStrategyConfig
from etf_strategies import strategy_manager, ETFStrategy
from data_fetcher import data_fetcher
from analyzer_engine import analyzer_engine, AnalysisResult
from portfolio_allocator import (
    PortfolioAllocatorV2,
    print_allocation_report_v2,
    compare_and_print_v2,
    quick_allocate_v2,
    allocate_specific_v2
)
from portfolio_backtest import run_portfolio_backtest_v4

# 创建全局配置器实例
portfolio_allocator = PortfolioAllocatorV2()


def print_separator(title: str = "", char: str = "=", length: int = 60):
    """打印分隔线"""
    if title:
        padding = (length - len(title) - 2) // 2
        print(f"\n{char * padding} {title} {char * padding}")
    else:
        print(char * length)


def format_signal(signal: str) -> str:
    """格式化信号显示"""
    signal_map = {
        'strong_buy': '🟢 强烈买入',
        'buy': '🟡 买入',
        'hold': '⚪ 持有',
        'sell': '🟠 卖出',
        'strong_sell': '🔴 强烈卖出',
    }
    return signal_map.get(signal, signal)


def format_phase(phase: str) -> str:
    """格式化情绪阶段"""
    phase_map = {
        'despair': '😰 绝望期',
        'hesitation': '🤔 犹豫期',
        'frenzy': '🤪 疯狂期',
        'unknown': '❓ 未知',
    }
    return phase_map.get(phase, phase)


def analyze_single_etf(symbol: str, verbose: bool = True) -> Optional[AnalysisResult]:
    """
    分析单个ETF
    
    Args:
        symbol: ETF代码
        verbose: 是否打印详细信息
    """
    print_separator(f"分析 {symbol} - {ETF_POOL.get(symbol, symbol)}")
    
    result = analyzer_engine.analyze_etf(symbol)
    
    if result is None:
        print("❌ 分析失败：数据不足")
        return None
    
    if verbose:
        # 打印分析结果
        print(f"\n📊 强弱分析:")
        print(f"   信号: {format_signal(result.strength_signal)}")
        print(f"   得分: {result.strength_score:.1f}")
        print(f"   理由: {', '.join(result.strength_reasons[:3])}")
        
        print(f"\n😊 情绪分析:")
        print(f"   阶段: {format_phase(result.emotion_phase)}")
        print(f"   指数: {result.emotion_score:.2f}")
        print(f"   趋势: {result.emotion_trend}")
        
        print(f"\n📈 趋势分析:")
        print(f"   方向: {result.trend_direction}")
        print(f"   确认: {'是' if result.trend_confirmed else '否'}")
        
        print(f"\n🎯 综合评分: {result.composite_score:.2f}")
        
        if result.trade_signal:
            signal = result.trade_signal
            print(f"\n💡 交易信号:")
            print(f"   动作: {format_signal(signal.action)}")
            print(f"   置信度: {signal.confidence:.0%}")
            print(f"   入场价: {signal.entry_price:.3f}")
            print(f"   止损价: {signal.stop_loss:.3f} ({(signal.stop_loss/signal.entry_price-1)*100:.1f}%)")
            print(f"   止盈价: {signal.take_profit:.3f} ({(signal.take_profit/signal.entry_price-1)*100:.1f}%)")
            print(f"   建议仓位: {signal.position_size:.0%}")
            print(f"   有效期: {signal.validity_weeks}周")
            print(f"   理由:")
            for reason in signal.reasons:
                print(f"      - {reason}")
    
    return result


def analyze_all_etfs(verbose: bool = True) -> Dict[str, AnalysisResult]:
    """分析所有ETF"""
    print_separator("分析所有ETF")
    
    results = analyzer_engine.analyze_all_etfs()
    
    if verbose:
        # 按综合评分排序
        sorted_results = sorted(
            results.values(),
            key=lambda x: x.composite_score,
            reverse=True
        )
        
        print(f"\n{'代码':<10} {'名称':<15} {'强弱信号':<12} {'情绪阶段':<10} {'趋势':<10} {'综合评分':<10}")
        print("-" * 80)
        
        for result in sorted_results:
            trend_str = f"{result.trend_direction[:4]}{'✓' if result.trend_confirmed else ''}"
            print(f"{result.symbol:<10} {result.name:<15} {result.strength_signal:<12} "
                  f"{result.emotion_phase:<10} {trend_str:<10} {result.composite_score:+.2f}")
    
    return results


def get_recommendations(top_n: int = 5):
    """获取买入和卖出推荐"""
    print_separator("投资推荐")
    
    # 买入推荐
    print("\n🟢 买入推荐:")
    buy_recs = analyzer_engine.get_buy_recommendations(top_n)
    
    if not buy_recs:
        print("   暂无买入推荐")
    else:
        for i, rec in enumerate(buy_recs, 1):
            signal = rec.trade_signal
            print(f"\n   {i}. {rec.symbol} - {rec.name}")
            print(f"      动作: {format_signal(signal.action)} | 置信度: {signal.confidence:.0%}")
            print(f"      入场价: {signal.entry_price:.3f} | 止损: {signal.stop_loss:.3f} | 止盈: {signal.take_profit:.3f}")
            print(f"      情绪: {format_phase(rec.emotion_phase)} | 综合评分: {rec.composite_score:+.2f}")
            print(f"      理由: {', '.join(signal.reasons[:2])}")
    
    # 卖出推荐
    print("\n🔴 卖出/回避推荐:")
    sell_recs = analyzer_engine.get_sell_recommendations(top_n)
    
    if not sell_recs:
        print("   暂无卖出推荐")
    else:
        for i, rec in enumerate(sell_recs, 1):
            signal = rec.trade_signal
            print(f"\n   {i}. {rec.symbol} - {rec.name}")
            print(f"      动作: {format_signal(signal.action)} | 置信度: {signal.confidence:.0%}")
            print(f"      情绪: {format_phase(rec.emotion_phase)} | 综合评分: {rec.composite_score:+.2f}")
            print(f"      理由: {', '.join(signal.reasons[:2])}")


def generate_portfolio(capital: float = 100000, max_positions: int = 6):
    """生成投资组合"""
    print_separator(f"投资组合建议 (资金: {capital:,.0f})")
    
    portfolio = analyzer_engine.generate_portfolio(capital, max_positions)
    
    # 市场环境
    regime = portfolio.get('market_regime', {})
    print(f"\n📊 市场环境: {regime.get('regime', 'unknown')}")
    
    # 持仓建议
    print(f"\n💼 建议持仓:")
    print(f"{'代码':<10} {'名称':<15} {'动作':<12} {'入场价':<10} {'股数':<10} {'资金':<12} {'仓位':<8}")
    print("-" * 90)
    
    for pos in portfolio['positions']:
        print(f"{pos['symbol']:<10} {pos['name']:<15} {pos['action']:<12} "
              f"{pos['entry_price']:<10.3f} {pos['shares']:<10} {pos['capital']:>10,.0f} {pos['weight']:>6.0%}")
    
    print("-" * 90)
    print(f"{'总投资':<37} {'':<10} {'':<10} {portfolio['invested_capital']:>10,.0f} {1-portfolio['cash_ratio']:>6.0%}")
    print(f"{'现金':<37} {'':<10} {'':<10} {capital-portfolio['invested_capital']:>10,.0f} {portfolio['cash_ratio']:>6.0%}")
    
    # 风控提示
    print(f"\n⚠️ 风控提示:")
    for pos in portfolio['positions']:
        print(f"   {pos['symbol']}: 止损 {pos['stop_loss']:.3f} | 止盈 {pos['take_profit']:.3f}")


def check_holdings(holdings: List[Dict]):
    """
    检查持仓出场信号
    
    Args:
        holdings: 持仓列表，格式 [{'symbol': '515450', 'entry_price': 1.0, 'entry_date': '2024-01-01'}, ...]
    """
    print_separator("持仓检查")
    
    exit_signals = analyzer_engine.check_exit_signals(holdings)
    
    if not exit_signals:
        print("\n✅ 所有持仓无出场信号")
    else:
        print("\n⚠️ 以下持仓有出场信号:")
        for sig in exit_signals:
            print(f"\n   {sig['symbol']} - {sig['name']}")
            print(f"   信号: {sig['signal']}")
            print(f"   原因: {sig['reason']}")
            print(f"   当前价: {sig['current_price']:.3f}")
            print(f"   收益率: {sig['pct_change']:+.1f}%")


def manage_strategy(symbol: str, action: str = 'show', updates: Dict = None):
    """
    管理ETF策略
    
    Args:
        symbol: ETF代码
        action: 操作类型 (show/update/reset)
        updates: 更新内容
    """
    print_separator(f"策略管理 - {symbol}")
    
    strategy = strategy_manager.get_strategy(symbol)
    
    if action == 'show':
        if strategy:
            config = strategy.to_dict()
            print(f"\n当前策略配置:")
            print(json.dumps(config, indent=2, ensure_ascii=False))
        else:
            print(f"\n❌ 未找到 {symbol} 的策略配置")
    
    elif action == 'update' and updates:
        if strategy:
            strategy_manager.update_strategy(symbol, updates)
            print(f"\n✅ 策略已更新")
            print(f"更新内容: {json.dumps(updates, indent=2, ensure_ascii=False)}")
        else:
            print(f"\n❌ 未找到 {symbol} 的策略配置")
    
    elif action == 'reset':
        # 从模板重新创建
        name = ETF_POOL.get(symbol, symbol)
        strategy_manager.create_strategy_from_template(symbol, name, 'balanced')
        print(f"\n✅ 策略已重置为默认配置")


def show_strategy_comparison():
    """显示不同ETF策略对比"""
    print_separator("策略对比")
    
    strategies = strategy_manager.list_strategies()
    
    print(f"\n{'代码':<10} {'名称':<15} {'分类':<12} {'风格':<15} {'状态':<8}")
    print("-" * 70)
    
    for s in strategies:
        status = '✅ 启用' if s['enabled'] else '❌ 禁用'
        print(f"{s['symbol']:<10} {s['name']:<15} {s['category']:<12} {s['style']:<15} {status:<8}")
    
    # 显示权重对比
    print(f"\n权重配置对比:")
    print(f"{'代码':<10} {'强弱':<10} {'情绪':<10} {'趋势':<10} {'资金':<10} {'止损':<10} {'止盈':<10}")
    print("-" * 70)
    
    for s in strategies:
        strategy = strategy_manager.get_strategy(s['symbol'])
        if strategy:
            w = strategy.weights
            r = strategy.risk_control
            print(f"{s['symbol']:<10} {w.strength:<10.0%} {w.emotion:<10.0%} "
                  f"{w.trend:<10.0%} {w.capital:<10.0%} {r.stop_loss:<10.1f}% {r.take_profit:<10.1f}%")


def smart_allocate(capital: float = 100000, symbols: list = None):
    """
    智能配置 - 基于收益率和胜率分配仓位
    
    Args:
        capital: 总资金
        symbols: 指定ETF列表，None表示分析所有
    """
    print_separator("智能配置 - 基金管理人视角")
    
    if symbols:
        allocation = portfolio_allocator.allocate(
            total_capital=capital,
            symbols=symbols
        )
    else:
        allocation = portfolio_allocator.allocate(total_capital=capital)
    
    print_allocation_report_v2(allocation)
    return allocation


def compare_etfs(symbols: list):
    """
    对比ETF配置价值
    
    Args:
        symbols: ETF代码列表
    """
    print_separator("ETF配置价值对比")
    return compare_and_print_v2(symbols)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='ETF配置系统')
    parser.add_argument('command', nargs='?', default='recommend',
                        choices=['analyze', 'all', 'recommend', 'portfolio', 'check', 'strategy', 'compare', 'allocate', 'etf-compare', 'backtest'],
                        help='命令: analyze(分析单个), all(分析所有), recommend(推荐), portfolio(组合), check(检查持仓), strategy(策略管理), compare(策略对比), allocate(智能配置), etf-compare(ETF对比), backtest(回测)')
    parser.add_argument('-s', '--symbol', type=str, help='ETF代码')
    parser.add_argument('-c', '--capital', type=float, default=100000, help='资金量')
    parser.add_argument('-n', '--top', type=int, default=5, help='推荐数量')
    parser.add_argument('--action', type=str, default='show', choices=['show', 'update', 'reset'],
                        help='策略操作')
    parser.add_argument('--symbols', type=str, nargs='+', help='多个ETF代码（用于对比或配置）')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("       ETF配置系统 - 五大策略综合分析")
    print("=" * 60)
    print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if args.command == 'analyze':
        if args.symbol:
            analyze_single_etf(args.symbol)
        else:
            print("请指定ETF代码，例如: python main.py analyze -s 515450")
    
    elif args.command == 'all':
        analyze_all_etfs()
    
    elif args.command == 'recommend':
        get_recommendations(args.top)
    
    elif args.command == 'portfolio':
        generate_portfolio(args.capital)
    
    elif args.command == 'check':
        # 示例持仓
        sample_holdings = [
            {'symbol': '515450', 'entry_price': 1.0, 'entry_date': '2020-03-01'},
            {'symbol': '159949', 'entry_price': 2.5, 'entry_date': '2020-03-01'},
        ]
        check_holdings(sample_holdings)
    
    elif args.command == 'strategy':
        if args.symbol:
            manage_strategy(args.symbol, args.action)
        else:
            print("请指定ETF代码，例如: python main.py strategy -s 515450")
    
    elif args.command == 'compare':
        show_strategy_comparison()
    
    elif args.command == 'allocate':
        # 智能配置
        symbols = args.symbols if args.symbols else None
        smart_allocate(args.capital, symbols)
    
    elif args.command == 'etf-compare':
        # ETF对比
        symbols = args.symbols if args.symbols else ['515450', '159949']
        compare_etfs(symbols)
    
    elif args.command == 'backtest':
        # 回测
        symbols = args.symbols if args.symbols else ['515450', '159949']
        run_portfolio_backtest_v4(symbols, '2020-03-01', '2025-12-31', rebalance_freq=10)
    
    print("\n" + "=" * 60)


# 快捷函数
def quick_analyze(symbol: str = '515450'):
    """快速分析单个ETF"""
    return analyze_single_etf(symbol)


def quick_recommend():
    """快速获取推荐"""
    get_recommendations()


def quick_portfolio(capital: float = 100000):
    """快速生成组合"""
    generate_portfolio(capital)


def quick_smart_allocate(capital: float = 100000):
    """快速智能配置"""
    return smart_allocate(capital)


def quick_compare(symbols: list = None):
    """快速对比ETF"""
    if symbols is None:
        symbols = ['515450', '159949']
    return compare_etfs(symbols)


if __name__ == '__main__':
    main()
