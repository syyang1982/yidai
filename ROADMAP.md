# 意怠工程 — 持续改进路线图

> **创建日期:** 2026-06-06
> **原则:** 渐进式改进，每一步可独立上线，不破坏已有功能
> **更新方式:** 每完成一个工作项，更新状态；新需求追加到对应模块
> **完整文档:** 见 [README.md](README.md)

---

## 模块一：预警系统 ✅

> **目标：** 在基本面恶化影响价格之前发出预警
> **设计原则：** 先做确定性高的规则型预警，再做需要 AI 判断的软信号

### 1.1 财务异常检测（规则型，可自动化）

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W1.1.1 | 应收账款 vs 营收增速 | 连续 2 期应收增速 > 营收增速 +10% → 🔴 | ✅ `anomaly.py` |
| W1.1.2 | 存货周转率趋势 | 连续 3 期下降 → 🟡 | ✅ |
| W1.1.3 | 利润质量 | 经营现金流 < 净利润（连续 2 期）→ 🟡 | ✅ |
| W1.1.4 | 短贷长投 | 短期借款激增 + 长期投资增加 → 🔴 | ✅ |
| W1.1.5 | 商誉占比 | 商誉/总资产比例上升超 5% → 🟡 | ✅ |

**实现方式：** `src/analysis/` 新增 `anomaly.py`，在 `scorer.py` 评分时顺带检测，结果写入周报。

### 1.2 市场信号预警

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W1.2.1 | 高管变动追踪 | 解析公告，CFO/审计师变更 → 🟡 | ✅ `market_signals.py` |
| W1.2.2 | 公告情绪分析 | 关键词频率异常上升 → 🟡 | ✅ `score_announcement_sentiment` |
| W1.2.3 | 行业景气度 | 选定 2-3 个领先行业月度指标，拐点检测 → 🟡 | ✅ `score_industry_health` |

### 1.3 预警输出

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W1.3.1 | 预警等级 | 🔴 高风险（建议减仓）/ 🟡 关注 / 🟢 正常 | ✅ anomaly.py severity |
| W1.3.2 | 周报集成 | 预警结果自动写入周报 | ✅ weekly_v2.py _render_anomaly_alerts |
| W1.3.3 | 即时推送 | 🔴 级别预警立即推送（不等周报） | ✅ `manage.py anomaly` |

---

## 模块二：决策记录与复盘闭环 ✅

> **目标：** 每笔决策有完整上下文，定期复盘验证预测
> **核心价值：** 这是系统"进化"的关键——没有记录就没有反馈

### 2.1 决策日志

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W2.1.1 | 决策记录结构 | 设计 JSON schema：ticker、动作、价格、理由、预期、七维评分快照 | ✅ `src/strategy/decision.py` |
| W2.1.2 | `manage.py decision` 命令 | 交互式记录买入/卖出/持有决策 | ✅ add/list/show/review/outcome/stats |
| W2.1.3 | 与 trade-log.md 整合 | 迁移现有交易记录到结构化格式 | ✅ `scripts/migrate_trades.py` (41条交易) |
| W2.1.4 | 历史决策补录 | 从trade-log.md + 公司分析文件补录41条决策到decisions.duckdb | ✅ `scripts/backfill_decisions.py` |

### 2.2 预期验证

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W2.2.1 | 预期 vs 实际对比 | 决策后 N 天/周自动回检：价格、基本面变化 | ✅ `review_engine.py` |
| W2.2.2 | 预警准确性回检 | 每次预警后记录：预警后股价表现、提前多久、是否误报 | ✅ `record_alert_outcome` |
| W2.2.3 | 因子有效性分析 | 哪些评分维度真正有预测力？回测 N 笔决策 | ✅ `analyze_dimension_effectiveness` |

### 2.3 策略参数更新

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W2.3.1 | 阈值校准 | 基于复盘结果自动建议阈值调整（人工确认） | ✅ `scripts/calibrate_thresholds.py` |
| W2.3.2 | 维度权重调整 | 哪些维度该加权？基于历史预测力 | 🔲 |

---

## 模块三：评分系统增强 ✅

> **目标：** 让评分更准确、更有区分度

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W3.1 | 行业相对评分 | 与同行业对比，而非绝对阈值 | ✅ `benchmarks.py` |
| W3.2 | 多期趋势评分 | 不只看最新一期，看 3-5 年趋势 | ✅ `health.py` + `scorer.py` |
| W3.3 | 估值百分位优化 | 需要更长的历史价格数据 | ✅ `percentile.py` |
| W3.4 | 现金流折现 (DCF) | 简化 DCF 模型，作为估值维度补充 | ✅ `dcf.py` |
| W3.5 | ESG 简化版 | 治理评分（关联交易、独董比例、审计意见） | ✅ `esg.py` |

---

## 模块四：数据源扩展 ⏸️ 暂缓

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W4.1 | 港股季报自动采集 | 当前部分手动，需自动化 | 🔲 |
| W4.2 | 宏观数据 | 利率、PMI、社融等宏观指标采集 | 🔲 |
| W4.3 | 行业数据 | 半导体 BB 值、新能源车销量、房地产销售面积 | 🔲 |
| W4.4 | 替代数据 | 招聘数据、App 下载量、官网流量（低优先） | 🔲 |

---

## 模块五：报告与可视化 ✅

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W5.1 | 周报 v3 | 集成预警信号 + 决策建议 + 预期验证 | ✅ weekly_v2.py 已集成 |
| W5.2 | 个股深度报告 | `manage.py report 01810.HK` 生成单股分析 | ✅ `company_report.py` |
| W5.3 | 持仓健康度仪表盘 | 组合层面：集中度、行业暴露、风险预算 | ✅ `src/viz/dashboard.py` |
| W5.4 | Power BI 雷达图 | 七维评分可视化（当前 vs 上期） | ✅ ASCII radar in dashboard |

---

## 模块六：信号准确率审计 ✅ 已完成 (2026-08-28)

> **目标：** 用已有750条信号数据做回溯审计，验证评分系统是否有预测力

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W6.1 | 准确率审计模块 | `src/analysis/accuracy_audit.py` — 方向准确率/收益率/分组统计 | ✅ |
| W6.2 | 价格回填脚本 | 从eastmoney回填当前价格到actual_6m | ✅ |
| W6.3 | 维度预测力分析 | 哪个维度评分高时信号更准？ | ✅ |
| W6.4 | `manage.py audit` 命令 | CLI入口 + 格式化报告 | ✅ |
| W6.5 | 周报集成 | 周报中显示准确率摘要 | ✅ |

## 模块七：领先指标结构化追踪 ✅ 已完成 (2026-08-28)

> **目标：** 将watchlist.md中15家公司的文本领先指标编码为可追踪结构

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W7.1 | 领先指标数据模型 | `src/analysis/leading_indicators.py` + DuckDB表 | ✅ |
| W7.2 | 批量导入脚本 | 从watchlist.md提取13家公司23条指标 | ✅ |
| W7.3 | `manage.py indicators` 命令 | 查看/更新指标状态 | ✅ |
| W7.4 | 周报集成 | 领先指标区块(含预警) | ✅ |

## 模块八：组合约束层 ✅ 已完成 (2026-08-28)

> **目标：** 在信号层面检查组合风险，防止过度集中

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W8.1 | 约束检查模块 | `src/strategy/portfolio_constraints.py` | ✅ |
| W8.2 | 约束配置 | 单股/行业/市场/相关性组配置 | ✅ |
| W8.3 | `manage.py constraints` 命令 | CLI入口 | ✅ |
| W8.4 | 周报+仪表盘集成 | 约束检查结果写入周报和dashboard | ✅ |

---

## 模块九：决策反馈闭环增强 ✅ 已完成 (2026-09-13)

> **目标：** 建立长期持续的反馈闭环，提高决策质量
> **核心思路：** 标准化分类→缩短反馈周期→周报集成→认知偏差检测

### 9.1 决策理由分类学 (P1)

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W9.1.1 | 分类模块 | `src/strategy/reason_taxonomy.py` — 10种催化剂类型 + 8种卖出原因 | ✅ |
| W9.1.2 | DecisionRecord扩展 | 新增 reason_category + sell_reason 字段 | ✅ |
| W9.1.3 | 迁移脚本 | `scripts/migrate_reason_categories.py` — 41条记录已分类 | ✅ |
| W9.1.4 | 测试 | `tests/test_reason_taxonomy.py` — 5 tests | ✅ |

**reason_category 分布:** 组合再平衡(19), 低位机会(10), 获利了结(6), 止损/清仓(5), 技术形态(1)

### 9.2 快速反馈周期 (P2)

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W9.2.1 | 1周/1月快检 | review_engine.py 新增 `quick_review()` + `get_quick_review_stats()` | ✅ |
| W9.2.2 | DecisionRecord扩展 | 新增 expected_price_1w/1m + actual_price_1w/1m 字段 | ✅ |

### 9.3 周报复盘区块 (P3)

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W9.3.1 | 复盘区块 | weekly_v2.py `_render_decision_review()` — 4个子区块 | ✅ |

**区块内容:** 🆕本周新增决策 → ⏰到期快检(1w/1m) → 📈累计决策胜率 → 💡最近教训

### 9.4 认知偏差检测 (P4)

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W9.4.1 | 偏差字段 | DecisionRecord 新增 confidence_level/counter_argument/regret_flag/market_regime | ✅ |
| W9.4.2 | 偏差检测 | review_engine.py `analyze_cognitive_biases()` — 3种模式 | ✅ |
| W9.4.3 | 偏差报告 | `format_bias_report()` 格式化输出 | ✅ |

**偏差模式:** 过度自信(高信心+亏损), 逆向成功(低信心+大赚), 缺失反面论据(无论据+亏损)

---

## 模块十：持仓实体 + 决策时闭环 ✅ 已完成 (2026-09-13)

> **目标：** 学习单位从「单笔成交」升级为「持仓论点」；写入前检索同类历史；缺失数据不得发出 BUY。

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W10.1 | Position 实体 | `src/strategy/position.py` — thesis/invalidation/book/FIFO 批次 | ✅ |
| W10.2 | 决策挂载持仓 | `DecisionRecord.position_id`；`manage.py position` | ✅ |
| W10.3 | 类比检索 | `src/strategy/analog.py` — 同玩法/同标的/信心校准，写入前打印 | ✅ |
| W10.4 | 过程硬约束 | 实盘 BUY/ADD 必须 confidence + counter_argument + invalidation | ✅ |
| W10.5 | 缺失数据阻断 BUY | `data_complete=False` → HOLD；current_ratio / IBD / FCF | ✅ |
| W10.6 | 决策库归一 | 规范库 `db/decisions.duckdb`（不再写入 signals.duckdb 的 decision_log） | ✅ |
| W10.7 | Hermes 交接 | `docs/hermes-decision-loop.md` + yidai-operations skill | ✅ |

**CLI:**
```
python manage.py position list|show|set|rebuild
python manage.py decision add TICKER --confidence 4 --counter-argument "..." --invalidation "..." --book compound
```

**原则:** 评分系统是风险过滤器（REDUCE 可靠，BUY 不可靠）。BUY 只表示「有资格研究」，不是下单指令。

---

## 待做事项

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W2.1.3 | 与 trade-log.md 整合 | 迁移现有交易记录到结构化格式 | ✅ `scripts/migrate_trades.py` |
| W2.3.1 | 阈值校准 | 基于复盘结果自动建议阈值调整（人工确认） | ✅ `scripts/calibrate_thresholds.py` |
| W2.3.2 | 维度权重调整 | 哪些维度该加权？基于历史预测力 | 🔲 |
| W4.1 | 港股季报自动采集 | 当前部分手动，需自动化 | ⏸️ 暂缓 |
| W4.2 | 宏观数据 | 利率、PMI、社融等宏观指标采集 | ⏸️ 暂缓 |
| W4.3 | 行业数据 | 半导体 BB 值、新能源车销量 | ⏸️ 暂缓 |
| W4.4 | 替代数据 | 招聘数据、App 下载量、官网流量 | ⏸️ 暂缓 |

### 2026-10-14 失效条件可自动观测（P0，本日完成）

> 来源：2026-10-14 组合诊断。核心发现是「飞轮不闭环」：架构完整但无数据流入，
> `review_results` / `alert_reviews` 均 0 行，失效条件无法自动触发。

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| I1 | 指标历史表 | `leading_indicators.duckdb` 新增 `indicator_history`（ticker+name+period 主键，同周期幂等覆盖）；`update_value` 自动写历史。**没有历史表，「连续两季」在数据层就无从判定** | ✅ |
| I2 | 失效评估器 | `src/strategy/invalidation_evaluator.py` — 读历史做「连续N期」判定，输出 触发/红/黄/绿/未知。单期红≠失效；`required_periods_from` 翻译「2季/3个月/1期」；恢复后连红重置 | ✅ |
| I3 | 采集器 | `scripts/collect_invalidation_indicators.py` — 东财港股 `RPT_HKF10_FN_MAININDICATOR`（89字段）+ 美股逐项报表 + Yahoo 行情。一次回填 **76 条历史值**，覆盖 10 条可自动化指标 | ✅ |
| I4 | 评估器解耦 | `evaluate_ticker(..., specs=)` 支持传入 specs，否则回退 WATCH 表。原实现硬绑定 WATCH，无法测试也无法监控新持仓 | ✅ |
| I5 | LX 数据修正 | 净资产覆盖倍数 **10.7 → 15.49**。根因：乐信 1 ADS = 2 普通股，原值未统一 ADS 口径。**该失效腿实际是绿灯（15.49 ≫ 1.0），未造成误判** | ✅ |
| I6 | 自动监控 cron | `91302eced8be` 每交易日 19:00 — 采集 → 评估 → 对比 `db/invalidation_monitor_state.json` → 变化才提醒 | ✅ |
| I7 | 回归测试 | `tests/test_strategy/test_invalidation_evaluator.py` 20 个用例（历史幂等/连续判定/期数翻译/单期不触发/恢复重置/越低越好） | ✅ |

**当前真实失效视图**：12 持仓 / 35 条腿 — 触发 0 · 红 2 · 黄 2 · 绿 13 · 未知 18

- 🔴 **名创 海外同店 -3.0% [2026H1]** — 第 1 期红。Q3 财报（预计 11 月）若再为负即触发失效 → D2 直接受益
- 🔴 **速腾 经营现金流 -4.20亿 [2026-06-30]** — 连红 3 期，但该腿判定为 1 期，需人工判定是否构成失效
- 🟢 **LX 净资产覆盖倍数 15.49**（修正后）— D1 的「每股净资产不再覆盖市值」这条失效腿**未触发**

**遗留（诚实记录）**：18 条腿仍无数据，需人工或网络检索 — SU7月交付、FILA/始祖鸟同店、
手术量、车型定点数、大客户CapEx、DAU、广告收入、存货周转、IP授权、新游流水、版号、
SGP.AX 全部 3 条（东财无澳股数据）。这些是运营数据，不在财报 API 覆盖范围内。

**未做（下一步候选）**：触发历史表 — 03888 曾在 2025 连续两季红后恢复，若不记录
「曾经触发过」，这类事件会永久丢失。见 `W6.x`。

### 2026-09-22 持仓诊断待办（P0 决策类）

> 来源：2026-09-22 组合诊断。价格 -14.1%、4 只票占 85.6% 浮亏、3 条 CRITICAL 卖出提醒。

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| D1 | 乐信 LX 终局判定 | 查 2026Q2 每股净资产 vs 市值、不良率/信贷成本、股息是否维持。触发失效条件 → 清仓剩余；未触发 → 写观察哨 + 检查日期 | ✅ **失效已触发**（不良率连升3季，条件需2期）待用户拍板 |
| D2 | 名创 9896.HK 锁定 Q3 判决日 | 海外同店 Q2+Q3 是否连续负增长。财报日复核，跌破 HK$12 强制清仓 | ✅ 判决日=11月下旬（历史模式11/21，尚未公告）；Q2已红第1期 |
| D3 | 速腾 2498.HK 硬止损豁免备案 | thesis 止损 HK$12，写决策日志 + 观察哨（Q3 毛利率 ≥20%、车型定点数未连续两季净减少），豁免到期 2026-12-31 | ✅ 三项失效均未触发；毛利率21.79%距红线1.79pp，定点数186→194净增 |
| D4 | 9/13-14 决策复核 | confidence + counter_argument 填充率检查（旧决策多为空，认知偏差检测失效） | ✅ 发现两问题：执行未闭环 + **数据归属污染**（agent文本混入用户决策字段） |

> 复盘全文：`knowledge/analysis/2026-10-14-d1-d4-review.md`
> 关键工程修复（D1 复盘中发现）：评估器原只有**水平判定**，会漏掉
> 「值未到极端区间但连续N期恶化」的腿——LX 不良率 3.6% 就是这样被误判为安全。
> 已加**趋势判定** `consecutive_periods_trending`，任一判定满足即触发。1015 tests pass。

#### D4 衍生修复：决策归属分离（2026-10-14 完成）

用户指出「自我批评不是我写的」，查实：`lessons.md #7` 与 decision_log 里 5 段
`review_notes` 的「复盘: 否决止损是沉没成本谬误」**均为 agent 文本**，与用户 9/13
真实决策（HOLD, confidence 3-4）方向相反，且无作者标注。危害：W9.4 认知偏差检测读的
正是这些字段 —— **检测的是 agent 的话，不是用户的决策，填充率多高都测不出东西**。

| # | 修复 | 说明 |
|---|------|------|
| A1 | `decision_log` 加 `author` / `agent_review` 列 | `author` = 谁做的决策（user/agent/agent_mixed/unknown）；agent 分析只能进 `agent_review` |
| A2 | `DecisionRecord` 加同名字段 + 写入路径 | `review_notes`/`lessons` 归属用户，`agent_review` 归属 agent，严格分开 |
| A3 | 迁移 5 条污染记录 | agent 文本移入 `agent_review`，`review_notes` 清空，`author='agent_mixed'`；存量未标注记录标 `unknown`（不能假设都是用户写的） |
| A4 | 补建表 schema + ALTER 兜底 | CREATE TABLE 与 ALTER 列表都加了新列。**教训：在 INSERT 列清单中间插列，必须同步改 CREATE TABLE，否则新库建表 42 列而 INSERT 44 列，全量测试直接炸 33 failed + 15 errors** |
| A5 | 用户 LX 继持决策入库 | `decision_id=e38f24f0`, `author='user'`, `confidence_level=0`（用户未给信心分，**不代填**） |

**归属分离后的 author 分布**：unknown 45 / agent_mixed 5 / user 1
> 45 条 unknown 是历史遗留，无法回溯归属——**复盘时这些记录不得当作用户立场引用**。

回归测试 `tests/test_strategy/test_decision_attribution.py` 6 例。全量 **1021 passed**。

### 2026-09-22 数据修复待办（P1/P2 工程类）

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W5.1 | constraints 读真实持仓 | `cmd_constraints` 现用 `create_sample_holdings()` 假数据 → 假绿灯（小米 61.1% 超 30% 硬线却报合规） | ✅ 2026-09-22 改读 portfolio_data.json |
| W5.2 | 对账两套持仓数据 | decisions.duckdb vs portfolio_data.json：5 处股数（LX/2252/3896/09988/01810）+ 1 处均价（3888）不一致，需确认口径 | ✅ 2026-09-25 用户裁决后完成：01810=37,400 / 2252=1,500 / 9988=3,100 / LX=2,250 以 json 为准，3896 以券商口述为准（12,000 = 8,000@¥4.708 + 4,000@HK$5.01，覆盖 json 的 10,000@5.651），3888 股数 4,400。新增 `position reconcile`（写权威批次 + `reconciled_at`，rebuild 跳过）+ `Lot.currency` + `to_hkd/from_hkd`（口径：港股成本一律港币、人民币按汇率折算），并回填了存量 lots 币种。实测 `manage.py loop` 两库对账 7 处 → 全部一致，`position rebuild` 连跑 2 次股数/行数不变，986 passed。同日二裁 3888 均价：券商 2,400@¥23.997 + 2,000@HK$24.52 → 综合 HK$26.148（决策库与 json 已同口径）。共 6 只持仓已 reconcile。遗留：decision_log 历史漏记误记（LX 9/14 REDUCE 900、2252/9988 漏记成交等）未清理，已由对账隔离、不影响持仓与提醒 |
| W5.3 | dashboard.py CNY→HKD 换算 | 名创显示 -54.7% 应为 -60.5%（sell_alert.py 已修，dashboard.py 未跟上） | ✅ 2026-09-22 改用 `to_hkd`，实测 -60.5% |
| W5.4 | ASX 持仓漏计 | dashboard 完全不显示 SGP.AX；portfolio_status 总计漏计，dashboard 又按 1:1 当 HKD | ✅ 2026-09-22 dashboard 补 AUD_PER_HKD=0.17936；2026-09-25 发现 portfolio_status.py 仍只分 USD/HKD/CNY 三组 → SGP.AX 整段不渲染、TOTAL 少 25,145 HKD（成本少 23,520），已补 AUD 分组 + 成本/市值换算 + 未识别币种兜底桶 + 渲染行数完整性核对，实测 TOTAL 1,631,153 与 dashboard 一致 |
| W5.5 | 小米集中度显式备案 | 61.1% 超 30% 硬线，写成「已知偏离 + 计划」（HK$33-35 减 1-2K 短线仓、核心 ~34K） | 🔲 待用户决策 |
| W5.6 | 清理 1361.HK 残留 | 0 股仍占 dashboard 一行 + sell_targets 目标价 HK$6.5 | ⏳ dashboard 已归入「已清仓（0 股，不计入）」，sell_targets 待清 |
| W5.7 | 3888.HK 金山软件观察 | REDUCE 24/40、-6.6%，止损 -30%，不加仓 | 🔲 待用户决策 |
| W5.8 | `position rebuild` 非幂等 | 每跑一次把所有持仓 lot 重放一遍 → 股数翻倍（实测 12 个 open 全部 ×2），已平仓持仓还会重复新增行 | ✅ 2026-09-25 `PositionBook.apply_fill` 按 decision_id（缺 id 时按日期+方向+股数+价格）去重，重放已平仓买入时复用原记录；实测连跑 2 次股数/行数完全不变 |
| W5.9 | loop 两库对账假差异 | `_norm_ticker` 没统一 `.ASX`/`.AX`，SGP.AX 同一持仓被报成 2 处差异 | ✅ 2026-09-25 归一后 7 → 0 |
| W5.10 | decision_log 历史漏记/误录 | 决策净额与券商对不上：LX 漏 450 股且首笔价格记成综合均价、9/14 REDUCE 900 无成交；01810 SC 批 12,000 vs 12,400；2252 漏 1,000 股；600036 买入被录成 REDUCE 且漏 7/3 卖出 | ✅ 2026-09-25 已改：LX 首笔改 1,800@US$6.29 + 补 450@2.11 + 9/14 改 HOLD（清 sell_reason）；01810 SC 改 12,400@39.688；2252 补 1,000@24.24；600036 6/30 改 BUY + 补 7/3 卖 300@36.82。14 只中 11 只决策净额=券商；**遗留 3 只需券商成交明细**：3896（决策 14,000 / trade-log 摘要 10,000 / 券商 12,000 三套数）、9988（trade-log #013 只写「+400 more later +100 later」，价格日期皆缺）、1361（两套持仓互斥，缺第二段 6,000 股的买入记录，P/L 备注暗示成本 HK$4.57）|

### 2026-09-22 闭环打通（W7）

> **问题：** 代码审查发现 `review.py`(785 行) + `review_engine.py`(697 行) 共 1482 行**零入口**（只被 tests 引用），复盘环节从未真正运行；`DIMENSION_WEIGHTS` 硬编码在 `models.py`，复盘结论无法回到评分层。四环节只有①分析真正跑通 → **是开环，不是闭环**。

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| W7.1 | 环节③接活复盘引擎 | `manage.py review`（pending/run/quick/dims/biases/alerts/stats）——1482 行死代码首次有 CLI 入口 | ✅ 实测 `review pending` 列出 80 条到期决策 |
| W7.2 | 环节④反灌层 | 新建 `src/strategy/feedback.py`：复盘结论 → 维度有效性 → `DIMENSION_WEIGHTS` + 阈值建议 | ✅ `manage.py feedback [--apply\|--reset]`，带 30 条/维安全闸 |
| W7.3 | 闭环健康检查 | 新建 `src/ops/closed_loop.py`：逐环节数据流体检 + 断点显式列出（只读） | ✅ `manage.py loop`，实测报出 4 处断点 |
| W7.4 | CJK 对齐表格工具 | 新建 `src/ops/text_table.py`（双宽字符列宽），供 feedback/closed_loop 复用 | ✅ |
| W7.5 | DuckDB 连接复用 | `DecisionLog`/`ReviewEngine` 支持 `conn=`，消除同文件双写锁 | ✅ |
| W7.6 | 统一决策记录口径 | DecisionLog 为唯一决策事实源（decision_log + positions），SignalTracker 只作信号事实层 | ⏳ 代码已按此分层，数据待 W5.2 对账后收敛 |
| W7.7 | 信号分桶兜底 + 完整性核对 | dashboard 未知信号不再静默丢持仓，渲染后核对行数 | ✅ 实测 12 个非零持仓全部渲染 + 1 个已清仓单列 |
| W7.8 | 回测漏评 D6 导致 BUY 被压制 | `backtest.py` 只评 7 维却把 total(满分35)喂给 8 维/40 分校准的 `_compute_grade`/`_compute_signal`（BUY 需 ≥33 = 35 里拿 94%）→ 回测几乎永不 BUY | ✅ 2026-09-22 与 scorer.py 同口径评 D6 |
| W7.9 | 测试漂移清理 | 8 个失败全在改动前就存在（已用干净 HEAD worktree 对照确认）：6 个是 /35→/40 分档未同步、2 个是硬编码日期随时间腐烂 | ✅ 982 passed / 0 failed |
| W7.10 | 无分红公司结构性够不到 A | `dividend=0 表示「无数据」`（代码注释明写），却仍按 0 计入 total → 不发股息的成长股满分只有 35，比发股息的低一档 | ✅ 2026-09-22 按实评维度归一化（用户裁决）：新增 `models.normalize_total` + `ScoreResult.scored_dimensions/normalized_total`，`dividend_quality.score` 增 `has_data`；`scorer`/`backtest`/`review`(3处)/`manage.py`(2处)/5 个 `scripts/analyze_*.py` 共 12 个调用点全改 |

### 2026-10-05 事件引擎待办（E1-E3）

> 来源：2026-10-05 事件简报 cron。`manage.py events --days 3` 报「未来3天共 41 条事件」，实际是**同一事件的 41 份拷贝**。

| # | 工作项 | 描述 | 状态 |
|---|--------|------|------|
| E1 | events.duckdb 无去重 | `EventStore.add_event` 对 `--refresh` 无条件 INSERT（uuid 主键不冲突）→ 1,395 行只有 35 个唯一事件，每跑一次 +34 行。需按 `(title, event_date, event_type)` 幂等 upsert 并清理存量重复 | ✅ 2026-10-24 修复+验证：`add_event(dedup=True)` 按业务键（类型+标题+日期+来源）跳重、`dedupe()` 清存量、`--refresh` 改为重建内置日历（先删旧内置再插）。实测连跑两次 refresh 行数稳定 52 行=52 唯一、0 重复组 |
| E2 | RBA 决议日全错 | `src/events/calendars.py` 硬编码的 2026 六次 RBA 日期（07-08/08-05/09-02/10-07/11-04/12-02）全部与官方不符；官方 2026：02-03、03-17、05-05、06-16、08-11、09-29、11-03、12-08（**10 月无会议**）→ 10-07「澳洲RBA利率决议」是幽灵事件，且 RBA 是 SGP.ASX 的核心变量 | ✅ 2026-10-24：RBA 已按官方 8 日期落库（10-07 幽灵事件已清）。同批按官方源核对修正：FOMC 7-30→7-29、9-17→9-16、10-29→**10-28**、12-17→**12-09**（federalreserve.gov）、中期选举 11-05→**11-03**、美国10月CPI 11-12→**11-10**（BLS）。calendars.py 头部已注释核对来源 |
| E3 | `events --type` 直接崩溃 | `manage.py:1427` 调 `store.get_by_type(event_type, days=days)`，但 `EventStore.get_by_type()` 不接受 `days` → TypeError（2026-10-05 实测复现） | ✅ 2026-10-24：`get_by_type(event_type, days=None)` 已收 days（None=全量原语义），实测 `events --type earnings --days 30` 正常返回。`tests/test_events/` 67 passed（含跳重/dedupe/get_by_type 窗口回归） |

---

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-06-06 | 创建路线图，基于投资策略框架文档整理工作项 |
| 2026-06-06 | ✅ W2.1.1 决策记录结构 (`src/strategy/decision.py`) — 24 tests |
| 2026-06-06 | ✅ W2.1.2 `manage.py decision` CLI — add/list/show/review/outcome/stats |
| 2026-08-28 | 📋 模块六/七/八规划完成 — 信号准确率审计+领先指标追踪+组合约束层 |

| 2026-09-09 | ✅ W2.1.3 trade-log迁移脚本 (41条交易→DuckDB决策日志) |
| 2026-09-09 | ✅ W2.3.1 阈值校准模块 (157条信号分析, 发现市场环境自适应需求) |
| 2026-09-13 | ✅ W2.1.4 历史决策补录 (41条交易→decisions.duckdb, 37条含七维评分) |
| 2026-09-13 | ✅ 模块九：决策反馈闭环 (P1理由分类学+P2快检+P3周报集成+P4认知偏差) |
| 2026-09-13 | ✅ 模块十：持仓实体+类比检索+缺失数据阻断BUY；规范库 decisions.duckdb |
| 2026-09-22 | 📋 持仓诊断待办登记：D1-D4（P0 决策）+ W5.1-W5.7（P1/P2 数据修复） |
| 2026-09-22 | ✅ W5.1/W5.3/W5.4 数据修复（constraints 真实持仓、dashboard 币种换算、ASX 漏计） |
| 2026-09-22 | ✅ W7.1-W7.5/W7.7 闭环打通：`manage.py review`/`feedback`/`loop` 三个新入口，1482 行复盘死代码接活，权重反灌层建成 |
| 2026-09-22 | ✅ W7.8 修复回测漏评 D6（7 维 total 喂给 8 维分档 → BUY 被系统性压制） |
| 2026-09-22 | ✅ W7.9 清理 8 个既有测试漂移（/35→/40 分档未同步 6 个 + 硬编码日期腐烂 2 个），982 passed / 0 failed |
| 2026-09-22 | 📋 W7.10 记录设计取舍：无分红公司 total 满分只有 35，结构性够不到 A / BUY |
| 2026-09-22 | ✅ W7.10 按实评维度归一化落地（用户裁决）。扫出并修掉 12 个同类调用点，含 6 处**从没成功跑过**的 `_compute_signal` 少传 dividend + dict 当 int 求和；`analyze` 显示改为「raw N/M（实评 k/8 维 → 归一 X/40）」。983 passed / 0 failed |
| 2026-09-22 | 📌 W5.2 两库对账仅登记待办（用户明确不动手）：7 处不一致 = 5 处股数 + 2 处 ticker 写法（`SGP.AX`/`SGP.ASX`、`01810.HK`/`1810.HK`），口径确认后用 `position set` 修 |
| 2026-10-05 | 📋 事件引擎待办登记 E1-E3：events.duckdb 刷一次 +34 行无去重（1,395 行/35 唯一）、RBA 2026 日期全错（10-07 为幽灵事件）、`events --type` TypeError |
| 2026-10-24 | ✅ E1-E3 事件引擎修复完成并验证：去重+存量清理（1,395 行 → 52 行=52 唯一）、`--refresh` 重建内置日历（错误日期/幽灵事件不再残留）、RBA+FOMC+CPI+中期选举日期按官方源修正、`events --type` 修复。`tests/test_events/` 67 passed |
