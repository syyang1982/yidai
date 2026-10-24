# Hermes 交接：持仓闭环（2026-09-13）

给后续 Hermes session 用。这是意怠工程从「研究工厂」转向「决策飞轮」的契约。不要回退到只记成交、不记持仓。

## 一句话

**学习单位是持仓（Position），不是单笔成交。** 评分系统是风险过滤器，不是买入引擎。缺失数据 ≠ 中性 3 分，缺失就不得 BUY。

## 规范数据库

| 用途 | 路径 | 说明 |
|------|------|------|
| 决策 + 持仓 | `~/.hermes/yidai/db/decisions.duckdb` | **唯一** `decision_log` / `positions` |
| 系统信号 | `~/.hermes/yidai/db/signals.duckdb` | 只放 `signal_records`，不要再往这里写 decision |
| 财报评分 | `~/.hermes/yidai/db/yidai.duckdb` | 财务/评分 |

`manage.py decision` 和 `manage.py position` 都指向 `decisions.duckdb`。  
`signals.duckdb` 里可能残留一份旧的 31 列 `decision_log`（43 行）——只读，当作历史残骸。

## 两个循环不要混

| 循环 | 问题 | 样本 | 用途 |
|------|------|------|------|
| 系统信号 | 八维评分能否预测 30–90 日价格？ | ~750 条 signal | 审计 / REDUCE 过滤器 |
| 个人决策 | *我* 这样买卖是否变好？ | ~41 笔 fill → 若干 position | 玩法统计、类比检索 |

不要用信号审计结果去改个人仓位规则；不要在 ~40 笔交易上拟合 8 维权重。个人侧只统计 **playbook**（`reason_category` + market）。

## Position 字段

打开仓必须有：

- `thesis` — 必须为真的故事
- `invalidation` — 与盈亏无关的无条件卖出条件
- `book` — `compound`（6–12m）或 `tactical`（1w–1m）
- `horizon` — 用哪个窗口复盘价格
- lots — FIFO 批次

同一 ticker 同时最多一个 `open` position。清仓后再买 = 新 `position_id`（新论点）。

历史重建后 `invalidation` 可能是 `待补全`。实盘开仓不允许这个值。

## 写入一笔 BUY/ADD 的顺序（强制）

```bash
cd ~/.hermes/yidai
python manage.py decision add 01810.HK \
  --action BUY --price 27.24 --shares 600 \
  --reason "低位加仓摊低成本" \
  --thesis "汽车+IoT 长期复合" \
  --confidence 4 \
  --counter-argument "AI 投入拖累现金流" \
  --invalidation "汽车交付连续两季下滑" \
  --book compound --horizon 12m
```

CLI 会：

1. 自动分类 `reason_category`
2. 打印 **类比检索**（同标的 + 同玩法胜率 + 同信心水平校准 + lessons/principles）
3. 挂到 open position 或开新仓（无失效条件则拒绝）
4. `enforce_process=True`：缺反面论据或信心则拒绝写入

禁止：先成交再补 `counter_argument`。事后合理化会毁掉偏差检测。

## 持仓命令

```bash
python manage.py position rebuild          # 从 decision_log 回放 FIFO
python manage.py position list             # 默认只看 open
python manage.py position show 01810.HK
python manage.py position set 01810.HK \
  --thesis "..." --invalidation "..." --book compound --horizon 12m
```

Hermes 在记录交易后应 `position show` 确认论点/失效条件仍在。周报会列出 open positions；失效条件为「待补全」的会打警告。

## BUY 门闩（评分）

`src/data/models.py` `_compute_signal`：

BUY 需要同时满足：

- 加权总分 ≥ 门槛（regime 可调）
- valuation ≥ 4, health ≥ 3, growth ≥ 3
- `qualitative_confirmed`（D7/D8 人工且 >0）
- **`data_complete`**

`data_complete=False` 当缺：

- `current_ratio`（常因港股 `current_assets` 缺失）
- `interest_bearing_debt`
- `free_cash_flow`（可用 OCF − |capex| 推导；推导不了就缺）

缺字段时等级仍可算，信号最多 HOLD，不会 BUY。  
**缺失跳过检查后打 3 分，只能进总分，不能进买入门。**

REDUCE 仍然优先：health < 2 或 cashflow < 2。审计结论不变：REDUCE 可用，BUY 只是研究名单。

## 失效条件自动观测（2026-10-14 起）

`python manage.py position watch` 现在走评估器，能判「连续N期」：

- `src/strategy/invalidation_evaluator.py` — 读 `indicator_history` 做连续红期判定
- `src/analysis/leading_indicators.py` — `update_value` 自动写历史；`consecutive_periods_negative()` 是判定入口
- `scripts/collect_invalidation_indicators.py` — 自动采集（东财港股/美股财报 + Yahoo 行情），cron `91302eced8be` 每交易日 19:00 跑

**规则不变**：单期红 ≠ 失效；写了「连续两季」的腿要连红够期数才触发；无数据的腿不得判失效。

**诚实边界**：35 条腿里只有 10 条能自动采（财报可得）。SU7月交付、同店销售、DAU、
版号、定点数、SGP.AX 全部 3 条等运营指标需人工或网络检索，仍显示 ❓。
**❓ 不是 bug，是数据源边界——不要用空值判失效。**

**已知缺口**：触发历史未落库。某条腿曾经触发后恢复（如 03888 在 2025 连续两季红），
这类事件目前不会被记录，只能靠 cron 的状态文件 `db/invalidation_monitor_state.json` 兜底。

## 复盘四桶（关闭仓位时）

不要只用价格 vs 预期：

1. **Thesis** — 故事发生了吗？
2. **Timing** — 早 / 晚 / 运气（按该仓 `horizon` 看价格）
3. **Sizing** — 仓位是否匹配信心
4. **Process** — 是否跳过反面论据/失效条件/类比

`compound` 仓的 1 周价格「错过」不是教训。`tactical` 仓才用 1w/1m 评分。

教训写入 `knowledge/lessons.md` 只是候选。同一玩法重复 3 次再升到 `principles.md`。

## 不要做

- 不要把 D7/D8 默认填 3 来换 BUY
- 不要每个月用单一熊市窗口重拟合 DIMENSION_WEIGHTS
- 不要在周报里倾倒 60+ 只「暂无评分数据」
- 不要用 AI 编 1 周目标价给 12 个月 compound 仓
- 不要同时开两个连接写同一个 duckdb（`PositionBook(conn=log.conn)`）

## 关键文件

| 文件 | 职责 |
|------|------|
| `src/strategy/position.py` | Position / FIFO / rebuild |
| `src/strategy/analog.py` | 写入前类比检索 |
| `src/strategy/decision.py` | decision_log；`enforce_process` |
| `src/data/models.py` | `data_complete` BUY 门闩 |
| `src/analysis/scorer.py` | `collect_buy_blocking_gaps` |
| `docs/hermes-decision-loop.md` | 本文 |

运维细节见 Hermes skill `yidai-operations` 与 `references/position-and-feedback-loop.md`。
