"""
回测报告生成器

功能：
1. 生成详细的Markdown交易记录
2. 使用matplotlib生成资金曲线图表
3. 生成收益率分析图表
"""

import os
from datetime import datetime
from typing import Dict, List
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from backtest import BacktestEngine, Trade, TradeAction, DailySnapshot

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'STHeiti', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


class BacktestReportGenerator:
    """回测报告生成器"""
    
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.charts_dir = self.output_dir / "charts"
        self.charts_dir.mkdir(exist_ok=True)
    
    def generate_report(self, result: dict, filename: str = None) -> str:
        """
        生成完整的回测报告
        
        Args:
            result: 回测结果字典
            filename: 输出文件名（不含扩展名）
        
        Returns:
            报告文件路径
        """
        if not filename:
            filename = f"backtest_{result['start_date']}_{result['end_date']}"
        
        report_path = self.output_dir / f"{filename}.md"
        
        # 生成图表
        chart_paths = self._generate_all_charts(result, filename)
        
        content = []
        
        # 标题
        content.append(f"# ETF策略回测报告")
        content.append(f"\n> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append(f"\n---\n")
        
        # 回测概览
        content.append(self._generate_overview(result))
        
        # 收益统计
        content.append(self._generate_performance_stats(result))
        
        # 资金曲线图表（使用图片）
        content.append(self._generate_equity_section(result, chart_paths))
        
        # 收益率对比图表（使用图片）
        content.append(self._generate_return_section(chart_paths))
        
        # 持仓分布图表（使用图片）
        content.append(self._generate_position_section(chart_paths))
        
        # 交易记录
        content.append(self._generate_trade_log(result))
        
        # 每周持仓快照
        content.append(self._generate_weekly_snapshots(result))
        
        # 最终持仓
        content.append(self._generate_final_positions(result))
        
        # 写入文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"\n📊 回测报告已生成: {report_path}")
        print(f"📈 图表已保存至: {self.charts_dir}")
        
        return str(report_path)
    
    def _generate_all_charts(self, result: dict, filename: str) -> dict:
        """生成所有图表"""
        snapshots: List[DailySnapshot] = result.get('snapshots', [])
        
        if not snapshots:
            return {}
        
        # 准备数据
        dates = [datetime.strptime(s.date, '%Y-%m-%d') for s in snapshots]
        total_values = [s.total_value for s in snapshots]
        cumulative_returns = [s.cumulative_return for s in snapshots]
        benchmark_returns = [s.benchmark_return for s in snapshots]
        position_counts = [len(s.positions) for s in snapshots]
        cash_values = [s.cash for s in snapshots]
        
        chart_paths = {}
        
        # 1. 综合仪表板图
        chart_paths['dashboard'] = self._create_dashboard_chart(
            dates, total_values, cumulative_returns, benchmark_returns, 
            position_counts, cash_values, result, filename
        )
        
        # 2. 资金曲线图
        chart_paths['equity'] = self._create_equity_chart(
            dates, total_values, cash_values, result, filename
        )
        
        # 3. 收益率对比图
        chart_paths['returns'] = self._create_returns_chart(
            dates, cumulative_returns, benchmark_returns, filename
        )
        
        # 4. 持仓变化图
        chart_paths['positions'] = self._create_positions_chart(
            dates, position_counts, filename
        )
        
        # 5. 回撤曲线图
        chart_paths['drawdown'] = self._create_drawdown_chart(
            dates, total_values, result['initial_capital'], filename
        )
        
        return chart_paths
    
    def _create_dashboard_chart(self, dates, total_values, cumulative_returns, 
                                 benchmark_returns, position_counts, cash_values,
                                 result, filename) -> str:
        """创建综合仪表板图"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('ETF策略回测仪表板', fontsize=16, fontweight='bold')
        
        # 1. 资金曲线（左上）
        ax1 = axes[0, 0]
        ax1.fill_between(dates, total_values, alpha=0.3, color='blue')
        ax1.plot(dates, total_values, 'b-', linewidth=2, label='账户总值')
        ax1.axhline(y=result['initial_capital'], color='gray', linestyle='--', 
                   alpha=0.5, label='初始资金')
        ax1.set_title('账户资金曲线', fontsize=12)
        ax1.set_ylabel('金额 (元)')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=4))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        
        # 2. 收益率对比（右上）
        ax2 = axes[0, 1]
        ax2.plot(dates, cumulative_returns, 'b-', linewidth=2, label='策略收益率')
        ax2.plot(dates, benchmark_returns, 'r--', linewidth=2, label='沪深300基准')
        ax2.fill_between(dates, cumulative_returns, benchmark_returns, 
                        where=[c > b for c, b in zip(cumulative_returns, benchmark_returns)],
                        alpha=0.3, color='green', label='超额收益')
        ax2.fill_between(dates, cumulative_returns, benchmark_returns,
                        where=[c <= b for c, b in zip(cumulative_returns, benchmark_returns)],
                        alpha=0.3, color='red')
        ax2.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
        ax2.set_title('收益率对比', fontsize=12)
        ax2.set_ylabel('收益率 (%)')
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=4))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
        
        # 3. 持仓数量（左下）
        ax3 = axes[1, 0]
        colors = ['green' if p > 0 else 'gray' for p in position_counts]
        ax3.bar(dates, position_counts, color=colors, alpha=0.7, width=5)
        ax3.axhline(y=6, color='red', linestyle='--', alpha=0.5, label='最大持仓限制')
        ax3.set_title('持仓数量变化', fontsize=12)
        ax3.set_ylabel('持仓数')
        ax3.set_ylim(0, 7)
        ax3.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax3.xaxis.set_major_locator(mdates.WeekdayLocator(interval=4))
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
        
        # 4. 关键指标（右下）
        ax4 = axes[1, 1]
        ax4.axis('off')
        
        # 创建指标表格
        metrics = [
            ['指标', '数值'],
            ['初始资金', f"¥{result['initial_capital']:,.2f}"],
            ['最终资金', f"¥{result['final_value']:,.2f}"],
            ['总收益率', f"{result['total_return']:+.2f}%"],
            ['年化收益率', f"{result['annual_return']:+.2f}%"],
            ['基准收益率', f"{result['benchmark_return']:+.2f}%"],
            ['超额收益', f"{result['excess_return']:+.2f}%"],
            ['最大回撤', f"{result['max_drawdown']:.2f}%"],
            ['夏普比率', f"{result['sharpe_ratio']:.2f}"],
            ['胜率', f"{result['win_rate']:.1f}%"],
            ['总交易次数', f"{result['total_trades']}"],
        ]
        
        table = ax4.table(cellText=metrics[1:], colLabels=metrics[0],
                         loc='center', cellLoc='center',
                         colWidths=[0.4, 0.4])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)
        
        # 设置表头样式
        for i in range(2):
            table[(0, i)].set_facecolor('#4472C4')
            table[(0, i)].set_text_props(color='white', fontweight='bold')
        
        # 设置收益相关行的颜色
        for i in range(1, len(metrics)):
            if '收益' in metrics[i][0] or '超额' in metrics[i][0]:
                value = float(metrics[i][1].replace('¥', '').replace(',', '').replace('%', '').replace('+', ''))
                if value > 0:
                    table[(i, 1)].set_text_props(color='green')
                elif value < 0:
                    table[(i, 1)].set_text_props(color='red')
        
        ax4.set_title('关键绩效指标', fontsize=12, pad=20)
        
        plt.tight_layout()
        
        chart_path = self.charts_dir / f"{filename}_dashboard.png"
        plt.savefig(chart_path, dpi=150, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        plt.close()
        
        return str(chart_path)
    
    def _create_equity_chart(self, dates, total_values, cash_values, result, filename) -> str:
        """创建资金曲线图"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        position_values = [t - c for t, c in zip(total_values, cash_values)]
        
        # 堆叠面积图
        ax.stackplot(dates, cash_values, position_values, 
                    labels=['现金', '持仓市值'],
                    colors=['#90EE90', '#4169E1'], alpha=0.7)
        
        # 总资金线
        ax.plot(dates, total_values, 'k-', linewidth=2, label='账户总值')
        
        # 初始资金线
        ax.axhline(y=result['initial_capital'], color='red', linestyle='--', 
                  alpha=0.7, label='初始资金')
        
        ax.set_title('账户资金变化', fontsize=14, fontweight='bold')
        ax.set_xlabel('日期')
        ax.set_ylabel('金额 (元)')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=4))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        
        chart_path = self.charts_dir / f"{filename}_equity.png"
        plt.savefig(chart_path, dpi=150, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close()
        
        return str(chart_path)
    
    def _create_returns_chart(self, dates, cumulative_returns, benchmark_returns, filename) -> str:
        """创建收益率对比图"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        ax.plot(dates, cumulative_returns, 'b-', linewidth=2.5, label='策略收益率', marker='o', markersize=3)
        ax.plot(dates, benchmark_returns, 'r--', linewidth=2, label='沪深300基准', marker='s', markersize=3)
        
        # 填充超额收益区域
        ax.fill_between(dates, cumulative_returns, benchmark_returns,
                       where=[c > b for c, b in zip(cumulative_returns, benchmark_returns)],
                       alpha=0.3, color='green', label='正超额收益')
        ax.fill_between(dates, cumulative_returns, benchmark_returns,
                       where=[c <= b for c, b in zip(cumulative_returns, benchmark_returns)],
                       alpha=0.3, color='red', label='负超额收益')
        
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
        
        ax.set_title('策略收益率 vs 基准收益率', fontsize=14, fontweight='bold')
        ax.set_xlabel('日期')
        ax.set_ylabel('累计收益率 (%)')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=4))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        
        chart_path = self.charts_dir / f"{filename}_returns.png"
        plt.savefig(chart_path, dpi=150, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close()
        
        return str(chart_path)
    
    def _create_positions_chart(self, dates, position_counts, filename) -> str:
        """创建持仓变化图"""
        fig, ax = plt.subplots(figsize=(12, 5))
        
        colors = ['#2E8B57' if p > 0 else '#D3D3D3' for p in position_counts]
        bars = ax.bar(dates, position_counts, color=colors, alpha=0.8, width=5)
        
        # 最大持仓限制线
        ax.axhline(y=6, color='red', linestyle='--', linewidth=2, 
                  alpha=0.7, label='最大持仓限制(6)')
        
        # 添加数值标签
        for bar, count in zip(bars, position_counts):
            if count > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                       str(count), ha='center', va='bottom', fontsize=8)
        
        ax.set_title('持仓数量变化', fontsize=14, fontweight='bold')
        ax.set_xlabel('日期')
        ax.set_ylabel('持仓数量')
        ax.set_ylim(0, 7)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3, axis='y')
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=4))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        
        chart_path = self.charts_dir / f"{filename}_positions.png"
        plt.savefig(chart_path, dpi=150, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close()
        
        return str(chart_path)
    
    def _create_drawdown_chart(self, dates, total_values, initial_capital, filename) -> str:
        """创建回撤曲线图"""
        fig, ax = plt.subplots(figsize=(12, 5))
        
        # 计算回撤
        peak = initial_capital
        drawdowns = []
        for value in total_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100
            drawdowns.append(-drawdown)  # 负值表示回撤
        
        ax.fill_between(dates, drawdowns, 0, color='red', alpha=0.3)
        ax.plot(dates, drawdowns, 'r-', linewidth=1.5)
        
        # 标记最大回撤点
        min_dd = min(drawdowns)
        min_idx = drawdowns.index(min_dd)
        ax.scatter([dates[min_idx]], [min_dd], color='darkred', s=100, zorder=5)
        ax.annotate(f'最大回撤: {-min_dd:.2f}%', 
                   xy=(dates[min_idx], min_dd),
                   xytext=(10, -20), textcoords='offset points',
                   fontsize=10, color='darkred',
                   arrowprops=dict(arrowstyle='->', color='darkred'))
        
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
        
        ax.set_title('回撤曲线', fontsize=14, fontweight='bold')
        ax.set_xlabel('日期')
        ax.set_ylabel('回撤 (%)')
        ax.grid(True, alpha=0.3)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=4))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        
        chart_path = self.charts_dir / f"{filename}_drawdown.png"
        plt.savefig(chart_path, dpi=150, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close()
        
        return str(chart_path)
    
    def _generate_overview(self, result: dict) -> str:
        """生成回测概览"""
        lines = [
            "## 📋 回测概览",
            "",
            "| 项目 | 数值 |",
            "|------|------|",
            f"| 回测期间 | {result['start_date']} 至 {result['end_date']} |",
            f"| 初始资金 | ¥{result['initial_capital']:,.2f} |",
            f"| 最终资金 | ¥{result['final_value']:,.2f} |",
            f"| 总收益率 | {result['total_return']:+.2f}% |",
            f"| 年化收益率 | {result['annual_return']:+.2f}% |",
            f"| 基准收益率(沪深300) | {result['benchmark_return']:+.2f}% |",
            f"| 超额收益 | {result['excess_return']:+.2f}% |",
            "",
        ]
        return '\n'.join(lines)
    
    def _generate_performance_stats(self, result: dict) -> str:
        """生成收益统计"""
        lines = [
            "## 📈 收益统计",
            "",
            "### 风险指标",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 最大回撤 | {result['max_drawdown']:.2f}% |",
            f"| 夏普比率 | {result['sharpe_ratio']:.2f} |",
            "",
            "### 交易统计",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 总交易次数 | {result['total_trades']} |",
            f"| 买入次数 | {result['buy_trades']} |",
            f"| 卖出次数 | {result['sell_trades']} |",
            f"| 盈利交易 | {result['winning_trades']} |",
            f"| 亏损交易 | {result['losing_trades']} |",
            f"| 胜率 | {result['win_rate']:.1f}% |",
            f"| 平均盈利 | ¥{result['avg_profit']:.2f} |",
            f"| 平均亏损 | ¥{result['avg_loss']:.2f} |",
            "",
        ]
        return '\n'.join(lines)
    
    def _generate_equity_section(self, result: dict, chart_paths: dict) -> str:
        """生成资金曲线部分"""
        snapshots: List[DailySnapshot] = result.get('snapshots', [])
        
        lines = [
            "## 💰 资金曲线",
            "",
        ]
        
        # 添加仪表板图
        if 'dashboard' in chart_paths:
            lines.append(f"### 综合仪表板")
            lines.append(f"![综合仪表板](charts/{Path(chart_paths['dashboard']).name})")
            lines.append("")
        
        # 添加资金曲线图
        if 'equity' in chart_paths:
            lines.append(f"### 资金变化详图")
            lines.append(f"![资金曲线](charts/{Path(chart_paths['equity']).name})")
            lines.append("")
        
        # 添加回撤图
        if 'drawdown' in chart_paths:
            lines.append(f"### 回撤曲线")
            lines.append(f"![回撤曲线](charts/{Path(chart_paths['drawdown']).name})")
            lines.append("")
        
        # 资金明细表
        if snapshots:
            lines.extend([
                "### 资金明细表",
                "",
                "| 日期 | 账户总值 | 现金 | 持仓市值 | 累计收益率 | 基准收益率 |",
                "|------|----------|------|----------|------------|------------|",
            ])
            
            for s in snapshots:
                position_value = s.total_value - s.cash
                lines.append(
                    f"| {s.date} | ¥{s.total_value:,.2f} | ¥{s.cash:,.2f} | "
                    f"¥{position_value:,.2f} | {s.cumulative_return:+.2f}% | {s.benchmark_return:+.2f}% |"
                )
            
            lines.append("")
        
        return '\n'.join(lines)
    
    def _generate_return_section(self, chart_paths: dict) -> str:
        """生成收益率对比部分"""
        lines = [
            "## 📊 收益率对比",
            "",
        ]
        
        if 'returns' in chart_paths:
            lines.append(f"![收益率对比](charts/{Path(chart_paths['returns']).name})")
            lines.append("")
            lines.append("> 📌 蓝线: 策略收益率 | 红线: 沪深300基准收益率 | 绿色区域: 正超额收益 | 红色区域: 负超额收益")
            lines.append("")
        
        return '\n'.join(lines)
    
    def _generate_position_section(self, chart_paths: dict) -> str:
        """生成持仓变化部分"""
        lines = [
            "## 📦 持仓变化",
            "",
        ]
        
        if 'positions' in chart_paths:
            lines.append(f"![持仓变化](charts/{Path(chart_paths['positions']).name})")
            lines.append("")
        
        return '\n'.join(lines)
    
    def _generate_trade_log(self, result: dict) -> str:
        """生成交易记录"""
        trades: List[Trade] = result.get('trades', [])
        
        if not trades:
            return "## 📝 交易记录\n\n无交易记录\n"
        
        lines = [
            "## 📝 交易记录",
            "",
            "| 日期 | 操作 | ETF名称 | 代码 | 价格 | 份额 | 金额 | 盈亏 | 盈亏率 | 原因 |",
            "|------|------|---------|------|------|------|------|------|--------|------|",
        ]
        
        for trade in trades:
            action_emoji = "🟢" if trade.action == TradeAction.BUY else "🔴"
            action_text = trade.action.value
            
            if trade.action == TradeAction.SELL:
                pnl_str = f"¥{trade.profit_loss:+.2f}"
                pnl_pct_str = f"{trade.profit_loss_pct:+.2f}%"
            else:
                pnl_str = "-"
                pnl_pct_str = "-"
            
            # 截断原因文本
            reason_text = trade.reason[:30] + "..." if len(trade.reason) > 30 else trade.reason
            
            lines.append(
                f"| {trade.date} | {action_emoji}{action_text} | {trade.name} | {trade.symbol} | "
                f"¥{trade.price:.3f} | {trade.shares:.2f} | ¥{trade.amount:.2f} | "
                f"{pnl_str} | {pnl_pct_str} | {reason_text} |"
            )
        
        lines.append("")
        
        # 添加交易汇总
        buy_trades = [t for t in trades if t.action == TradeAction.BUY]
        sell_trades = [t for t in trades if t.action == TradeAction.SELL]
        
        total_buy_amount = sum(t.amount for t in buy_trades)
        total_sell_amount = sum(t.amount for t in sell_trades)
        total_profit = sum(t.profit_loss for t in sell_trades)
        
        lines.extend([
            "### 交易汇总",
            "",
            f"- 总买入金额: ¥{total_buy_amount:,.2f}",
            f"- 总卖出金额: ¥{total_sell_amount:,.2f}",
            f"- 已实现盈亏: ¥{total_profit:+,.2f}",
            "",
        ])
        
        return '\n'.join(lines)
    
    def _generate_weekly_snapshots(self, result: dict) -> str:
        """生成每周持仓快照"""
        snapshots: List[DailySnapshot] = result.get('snapshots', [])
        
        if not snapshots:
            return ""
        
        lines = [
            "## 📅 每周持仓快照",
            "",
        ]
        
        for snapshot in snapshots:
            lines.append(f"### {snapshot.date}")
            lines.append("")
            lines.append(f"- 💰 账户总值: ¥{snapshot.total_value:,.2f}")
            lines.append(f"- 💵 现金: ¥{snapshot.cash:,.2f}")
            lines.append(f"- 📈 累计收益: {snapshot.cumulative_return:+.2f}%")
            lines.append(f"- 📊 基准收益: {snapshot.benchmark_return:+.2f}%")
            lines.append("")
            
            if snapshot.positions:
                lines.append("| ETF | 代码 | 份额 | 成本价 | 现价 | 市值 | 盈亏 | 盈亏率 |")
                lines.append("|-----|------|------|--------|------|------|------|--------|")
                
                for symbol, pos in snapshot.positions.items():
                    pnl = pos.profit_loss
                    pnl_pct = pos.profit_loss_pct
                    lines.append(
                        f"| {pos.name} | {pos.symbol} | {pos.shares:.2f} | "
                        f"¥{pos.cost_price:.3f} | ¥{pos.current_price:.3f} | "
                        f"¥{pos.market_value:.2f} | ¥{pnl:+.2f} | {pnl_pct:+.2f}% |"
                    )
                lines.append("")
            else:
                lines.append("> 空仓")
                lines.append("")
        
        return '\n'.join(lines)
    
    def _generate_final_positions(self, result: dict) -> str:
        """生成最终持仓"""
        positions = result.get('final_positions', {})
        
        lines = [
            "## 🏁 最终持仓",
            "",
        ]
        
        if not positions:
            lines.append("> 空仓结束")
            lines.append("")
            return '\n'.join(lines)
        
        lines.extend([
            "| ETF | 代码 | 份额 | 成本价 | 现价 | 市值 | 浮动盈亏 | 盈亏率 |",
            "|-----|------|------|--------|------|------|----------|--------|",
        ])
        
        total_value = 0
        total_pnl = 0
        
        for symbol, pos in positions.items():
            pnl = pos.profit_loss
            pnl_pct = pos.profit_loss_pct
            total_value += pos.market_value
            total_pnl += pnl
            
            lines.append(
                f"| {pos.name} | {pos.symbol} | {pos.shares:.2f} | "
                f"¥{pos.cost_price:.3f} | ¥{pos.current_price:.3f} | "
                f"¥{pos.market_value:.2f} | ¥{pnl:+.2f} | {pnl_pct:+.2f}% |"
            )
        
        lines.extend([
            "",
            f"**持仓总市值**: ¥{total_value:,.2f}",
            f"**浮动盈亏合计**: ¥{total_pnl:+,.2f}",
            "",
        ])
        
        return '\n'.join(lines)


def generate_backtest_report(result: dict, filename: str = None) -> str:
    """
    生成回测报告的便捷函数
    
    Args:
        result: 回测结果
        filename: 文件名
    
    Returns:
        报告路径
    """
    generator = BacktestReportGenerator()
    return generator.generate_report(result, filename)
