Yidai Project — Very Thorough Exploration /home/frank/.hermes/yidai
1. src/ Directory Structure
Project root: /home/frank/.hermes/yidai
src/
├── analysis/           22 modules — core decision science
│   ├── __init__.py
│   ├── scorer.py                 # master 8-dim aggregator (see §7)
│   ├── profitability.py          # D1
│   ├── health.py                 # D2
│   ├── cashflow.py               # D3
│   ├── valuation.py              # D4
│   ├── growth.py                 # D5
│   ├── dividend_quality.py       # D6 (auto)
│   ├── percentile.py             # historical PE percentile helper
│   ├── benchmarks.py             # industry median comparisons
│   ├── leading_indicators.py     # structured leading indicator store
│   ├── anomaly.py                # 5-rule financial anomaly detection
│   ├── market_signals.py         # announcement sentiment + industry health + mgmt change
│   ├── dcf.py                    # simplified DCF
│   ├── esg.py                    # governance ESG simplified
│   ├── ownership_structure.py    # controller / barbarian-at-gate advisory
│   ├── insider_activity.py       # reduction + issuance advisory (Check 6)
│   ├── quarterly.py              # quarterly analysis
│   ├── return_projection.py      # 12-month return projection
│   ├── master_integration.py     # multi-master (Buffett/Lynch etc.) integration
│   ├── dividend_tracker.py       # JSON dividend calendar
│   ├── cashflow.py / health etc  # as above
│   └── accuracy_audit.py         # signal accuracy multi-window audit
├── data/
│   ├── __init__.py
│   ├── fetcher.py        # EastmoneyFetcher — 823 lines
│   ├── store.py          # YidaiStore DuckDB layer — 317 lines
│   └── models.py         # Company, FinancialStatement, PriceData, ScoreResult + weights
├── strategy/             8 modules — portfolio & decision science
│   ├── decision.py            # DecisionLog / DecisionRecord (active/reviewed_6m/12m)
│   ├── review.py              # older ReviewEngine (decision_records / holding_snapshots)
│   ├── review_engine.py       # newer expectation validation engine (review_results + alert_reviews)
│   ├── signal_tracker.py      # signal lifecycle: observe→analyze→act→predict→result→learn
│   ├── backtest.py            # v1 — 7-dim scoring, full position, annual only
│   ├── backtest_v2.py         # v2 — quarterly + trend filter (200MA, 30% DD) + gradual sizing
│   ├── portfolio_constraints.py # single/sector/market/correlation group checks
│   └── portfolio_config.py    # default limits + sample holdings
├── events/
│   ├── collector.py, calendars.py, calendar_writer.py, impact_analyzer.py
│   ├── news_monitor.py, theme_mapper.py, store.py, models.py
├── knowledge/
│   └── base.py           # KnowledgeBase — markdown-file CRUD, 1121 lines
├── report/
│   ├── weekly.py, weekly_v2.py, company_report.py
└── viz/
    └── dashboard.py
Absolute paths for key files:
- /home/frank/.hermes/yidai/src/analysis/scorer.py
- /home/frank/.hermes/yidai/src/analysis/anomaly.py
- /home/frank/.hermes/yidai/src/analysis/market_signals.py
- /home/frank/.hermes/yidai/src/analysis/dcf.py
- /home/frank/.hermes/yidai/src/analysis/benchmarks.py
- /home/frank/.hermes/yidai/src/analysis/leading_indicators.py
- /home/frank/.hermes/yidai/src/analysis/accuracy_audit.py
- /home/frank/.hermes/yidai/src/strategy/decision.py
- /home/frank/.hermes/yidai/src/strategy/review_engine.py
- /home/frank/.hermes/yidai/src/strategy/review.py
- /home/frank/.hermes/yidai/src/strategy/backtest.py
- /home/frank/.hermes/yidai/src/strategy/backtest_v2.py
- /home/frank/.hermes/yidai/src/strategy/portfolio_constraints.py
- /home/frank/.hermes/yidai/src/strategy/portfolio_config.py
- /home/frank/.hermes/yidai/src/data/models.py
- /home/frank/.hermes/yidai/src/data/fetcher.py
- /home/frank/.hermes/yidai/src/data/store.py
Key File Deep Dives
src/analysis/scorer.py (457 lines) — 8-dim Aggregation
Structure: 6 quantitative (prob, health, cashflow, valuation, growth, dividend) + 2 qualitative (ownership, strategy). score_all() builds inputs via _build_*_data() helpers, calls each sub-module, builds ScoreResult, combines details.
Helpers:
- _build_profitability_data() computes rev_growth, gross/net margin, ROE, plus multi-year rev_growth_rates / ni_growth_rates and optional industry_median_gross_margin.
- _build_health_data() debt_ratio, interest_bearing_debt_ratio, current_ratio, debt_to_equity.
- _build_cashflow_data() ocf_to_ni, passes FCF as None if missing (vs 0).
- _build_valuation_data() PE, PE history percentile, rev_growth*100 for PEG, EV/EBITDA via market_cap + ibd - cash, peer_median_pe passthrough.
- _build_growth_data() revenue growth list, 5yr ROE & gross margin collections.
- _build_dividend_data() DPS via dividend_per_share or total_dividends/shares, DY, payout_ratio, historical DPS growth.
Main score_all(financial_data, price_data, qualitative_scores, prev_financial_data, all_annual_data, peer_median_pe, industry, previous_health_data, insider_activity_events, ownership_structure_events) — returns dict with 8 scores, total_score, grade, signal, details, insider_activity, ownership_structure. Grade via ScoreResult (now 0-40, but scorer comments say 35). Advisory sections appended without affecting score.
Signal text: generate_signal_text() gives Chinese BUY/HOLD/WATCH/REDUCE with valuation/health refinement.
src/analysis/anomaly.py (347 lines) — 5 Rules, Advisory
detect_anomalies(ticker, annual_data[>=2], company_name) returns sorted alerts:
- W1.1.1 AR vs Revenue: consecutive >=2 periods AR growth > rev growth+10% => HIGH else 1 period => MEDIUM.
- W1.1.2 Inventory turnover: rev/inventory declining 3 contiguous periods => MEDIUM.
- W1.1.3 Profit quality: OCF < NI consecutive >=2 (skips loss periods) => MEDIUM.
- W1.1.4 Short-loan long-invest: latest short_loan +30% & >5% TA & long_term_invest +10% => HIGH.
- W1.1.5 Goodwill: >10% TA + delta>5pp => MEDIUM, or >20% alone => MEDIUM.
All fields Optional; missing data skips rule. No score impact; format_alerts() for markdown.
src/analysis/market_signals.py (268 lines) — 3 Types
1. Announcement Sentiment: NEGATIVE_KEYWORDS 20 Chinese terms (下调,暴雷...), POSITIVE_KEYWORDS 15 (超预期,回购...). score_announcement_sentiment(text) counts hits, pos_ratio -> score 1-5, sentiment neutral/positive/negative.
2. Industry Health: score_industry_health(industry, metrics) with thresholds per industry (default, 半导体, 新能源, 消费) on pmi, sales_growth, inventory_ratio (inverse), capacity_utilization. Points 2/1/0 -> avg*2.5 -> 0-5 score, status expanding/stable/contracting.
3. Management Change: MGMT_KEYWORDS 12 terms (辞职,解聘...), detect_management_change(announcements) maps to severity high/medium/low.
src/analysis/dcf.py (241 lines)
simple_dcf(current_fcf, growth_rates[], terminal_growth, discount_rate, shares_outstanding) projects FCFs, Gordon terminal value, discounts to PV, derives intrinsic_value/share. Handles discount_rate <= terminal fallback, zero shares, empty growth. dcf_valuation(financial_data, price_data) extracts FCF (fcf or free_cash_flow), handles negative FCF => score 1, estimates growth_rates via revenue_growth_rates avg*decay or estimate_growth_rate(annual_data) capped -20% to 50%, uses 10% WACC, 3% terminal, scores via margin_of_safety >30%/15%/0%/-15% => 5/4/3/2/1. Standalone scorer not integrated into main scorer.py (used in report enrichment only).
src/analysis/benchmarks.py (192 lines)
INDUSTRY_BENCHMARKS 10 sectors (technology median GM 45%, net 12%, ROE 14%, debt 35%, growth 15%, PE 25-60; internet, auto_parts etc). _percentile_like(value, median, higher_is_better) = (value/median)*50 clamped 0-100 (inverse for debt). relative_score(industry, metrics) returns benchmark, per-metric scores, overall avg. PE linear interpolation lower => higher score.
src/analysis/leading_indicators.py (270 lines)
LeadingIndicatorStore DuckDB leading_indicators table PK (ticker, indicator_name), fields threshold_positive/negative, unit, category, latest_value/period/date/status. _calculate_status() supports both higher-is-better (pos>neg) and lower-is-better. Methods: add_indicator(), update_value() auto-status, get_indicators(ticker?), get_alerts() where status=negative or latest_value IS NULL.
src/analysis/accuracy_audit.py (841 lines) — Exists
AccuracyAuditor audits signal accuracy vs current price. Key methods:
- _calculate_return_pct, _is_direction_correct (BUY >0, REDUCE <0, HOLD |ret|<10%, WATCH always False)
- _to_yahoo_ticker handle 01810.HK ->1810.HK, 600900.SH->600900.SS etc, fetch_price_at_date(ticker, target_date) via Yahoo v8 chart ±7 days, closest close.
- load_pending_signals(min_days_old) loads signal_records JSON parsing company_state->signal_price, prediction_6m->expected.
- compute_accuracy_stats(records, window_days?) aggregates total/correct/direction_accuracy/avg_return, by_type, by_grade, by_dimension (high>=3 vs low)
- backfill_prices(fetcher), backfill_time_windows(window_days=[30,60,90,180]) with 0.3s rate limit, stores JSON time_window_prices
- format_report() multi-window renderer and legacy, generate_full_report() loads enriched records.
Database default ~/.hermes/yidai/db/signals.duckdb.
Strategy Modules
src/strategy/decision.py (329 lines): DecisionRecord dataclass 30 fields (ticker/action/shares/price/reason/thesis/catalyst/risk/dimension_scores/total/grade/signal/portfolio_pct/expected 6m/12m/actual/return/lessons/status active/reviewed6m/reviewed12m/closed). DecisionLog DuckDB decision_log table, record() UUID8, get(), list_decisions(), record_outcome(decision_id, actual_price, period), get_pending_reviews(period), get_stats(), to_markdown().
src/strategy/review_engine.py (454 lines): ReviewResult, DimensionEffectiveness, AlertAccuracy. ReviewEngine(db_path, decision_log) creates review_results + alert_reviews. review_decision(decision_id, actual_price, period, fetch_fn) computes actual_ret, expected_ret, price_accuracy=1-|actual-expected|/expected, direction_correct, beat, persists. batch_review(), analyze_dimension_effectiveness() splits high>=4 vs low<=2 per dim, effectiveness=high_avg - low_avg, record_alert_outcome(), get_alert_accuracy_stats(), format_dimension_report().
src/strategy/review.py (784 lines) older: DecisionRecord 7-dim, HoldingSnapshot price_change_pct + alerts, ReviewRecord entry vs exit comparison. ReviewEngine(db_path) creates decision_records/holding_snapshots/review_records, take_snapshot() alerts on dim drop >=2, grade downgrade, signal BUY->HOLD/REDUCE, generate_review() computes what_was_right/wrong/missed_signals/lessons (cashflow/growth deterioration patterns), generate_weekly_check().
src/strategy/backtest.py (486 lines): BacktestEngine(initial_capital=1M) run(ticker, annual_financials, price_history, ownership_scores, strategy_scores, revenue_growth_rates, growth_drivers) — no look-ahead, report_date = report_date or FY+1 April30, PE percentile, 6-dim scoring (dividend assumed 0), total/grade/signal, trades BUY full cash / REDUCE full shares, metrics: total_return, CAGR, max_drawdown, Sharpe (daily ret annualised 252), benchmark buy-and-hold, win_rate.
src/strategy/backtest_v2.py (729 lines): Extends v1 with quarterly support, trend filter (200MA, 30% DD stop forced REDUCE), gradual sizing (BUY 50%, ADD 25% when scores improve, REDUCE 50% else EXIT), YoY growth _get_yoy_growth via exact 1yr ago period string, trend_filter_blocked metric, _compute_ma, _check_drawdown, _execute_gradual.
src/strategy/portfolio_constraints.py (201 lines): PortfolioConstraints(max_single_pct=25, max_sector_pct=40, max_market_pct=70, max_correlation_group_pct=35), add_correlation_group(name, tickers, reason), check_position_limits, check_sector_concentration, check_market_exposure, check_correlation_groups, check_all() -> dict, format_report() Chinese.
src/strategy/portfolio_config.py (62 lines): get_default_constraints() presets 4 groups (金山系 3888/3896, 小米生态 1810/3896, 港股互联网, 港股消费), create_sample_holdings() 13 positions Xiaomi 60% etc total ~1M HKD.
src/data/models.py (283 lines) — Core Decision Science Logic
Defines DIMENSION_WEIGHTS from 2026-08-29 audit:
- profitability 0.5 (反预测力 -0.35)
- health 1.5 (强 +0.50)
- cashflow 0.5 (-0.42)
- valuation 1.5 (+0.50)
- growth 1.0 (+0.13)
- dividend 0.8
- ownership 1.2 (+0.50)
- strategy 1.2 (+0.50)
_compute_weighted_total() max ~41. _compute_signal() priority: (1) health<2 or cashflow<2 or ownership<1 => REDUCE, (2) total<=16 => REDUCE, (3) any dim <2 => REDUCE, (4) weighted_total>=33 & valuation>=4 & health>=3 & growth>=3 => BUY, (5) total>=17 => HOLD else WATCH. Note inconsistency: docs still say 35 max but code now 40.
2. Tests Coverage
44 test files, 891 def test_ functions (38 files with tests).
Distribution (top files):
- test_strategy/test_backtest.py 57 tests
- test_analysis/test_accuracy_audit.py 55
- test_knowledge/test_base.py 48
- test_viz/test_dashboard.py 41
- test_strategy/test_backtest_v2.py 36
- test_report/test_weekly_v2.py 34
- test_strategy/test_review.py 33
- test_analysis/test_dcf.py 31
- test_analysis/test_master_integration.py 29
- test_analysis/test_anomaly.py 29
- test_analysis/test_insider_activity.py 28
- test_analysis/test_market_signals.py 27
... plus test_analysis 19 files (cashflow, health, growth, valuation, profitability, ownership, quarterly, percentile, return_projection, benchmarks, leading_indicators, esg etc), test_data fetcher/store/models, test_strategy decision/signal_tracker/review_engine/portfolio_constraints/portfolio_config, test_report weekly/company, test_events news/theme, test_e2e_* (Xiaomi, compare, backtest, review, integration).
What is tested: All scoring dimensions (edge cases zero/negative, missing data, loss penalty, quality bonus, trend), anomaly 5 rules, DCF margin, benchmarks percentile, quarterly, ESG, insider activity severity, leading indicator status thresholds (high/low), market signals thresholds, portfolio constraints (position/sector/market/correlation), backtest metrics & trade logic, decision log CRUD, signal tracker lifecycle & accuracy stats, review engine dimension effectiveness, weekly report rendering, fetcher safe_float/_detect_market/parse_date, knowledge base markdown CRUD.
Gaps noted: No integration tests for live price fetch robustness, limited accuracy_audit backfill idempotency, dividend_quality covered lightly, no chaos test for 40 vs 35 grade inconsistency.
3. data/ Directory Contents
- /home/frank/.hermes/yidai/data/dividends.json — only file in data/. Metadata last_updated 2026-06-08, holdings map ticker-> {name, shares, currency, dividends{ex_date, amount, currency, type, year, note}}. Example 09988.HK Alibaba 2500 shares final 1.9587 HKD + interim 0.131 USD, 03888.HK 金山软件 3400 shares final 0.13 HKD. Covers 014 holdings.
- db/ adjacent (not data/): yidai.duckdb 4.4MB (company+financial+price+scores), signals.duckdb 3.4MB (~750 signals), events.duckdb 0.8MB, leading_indicators.duckdb 0.8MB, yidai_review.duckdb 0.5MB.
4. knowledge/companies — Sample
~70 files, ~3672 total lines. Most are stub 48 lines generated by create_company_profile with no thesis, awaiting manage.py analyze.
Sample 1: /home/frank/.hermes/yidai/knowledge/companies/01810.HK.md (Xiaomi, 48 lines):
小米集团 (01810.HK) — 基本信息 HK, 首次关注 2026-08-22
评分: 盈利5↑ 健康5↑ 现金流4↑ 估值5↑ 成长5↑ 股东4↑ 战略5↑ => 33/40 A BUY
历史: 2026-08-22 评分更新 33/40
关键指标: 营收4572.87亿 净利416.43亿 ROE15.64% 毛利率22.26% PE19.98 负债率47.58%
风险/反思 empty.
Contrast with handbook case (FY2025 detailed manual scoring 29/35 A) vs auto 33/40 A BUY — inflated qualitative defaults 4/5.
Sample 2: /home/frank/.hermes/yidai/knowledge/companies/09988.HK.md (Alibaba, 54 lines): Similar stub, total not yet scored in example but KB would hold 投资论点待填写 unless analyze.
Sample 3: /home/frank/.hermes/yidai/knowledge/companies/爱柯迪-600933.md (156 lines): Rare enriched file with thesis etc.
Pattern: stubs indicate automation not yet backfilled with human thesis; KB is scaffolding awaiting population.
Other KB roots: /home/frank/.hermes/yidai/knowledge/journal.md, lessons.md, principles.md, decisions/2026-06.md, events/calendar.md etc. Analysis docs: /home/frank/.hermes/yidai/knowledge/analysis/scoring-system-review-2026-06.md, ai-industry-chain-2026-05.md etc 30+ research reports.
5. reports/ — Weekly Sample
11 reports: weekly_2026-05-26.md, weekly_v2_2026-05-31 ... 2026-08-23 etc plus company report company_02252_HK_2026-06-13.md.
Sample: /home/frank/.hermes/yidai/reports/weekly_v2_2026-08-23.md (~1270 lines, 2026-08-23 13:19, 64 companies tracked, signal summary BUY1/HOLD0/WATCH0/REDUCE0 but internally lists 750 pending signals section with table of signal history per ticker):
- Sections: 信号预警 new 5 signals + 待回顾6m/12m massive table (actually dumping full signal DB due to pending status not culled — bug: 300+ rows duplicate tickers), 财务异常预警 HIGH 002460.SZ/300020.SZ W1.1.1 & MEDIUM 002896/300540, 组合概览 shows only 1 scored company (01810) avg 30/35, then 个股分析 iterates all 64 tickers but only 01810 has data (others "暂无评分数据"), 知识库洞察 last 3 lessons, 📚 accuracy if available.
- Rendering bug: store.get_all_tickers returns companies table but scores missing — report generated before analyze run, thus empty.
- File size inflated by unfiltered pending signals (should be due-date filtered, not all active).
Company report: /home/frank/.hermes/yidai/reports/company_02252_HK_2026-06-13.md — single-company deep dive (similar structure but per ticker).
6. manage.py — All Commands (1300+ lines)
Entry sys.path PROJECT_ROOT insertion, manual argparse dispatcher.
Commands implemented:
- python manage.py dashboard [--enhanced] — scripts.dashboard main vs main_enhanced (holdings+signals unified panel)
- python manage.py signals — scripts.record_all_signals main update all signals
- python manage.py signal [<ticker>] | --all — cmd_signal shows per-company history or latest per company table with dimension breakdown, trend arrow.
- python manage.py report [<ticker>] — generate_company_report if ticker else generate_report_v2 -> reports/
- python manage.py analyze <ticker> [--thesis ""] | --all — _analyze_one fetches Eastmoney 20 periods, detects FY month via Counter, computes 8 dims via profitability/health/cashflow/valuation/growth/dividend_quality/insider/ownership, prints Chinese bar, integrated master assessment, saves to KB + DuckDB + SignalTracker; batch iterates kb.list_companies()
- python manage.py backtest <ticker> — BacktestEngineV2 run with 50 periods, fetches monthly prices via web.ifzq.gtimg.cn 2015-2026, prints last 10 signals + trades + metrics
- python manage.py kb [<ticker>] — cmd_kb lists sorted by total descending, or shows profile risks/financials
- python manage.py list — alias to kb overview
- python manage.py score --list | <ticker> --ownership 0-5 --strategy 0-5 — cmd_score reads/writes qualitative scores
- python manage.py decision list|add <ticker> --action --price --shares --reason --thesis --catalyst --risk --pct --expect-6m/12m --expect-reason --date | show <id> | review [--period 6m/12m] | outcome <id> --actual-price --period --notes --lessons | stats — DecisionLog based
- python manage.py events [--days 7|30] [--scan] [--refresh] [--calendar] [--ticker X] [--type Y] — EventStore/Collector/Writer, scans ~/.hermes/portfolio_data.json holdings
- python manage.py test — pytest tests/ -q --tb=short
- python manage.py anomaly [<ticker>] — detect_anomalies + format, batch all KB companies
- python manage.py dividend calendar|add --ticker --ex-date --amount --currency --type --note | summary --year — dividend_tracker
- python manage.py with no args prints help covering above 20 usage examples.
Additional undocumented: audit, indicators, constraints referenced in ROADMAP but not wired in manage.py help (implemented but hidden? generate_full_report exists but no manage.py audit dispatcher visible in read — possibly via scripts).
7. src/analysis/scorer.py — How Scoring Works, Weights, Logic
Weighted vs Raw: Raw total_score = sum 8 dims 0-5 = 0-40 used for grade. Weighted weighted_total = sum(dim*weight) max 41 used only for BUY gate (valuation>=4 && health>=3 && growth>=3 && weighted>=33).
Grade thresholds (models.py / scorer): A 33-40, B 26-32, C 17-25, D 9-16, F 0-8. Handbook originally 29-35 for 7 dims but migrated to 40 without fixing thresholds? Report threshold _GRADE_THRESHOLDS in weekly_v2 still 29/22/15/8 (35 scale) — inconsistency.
Signal logic (critical): See § models.
Logic flow per dim:
- D1 profitability: 4 checks >8% rev, >0.15 GM, >5% net, >10% ROE, plus quality bonus/penalty if NI growth > rev growth => +1, rev up but NI down => -1, loss => extra -1.
- D2 health: up to 4 checks <0.70 debt, >1.0 current, <0.30 ibd, <2.0 D/E, scoring 5/4/3/1/0, plus trend penalty if debt rising vs prev.
- D3 cashflow: OCF>0, OCF/NI>0.7, FCF>0 (skip if None), plus OCF trend ok; OCF<=0 => 0 automatic; scoring table failures 0=5/0&trend bad=4/1fail trend ok=4 etc.
- D4 valuation: growth-aware (>15% rev = growth company): PE<=0 skip, PE<100 pass else PEG<3 pass; non-growth PE<100 strict, PE percentile <0.70, PEG<2, EV/EBITDA buckets, peer PE vs median.
- D5 growth: latest >10% strong, trend 0/<=0.5/>0.5 declining ratio, volatility range>0.5 penalty, one-time drivers penalty, CAGR excellent >15% +1/declining -1, 5yr ROE & GM stability trend/vol bonus/penalty.
- D6 dividend_quality: DY, payout, historical growth -> score via dividend_quality module.
- D7/D8 qualitative: human 0-5 default 3.
Details aggregated: prefixed headers --- Profitability --- etc for report rendering.
8. src/analysis/accuracy_audit.py — Exists (841 lines)
See §1 deep dive. Implements multi-window directional accuracy (30/60/90/180 days via Yahoo), by_type, by_grade, by_dimension predictive_power = high_acc - low_acc, backfill with Yahoo rate limit 0.3s, stores time_window_prices JSON. Used in weekly_v2 header 信号准确率: X% and knowledge insights. CLI manage.py audit (planned) uses format_report table counts.
Current audit claim: ROADMAP W6 says 750 signals audited 2026-08-28, but signals DB currently 3.4MB pending signals not yet enriched with actual_6m / time_window_prices — many signals lack future price so audit stats likely near zero if run now.
9. Portfolio / Risk Management Code
- /home/frank/.hermes/yidai/src/strategy/portfolio_constraints.py — pure constraint checker, no rebalancing optimizer. Limits: single 25%, sector 40%, market 70%, correlation 35%. Used in weekly_v2 _render_action_items and constraints check section, plus dashboard.
- /home/frank/.hermes/yidai/src/strategy/portfolio_config.py — hard-coded groups, sample holdings with Xiaomi 60% (deliberately violates single limit to test).
- /home/frank/.hermes/yidai/src/strategy/signal_tracker.py — signal lifecycle persistence, prediction_6m/12m auto current_price*(1+growth*0.5) naive, get_pending_reviews unfiltered by due date (status only). No position sizing risk, no stop-loss.
- /home/frank/.hermes/yidai/src/strategy/decision.py + review engines — decision review but no portfolio VaR, no Kelly, no max drawdown budgeting.
- Missing: No risk model (volatility, beta, correlation matrix), no position sizing (Kelly/ volatility targeting), no stop-loss/trailing, no sector neutrality, no liquidity filter, no currency hedging, no drawdown attribution.
Architecture Strengths
1. End-to-end automation: Fetcher → Store → Scorer → KB → SignalTracker → Report → Backtest closed loop; manage.py single entry reduces UX friction.
2. Separation of concerns: analysis pure functions (score(dict)->dict) testable; data isolated; strategy stateful DB-backed; knowledge human-in-loop markdown; events orthogonal.
3. High test coverage: 891 tests, parametrized edge cases, E2E Xiaomi real data path gives confidence.
4. Advisory vs scoring separation: Insider & ownership warnings appended to details without affecting score avoids false precision.
5. Multi-period awareness: Health trend penalty, growth 5yr CAGR/ROE/GM stability, scorer prev_all_annual for growth rates.
6. Auditability: Decision log snapshots + signal tracker predictions enable future causal analysis (predictive_power).
7. Gradual evolution: V2 backtest adds quarterly, YoY, trend filter — shows learning from 长期持有+69% vs 策略-41% lesson.
Architecture Weaknesses & Risks (Critical for Decision Science Success Rate)
 1. Score-to-signal contradiction: models.py 40-point scale but weekly_v2._GRADE_THRESHOLDS 35-point, manage.py analyze sums 8 dims but uses health.score with only debt_ratio (ignores current_ratio etc fallback), DecisionLog record vs models._compute_signal duplicated logic with differing dividend handling — signal may flip between modules.
 2. Qualitative pollution: analyze --all defaults ownership/strategy 3 for all companies never manually scored, inflating totals by 6 points flat; BUY gate requires ownership/strategy effectively neutral, masking true skill; 70 stubs with default 3 skew portfolio overview.
 3. Negative predictive dims: Audit says profitability & cashflow are inverse predictors (-0.35/-0.42) — scoring rewards high profitability but empirical edge says avoid it. Down-weight to 0.5 is ad-hoc not inverse; should invert or remove. Indicates overfitting to small sample or survivorship (profitable companies at peak).
 4. Data quality gaps: HK fetcher current_assets incorrectly mapped to CURRENT_RATIO placeholder, free_cash_flow always None for HK, interest_bearing_debt None, capex missing — health/cashflow dims underdetermined, returns neutral 3. div_per_share often null, dividend_quality then skews low (0.8 weight).
 5. Insider/ownership data fragility: Eastmoney disclosure endpoints undocumented, return empty list fallback silently, no validation — advisory never triggers, false sense of safety.
 6. Report generation bug: weekly_v2 iterates store.get_all_tickers() (company table) but store.get_scores() empty for most => "暂无评分数据" for 63/64; pending signals table dumps unfiltered active_6m without signal_date <= now-6m => noise.
 7. No risk-adjusted sizing: Portfolio constraints only flag, not prevent; no volatility targeting; Xiaomi 60% sample violates but system allows recording. No drawdown-aware position reduction until 30% DD (too late).
 8. Yahoo price dependency for audit: Backfill requires live Yahoo fetch 0.3s * 750*4 windows = 900s, fragile, no caching, no fallback to Eastmoney; audit stats stale.
 9. Leading indicator store isolated: Not linked to scorer — indicators never affect signal, just displayed as "待更新" list; wasted structure.
10. Scale inconsistency: profitability growth_rate computed from prev_revenue but revenue_growth_rates list built sequentially not YoY for quarterly — growth dim conflates QoQ vs YoY.
Recommendations to Improve Decision Science & Success Rate
Immediate (0-2 weeks):
- Fix 35 vs 40 mismatch: choose 8*5=40, update weekly_v2, handbook, ROADMAP, score_result table docs, and manage.py list thresholds.
- Make qualitative explicit: require manage.py score before BUY signal counts; show ownership/strategy as ? if default not set, exclude from total until human input.
- Invert anti-predictive dims: set profitability/cashflow weight 0 or -0.5 and test, or flip logic (high profitability at high valuation is value trap flag).
- Fix HK fetcher: map CURRENT_ASSETS correctly, compute FCF from OCF + capex where available, fetch proper interest_bearing_debt.
Short-term (1 month):
- Add YidaiStore.get_scores_with_actual_price join and weekly_v2 filter pending_6m by signal_date <= today-180 via SQL, not in-memory.
- Introduce position sizer: risk-parity or Kelly fraction f = edge/odds, cap single 15%, sector 30%, enforce in DecisionLog.record() reject if portfolio_pct violates.
- Wire leading indicators into scorer: if indicator status negative -> -1 to relevant dim (e.g., b2b_leading_indicators revenue quality).
Medium-term (2-3 months):
- Replace naive prediction_6m = price*(1+growth*0.5) with DCF-derived target + analyst consensus; store confidence based on factor dispersion.
- Calibrate thresholds via audit: grid-search debt_ratio 0.60/0.70, PE percentile 0.70 etc to maximize by_dimension predictive_power.
- Add out-of-sample backtest: walk-forward 2020-2024 train, 2025-2026 test, report Sharpe not just accuracy.
Success metrics: Aim to raise accuracy_audit directional accuracy from placeholder ~50% to >55% for BUY, reduce anomaly false positives, and achieve review_engine.dimension_effectiveness stability across 90/180 windows before trusting weights.