"""Markdown报告生成器"""

from datetime import datetime
from typing import Dict, List, Optional
import os


class MarkdownReportGenerator:
    """生成格式化的Markdown分析报告"""
    
    def __init__(self, output_dir: str = "reports"):
        """
        初始化报告生成器
        
        Args:
            output_dir: 报告输出目录
        """
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
    def generate_single_report(self, results: Dict, filename: Optional[str] = None) -> str:
        """
        生成单次分析的Markdown报告
        
        Args:
            results: 分析结果字典
            filename: 输出文件名（不含扩展名）
        
        Returns:
            生成的文件路径
        """
        timestamp = results.get('timestamp', datetime.now().strftime('%Y-%m-%d'))
        if filename is None:
            filename = f"etf_analysis_{timestamp.replace(' ', '_').replace(':', '-')}"
        
        content = self._build_single_report(results)
        filepath = os.path.join(self.output_dir, f"{filename}.md")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\n📄 报告已生成: {filepath}")
        return filepath
    
    def generate_verification_report(self, all_results: List[Dict], 
                                     start_date: str, end_date: str,
                                     filename: Optional[str] = None) -> str:
        """
        生成验证报告（包含多个周二的分析和验证结果）
        
        Args:
            all_results: 所有分析结果列表
            start_date: 开始日期
            end_date: 结束日期
            filename: 输出文件名
        
        Returns:
            生成的文件路径
        """
        if filename is None:
            filename = f"etf_verification_{start_date}_to_{end_date}"
        
        content = self._build_verification_report(all_results, start_date, end_date)
        filepath = os.path.join(self.output_dir, f"{filename}.md")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\n📄 验证报告已生成: {filepath}")
        return filepath
    
    def _build_single_report(self, results: Dict) -> str:
        """构建单次分析报告内容"""
        lines = []
        timestamp = results.get('timestamp', 'N/A')
        mode = '周线' if results.get('analysis_mode') == 'weekly' else '日线'
        
        # 标题
        lines.append(f"# 📊 ETF配置分析报告")
        lines.append(f"\n> **分析日期**: {timestamp} | **分析模式**: {mode}级别\n")
        lines.append("---\n")
        
        # 一、强弱分析
        lines.append("## 一、强弱分析\n")
        lines.append(self._build_strength_table(results.get('etf_analysis', {})))
        
        # 二、资金面分析
        lines.append("\n## 二、资金面分析\n")
        lines.append(self._build_style_analysis(results.get('style_analysis', {})))
        
        # 三、市场健康度
        lines.append("\n## 三、市场健康度\n")
        lines.append(self._build_health_analysis(results.get('market_health', {})))
        
        # 四、对冲策略
        lines.append("\n## 四、对冲策略建议\n")
        lines.append(self._build_portfolio_suggestion(results.get('portfolio_suggestion', {})))
        
        # 五、综合建议
        lines.append("\n## 五、综合配置建议\n")
        lines.append(self._build_final_suggestion(results))
        
        # 核心理念
        lines.append("\n## 💡 核心理念提醒\n")
        lines.append("""
| # | 理念 |
|---|------|
| 1 | 该涨不涨看跌，该跌不跌看涨 |
| 2 | 行情在绝望中产生，犹豫中发展，疯狂中消亡 |
| 3 | 恶炒消耗资金，价值白马领涨才有持续性 |
| 4 | 留有余地，仓位不可用足 |
| 5 | 策略比预测更重要，以变应变 |
""")
        
        # 免责声明
        lines.append("\n---\n")
        lines.append("*⚠️ 免责声明：本报告仅供学习研究，不构成投资建议。投资有风险，入市需谨慎。*\n")
        
        return '\n'.join(lines)
    
    def _build_strength_table(self, etf_analysis: Dict, verified_symbols: set = None, 
                               verification_data: Dict = None, verification_data_3m: Dict = None) -> str:
        """构建强弱分析表格
        
        Args:
            etf_analysis: ETF分析结果
            verified_symbols: 被验证的ETF代码集合，用于标记
            verification_data: 验证数据，包含每个ETF的未来1个月涨跌信息
            verification_data_3m: 验证数据，包含每个ETF的未来3个月涨跌信息
        """
        if not etf_analysis:
            return "*暂无数据*\n"
        
        if verified_symbols is None:
            verified_symbols = set()
        
        if verification_data is None:
            verification_data = {}
        
        if verification_data_3m is None:
            verification_data_3m = {}
        
        signal_map = {
            'strong_buy': '🟢🟢 强买入',
            'buy': '🟢 买入',
            'neutral': '⚪ 中性',
            'sell': '🔴 卖出',
            'strong_sell': '🔴🔴 强卖出'
        }
        
        phase_map = {
            'despair': '😰 绝望期',
            'hesitation': '🤔 犹豫期',
            'frenzy': '🤩 疯狂期',
            'unknown': '❓ 未知'
        }
        
        lines = []
        # 根据是否有验证数据决定表头
        if verification_data or verification_data_3m:
            lines.append("| ETF名称 | 代码 | 信号 | 得分 | 综合得分 | 情绪阶段 | RSI | 近1月涨跌 | 未来1月涨跌 | 未来3月涨跌 | 原因 | 验证 |")
            lines.append("|---------|------|------|------|----------|----------|-----|----------|------------|------------|------|------|")
        else:
            lines.append("| ETF名称 | 代码 | 信号 | 得分 | 综合得分 | 情绪阶段 | RSI | 近1月涨跌 | 原因 | 验证 |")
            lines.append("|---------|------|------|------|----------|----------|-----|----------|------|------|")
        
        for symbol, analysis in etf_analysis.items():
            name = analysis.get('name', symbol)
            strength = analysis.get('strength', {})
            emotion = analysis.get('emotion', {})
            
            signal = signal_map.get(strength.get('signal', 'neutral'), '⚪ 中性')
            score = strength.get('score', 0)
            composite_score = analysis.get('composite_score', 0)
            phase = phase_map.get(emotion.get('phase', 'unknown'), '❓ 未知')
            rsi = strength.get('rsi', 0)
            pct_change = analysis.get('pct_change_1m', 0)
            reasons = strength.get('reasons', [])
            reason_str = reasons[0] if reasons else '-'
            
            pct_str = f"+{pct_change:.1f}%" if pct_change >= 0 else f"{pct_change:.1f}%"
            composite_str = f"{composite_score:.2f}" if composite_score else "0.00"
            
            # 标记是否被验证
            verified_mark = "✓" if symbol in verified_symbols else ""
            
            # 获取未来涨跌
            if verification_data or verification_data_3m:
                # 未来1个月涨跌
                future_change_1m = verification_data.get(symbol)
                if future_change_1m is not None:
                    future_str_1m = f"+{future_change_1m:.1f}%" if future_change_1m >= 0 else f"{future_change_1m:.1f}%"
                else:
                    future_str_1m = "N/A"
                
                # 未来3个月涨跌
                future_change_3m = verification_data_3m.get(symbol)
                if future_change_3m is not None:
                    future_str_3m = f"+{future_change_3m:.1f}%" if future_change_3m >= 0 else f"{future_change_3m:.1f}%"
                else:
                    future_str_3m = "N/A"
                
                lines.append(f"| {name} | {symbol} | {signal} | {score} | {composite_str} | {phase} | {rsi:.1f} | {pct_str} | {future_str_1m} | {future_str_3m} | {reason_str} | {verified_mark} |")
            else:
                lines.append(f"| {name} | {symbol} | {signal} | {score} | {composite_str} | {phase} | {rsi:.1f} | {pct_str} | {reason_str} | {verified_mark} |")
        
        return '\n'.join(lines) + '\n'
    
    def _build_style_analysis(self, style: Dict) -> str:
        """构建风格分析内容"""
        if not style or 'error' in style:
            return "*数据获取失败*\n"
        
        style_map = {
            'large_cap_dominant': '📈 大盘股占优',
            'small_cap_dominant': '📉 小盘股占优',
            'balanced': '⚖️ 风格均衡'
        }
        
        trend_map = {
            'rotating_to_large': '→ 转向大盘',
            'rotating_to_small': '→ 转向小盘',
            'stable': '→ 稳定'
        }
        
        current_style = style_map.get(style.get('style', 'balanced'), '⚖️ 风格均衡')
        trend = trend_map.get(style.get('style_trend', 'stable'), '')
        
        lines = []
        lines.append(f"**当前风格**: {current_style} {trend}\n")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 大盘股收益 | {style.get('large_cap_return', 0):.2f}% |")
        lines.append(f"| 小盘股收益 | {style.get('small_cap_return', 0):.2f}% |")
        lines.append(f"| 风格差异 | {style.get('style_diff', 0):.2f}% |")
        lines.append(f"| 资金效率比 | {style.get('efficiency_ratio', 0):.1f}x |")
        lines.append("")
        lines.append(f"**建议**: {style.get('suggestion', '-')}")
        
        if style.get('trend_suggestion'):
            lines.append(f"\n**趋势**: {style.get('trend_suggestion')}")
        
        if 'allocation' in style:
            lines.append("\n### 风格配置建议\n")
            lines.append("```")
            lines.append(f"大盘股: {style['allocation']['large_cap']*100:.0f}%")
            lines.append(f"小盘股: {style['allocation']['small_cap']*100:.0f}%")
            lines.append("```")
        
        return '\n'.join(lines) + '\n'
    
    def _build_health_analysis(self, health: Dict) -> str:
        """构建市场健康度分析"""
        if not health:
            return "*暂无数据*\n"
        
        health_map = {
            'excellent': '🟢 优秀',
            'good': '🟡 良好',
            'fair': '🟠 一般',
            'poor': '🔴 较差',
            'unknown': '⚪ 未知'
        }
        
        status = health_map.get(health.get('health', 'unknown'), '⚪ 未知')
        score = health.get('score', 0)
        max_score = health.get('max_score', 10)
        
        # 进度条
        progress = int((score / max_score) * 10) if max_score > 0 else 0
        bar = '█' * progress + '░' * (10 - progress)
        
        lines = []
        lines.append(f"**健康状态**: {status}\n")
        lines.append(f"**得分**: [{bar}] {score}/{max_score}\n")
        
        factors = health.get('factors', [])
        if factors:
            lines.append("\n**影响因素**:\n")
            for factor in factors[:5]:
                lines.append(f"- {factor}")
        
        suggestion = health.get('suggestion', '')
        if suggestion:
            lines.append(f"\n**建议**: {suggestion}")
        
        return '\n'.join(lines) + '\n'
    
    def _build_portfolio_suggestion(self, portfolio: Dict) -> str:
        """构建组合建议"""
        if not portfolio:
            return "*暂无数据*\n"
        
        lines = []
        cash_ratio = portfolio.get('cash_ratio', 0) * 100
        net_exposure = portfolio.get('net_exposure', 0) * 100
        
        lines.append("### 仓位配置\n")
        lines.append(f"| 指标 | 配置 |")
        lines.append(f"|------|------|")
        lines.append(f"| 现金比例 | **{cash_ratio:.0f}%** (留有余地) |")
        lines.append(f"| 多头敞口 | **{net_exposure:.0f}%** |")
        
        # 多头配置
        long_positions = portfolio.get('long_positions', [])
        if long_positions:
            lines.append("\n### 🟢 多头配置\n")
            lines.append("| ETF | 代码 | 权重 | 原因 |")
            lines.append("|-----|------|------|------|")
            for pos in long_positions:
                weight = pos.get('weight', 0) * 100
                lines.append(f"| {pos['name']} | {pos['symbol']} | {weight:.0f}% | {pos.get('reason', '-')} |")
        else:
            lines.append("\n### 🟢 多头配置\n")
            lines.append("*暂无强势标的*\n")
        
        # 风险提示
        hedge_positions = portfolio.get('hedge_positions', [])
        if hedge_positions:
            lines.append("\n### 🔴 风险提示（建议回避）\n")
            lines.append("| ETF | 代码 | 原因 |")
            lines.append("|-----|------|------|")
            for pos in hedge_positions:
                lines.append(f"| {pos['name']} | {pos['symbol']} | {pos.get('reason', '-')} |")
        
        return '\n'.join(lines) + '\n'
    
    def _build_final_suggestion(self, results: Dict) -> str:
        """构建综合建议"""
        etf_analysis = results.get('etf_analysis', {})
        
        buy_signals = []
        sell_signals = []
        despair_etfs = []
        frenzy_etfs = []
        improving_etfs = []
        
        for symbol, analysis in etf_analysis.items():
            name = analysis.get('name', symbol)
            if analysis['strength']['signal'] in ['strong_buy', 'buy']:
                buy_signals.append(name)
            elif analysis['strength']['signal'] in ['strong_sell', 'sell']:
                sell_signals.append(name)
            
            if analysis['emotion']['phase'] == 'despair':
                despair_etfs.append(name)
            elif analysis['emotion']['phase'] == 'frenzy':
                frenzy_etfs.append(name)
            
            if analysis.get('emotion_trend', {}).get('trend') in ['improving', 'improving_fast']:
                improving_etfs.append(name)
        
        lines = []
        lines.append("### 市场状态总结\n")
        lines.append("| 类型 | 数量 | ETF |")
        lines.append("|------|------|-----|")
        lines.append(f"| 🟢 超跌反弹机会 | {len(buy_signals)} | {', '.join(buy_signals) if buy_signals else '-'} |")
        lines.append(f"| 🔴 超涨回调风险 | {len(sell_signals)} | {', '.join(sell_signals) if sell_signals else '-'} |")
        lines.append(f"| 😰 绝望期(可建仓) | {len(despair_etfs)} | {', '.join(despair_etfs[:4]) if despair_etfs else '-'} |")
        lines.append(f"| 🤩 疯狂期(注意风险) | {len(frenzy_etfs)} | {', '.join(frenzy_etfs[:4]) if frenzy_etfs else '-'} |")
        lines.append(f"| 📈 情绪改善中 | {len(improving_etfs)} | {', '.join(improving_etfs[:4]) if improving_etfs else '-'} |")
        
        return '\n'.join(lines) + '\n'
    
    def _build_verification_report(self, all_results: List[Dict], 
                                   start_date: str, end_date: str) -> str:
        """构建验证报告"""
        from verification import get_future_price_change
        from data_fetcher import ETFDataFetcher
        
        lines = []
        
        # 标题
        lines.append(f"# 📊 ETF策略验证报告")
        lines.append(f"\n> **验证周期**: {start_date} 至 {end_date} | **样本数**: {len(all_results)} 个周二\n")
        lines.append("---\n")
        
        # 总体准确率汇总
        lines.append("## 📈 总体准确率\n")
        total_summary = self._calculate_total_accuracy(all_results)
        
        lines.append("| 验证周期 | 准确率 | 正确/总数 | 跳过 | 进度条 |")
        lines.append("|----------|--------|-----------|------|--------|")
        
        for period_name in ['1个月', '2个月', '3个月']:
            stats = total_summary.get(period_name, {'correct': 0, 'total': 0, 'skipped': 0})
            correct = stats['correct']
            total = stats['total']
            skipped = stats.get('skipped', 0)
            accuracy = correct / total * 100 if total > 0 else 0
            progress = int(accuracy / 5)
            bar = '█' * progress + '░' * (20 - progress)
            skip_str = str(skipped) if skipped > 0 else "-"
            lines.append(f"| {period_name} | **{accuracy:.1f}%** | {correct}/{total} | {skip_str} | `{bar}` |")
        
        lines.append("\n---\n")
        
        # 验证说明
        lines.append("## 📋 验证说明\n")
        lines.append("""
验证范围仅包括以下三类ETF：
1. **多头推荐** - 对冲策略模块推荐的做多标的
2. **建议回避** - 对冲策略模块建议回避的标的
3. **强信号** - 强弱分析中得分≥4（强买入）或≤-4（强卖出）的ETF

**优化后的验证标准**：
- 买入信号：收益 ≥ 1%（弱信号）或 ≥ 2%（强信号）
- 回避信号：涨幅 ≤ 3%
- 止损规则：1个月内亏损超过5%触发止损
- 绝望期做空：底部反转风险大，给予宽容度（涨幅≤4.5%仍算成功）
- 商品类ETF：波动大，买入阈值降低0.5%

表格中"验证"列标记 ✓ 的ETF参与了准确率统计。
""")
        
        # 创建数据获取器用于获取所有ETF的未来涨跌
        fetcher = ETFDataFetcher()
        
        # 每周详细分析
        lines.append("## 📅 每周分析详情\n")
        
        for i, result in enumerate(all_results, 1):
            date = result.get('simulate_date', 'N/A')
            lines.append(f"### 第 {i} 周 - {date}\n")
            
            # 简要强弱分析
            lines.append("<details>")
            lines.append(f"<summary>点击展开详情</summary>\n")
            
            # 获取被验证的ETF列表
            verified_symbols = result.get('verified_symbols', set())
            
            # 获取所有ETF的未来涨跌数据（不仅仅是被验证的）
            etf_analysis = result.get('etf_analysis', {})
            future_changes_1m = {}
            future_changes_3m = {}
            
            for symbol in etf_analysis.keys():
                # 获取未来1个月涨跌
                change_1m = get_future_price_change(fetcher, symbol, date, 30)
                if change_1m is not None:
                    future_changes_1m[symbol] = change_1m
                
                # 获取未来3个月涨跌
                change_3m = get_future_price_change(fetcher, symbol, date, 90)
                if change_3m is not None:
                    future_changes_3m[symbol] = change_3m
            
            # ETF分析表格（带验证标记和未来涨跌）
            lines.append(self._build_strength_table(etf_analysis, verified_symbols, future_changes_1m, future_changes_3m))
            
            # 组合建议
            portfolio = result.get('portfolio_suggestion', {})
            if portfolio:
                cash_ratio = portfolio.get('cash_ratio', 0) * 100
                lines.append(f"\n**现金比例**: {cash_ratio:.0f}%\n")
                
                # 显示完整的多头推荐列表（使用etf_analysis中的综合得分以保持一致）
                long_positions = portfolio.get('long_positions', [])
                if long_positions:
                    long_items = []
                    for p in long_positions:
                        symbol = p['symbol']
                        # 优先使用etf_analysis中的综合得分（与表格显示一致）
                        if symbol in etf_analysis:
                            score = etf_analysis[symbol].get('composite_score', 0)
                        else:
                            score = p.get('composite_score', 0)
                        long_items.append(f"{p['name']}({score:.2f})")
                    lines.append(f"**推荐多头**: {', '.join(long_items)}\n")
                
                # 显示回避建议列表（使用etf_analysis中的综合得分以保持一致）
                hedge_positions = portfolio.get('hedge_positions', [])
                if hedge_positions:
                    hedge_items = []
                    for p in hedge_positions:
                        symbol = p['symbol']
                        # 优先使用etf_analysis中的综合得分（与表格显示一致）
                        if symbol in etf_analysis:
                            score = etf_analysis[symbol].get('composite_score', 0)
                        else:
                            score = p.get('composite_score', 0)
                        hedge_items.append(f"{p['name']}({score:.2f})")
                    lines.append(f"**建议回避**: {', '.join(hedge_items)}\n")
                
                # 显示强信号ETF（不在多头/回避中的）
                etf_analysis = result.get('etf_analysis', {})
                strong_signals = []
                long_symbols = {p['symbol'] for p in long_positions}
                hedge_symbols = {p['symbol'] for p in hedge_positions}
                for symbol, analysis in etf_analysis.items():
                    signal = analysis.get('strength', {}).get('signal', 'neutral')
                    if signal in ['strong_buy', 'strong_sell']:
                        if symbol not in long_symbols and symbol not in hedge_symbols:
                            name = analysis.get('name', symbol)
                            signal_text = '强买入' if signal == 'strong_buy' else '强卖出'
                            strong_signals.append(f"{name}({signal_text})")
                if strong_signals:
                    lines.append(f"**强信号**: {', '.join(strong_signals)}\n")
            
            # 验证结果
            verification = result.get('verification', {})
            if verification:
                lines.append("\n**验证结果**:\n")
                lines.append("| 周期 | 正确 | 总数 | 准确率 |")
                lines.append("|------|------|------|--------|")
                for period in ['1个月', '2个月', '3个月']:
                    results_list = verification.get(period, [])
                    if results_list:
                        # 支持两种格式：布尔值列表或字典列表
                        if isinstance(results_list[0], dict):
                            # 排除跳过的验证
                            valid_results = [r for r in results_list if not r.get('skipped', False)]
                            correct = sum(1 for r in valid_results if r.get('match'))
                            total = len(valid_results)
                        else:
                            correct = sum(1 for r in results_list if r)
                            total = len(results_list)
                        if total > 0:
                            acc = correct / total * 100
                            lines.append(f"| {period} | {correct} | {total} | {acc:.0f}% |")
                
                # 添加验证失败详情
                failed_details = []
                for period in ['1个月', '2个月', '3个月']:
                    results_list = verification.get(period, [])
                    if results_list and isinstance(results_list[0], dict):
                        for r in results_list:
                            # 跳过的验证也显示在失败详情中
                            if r.get('skipped', False):
                                failed_details.append({
                                    'period': period,
                                    'name': r.get('name', ''),
                                    'symbol': r.get('symbol', ''),
                                    'signal_desc': '买入信号' if r.get('signal') in ['buy', 'strong_buy'] else '回避信号',
                                    'change': 'N/A',
                                    'reason': r.get('reason', '')
                                })
                            elif not r.get('match'):
                                signal_desc = '买入信号' if r.get('signal') in ['buy', 'strong_buy'] else '回避信号'
                                change_str = f"{r.get('price_change', 0):+.1f}%" if r.get('price_change') is not None else "N/A"
                                failed_details.append({
                                    'period': period,
                                    'name': r.get('name', ''),
                                    'symbol': r.get('symbol', ''),
                                    'signal_desc': signal_desc,
                                    'change': change_str,
                                    'reason': r.get('reason', '')
                                })
                
                if failed_details:
                    lines.append("\n**❌ 验证失败详情**:\n")
                    lines.append("| 周期 | ETF名称 | 代码 | 信号类型 | 实际涨跌 | 失败原因 |")
                    lines.append("|------|---------|------|----------|----------|----------|")
                    for detail in failed_details:
                        lines.append(f"| {detail['period']} | {detail['name']} | {detail['symbol']} | {detail['signal_desc']} | {detail['change']} | {detail['reason']} |")
            
            lines.append("\n</details>\n")
        
        # 免责声明
        lines.append("\n---\n")
        lines.append("*⚠️ 免责声明：本报告仅供学习研究，不构成投资建议。投资有风险，入市需谨慎。*\n")
        
        return '\n'.join(lines)
    
    def _calculate_total_accuracy(self, all_results: List[Dict]) -> Dict:
        """计算总体准确率
        
        优化：排除跳过的验证，只统计有效验证
        """
        total_summary = {
            '1个月': {'correct': 0, 'total': 0, 'skipped': 0},
            '2个月': {'correct': 0, 'total': 0, 'skipped': 0},
            '3个月': {'correct': 0, 'total': 0, 'skipped': 0}
        }
        
        for result in all_results:
            verification = result.get('verification', {})
            for period_name in ['1个月', '2个月', '3个月']:
                results_list = verification.get(period_name, [])
                if results_list:
                    # 支持两种格式：布尔值列表或字典列表
                    if isinstance(results_list[0], dict):
                        # 区分有效验证和跳过的验证
                        valid_results = [r for r in results_list if not r.get('skipped', False)]
                        skipped_results = [r for r in results_list if r.get('skipped', False)]
                        correct = sum(1 for r in valid_results if r.get('match'))
                        total_summary[period_name]['correct'] += correct
                        total_summary[period_name]['total'] += len(valid_results)
                        total_summary[period_name]['skipped'] += len(skipped_results)
                    else:
                        correct = sum(1 for r in results_list if r)
                        total_summary[period_name]['correct'] += correct
                        total_summary[period_name]['total'] += len(results_list)
        
        return total_summary
