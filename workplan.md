意怠工程 (yidai) — 提高决策科学性与成功率的诊断与规划建议
说明: 当前为 Plan Mode，只做观察与规划，不执行任何代码/配置修改。以下分析基于 ~/.hermes/yidai 现场文件证据。
1. 现状诊断 — 做得好的地方
1. 闭环设计完整: handbook.md:9-24 三层架构 + README.md:48-66 已实现 数据采集(src/data/fetcher.py:1, src/data/store.py:1) → 评分(src/analysis/scorer.py:1) → 信号(src/data/models.py:170) → 决策日志(src/strategy/decision.py:1) → 复盘(src/strategy/review_engine.py:1) → 报告(src/report/weekly_v2.py:1)，在个人系统中罕见。
2. 七/八维框架有工程类比且可量化: handbook.md:22-36 D1-D8 映射到数据质量断言，src/analysis/profitability.py:1等5个量化维度全自动，D7/D8 结构化待人工打分，符合「可量化、可回测、可自动化」理念。
3. 高测试覆盖: tests/ 44文件/891个用例，覆盖异常预警、DCF、回测v2、信号追踪，质量优于多数个人量化项目。
4. B2B领先指标方法论深度: b2b_leading_indicators_framework.md:1 对36家公司的PE失效分析与五层领先指标分类是核心差异化资产，但尚未与评分联动。
5. 已启动自我审计: src/analysis/accuracy_audit.py:1 + src/strategy/review_engine.py:1 尝试回答「哪些维度真有用」，ROADMAP.md:111 模块六/七/八已标志完成。
2. 核心问题 — 制约成功率的 7 类风险
2.1 评分与信号的不一致 (最高优先级)
- 40分制 vs 35分制分裂: src/data/models.py:153 等级 A 33-40 / src/analysis/scorer.py:210 加权阈值33，但 handbook.md:311 仍为 29-35(A)且 src/report/weekly_v2.py 阈值未同步，导致同一家公司在仪表盘与周报中等级不同。
- 信号逻辑双重实现: src/data/models.py:170 _compute_signal 与 handbook.md:325 generate_signal 规则不完全一致（后者对 D6股权限重不同），易分叉。
- 加权总分仅用于 BUY 门槛: src/data/models.py:48 _compute_weighted_total 最大41分但 grade 仍用原始 total_score，用户易误读。
2.2 定性维度污染定量信号
src/analysis/scorer.py:347 qualitative_scores.get(...,0) 默认0，但 manage.py analyze --all 若未手动输入则填3（见探索报告）。knowledge/companies/01810.HK.md:1 小米 33/40 中 D7/D8 贡献6分（默认值），70个档案多数为stub，BUY 判定 src/data/models.py:212 weighted>=33 && valuation>=4 && health>=3 && growth>=3 实被固定分抬高，削弱区分度。
2.3 审计结果反直觉且可能过拟合
src/data/models.py:11 注释：盈利-0.35 现金流-0.42 反预测力，DIMENSION_WEIGHTS:29 将其降权至0.5。这意味「盈利越高、现金流越好反而预测未来涨越差」——典型周期顶部/价值陷阱特征，但直接降权而非反转或条件化，会丢失信息。小样本(~750条信号，多为 status=active 未到期，见探索报告) + 牛市幸存样本会导致权重不稳定。
2.4 数据质量缺口
- 港股 fetcher.py:823 中 current_assets/interest_bearing_debt/free_cash_flow 常为 None/src/analysis/scorer.py:94-100 缺失则跳过，health与cashflow 退化为中性3分。
- 估值 src/analysis/scorer.py:157 cash = current_assets 近似过度，EV/EBITDA 失真。
- src/analysis/insider_activity.py:1 与 ownership_structure.py:1 依赖东财非官方接口，失败时静默空列表，无预警即被误认为安全。
2.5 领先指标与决策层脱节
b2b_leading_indicators_framework.md:159-470 定义了36家×5层×数十指标 + src/analysis/leading_indicators.py:1 的 DuckDB 存储，但 src/analysis/scorer.py:276 score_all 从未读取它，周报仅列「待更新」。36家同时追踪超出个人精力，watchlist.md:13 中大量 PE<xx 目标价实质仍回归PE。
2.6 风险/仓位管理仅做「提示」不做「约束」
src/strategy/portfolio_constraints.py:1 max_single 25%/sector 40% 仅 format_report 提示，src/strategy/decision.py:124 record 不校验 portfolio_pct，无波动率目标、Kelly、止损、流动性过滤。src/strategy/backtest_v2.py:1 的 30%回撤才强制 REDUCE 为时过晚。
2.7 回测与审计的可信度不足
- src/analysis/accuracy_audit.py:1 依赖 Yahoo fetch_price_at_date 0.3s×750×4窗口≈900s，易超时且无 Eastmoney 兜底，reports/weekly_v2_2026-08-23.md:1 显示 300+条未到期信号被全量倾泻。
- src/strategy/backtest.py:1 vs backtest_v2.py:1 均无 walk-forward（训练/测试期分离）、无交易成本/滑点、基准仅 buy-and-hold。
3. 改进规划 — 按「科学性→成功率」优先级排序
Plan A: 地基修复 (1-2周, 零风险高回报)
1. 统一尺度: 选定 40分制，同步 handbook.md:311, ROADMAP.md:1, src/report/weekly_v2.py, src/strategy/decision.py:305 的 /35 字样与阈值表；ScoreResult 文档化 weighted_total 用途。
2. 定性显式化: manage.py score 未设置时显示 ? 且不计入 total_score（或单独 total_quant），BUY 要求 D7/D8 已人工确认；批量 analyze --all 不再自动填3。
3. 修复港股数据: 在 src/data/fetcher.py:1 正确映射 CURRENT_ASSETS，用 OCF + capex 推导 free_cash_flow，interest_bearing_debt 缺失时回退 total_liabilities * 0.5 并打标签。
4. 周报过滤: weekly_v2.py 按 signal_date <= today-180 SQL 过滤待复盘信号，修复「暂无评分数据 63/64」问题。
Plan B: 评分科学化 (2-4周)
1. 权重校准 walk-forward: 不直接用全量审计权重。将 750 信号按时间切 2024前/2024后，网格搜索 debt_ratio 0.6/0.7, pe_pct 0.6/0.7, DIMENSION_WEIGHTS 使 by_dimension predictive_power 在测试集稳定>0.15才采纳；对反预测维度做条件化而非一刀切降权：如 valuation<2 时 profitability 高分视为价值陷阱扣分。
2. 估值分层: 对 B2B 公司（b2b_leading_indicators.md:77 结论）主用 PS/EV/EBITDA/FCF Yield，PE仅作辅助；在 src/analysis/valuation.py:1 增加 ps_score/ev_score 并按 industry 切换。
3. 成长质量细化: src/analysis/growth.py:1 区分 QoQ vs YoY，all_annual_data 仅用年报，避免季度拼接失真；引入 ROE* (1-payout) 可持续增长率交叉验证。
Plan C: 领先指标实战化 (4-6周)
1. 聚焦 Top10: 从 36家 收敛至持仓+观察清单前10（小米/拓普/来福/金山云/海光/英维克/中际/工业富联/铖昌/万国数据），每家仅保留 b2b_leading_indicators.md:159 中 3个核心指标（如金山云 AI云增速/合同负债/大客户CapEx）。
2. 打通评分: leading_indicators.py:get_alerts 若 status=negative 则 scorer.py 对应维度 -1（例：CapEx下调 → growth-1），周报高亮。
3. 自动化采集: 优先接 中汽协/乘联会 月度产量、WSTS 半导体销售额、Boeing/Airbus 交付、DoD/NDAA 预算——均为公开免费源，降低付费依赖（见 b2b_leading_indicators.md:832 速查表）。
Plan D: 组合约束硬化 (并行)
1. 强制校验: DecisionLog.record 若 portfolio_pct > max_single_pct 或 check_correlation_groups 触发则拒绝并提示分批；在 src/strategy/portfolio_config.py:1 将示例小米 60% 修正为演示用例。
2. 引入风险预算: 增加波动率目标（单股年化波动>60%则减半仓）、流动性过滤（日均成交额<1亿跳过）、止损纪律（技术破200MA + 基本面降级双确认）。
3. 替代数据低优先: ROADMAP.md:152 W4.4 招聘/下载量仅对 B2C（如 watchlist.md:66 361度）可选试点。
Plan E: 验证闭环硬化
1. 迁移历史交易: ROADMAP.md:151 W2.1.3 trade-log.md → decision_log，补全 dimension_scores 快照，否则 review_engine.py:analyze_dimension_effectiveness 无基线。
2. 修复审计: accuracy_audit.py 增加 Eastmoney 兜底、time_window_prices 缓存、空窗期信号不计入分母；在 manage.py audit 中输出 direction_accuracy 置信区间（需 N≥30）。
3. 回测升级: backtest_v2.py 加 0.15% 费率+滑点，报告 Sharpe/Sortino/Calmar，且 walk-forward 2020-2024训练 →2025-2026测试。
4. 预期收益与度量
- 完成 Plan A 后，信号一致性与数据完整度可验证（pytest tests/ -q 全绿 + manage.py anomaly --all 无缺失字段）。
- 完成 Plan B/C 后，目标 accuracy_audit BUY 方向准确率从 ~50% 提升至 >55%（6M窗口，样本≥100），且 health/valuation 预测力在多窗口稳定。
- 完成 Plan D 后，组合单股暴露<25%、行业<35% 强制达标，回撤归因可追溯到决策而非事后解释。
5. 需要与您确认的取舍
1. 研究广度 vs 深度: 是否接受将 36家 领先指标收敛至 Top10 以换取可执行性？
2. 定性权重: 是否愿意在未人工打分时暂不给 BUY 信号（会减少信号数量但提高纯度）？
3. 风险偏好: 组合约束改为「硬拒绝」是否符合您的交易习惯，还是仅需「强提示」？
4. 数据源投入: 是否愿意为 Wind/iFinD 付费以补全港股 interest_bearing_debt/capex，或接受近似估算？