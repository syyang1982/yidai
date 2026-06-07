"""
意怠工程 — 终端数据可视化模块

Provides terminal-based dashboards and charts for portfolio analysis.
"""
from .dashboard import render_portfolio_dashboard, render_score_radar

__all__ = ["render_portfolio_dashboard", "render_score_radar"]
