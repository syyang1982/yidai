# 意怠工程 (Yidai Project)

> **用数据工程思维做投研** — 个人投研分析系统

---

## 项目简介

意怠工程是一套基于数据工程思维构建的个人投研分析系统。核心理念是把财务分析当作数据质量检查来做，建立一套**可量化、可回测、可自动化**的投资分析体系。系统采用七维评分框架（5 个量化维度 + 2 个定性维度），覆盖从数据采集、财务异常预警、决策记录、复盘闭环到报告生成的完整投研流程。目前知识库已积累 44 家公司档案，覆盖 A 股、港股及中概股。

```
┌─────────────────────────────────────────────────────┐
│                  意怠工程 三层架构                      │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌───────────┐  ┌───────────┐  ┌──────────────┐    │
│  │ 第一层     │  │ 第二层     │  │ 第三层        │    │
│  │ 投研手册   │→│ 代码实现   │→│ 可视化/报告   │    │
│  │ (方法论)   │  │ (自动化)   │  │ (决策支持)    │    │
│  └───────────┘  └───────────┘  └──────────────┘    │
│                                                     │
│  定义"查什么"    自动"怎么查"    展示"结果是啥"       │
└─────────────────────────────────────────────────────┘
```

---

## 核心功能

### 七维评分框架
- **D1 盈利能力** — ROE、毛利率、净利率、营收增长
- **D2 财务健康** — 资产负债率、流动比率、利息覆盖
- **D3 现金流质量** — 自由现金流、经营现金流/净利润
- **D4 估值水平** — PE/PB/PS 百分位、DCF 估值
- **D5 成长性** — 营收/利润增长趋势、多期趋势分析
- **D6 股权结构**（定性） — 关联交易、独董比例、审计意见
- **D7 战略前景**（定性） — 行业地位、竞争壁垒、管理团队

### 财务异常预警（5 条规则）
| # | 规则 | 触发条件 | 等级 |
|---|------|---------|------|
| 1 | 应收账款 vs 营收增速 | 连续 2 期应收增速 > 营收增速 +10% | 🔴 高风险 |
| 2 | 存货周转率趋势 | 连续 3 期下降 | 🟡 关注 |
| 3 | 利润质量 | 经营现金流 < 净利润（连续 2 期） | 🟡 关注 |
| 4 | 短贷长投 | 短期借款激增 + 长期投资增加 | 🔴 高风险 |
| 5 | 商誉占比 | 商誉/总资产比例上升超 5% | 🟡 关注 |

### 决策日志与复盘闭环
- 结构化记录每笔投资决策（标的、动作、价格、理由、预期、评分快照）
- 预期 vs 实际自动回检（价格、基本面变化）
- 因子有效性分析（哪些评分维度真正有预测力）
- 预警准确性回检

### 市场信号分析
- 公告情绪分析 — 关键词频率异常检测
- 行业景气度 — 领先行业月度指标拐点检测
- 高管变动追踪 — CFO/审计师变更预警

### 其他功能
- **预期验证引擎** — 决策后 N 天/周自动回检
- **行业基准对比** — 与同行业中位数对比评分
- **DCF 估值模型** — 简化现金流折现模型
- **ESG 治理评分** — 关联交易、独董比例、审计意见
- **数据可视化仪表盘** — 七维雷达图、持仓健康度
- **个股深度报告** — 单股全面分析报告
- **自动化周报** — 集成预警信号 + 决策建议 + 预期验证

---

## 项目结构

```
yidai/
├── manage.py                  # CLI 管理工具（统一入口）
├── pyproject.toml             # 项目配置与依赖
├── ROADMAP.md                 # 持续改进路线图
├── plan.md                    # 项目愿景与架构设计
│
├── src/                       # 核心源码
│   ├── analysis/              # 分析引擎
│   │   ├── profitability.py   #   D1 盈利能力评分
│   │   ├── health.py          #   D2 财务健康评分
│   │   ├── cashflow.py        #   D3 现金流质量评分
│   │   ├── valuation.py       #   D4 估值水平评分
│   │   ├── growth.py          #   D5 成长性评分
│   │   ├── scorer.py          #   七维综合评分聚合
│   │   ├── anomaly.py         #   财务异常预警
│   │   ├── market_signals.py  #   市场信号分析
│   │   ├── benchmarks.py      #   行业基准对比
│   │   ├── dcf.py             #   DCF 估值模型
│   │   ├── esg.py             #   ESG 治理评分
│   │   ├── percentile.py      #   估值百分位
│   │   ├── quarterly.py       #   季报分析
│   │   └── return_projection.py # 收益预测
│   │
│   ├── data/                  # 数据层
│   │   ├── fetcher.py         #   Eastmoney API 数据采集（A股+港股）
│   │   ├── store.py           #   DuckDB 存储层
│   │   └── models.py          #   数据模型（ScoreResult 等）
│   │
│   ├── strategy/              # 策略层
│   │   ├── decision.py        #   决策日志管理
│   │   ├── review_engine.py   #   预期验证引擎
│   │   ├── review.py          #   交易复盘
│   │   ├── signal_tracker.py  #   信号追踪
│   │   ├── backtest.py        #   回测引擎 v1
│   │   └── backtest_v2.py     #   回测引擎 v2
│   │
│   ├── report/                # 报告生成
│   │   ├── weekly_v2.py       #   自动化周报
│   │   └── company_report.py  #   个股深度报告
│   │
│   ├── knowledge/             # 知识库管理
│   │   └── base.py            #   公司档案读写
│   │
│   └── viz/                   # 可视化
│       └── dashboard.py       #   持仓仪表盘
│
├── tests/                     # 测试套件（pytest）
│   ├── test_analysis/         #   分析模块测试
│   ├── test_data/             #   数据层测试
│   ├── test_strategy/         #   策略层测试
│   ├── test_report/           #   报告模块测试
│   ├── test_knowledge/        #   知识库测试
│   ├── test_viz/              #   可视化测试
│   └── test_e2e_*.py          #   端到端集成测试
│
├── scripts/                   # 辅助脚本
│   ├── dashboard.py           #   仪表盘主程序
│   ├── analyze_batch.py       #   批量分析
│   └── init_kb.py             #   知识库初始化
│
├── knowledge/                 # 知识库文件
│   ├── companies/             #   44 家公司档案（Markdown）
│   └── analysis/              #   11 篇行业研究报告
│
├── db/                        # 数据库文件
│   ├── yidai.duckdb           #   主数据库（财务数据）
│   ├── signals.duckdb         #   信号数据库
│   └── yidai_review.duckdb    #   复盘数据库
│
└── reports/                   # 生成的报告
    └── weekly_*.md            #   周报文件
```

---

## 快速开始

```bash
# 克隆项目
cd /home/frank/.hermes/yidai

# 安装依赖
pip install -e .

# 安装开发依赖（含测试）
pip install -e ".[dev]"

# 运行测试
python manage.py test

# 查看所有命令
python manage.py
```

---

## CLI 命令参考

所有命令通过 `python manage.py <command>` 调用：

### 仪表盘

```bash
# 标准仪表盘
python manage.py dashboard

# 增强版仪表盘（含雷达图）
python manage.py dashboard --enhanced
```

### 分析

```bash
# 分析单个公司
python manage.py analyze 01810.HK
python manage.py analyze 9988.HK --thesis "低估+高股息"

# 批量分析所有持仓
python manage.py analyze --all
```

### 决策管理

```bash
# 记录投资决策（交互式）
python manage.py decision add 01810.HK

# 列出所有决策
python manage.py decision list

# 查看决策详情
python manage.py decision show <id>

# 查看待复盘决策
python manage.py decision review

# 记录决策结果
python manage.py decision outcome <id>

# 决策统计汇总
python manage.py decision stats
```

### 信号追踪

```bash
# 查看单个公司信号历史
python manage.py signal 01810.HK

# 查看所有公司最新信号
python manage.py signal --all

# 更新所有公司信号
python manage.py signals
```

### 评分

```bash
# 列出所有公司评分
python manage.py score --list

# 设置定性评分（D6 股权 / D7 战略）
python manage.py score set 01810.HK --ownership 4 --strategy 5
```

### 异常预警

```bash
# 检查单个公司
python manage.py anomaly 01810.HK

# 检查所有持仓
python manage.py anomaly
```

### 报告

```bash
# 生成周报
python manage.py report

# 生成个股深度报告
python manage.py report 01810.HK
```

### 回测

```bash
# 回测单个公司
python manage.py backtest 01810.HK
```

### 知识库

```bash
# 知识库概览
python manage.py kb

# 查看公司档案
python manage.py kb 01810.HK
```

### 其他

```bash
# 列出所有公司评分
python manage.py list

# 运行测试
python manage.py test
```

---

## 七维评分体系

### 评分维度

| 维度 | 类型 | 评分范围 | 说明 |
|------|------|---------|------|
| D1 盈利能力 | 量化 | 0-5 | ROE、毛利率、净利率、营收增长 |
| D2 财务健康 | 量化 | 0-5 | 资产负债率、流动比率、利息覆盖、多期趋势 |
| D3 现金流质量 | 量化 | 0-5 | 自由现金流、经营现金流/净利润 |
| D4 估值水平 | 量化 | 0-5 | PE/PB/PS 百分位、DCF 估值、同行对比 |
| D5 成长性 | 量化 | 0-5 | 营收/利润增长、多期增长趋势 |
| D6 股权结构 | 定性 | 0-5 | 关联交易、独董比例、审计意见（人工评分） |
| D7 战略前景 | 定性 | 0-5 | 行业地位、竞争壁垒、管理团队（人工评分） |

### 等级体系

| 等级 | 总分范围 | 含义 |
|------|---------|------|
| **A** | 29-35 | 优质标的，强烈关注 |
| **B** | 22-28 | 良好标的，值得持有 |
| **C** | 15-21 | 一般标的，谨慎持有 |
| **D** | 8-14  | 较差标的，建议回避 |
| **F** | 0-7   | 风险标的，建议减仓 |

### 信号逻辑

| 信号 | 条件 | 含义 |
|------|------|------|
| 🟢 **BUY** | 总分 ≥ 29 且估值 ≥ 4 | 优质且便宜，具备投资价值 |
| 🟡 **HOLD** | 总分 ≥ 15 且无关键维度失败 | 基本面尚可，继续持有 |
| 🔵 **WATCH** | 总分 < 15 但无严重风险 | 暂不建议介入 |
| 🔴 **REDUCE** | 健康 < 2 或 现金流 < 2 或 股权 < 1 或 总分 ≤ 14 | 存在明显风险，建议减仓 |

> **优先级：** 关键维度失败（健康/现金流/股权）> 总分过低 > 单维度过低 > 买入信号 > 持有信号

---

## 数据源

| 数据源 | 覆盖范围 | 说明 |
|--------|---------|------|
| Eastmoney API | A 股 + 港股 | 财务报表、估值数据 |
| Sina Finance | 行情数据 | 实时/历史价格 |
| Knowledge Base | 本地 Markdown | 44 家公司档案 + 11 篇行业研究报告 |

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 语言 | Python ≥ 3.10 | 主要开发语言 |
| 数据处理 | Polars ≥ 1.0 | 高性能 DataFrame |
| 数据库 | DuckDB ≥ 1.0 | 嵌入式分析数据库 |
| HTTP 请求 | Requests ≥ 2.31 | API 数据采集 |
| 测试框架 | pytest ≥ 8.0 | 单元/集成/E2E 测试 |
| 覆盖率 | pytest-cov ≥ 5.0 | 代码覆盖率统计 |

> 完整依赖见 [`pyproject.toml`](pyproject.toml)

---

## 测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/test_analysis/ -v
python -m pytest tests/test_strategy/ -v

# 查看覆盖率
python -m pytest tests/ --cov=src --cov-report=term-missing

# 通过 manage.py 运行
python manage.py test
```

测试覆盖：

- `test_analysis/` — 14 个测试文件，覆盖所有分析模块
- `test_data/` — 数据采集、存储、模型测试
- `test_strategy/` — 决策、复盘、回测、信号追踪测试
- `test_report/` — 周报、个股报告测试
- `test_knowledge/` — 知识库测试
- `test_viz/` — 可视化测试
- `test_e2e_*.py` — 端到端集成测试（小米、阿里巴巴等）

---

## ROADMAP 进度

### 已完成 ✅

| 模块 | 状态 | 说明 |
|------|------|------|
| 数据采集 | ✅ | Eastmoney API，A 股 + 港股财报 |
| 存储层 | ✅ | DuckDB（yidai.duckdb + signals.duckdb） |
| 五维量化分析 | ✅ | 盈利、健康、现金流、估值、增长 |
| 综合评分 | ✅ | 七维评分（5 量化 + 2 定性） |
| 财务异常预警 | ✅ | 5 条规则型预警 |
| 市场信号预警 | ✅ | 高管变动、公告情绪、行业景气度 |
| 决策日志 | ✅ | 结构化记录 + CLI 管理 |
| 预期验证 | ✅ | 预期 vs 实际自动回检 |
| 行业基准对比 | ✅ | 同行业中位数对比 |
| DCF 估值 | ✅ | 简化现金流折现模型 |
| ESG 评分 | ✅ | 治理评分 |
| 信号追踪 | ✅ | 信号记录到 signals.duckdb |
| 回测引擎 | ✅ | 基本回测框架 v1 + v2 |
| 复盘 | ✅ | 交易复盘 + 因子有效性分析 |
| 周报 | ✅ | 自动生成 Markdown 周报 |
| 个股报告 | ✅ | 单股深度分析报告 |
| 仪表盘 | ✅ | 持仓健康度 + ASCII 雷达图 |
| 知识库 | ✅ | 44 家公司档案 + 11 篇研究报告 |
| CLI | ✅ | 完整的 manage.py 命令行工具 |
| 测试 | ✅ | 13+ 测试文件覆盖各模块 |

### 待建设 🔲

| 模块 | 状态 | 说明 |
|------|------|------|
| 港股季报自动采集 | 🔲 | 当前部分手动 |
| 宏观数据采集 | 🔲 | 利率、PMI、社融等 |
| 行业数据采集 | 🔲 | 半导体 BB 值、新能源车销量等 |
| 替代数据采集 | 🔲 | 招聘、App 下载量等（低优先） |
| 阈值校准 | 🔲 | 基于复盘结果自动建议调整 |
| 维度权重调整 | 🔲 | 基于历史预测力优化权重 |
| 历史交易数据迁移 | 🔲 | trade-log.md → 结构化格式 |

---

## 免责声明

**本项目仅供个人学习和研究使用，不构成任何投资建议。**

- 本系统提供的分析结果、评分和信号仅基于历史财务数据的量化计算，**不代表对未来股价走势的预测**。
- 投资有风险，入市需谨慎。任何投资决策应基于您自己的独立判断和风险承受能力。
- 本项目作者不对因使用本系统而产生的任何投资损失承担责任。
- 本系统使用的数据来源于公开 API，数据的准确性和完整性无法完全保证。
- **请勿将本系统作为唯一的投资决策依据。**

---

## 许可证

本项目为个人项目，仅供内部使用。
