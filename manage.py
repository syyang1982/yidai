#!/usr/bin/env python3
"""
意怠工程 — 管理工具 (TUI)

用法:
    python manage.py dashboard              持仓+信号统一面板
    python manage.py signals                更新所有公司信号
    python manage.py signal 01810.HK        查看公司信号历史
    python manage.py signal --all           查看所有公司最新信号
    python manage.py report                 生成增强版周报
    python manage.py analyze 01810.HK       分析单个公司
    python manage.py analyze --all          批量分析所有持仓
    python manage.py backtest 01810.HK      回测单个公司
    python manage.py kb                     知识库概览
    python manage.py kb 01810.HK            查看公司档案
    python manage.py list                   列出所有公司评分
    python manage.py decision list           列出所有决策
    python manage.py decision add 01810.HK   记录投资决策
    python manage.py decision show <id>      查看决策详情
    python manage.py decision review         查看待复盘决策
    python manage.py decision stats          决策统计汇总
    python manage.py test                   运行测试
    python manage.py events                 显示未来7天事件
    python manage.py events --days 30       显示未来30天事件
    python manage.py events --scan          扫描突发新闻
    python manage.py events --refresh       刷新预知事件日历
    python manage.py events --calendar      显示事件日历文件
    python manage.py events --ticker 1810.HK  按股票过滤事件

示例:
    python manage.py dashboard
    python manage.py signal 小米集团
    python manage.py signal --all
    python manage.py analyze 9988.HK
    python manage.py analyze LX --thesis "低估+高股息"
    python manage.py signals
    python manage.py report
"""

import sys
import os
import argparse

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def cmd_dashboard(args):
    """持仓+信号统一面板（增强版）。"""
    enhanced = getattr(args, 'enhanced', False)
    if enhanced:
        from scripts.dashboard import main_enhanced
        main_enhanced()
    else:
        from scripts.dashboard import main
        main()


def cmd_signals(args):
    """更新所有公司信号。"""
    from scripts.record_all_signals import main
    main()


def cmd_report(args):
    """生成报告 — 个股深度报告（指定ticker）或增强版周报（不指定）。"""
    db_path = os.path.join(PROJECT_ROOT, "db", "yidai.duckdb")
    kb_dir = os.path.join(PROJECT_ROOT, "knowledge")
    signal_db = os.path.join(PROJECT_ROOT, "db", "signals.duckdb")
    output_dir = os.path.join(PROJECT_ROOT, "reports")

    ticker = getattr(args, "ticker", None)
    if ticker:
        from src.report.company_report import generate_company_report
        path = generate_company_report(ticker, db_path, kb_dir, signal_db, output_dir)
        print(f"\n✅ 个股深度报告已生成: {path}")
    else:
        from src.report.weekly_v2 import generate_report_v2
        path = generate_report_v2(db_path, kb_dir, signal_db, output_dir)
        print(f"\n✅ 周报已生成: {path}")


def cmd_analyze(args):
    """分析公司。"""
    from src.data.fetcher import EastmoneyFetcher
    from src.data.store import YidaiStore
    from src.analysis import profitability, health, cashflow, valuation, growth
    from src.data.models import _compute_grade, _compute_signal
    from src.knowledge.base import KnowledgeBase

    DB_PATH = os.path.join(PROJECT_ROOT, "db", "yidai.duckdb")
    fetcher = EastmoneyFetcher()
    kb = KnowledgeBase()

    if args.all:
        # Batch analyze all companies in knowledge base
        companies = kb.list_companies()
        if not companies:
            print("❌ 知识库为空，请先添加公司")
            return

        print(f"批量分析 {len(companies)} 家公司...\n")
        for c in companies:
            ticker = c["ticker"]
            # Try to find the eastmoney code
            _analyze_one(fetcher, kb, ticker, ticker, c.get("name", ticker),
                        "HK" if ".HK" in ticker else ("SH" if ".SH" in ticker else ("SZ" if ".SZ" in ticker else "US")),
                        "", args.thesis or "")
        return

    ticker = args.ticker
    if not ticker:
        print("❌ 请指定ticker，例如: python manage.py analyze 01810.HK")
        return

    # Auto-detect display name
    display = ticker
    name = ticker
    market = "HK" if ".HK" in ticker else ("SH" if ".SH" in ticker else ("SZ" if ".SZ" in ticker else "US"))
    _analyze_one(fetcher, kb, ticker, display, name, market, "", args.thesis or "")


def _analyze_one(fetcher, kb, ticker, display, name, market, sector, thesis):
    """分析单个公司。"""
    from src.analysis import profitability, health, cashflow, valuation, growth, dividend_quality
    from src.analysis.insider_activity import check_insider_activity, format_insider_warnings
    from src.analysis.ownership_structure import analyze_controller_status, format_ownership_structure
    from src.analysis.master_integration import integrated_assessment, format_integrated_assessment
    from src.data.models import _compute_grade, _compute_signal
    from src.data.store import YidaiStore

    DB_PATH = os.path.join(PROJECT_ROOT, "db", "yidai.duckdb")

    print(f"\n{'='*55}")
    print(f"  {name} ({display})")
    print(f"{'='*55}")

    # Fetch data
    east_ticker = ticker.replace(".HK", "").replace(".SZ", "").replace(".SH", "")
    if market == "US":
        east_ticker = ticker  # US tickers keep their format

    all_fin = fetcher.fetch_financials(east_ticker, periods=20)

    # 智能检测财年结束月：统计所有期间中出现最多的月份
    from collections import Counter
    month_counts = Counter()
    for f in all_fin:
        p = f.get("period", "")
        if len(p) >= 7:
            month_counts[p[5:7]] += 1
    # 取出现频率最高的月份作为财年结束月
    fy_month = month_counts.most_common(1)[0][0] if month_counts else "12"
    annual = sorted([f for f in all_fin if f.get("period", "")[5:7] == fy_month],
                    key=lambda x: x["period"])
    price = fetcher.fetch_price(east_ticker)

    if len(annual) < 2:
        print(f"  ❌ 数据不足（{len(annual)}期）")
        return

    latest = annual[-1]
    prev = annual[-2]

    # Score
    revenue = latest.get("revenue", 0) or 0
    denom = revenue if revenue else 1
    prev_rev = prev.get("revenue", 0) or 0
    rev_growth = (revenue - prev_rev) / prev_rev if prev_rev > 0 else 0

    ta = latest.get("total_assets", 0) or 0
    tl = latest.get("total_liabilities", 0) or 0

    prof = profitability.score({
        "revenue_growth": rev_growth,
        "gross_margin": (latest.get("gross_profit", 0) or 0) / denom,
        "net_margin": (latest.get("net_income", 0) or 0) / denom,
        "roe": (latest.get("net_income", 0) or 0) / (latest.get("total_equity", 0) or 1),
    })
    h_data = {"debt_ratio": tl / ta if ta > 0 else 0}
    h = health.score(h_data)

    ocf = latest.get("operating_cash_flow", 0) or 0
    ni = latest.get("net_income", 0) or 1
    cf = cashflow.score({
        "operating_cash_flow": ocf,
        "ocf_to_ni_ratio": ocf / ni if ni else 0,
        "free_cash_flow": latest.get("free_cash_flow", 0) or 0,
    })

    pe = price.get("pe_ratio")

    # Fetch peer PE data for industry comparison
    peer_data = None
    try:
        peer_data = fetcher.fetch_peer_pe(ticker)
    except Exception:
        pass

    val_input = {
        "pe_ratio": pe,
        "pe_history_percentile": None,
        "revenue_growth_rate": rev_growth * 100,
    }
    if peer_data:
        val_input["peer_median_pe"] = peer_data["peer_median_pe"]
    v = valuation.score(val_input)

    g = growth.score({
        "revenue_growth_rates": [rev_growth],
        "growth_drivers": ["市场份额提升", "行业增长"],
    })

    # Dividend quality
    try:
        # 从财务数据获取DPS（每股股息），而非从price端获取
        dps_latest = latest.get("dividend_per_share") or 0
        close_price = price.get("close_price", 0) if price else 0
        eps_val = latest.get("eps") or 0

        # 从历年年报计算DPS历史（用于增长趋势）
        historical_dps = []
        for f in annual:
            d = f.get("dividend_per_share") or 0
            historical_dps.append(d)

        d_score = dividend_quality.compute_dividend_metrics(
            dividend_per_share=dps_latest,
            stock_price=close_price,
            net_income_per_share=eps_val,
            historical_dps=historical_dps if len(historical_dps) >= 2 else None,
        )
        d_score = dividend_quality.score(d_score)
    except Exception:
        d_score = {"score": 0}

    # Insider activity check (Check 6 — advisory only, does NOT affect score)
    insider_events = []
    insider_result = {"has_warning": False, "severity": "none", "warnings": [], "details": []}
    try:
        insider_events = fetcher.fetch_insider_activity(ticker, lookback_days=365)
        insider_result = check_insider_activity(insider_events)
    except Exception as e:
        print(f"  ⚠️ 内部人数据获取失败: {e}")

    # Ownership structure check (advisory — 无实际控制人 / 门口的野蛮人)
    shareholders = []
    ownership_result = {"category": "unknown", "opportunity": "", "warnings": []}
    try:
        shareholders = fetcher.fetch_top_shareholders(ticker)
        ownership_result = analyze_controller_status(shareholders)
    except Exception as e:
        print(f"  ⚠️ 股东数据获取失败: {e}")

    # 读取KB中已有的定性评分（人工设置），不存在则默认3
    existing_scores = {}
    try:
        existing_profile = kb.get_company_profile(display)
        existing_scores = existing_profile.get("scores", {})
    except (FileNotFoundError, Exception):
        pass

    def _get_qual(dim_cn, default=3):
        val = existing_scores.get(dim_cn)
        if val is not None:
            if isinstance(val, dict):
                return val.get("score", default)
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return default

    scores = {
        "profitability": prof["score"], "health": h["score"],
        "cashflow": cf["score"], "valuation": v["score"],
        "growth": g["score"], "dividend": d_score["score"],
        "ownership": _get_qual("股东", 3),
        "strategy": _get_qual("战略", 3),
    }
    total = sum(scores.values())
    grade = _compute_grade(total)
    sig = _compute_signal(total, *scores.values())

    # Print
    dim_cn = {"profitability": "盈利能力", "health": "财务健康", "cashflow": "现金流",
              "valuation": "估值", "growth": "增长质量", "dividend": "分红质量",
              "ownership": "股权结构", "strategy": "公司战略"}
    print(f"  年报: {latest['period']}")
    print(f"  营收: {revenue/1e8:.2f}亿  净利: {ni/1e8:.2f}亿  经营现金流: {ocf/1e8:.2f}亿")
    ccy_map = {"HK": "HKD", "US": "USD", "SZ": "CNY", "SH": "CNY"}
    ccy = ccy_map.get(market, "")
    close = price.get("close_price", 0) if price else 0
    if pe:
        print(f"  价格: {close:.2f} {ccy}  PE: {pe:.2f}")
    if peer_data:
        peer_names = {"battery": "动力电池", "auto_parts": "汽车零部件",
                      "lidar": "激光雷达", "robot_parts": "机器人零部件",
                      "internet": "互联网"}
        group_cn = peer_names.get(peer_data["peer_group"], peer_data["peer_group"])
        median = peer_data["peer_median_pe"]
        premium = (pe - median) / median * 100 if pe and median else 0
        peer_str = ", ".join(f"{c}:{p:.1f}" for c, p in peer_data["peer_pes"])
        print(f"  同行({group_cn}): 中位PE {median:.1f}x  溢价 {premium:+.0f}%  [{peer_str}]")

    for dim, cn in dim_cn.items():
        s = scores[dim]
        bar = "█" * s + "░" * (5 - s)
        print(f"  {cn:　<6} [{bar}] {s}/5")

    emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(sig, "❓")
    print(f"\n  总分: {total}/35  等级: {grade}  信号: {emoji} {sig}")

    gross_margin = (latest.get("gross_profit", 0) or 0) / denom
    net_margin = (ni or 0) / denom
    roe = (ni or 0) / (latest.get("total_equity", 0) or 1)
    debt_ratio = tl / (ta or 1)
    print(f"  毛利率: {gross_margin*100:.2f}%  净利率: {net_margin*100:.2f}%  ROE: {roe*100:.2f}%  负债率: {debt_ratio*100:.2f}%")

    # Display insider activity warnings (Check 6)
    insider_formatted = format_insider_warnings(insider_result)
    if insider_formatted:
        print(insider_formatted)

    # Display ownership structure analysis (advisory)
    ownership_formatted = format_ownership_structure(ownership_result)
    if ownership_formatted:
        print(ownership_formatted)

    # Integrated multi-master assessment
    yidai_dim_scores = {
        "profitability": scores['profitability'], "health": scores['health'],
        "cashflow": scores['cashflow'], "valuation": scores['valuation'],
        "growth": scores['growth'], "dividend": scores.get('dividend', d_score.get('score', 0)),
        "ownership": scores['ownership'], "strategy": scores['strategy'],
    }
    master_result = integrated_assessment(
        yidai_scores=yidai_dim_scores,
        financial_data={
            "revenue_growth_rate": rev_growth * 100,
            "ebit": latest.get("operating_income") or latest.get("ebitda"),
            "invested_capital": ta - (latest.get("current_liabilities") or 0) - (latest.get("current_assets", 0) - (latest.get("inventory") or 0)),
        },
        price_data={
            "pe_ratio": pe,
            "pb_ratio": price.get("pb_ratio") if price else None,
            "ev": price.get("market_cap", 0) if price else 0,
        },
        qualitative={"circle_of_competence": True},  # default: assume in circle
    )
    master_formatted = format_integrated_assessment(master_result)
    print(master_formatted)

    # Save to knowledge base
    if not thesis:
        thesis = "待填写"
    kb.create_company_profile(ticker=display, name=name, market=market,
                              sector=sector or "", thesis=thesis)
    kb.update_company_scores(display, {
        '盈利': scores['profitability'], '健康': scores['health'],
        '现金流': scores['cashflow'], '估值': scores['valuation'],
        '成长': scores['growth'], '股东': scores['ownership'], '战略': scores['strategy'],
    })
    kb.update_company_financials(display, {
        '营收': f'{revenue/1e8:.2f}亿', '净利': f'{ni/1e8:.2f}亿',
        'ROE': f'{roe*100:.2f}%', '毛利率': f'{gross_margin*100:.2f}%',
        '净利率': f'{net_margin*100:.2f}%', '负债率': f'{debt_ratio*100:.2f}%',
        'PE': f'{pe:.2f}' if pe else 'N/A',
    })

    # Save to DuckDB
    store = YidaiStore(DB_PATH)
    store.upsert_company({"ticker": display, "name": name, "market": market,
                          "currency": "HKD" if market == "HK" else ("USD" if market == "US" else "CNY"),
                          "sector": sector or ""})
    for f in annual:
        f["ticker"] = display
        store.upsert_financial(f)
    price["ticker"] = display
    store.upsert_price(price)
    store.close()

    # Record signal in signal tracker
    try:
        from src.strategy.signal_tracker import SignalTracker
        import json
        SIGNALS_DB = os.path.join(PROJECT_ROOT, "db", "signals.duckdb")
        st = SignalTracker(SIGNALS_DB)
        signal_id = st.record_signal(
            ticker=display,
            company_name=name,
            signal_date=__import__("datetime").date.today().isoformat(),
            signal_type=sig,
            company_state={
                "price": price.get("close_price", 0) if price else 0,
                "pe": pe,
                "revenue": revenue,
                "net_income": ni,
                "gross_margin": gross_margin,
                "roe": roe,
                "debt_ratio": debt_ratio,
                "insider_activity": {
                    "has_warning": insider_result.get("has_warning", False),
                    "severity": insider_result.get("severity", "none"),
                    "event_count": len(insider_events),
                },
                "ownership_structure": {
                    "category": ownership_result.get("category", "unknown"),
                    "has_controller": ownership_result.get("has_controller"),
                    "controller_name": ownership_result.get("controller_name"),
                    "controller_pct": ownership_result.get("controller_pct"),
                    "top_shareholders": [
                        {"name": n, "pct": p}
                        for n, p in ownership_result.get("top_shareholders", [])
                    ],
                },
            },
            dimension_scores=scores,
            total_score=total,
            grade=grade,
            analysis_details={},
        )
        st.record_action(signal_id, "系统记录")
        st.conn.close()
        print(f"  ✅ 已记录信号到信号追踪器")
    except Exception as e:
        print(f"  ⚠️ 信号记录失败: {e}")

    print(f"\n  ✅ 已存入知识库 + DuckDB")


def cmd_backtest(args):
    """回测分析。"""
    from src.data.fetcher import EastmoneyFetcher
    from src.strategy.backtest_v2 import BacktestEngineV2
    import requests

    ticker = args.ticker
    if not ticker:
        print("❌ 请指定ticker，例如: python manage.py backtest 01810.HK")
        return

    print(f"回测 {ticker}...")
    fetcher = EastmoneyFetcher()
    east_ticker = ticker.replace(".HK", "").replace(".SZ", "")

    # Fetch financials
    all_fin = fetcher.fetch_financials(east_ticker, periods=50)
    annual = sorted([f for f in all_fin if f["period"].endswith("12-31")],
                    key=lambda x: x["period"])
    all_periods = sorted(all_fin, key=lambda x: x["period"])

    # Fetch prices (monthly)
    prices = []
    try:
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        for year in range(2015, 2027):
            resp = requests.get(url, params={"param": f"hk{east_ticker},month,{year}-01-01,{year}-12-31,240,qfq"},
                              headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            data = resp.json()
            klines = data.get("data", {}).get(f"hk{east_ticker}", {}).get("month", [])
            if not klines:
                klines = data.get("data", {}).get(f"hk{east_ticker}", {}).get("qfqmonth", [])
            for k in klines:
                if len(k) >= 2:
                    prices.append({"date": k[0], "close_price": float(k[2]) if len(k) > 2 else float(k[1])})
    except Exception:
        pass
    prices.sort(key=lambda p: p["date"])

    if not prices:
        print("❌ 无法获取价格数据")
        return

    # Run v2 backtest
    engine = BacktestEngineV2(initial_capital=1_000_000)
    result = engine.run(east_ticker, all_periods, prices)

    # Print results
    print(f"\n  信号 ({len(result['signals'])} 个):")
    for item in result["signals"][-10:]:  # Last 10
        period, sig, sc, total, grade = item[:5]
        trend = item[5] if len(item) > 5 else ""
        emoji = {"BUY": "🟢", "HOLD": "🟡", "REDUCE": "🔴"}.get(sig, "❓")
        print(f"    {period}: {emoji} {sig:6} {grade} ({total}/35) {trend}")

    print(f"\n  交易 ({len(result['trades'])} 笔):")
    for t in result["trades"]:
        emoji = "🟢" if t["action"] == "BUY" else "🔴"
        print(f"    {emoji} {t['date']} {t['action']:4} {t['shares']:>6}股 @ {t['price']:.2f}")

    m = result["metrics"]
    print(f"\n  指标:")
    print(f"    总收益: {m['total_return']*100:.1f}%  年化: {m['cagr']*100:.1f}%  回撤: {m['max_drawdown']*100:.1f}%")
    print(f"    夏普: {m['sharpe_ratio']:.2f}  基准: {m['benchmark_return']*100:.1f}%  交易: {m['num_trades']}笔")


def cmd_kb(args):
    """知识库操作。"""
    from src.knowledge.base import KnowledgeBase

    kb = KnowledgeBase()

    if args.company:
        ticker = args.company
        try:
            profile = kb.get_company_profile(ticker)
        except FileNotFoundError:
            print(f"❌ 未找到 {ticker} 的档案")
            return

        print(f"\n{'='*55}")
        print(f"  {profile.get('name', ticker)} ({ticker})")
        print(f"{'='*55}")
        print(f"  市场: {profile.get('market', '?')}")
        print(f"  行业: {profile.get('sector', '?')}")
        print(f"  论点: {profile.get('thesis', '待填写')}")
        print(f"  评分: {profile.get('total', '?')}/35  等级: {profile.get('grade', '?')}  信号: {profile.get('signal', '?')}")

        if profile.get("risks"):
            print(f"\n  风险因素:")
            for r in profile["risks"]:
                print(f"    · {r}")

        if profile.get("financials"):
            print(f"\n  关键指标:")
            for k, v in profile["financials"].items():
                print(f"    {k}: {v}")
        return

    # List all companies
    companies = kb.list_companies()
    if not companies:
        print("知识库为空")
        return
    print()
    print("  ┌──────────────────────────────────────────────────────────────┐")
    print(f"  │                知识库 ({len(companies)} 家公司)                       │")
    print("  ├──────────────────────────────────────────────────────────────┤")
    print("  │  代码          名称       评分  等级  信号                 │")
    print("  ├──────────────────────────────────────────────────────────────┤")
    for c in sorted(companies, key=lambda x: x.get("total", 0), reverse=True):
        emoji = {"BUY": "🟢", "HOLD": "🟡", "REDUCE": "🔴"}.get(c.get("signal", ""), "⚪")
        total = c.get("total", "?")
        grade = c.get("grade", "?")
        sig = c.get("signal", "?")
        name = c.get("name", "")
        ticker = c["ticker"]
        print(f"  │  {ticker:<12} {name:<10} {total:>4}  {grade:>2}  {emoji} {sig:<6}           │")
    lessons = kb.get_lessons()
    principles = kb.get_principles()
    print("  ├──────────────────────────────────────────────────────────────┤")
    print(f"  │  教训: {len(lessons)}条   原则: {len(principles)}条                          │")
    print(f"  │  档案: knowledge/companies/*.md                             │")
    print("  └──────────────────────────────────────────────────────────────┘")

def cmd_list(args):
    """列出所有公司评分。"""
    cmd_kb(args)


def cmd_score(args):
    """设置定性维度评分（股东/战略）。"""
    from src.knowledge.base import KnowledgeBase

    kb = KnowledgeBase()

    if args.list:
        # 列出所有公司的定性评分
        print(f"\n  {'公司':<10} {'代码':<12} {'股东':>4} {'战略':>4}")
        print(f"  {'-'*36}")
        for c in kb.list_companies():
            ticker = c["ticker"]
            name = c.get("name", ticker)
            try:
                profile = kb.get_company_profile(ticker)
                scores = profile.get("scores", {})
                gu = scores.get("股东", "-")
                st = scores.get("战略", "-")
                if isinstance(gu, dict): gu = gu.get("score", "-")
                if isinstance(st, dict): st = st.get("score", "-")
            except:
                gu, st = "-", "-"
            print(f"  {name:<10} {ticker:<12} {gu:>4} {st:>4}")
        print(f"\n  用法: python manage.py score 01810.HK --ownership 4 --strategy 5")
        return

    if not args.ticker:
        print("用法:")
        print("  python manage.py score --list              列出所有公司定性评分")
        print("  python manage.py score 01810.HK --ownership 4 --strategy 5")
        return

    ticker = args.ticker
    try:
        profile = kb.get_company_profile(ticker)
    except FileNotFoundError:
        print(f"❌ 未找到 {ticker} 的档案")
        return

    name = profile.get("name", ticker)
    scores = profile.get("scores", {})
    current_gu = scores.get("股东", 3)
    current_st = scores.get("战略", 3)
    if isinstance(current_gu, dict): current_gu = current_gu.get("score", 3)
    if isinstance(current_st, dict): current_st = current_st.get("score", 3)

    updated = False
    if args.ownership is not None:
        if not 0 <= args.ownership <= 5:
            print("❌ 股东评分范围: 0-5")
            return
        kb.update_company_scores(ticker, {"股东": args.ownership})
        print(f"  {name} 股东: {current_gu} → {args.ownership}")
        updated = True

    if args.strategy is not None:
        if not 0 <= args.strategy <= 5:
            print("❌ 战略评分范围: 0-5")
            return
        kb.update_company_scores(ticker, {"战略": args.strategy})
        print(f"  {name} 战略: {current_st} → {args.strategy}")
        updated = True

    if not updated:
        print(f"  {name} 当前: 股东={current_gu} 战略={current_st}")
        print(f"  用法: python manage.py score {ticker} --ownership 4 --strategy 5")


def cmd_decision(args):
    """决策日志：记录、查看、复盘投资决策。"""
    from src.strategy.decision import DecisionLog, DecisionRecord
    from src.knowledge.base import KnowledgeBase

    DECISION_DB = os.path.join(PROJECT_ROOT, "db", "signals.duckdb")
    log = DecisionLog(DECISION_DB)

    # Resolve the second positional arg: ticker for add, decision_id for show/outcome
    action = args.decision_action
    if not action:
        # Show help
        print("  用法:")
        print("    python manage.py decision list                    列出所有决策")
        print("    python manage.py decision add 01810.HK \\")
        print("        --action BUY --price 30.5 --shares 1000 \\")
        print("        --reason \"评分A级\" --thesis \"长期看好\" \\")
        print("        --expect-6m 35 --expect-12m 40")
        print("    python manage.py decision show <id>               查看决策详情")
        print("    python manage.py decision review                  查看待复盘")
        print("    python manage.py decision outcome <id> \\")
        print("        --actual-price 35 --period 6m --notes \"符合预期\"")
        print("    python manage.py decision stats                   统计汇总")
        return

    ticker = getattr(args, 'ticker', None)
    decision_id = getattr(args, 'decision_id', None)

    # Resolve positional arg based on action
    pos = getattr(args, 'ticker_or_id', None)
    if pos:
        if action == "add":
            ticker = ticker or pos
        elif action in ("show", "outcome"):
            decision_id = decision_id or pos

    # ── list ──
    if action == "list":
        recs = log.list_decisions(ticker=ticker, limit=args.limit or 20)
        if not recs:
            print("  暂无决策记录")
            return
        print(f"\n  {'日期':<12} {'代码':<12} {'操作':<8} {'股数':>6} {'价格':>8} {'评分':>4} {'等级':>2} {'状态':<12}")
        print(f"  {'-'*70}")
        for r in recs:
            print(f"  {r.decision_date:<12} {r.ticker:<12} {r.action:<8} "
                  f"{r.shares:>6,} {r.price:>8.2f} {r.total_score:>4} {r.grade:>2} {r.status:<12}")
        stats = log.get_stats()
        print(f"\n  共 {stats['total_decisions']} 条决策, "
              f"已复盘 {stats['reviewed']}, 待复盘 {stats['pending_review']}")
        if stats['avg_return_pct'] != 0:
            print(f"  平均收益率: {stats['avg_return_pct']:+.1f}%")
        return

    # ── show ──
    if action == "show":
        if not decision_id:
            print("  用法: python manage.py decision show <decision_id>")
            return
        rec = log.get(decision_id)
        if not rec:
            print(f"  ❌ 未找到决策: {decision_id}")
            return
        print(log.to_markdown(rec))
        return

    # ── review ──
    if action == "review":
        pending = log.get_pending_reviews(period=args.period or "6m")
        if not pending:
            print("  暂无待复盘的决策")
            return
        period = args.period or "6m"
        print(f"\n  待复盘 ({period}):")
        for r in pending:
            print(f"  [{r.decision_id}] {r.decision_date} {r.company_name}({r.ticker}) "
                  f"{r.action} @ {r.price} → 预期: {r.expected_price_6m if period=='6m' else r.expected_price_12m}")
        print(f"\n  复盘: python manage.py decision outcome <id> --actual-price <price>")
        return

    # ── add ──
    if action == "add":
        if not ticker:
            print("  用法: python manage.py decision add <ticker> --action BUY --price 30.5 --shares 1000 --reason \"...\"")
            return

        # Try to get company name from knowledge base
        company_name = ticker
        market = "HK" if ".HK" in ticker else ("SH" if ".SH" in ticker else ("SZ" if ".SZ" in ticker else "US"))
        try:
            kb = KnowledgeBase()
            profile = kb.get_company_profile(ticker)
            company_name = profile.get("name", ticker)
        except Exception:
            pass

        # Try to get current scores
        scores = {}
        total_score = 0
        grade = ""
        signal = ""
        try:
            from src.data.fetcher import EastmoneyFetcher
            from src.data.models import _compute_grade, _compute_signal
            from src.analysis import profitability, health, cashflow, valuation, growth

            fetcher = EastmoneyFetcher()
            east_ticker = ticker.replace(".HK", "").replace(".SZ", "").replace(".SH", "")
            all_fin = fetcher.fetch_financials(east_ticker, periods=10)
            annual = sorted([f for f in all_fin if f["period"].endswith("12-31")],
                            key=lambda x: x["period"])
            if len(annual) >= 2:
                latest = annual[-1]
                prev = annual[-2]
                revenue = latest.get("revenue", 0) or 0
                prev_rev = prev.get("revenue", 0) or 0
                rev_growth = (revenue - prev_rev) / prev_rev if prev_rev > 0 else 0
                ta = latest.get("total_assets", 0) or 0
                tl = latest.get("total_liabilities", 0) or 0
                ocf = latest.get("operating_cash_flow", 0) or 0
                ni = latest.get("net_income", 0) or 1

                prof = profitability.score({
                    "revenue_growth": rev_growth,
                    "gross_margin": (latest.get("gross_profit", 0) or 0) / (revenue or 1),
                    "net_margin": (latest.get("net_income", 0) or 0) / (revenue or 1),
                    "roe": (latest.get("net_income", 0) or 0) / (latest.get("total_equity", 0) or 1),
                })
                h = health.score({"debt_ratio": tl / ta if ta > 0 else 0})
                cf = cashflow.score({
                    "operating_cash_flow": ocf,
                    "ocf_to_ni_ratio": ocf / ni if ni else 0,
                    "free_cash_flow": latest.get("free_cash_flow", 0) or 0,
                })
                price_data = fetcher.fetch_price(east_ticker)
                pe = price_data.get("pe_ratio")
                v = valuation.score({
                    "pe_ratio": pe,
                    "pe_history_percentile": None,
                    "revenue_growth_rate": rev_growth * 100,
                })
                g = growth.score({
                    "revenue_growth_rates": [rev_growth],
                    "growth_drivers": [],
                })

                ownership_score = 3
                strategy_score = 3
                try:
                    kb_scores = profile.get("scores", {})
                    ownership_score = kb_scores.get("股东", 3)
                    strategy_score = kb_scores.get("战略", 3)
                    if isinstance(ownership_score, dict): ownership_score = ownership_score.get("score", 3)
                    if isinstance(strategy_score, dict): strategy_score = strategy_score.get("score", 3)
                except Exception:
                    pass

                scores = {
                    "盈利": prof, "健康": h, "现金流": cf,
                    "估值": v, "成长": g, "股东": ownership_score, "战略": strategy_score,
                }
                total_score = sum(scores.values())
                grade = _compute_grade(total_score)
                signal = _compute_signal(total_score, prof, h, cf, v, g, ownership_score, strategy_score)
                print(f"  📊 自动获取评分: {total_score}/35 ({grade}, {signal})")
        except Exception as e:
            print(f"  ⚠️ 无法自动获取评分: {e}")

        rec = DecisionRecord(
            ticker=ticker,
            company_name=company_name,
            market=market,
            action=args.action or "HOLD",
            shares=args.shares or 0,
            price=args.price or 0,
            currency=args.currency or ("HKD" if market == "HK" else "CNY"),
            reason=args.reason or "",
            thesis=args.thesis or "",
            catalyst=args.catalyst or "",
            risk_note=args.risk or "",
            dimension_scores=scores,
            total_score=total_score,
            grade=grade,
            signal=signal,
            portfolio_pct=args.pct or 0,
            expected_price_6m=args.expect_6m or 0,
            expected_price_12m=args.expect_12m or 0,
            expected_reasoning=args.expect_reason or "",
            decision_date=args.date or date.today().isoformat(),
        )

        did = log.record(rec)
        print(f"\n  ✅ 决策已记录: {did}")
        print(f"  {company_name} ({ticker}) {rec.action} {rec.shares}股 @ {rec.price} {rec.currency}")
        if total_score > 0:
            print(f"  评分: {total_score}/35 ({grade}, {signal})")
        print(f"\n  查看: python manage.py decision show {did}")
        return

    # ── outcome ──
    if action == "outcome":
        if not decision_id or not args.actual_price:
            print("  用法: python manage.py decision outcome <id> --actual-price <price> [--period 6m|12m]")
            return
        ok = log.record_outcome(
            decision_id,
            actual_price=args.actual_price,
            period=args.period or "6m",
            review_notes=args.notes or "",
            lessons=args.lessons or "",
        )
        if ok:
            rec = log.get(decision_id)
            print(f"  ✅ 已记录 {args.period or '6m'} 结果: {decision_id}")
            if rec and rec.actual_return_pct != 0:
                print(f"  收益率: {rec.actual_return_pct:+.1f}%")
        else:
            print(f"  ❌ 未找到决策: {decision_id}")
        return

    # ── stats ──
    if action == "stats":
        stats = log.get_stats()
        print(f"\n  📈 决策统计")
        print(f"  {'-'*30}")
        print(f"  总决策数: {stats['total_decisions']}")
        print(f"  已复盘:   {stats['reviewed']}")
        print(f"  待复盘:   {stats['pending_review']}")
        if stats['by_action']:
            print(f"\n  按操作:")
            for act, count in stats['by_action'].items():
                print(f"    {act}: {count}")
        if stats['avg_return_pct'] != 0:
            print(f"\n  平均收益率: {stats['avg_return_pct']:+.1f}%")
        return

    # fallback
    print(f"  未知操作: {action}")
    print("  可用: add, list, show, review, outcome, stats")


def cmd_signal(args):
    """查看信号历史。"""
    import json
    import unicodedata
    from src.strategy.signal_tracker import SignalTracker

    SIGNALS_DB = os.path.join(PROJECT_ROOT, "db", "signals.duckdb")
    if not os.path.exists(SIGNALS_DB):
        print("❌ 信号数据库不存在，请先运行: python manage.py signals")
        return

    st = SignalTracker(SIGNALS_DB)

    def _dw(s):
        w = 0
        for ch in str(s):
            if unicodedata.east_asian_width(ch) in ("W", "F"):
                w += 2
            else:
                w += 1
        return w

    def _pad(s, width, align="left"):
        s = str(s)
        pad = width - _dw(s)
        if pad <= 0:
            return s
        if align == "right":
            return " " * pad + s
        return s + " " * pad

    emoji_map = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}

    if args.all:
        # Show latest signal per company
        rows = st.conn.execute("""
            SELECT company_name, ticker, signal_date, signal_type,
                   total_score, grade, dimension_scores
            FROM signal_records
            WHERE signal_id IN (
                SELECT signal_id FROM (
                    SELECT signal_id, ROW_NUMBER() OVER (
                        PARTITION BY company_name ORDER BY signal_id DESC
                    ) AS rn
                    FROM signal_records
                ) WHERE rn = 1
            )
            ORDER BY total_score DESC
        """).fetchall()

        if not rows:
            print("❌ 没有信号记录，请先运行: python manage.py signals")
            st.conn.close()
            return

        print(f"\n{'=' * 60}")
        print("  最新信号一览")
        print(f"{'=' * 60}\n")

        # Table header
        W_NAME = 10
        W_TICKER = 10
        W_DATE = 10
        W_SIG = 10
        W_SCORE = 4
        W_GRADE = 4
        dims = ["盈利", "健康", "现金流", "估值", "增长", "股东", "战略"]
        dim_hdrs = dims
        dim_cw = [4, 4, 6, 4, 4, 4, 4]  # 现金流3字=6显示宽度

        headers = ["公司", "代码", "日期", "信号", "总分", "等级"] + dim_hdrs
        cw = [W_NAME, W_TICKER, W_DATE, W_SIG, W_SCORE, W_GRADE] + dim_cw

        def _render_table(hdrs, data, widths, indent="  "):
            n = len(hdrs)
            cell_ws = [w + 2 for w in widths]
            def hline(l, m, r):
                return l + m.join("─" * c for c in cell_ws) + r
            def fmt(cells):
                parts = []
                for cell, w in zip(cells, widths):
                    parts.append(" " + _pad(str(cell), w) + " ")
                return "│" + "│".join(parts) + "│"
            lines = [indent + hline("┌", "┬", "┐"), indent + fmt(hdrs),
                     indent + hline("├", "┼", "┤")]
            for row in data:
                lines.append(indent + fmt(row))
            lines.append(indent + hline("└", "┴", "┘"))
            return "\n".join(lines)
        dims = ["盈利", "健康", "现金流", "估值", "增长", "股东", "战略"]
        data = []
        for row in rows:
            name, ticker, sig_date, sig_type, total, grade, scores_json = row
            em = emoji_map.get(sig_type, "❓")
            scores = json.loads(scores_json) if scores_json else {}
            # 兼容旧记录 "成长" 和新记录 "增长"
            if "增长" not in scores and "成长" in scores:
                scores["增长"] = scores["成长"]
            r = [name, ticker, str(sig_date),
                 f"{em} {sig_type}", str(total), grade]
            for d in dims:
                r.append(str(scores.get(d, "?")))
            data.append(r)

        print(_render_table(headers, data, cw))

    elif args.ticker:
        # Show signal history for one company
        ticker = args.ticker
        rows = st.conn.execute("""
            SELECT signal_date, signal_type, total_score, grade,
                   dimension_scores, company_state
            FROM signal_records
            WHERE ticker = ? OR company_name = ?
            ORDER BY signal_date
        """, [ticker, ticker]).fetchall()

        if not rows:
            print(f"❌ 未找到 {ticker} 的信号记录")
            st.conn.close()
            return

        # Get company name from first row
        name_row = st.conn.execute(
            "SELECT company_name FROM signal_records WHERE ticker = ? OR company_name = ? LIMIT 1",
            [ticker, ticker]
        ).fetchone()
        company_name = name_row[0] if name_row else ticker

        print(f"\n{'=' * 55}")
        print(f"  {company_name} — 信号历史 ({len(rows)} 条)")
        print(f"{'=' * 55}\n")

        W_DATE = 10
        W_SIG = 10
        W_SCORE = 4
        W_GRADE = 4
        W_PRICE = 10
        W_PE = 8
        dims = ["盈利", "健康", "现金流", "估值", "增长", "股东", "战略"]
        dim_hdrs = dims
        dim_cw = [4, 4, 6, 4, 4, 4, 4]

        headers = ["日期", "信号", "总分", "等级"] + dim_hdrs + ["价格", "PE"]
        cw = [W_DATE, W_SIG, W_SCORE, W_GRADE] + dim_cw + [W_PRICE, W_PE]

        def _render_table(hdrs, data, widths, indent="    "):
            n = len(hdrs)
            cell_ws = [w + 2 for w in widths]
            def hline(l, m, r):
                return l + m.join("─" * c for c in cell_ws) + r
            def fmt(cells):
                parts = []
                for cell, w in zip(cells, widths):
                    parts.append(" " + _pad(str(cell), w) + " ")
                return "│" + "│".join(parts) + "│"
            lines = [indent + hline("┌", "┬", "┐"), indent + fmt(hdrs),
                     indent + hline("├", "┼", "┤")]
            for row in data:
                lines.append(indent + fmt(row))
            lines.append(indent + hline("└", "┴", "┘"))
            return "\n".join(lines)

        dims = ["盈利", "健康", "现金流", "估值", "增长", "股东", "战略"]
        data = []
        for row in rows:
            sig_date, sig_type, total, grade, scores_json, state_json = row
            em = emoji_map.get(sig_type, "❓")
            scores = json.loads(scores_json) if scores_json else {}
            state = json.loads(state_json) if state_json else {}
            # 兼容旧记录 "成长" 和新记录 "增长"
            if "增长" not in scores and "成长" in scores:
                scores["增长"] = scores["成长"]
            price = state.get("price", 0)
            pe = state.get("pe")
            r = [str(sig_date), f"{em} {sig_type}", str(total), grade]
            for d in dims:
                r.append(str(scores.get(d, "?")))
            r.append(f"{price:.2f}" if price else "N/A")
            r.append(f"{pe:.1f}" if pe else "N/A")
            data.append(r)

        print(_render_table(headers, data, cw))

        # Score trend summary
        if len(rows) >= 2:
            first = rows[0]
            last = rows[-1]
            delta = last[2] - first[2]  # total_score change
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            print(f"\n    趋势: {first[2]}→{last[2]} ({arrow}{abs(delta)}) "
                  f"  {first[0]} ~ {last[0]}")

    else:
        print("用法:")
        print("  python manage.py signal 01810.HK    查看公司信号历史")
        print("  python manage.py signal --all       查看所有公司最新信号")

    st.conn.close()


def cmd_events(args):
    """事件管理命令 — 显示/扫描/刷新投资事件。"""
    from src.events.store import EventStore
    from src.events.collector import EventCollector
    from src.events.calendar_writer import CalendarWriter
    from src.events.models import MarketEvent

    store = EventStore()
    writer = CalendarWriter()

    # 获取持仓ticker列表
    portfolio_path = os.path.expanduser("~/.hermes/portfolio_data.json")
    tickers = []
    if os.path.exists(portfolio_path):
        import json
        with open(portfolio_path, "r") as f:
            pdata = json.load(f)
        tickers = [h["ticker"] for h in pdata.get("holdings", [])]

    if getattr(args, "scan", False):
        # 扫描突发新闻
        from src.events.news_monitor import NewsMonitor

        # 公司名映射
        ticker_names = {
            "1810.HK": "小米", "09988.HK": "阿里巴巴", "3896.HK": "金山云",
            "3888.HK": "金山软件", "2252.HK": "微创机器人", "2498.HK": "速腾聚创",
            "9626.HK": "B站", "9999.HK": "网易", "9896.HK": "名创优品",
            "1361.HK": "361度", "2020.HK": "安踏", "LX": "乐信",
            "159227.SZ": "航空航天", "SGP.ASX": "Stockland",
        }
        monitor = NewsMonitor()
        new_events = monitor.scan_breaking_news(tickers, ticker_names=ticker_names)
        for e in new_events:
            store.add_event(e)
        print(f"发现 {len(new_events)} 条新事件")
        if new_events:
            print(writer.format_daily_briefing(new_events))

    elif getattr(args, "refresh", False):
        # 刷新预知事件
        collector = EventCollector()
        events = collector.collect_all(tickers)
        for e in events:
            store.add_event(e)
        print(f"更新 {len(events)} 条预知事件")
        # 生成日历文件
        path = writer.write_calendar(events)
        print(f"日历已写入: {path}")

    elif getattr(args, "calendar", False):
        # 显示日历文件
        cal_path = os.path.join(PROJECT_ROOT, "knowledge", "events", "calendar.md")
        if os.path.exists(cal_path):
            with open(cal_path, "r") as f:
                print(f.read())
        else:
            print("日历文件不存在，请先运行: python manage.py events --refresh")

    else:
        # 默认: 显示事件
        days = getattr(args, "days", 7)
        event_type = getattr(args, "type", None)
        ticker_filter = getattr(args, "ticker", None)

        if ticker_filter:
            events = store.get_upcoming(days=days, tickers=[ticker_filter])
        elif event_type:
            events = store.get_by_type(event_type, days=days)
        else:
            events = store.get_upcoming(days=days)

        if events:
            print(writer.format_daily_briefing(events))
            print(f"\n未来{days}天共 {len(events)} 条事件")
        else:
            print(f"✅ 未来{days}天无事件")
            print("提示: 运行 python manage.py events --refresh 刷新事件日历")


def cmd_test(args):
    """运行测试。"""
    import subprocess
    os.chdir(PROJECT_ROOT)
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"],
                          capture_output=False)
    sys.exit(result.returncode)


def cmd_anomaly(args):
    """运行异常检测。"""
    from src.analysis.anomaly import detect_anomalies, format_alerts
    from src.data.fetcher import EastmoneyFetcher
    from src.knowledge.base import KnowledgeBase

    fetcher = EastmoneyFetcher()
    kb = KnowledgeBase()

    if args.ticker:
        # Single company
        ticker = args.ticker
        company_name = ticker
        try:
            profile = kb.get_company_profile(ticker)
            company_name = profile.get("name", ticker)
        except Exception:
            pass

        east_ticker = ticker.replace(".HK", "").replace(".SZ", "").replace(".SH", "")
        try:
            all_fin = fetcher.fetch_financials(east_ticker, periods=10)
        except Exception as e:
            print(f"❌ 无法获取 {ticker} 的财务数据: {e}")
            return

        annual = sorted(
            [f for f in all_fin if f.get("period", "").endswith("12-31")],
            key=lambda x: x.get("period", ""),
        )
        if len(annual) < 2:
            print(f"❌ {ticker} 年报数据不足（{len(annual)}期），至少需要2期")
            return

        alerts = detect_anomalies(ticker, annual, company_name)
        print(format_alerts(alerts, company_name))
    else:
        # All companies
        companies = kb.list_companies()
        if not companies:
            print("❌ 知识库为空，请先添加公司")
            return

        print(f"批量异常检测 {len(companies)} 家公司...\n")
        total_alerts = 0
        for c in companies:
            ticker = c["ticker"]
            company_name = c.get("name", ticker)
            east_ticker = ticker.replace(".HK", "").replace(".SZ", "").replace(".SH", "")
            try:
                all_fin = fetcher.fetch_financials(east_ticker, periods=10)
            except Exception:
                print(f"  ⚠️ {company_name} ({ticker}): 无法获取数据，跳过")
                continue

            annual = sorted(
                [f for f in all_fin if f.get("period", "").endswith("12-31")],
                key=lambda x: x.get("period", ""),
            )
            if len(annual) < 2:
                print(f"  ⚠️ {company_name} ({ticker}): 数据不足，跳过")
                continue

            alerts = detect_anomalies(ticker, annual, company_name)
            total_alerts += len(alerts)
            print(format_alerts(alerts, company_name))

        print(f"\n共检测 {len(companies)} 家公司，发现 {total_alerts} 条异常预警")


def cmd_dividend(args):
    """分红追踪命令。"""
    from src.analysis.dividend_tracker import (
        add_dividend, format_calendar_report, get_annual_summary,
        get_upcoming_dividends,
    )
    from datetime import date, timedelta

    action = args.div_action or "calendar"

    if action == "calendar":
        start = args.start or date.today().isoformat()
        end = args.end or (date.today() + timedelta(days=90)).isoformat()
        print(format_calendar_report(start, end))

    elif action == "add":
        if not args.ticker or not args.ex_date or not args.amount:
            print("用法: python manage.py dividend add --ticker 01810.HK --ex-date 2026-06-01 --amount 0.50")
            return
        add_dividend(
            ticker=args.ticker,
            ex_date=args.ex_date,
            amount=args.amount,
            currency=args.currency,
            div_type=args.type,
            note=args.note or "",
        )

    elif action == "summary":
        summary = get_annual_summary(args.year)
        print(f"\n  {args.year}年度分红汇总")
        print("  " + "=" * 50)
        for ticker, info in summary.get("tickers", {}).items():
            print(
                f"  {info['name']:<10}({ticker:<10})  "
                f"{info['div_count']}次  "
                f"{info['currency']} {info['total_amount']:,.2f}  "
                f"(≈HKD {info['hkd_equivalent']:,.2f})"
            )
        print("  " + "-" * 50)
        print(f"  合计: ≈HKD {summary['total_hkd']:,.2f}")

    elif action == "upcoming":
        days = args.days or 60
        divs = get_upcoming_dividends(days)
        if not divs:
            print(f"  未来{days}天内无分红事件")
        else:
            print(f"\n  未来{days}天分红预告")
            print("  " + "=" * 60)
            for d in divs:
                print(
                    f"  {d['ex_date']}  {d['name']:<8}({d['ticker']:<10})  "
                    f"{d['currency']} {d['amount']:.4f}/股 × {d['shares']:,}股 = "
                    f"{d['currency']} {d['total_amount']:,.2f}"
                )


def main():
    """Entry point for the YiDai investment analysis CLI."""
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="意怠工程 — 个人投研系统管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python manage.py dashboard              持仓+信号面板
  python manage.py signals                更新所有信号
  python manage.py signal 01810.HK        查看小米信号历史
  python manage.py signal --all           所有公司最新信号
  python manage.py report                 生成周报
  python manage.py analyze 01810.HK       分析小米
  python manage.py analyze LX --thesis "低估+高股息"
  python manage.py analyze --all          批量分析
  python manage.py backtest 01810.HK      回测小米
  python manage.py kb                     知识库概览
  python manage.py kb 01810.HK            查看公司档案
  python manage.py test                   运行测试
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # dashboard
    p_dashboard = subparsers.add_parser("dashboard", help="持仓+信号统一面板")
    p_dashboard.add_argument("--enhanced", action="store_true", help="使用增强版可视化面板")

    # signals
    subparsers.add_parser("signals", help="更新所有公司信号")

    # report
    p_report = subparsers.add_parser("report", help="生成增强版周报或个股深度报告")
    p_report.add_argument("ticker", nargs="?", help="股票代码 (如 01810.HK)，指定则生成个股深度报告")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="分析公司")
    p_analyze.add_argument("ticker", nargs="?", help="股票代码 (如 01810.HK, LX)")
    p_analyze.add_argument("--all", action="store_true", help="批量分析所有持仓")
    p_analyze.add_argument("--thesis", help="投资论点")

    # backtest
    p_backtest = subparsers.add_parser("backtest", help="回测分析")
    p_backtest.add_argument("ticker", help="股票代码 (如 01810.HK)")

    # kb
    p_kb = subparsers.add_parser("kb", help="知识库操作")
    p_kb.add_argument("company", nargs="?", help="查看公司档案 (如 01810.HK)")

    # list
    p_list = subparsers.add_parser("list", help="列出所有公司评分")
    p_list.add_argument("company", nargs="?", help="查看公司档案")

    # signal
    p_signal = subparsers.add_parser("signal", help="查看信号历史")
    p_signal.add_argument("ticker", nargs="?", help="股票代码 (如 01810.HK)")
    p_signal.add_argument("--all", action="store_true", help="查看所有公司最新信号")

    # score
    p_score = subparsers.add_parser("score", help="设置定性评分 (股东/战略)")
    p_score.add_argument("ticker", nargs="?", help="股票代码 (如 01810.HK)")
    p_score.add_argument("--ownership", type=int, help="股东评分 (0-5)")
    p_score.add_argument("--strategy", type=int, help="战略评分 (0-5)")
    p_score.add_argument("--list", action="store_true", help="列出所有公司定性评分")

    # decision
    p_decision = subparsers.add_parser("decision", help="决策日志：记录/查看/复盘")
    p_decision.add_argument("decision_action", nargs="?", default=None,
                            choices=["add", "list", "show", "review", "outcome", "stats"],
                            help="操作: add/list/show/review/outcome/stats")
    p_decision.add_argument("ticker_or_id", nargs="?", help="股票代码或决策ID")
    p_decision.add_argument("--ticker", help="股票代码")
    p_decision.add_argument("--action", choices=["BUY", "SELL", "REDUCE", "ADD", "HOLD"],
                            help="操作类型")
    p_decision.add_argument("--shares", type=int, help="交易股数")
    p_decision.add_argument("--price", type=float, help="交易价格")
    p_decision.add_argument("--currency", help="货币 (HKD/CNY/USD)")
    p_decision.add_argument("--reason", help="简短理由")
    p_decision.add_argument("--thesis", help="投资论点")
    p_decision.add_argument("--catalyst", help="催化剂")
    p_decision.add_argument("--risk", help="风险提示")
    p_decision.add_argument("--pct", type=float, help="持仓占比 (%%)")
    p_decision.add_argument("--expect-6m", type=float, dest="expect_6m", help="6个月预期价格")
    p_decision.add_argument("--expect-12m", type=float, dest="expect_12m", help="12个月预期价格")
    p_decision.add_argument("--expect-reason", help="预期逻辑")
    p_decision.add_argument("--date", help="决策日期 (YYYY-MM-DD)")
    p_decision.add_argument("--decision-id", dest="decision_id", help="决策ID (show/outcome)")
    p_decision.add_argument("--actual-price", type=float, dest="actual_price", help="实际价格")
    p_decision.add_argument("--period", default="6m", help="复盘周期 (6m/12m)")
    p_decision.add_argument("--notes", help="复盘笔记")
    p_decision.add_argument("--lessons", help="经验教训")
    p_decision.add_argument("--limit", type=int, help="列表数量限制")

    # events
    p_events = subparsers.add_parser("events", help="事件管理：显示/扫描/刷新")
    p_events.add_argument("--days", type=int, default=7, help="显示未来N天 (默认7)")
    p_events.add_argument("--type", type=str, help="按类型过滤 (earnings/macro/breaking/product)")
    p_events.add_argument("--ticker", type=str, help="按股票过滤 (如 1810.HK)")
    p_events.add_argument("--scan", action="store_true", help="扫描突发新闻")
    p_events.add_argument("--refresh", action="store_true", help="刷新预知事件日历")
    p_events.add_argument("--calendar", action="store_true", help="显示事件日历文件")

    # test
    subparsers.add_parser("test", help="运行测试")

    # anomaly
    p_anomaly = subparsers.add_parser("anomaly", help="运行异常检测")
    p_anomaly.add_argument("ticker", nargs="?", help="股票代码 (如 01810.HK)，不指定则检测所有公司")

    # dividend
    p_dividend = subparsers.add_parser("dividend", help="分红追踪：日历/记录/预告")
    p_dividend.add_argument("div_action", nargs="?", default="calendar",
                            choices=["calendar", "add", "summary", "upcoming"],
                            help="操作: calendar/add/summary/upcoming")
    p_dividend.add_argument("--start", help="起始日期 (YYYY-MM-DD)")
    p_dividend.add_argument("--end", help="结束日期 (YYYY-MM-DD)")
    p_dividend.add_argument("--days", type=int, default=60, help="预告天数 (默认60)")
    p_dividend.add_argument("--year", type=int, default=2026, help="汇总年度")
    p_dividend.add_argument("--ticker", help="股票代码")
    p_dividend.add_argument("--ex-date", dest="ex_date", help="除净日 (YYYY-MM-DD)")
    p_dividend.add_argument("--amount", type=float, help="每股股息")
    p_dividend.add_argument("--currency", default="HKD", help="币种")
    p_dividend.add_argument("--type", default="final", help="类型 (final/interim/special)")
    p_dividend.add_argument("--note", help="备注")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "dashboard": cmd_dashboard,
        "signals": cmd_signals,
        "report": cmd_report,
        "analyze": cmd_analyze,
        "backtest": cmd_backtest,
        "kb": cmd_kb,
        "list": cmd_list,
        "signal": cmd_signal,
        "score": cmd_score,
        "decision": cmd_decision,
        "test": cmd_test,
        "anomaly": cmd_anomaly,
        "dividend": cmd_dividend,
        "events": cmd_events,
    }

    func = commands.get(args.command)
    if func:
        func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
