# VLDB 2027 Demo 新定位：Question-Only Analytics

状态日期：2026-09-06（Asia/Shanghai）  
状态：**作者已确认标题与方向；固定资产、17 个注册任务、Web 原型、部署骨架和四种
controller 的初步评测已完成；受约束模型规划路径已通过合成验证与浏览器到 loopback mock
provider 的完整集成测试，静态题集/路径/模型 plan 与完整性状态机已纳入盲态 implementation
freeze，下一步是在新 credential 上完成公开
provider smoke 和无解盲 preflight，再经明确授权执行 prospective held-out 验证。**

## 0. 推荐结论

已确认的 Demo paper 标题为：

> **Ask, Don't Upload: A Question-Driven Agentic System for Closed-Loop Data Discovery, Preparation, and Analysis**

中文可概括为：

> **只给分析问题，不给数据集；系统在未经整理的数据环境中按需找数据、准备数据、执行分析，并自动生成有执行证据支撑的报告。Data Discovery 不是一次性前置步骤：若下游分析发现数据不充分，系统会自动重新打开上游发现与准备决策。**

一句话 hook：

> **Ask a question, not provide a dataset.**

这里，完整自动化和 Question-Only 是用户体验；真正应当写成技术贡献的中心机制是：

> **closed-loop data discovery：把 Discovery 作为分析执行中可重开的决策，由下游的、可执行的数据充分性 obligation 触发 source repair、依赖失效和 Preparation/Analysis 重放，而不是一次性、单向地串联四个模块。**

具体运行时仍可称为 **sufficiency-guided lifecycle search**，但不再把这个抽象词组放在标题中。完整的 301 篇标题证据、最近邻冲突与更名理由见 [demo-title-analysis-2025-2026.md](demo-title-analysis-2025-2026.md)。

当前不建议急着造一个缩写或产品名。先冻结问题与机制；系统名可以在最小验证通过后再定，避免名字先行、贡献随后硬凑。

## 1. 为什么不叫 Data-Free Analysis

`Data-Free` 在机器学习文献中已经有稳定含义，通常表示模型提取、蒸馏或压缩时不访问原始训练数据。例如 [Data-Free Model Extraction](https://arxiv.org/abs/2011.14779) 明确把它用于“不需要 surrogate dataset”的模型提取。

我们的系统并不是不使用数据，而是：

- 用户在**每次分析任务**中不指定数据集、文件名、表名或 schema；
- 系统仍然在一个预先授权的数据环境中主动发现并读取数据；
- 系统管理员仍需一次性配置数据边界、连接器、权限和预算。

因此，更准确的术语是：

- **Question-Only Analytics**：强调每个任务只输入分析问题；
- **without user-specified data**：强调不要求用户绑定正确数据源；
- **over uncurated data environments**：强调环境中包含未知、异构和无关数据。

不要使用 `data-free`、`no-data` 或“无需任何数据配置”这类会被 reviewer 直接质疑的表述。

## 2. 精确问题定义

系统部署时给定一个预先授权环境：

```text
E = (data repositories, connectors, access policies, execution budget)
```

每个分析任务只接收：

```text
q = a natural-language analytical question
```

用户不为该任务提供：

```text
dataset IDs, filenames, schemas, join paths,
preparation pipelines, analysis plans, or report outlines
```

系统输出二者之一：

```text
R = an evidence-grounded analytical report
```

或：

```text
U = an explicit insufficiency diagnosis describing what data is missing
```

这里的“完全脱手”应严格解释为 **zero per-task data handoff**，而不是取消组织级权限、连接器和数据边界。这个限定既更真实，也使 Demo 可以复现和评测。

## 3. 核心研究问题

> **When only an analytical question is given, how can a data agent progressively acquire and prepare sufficient data, and automatically revisit upstream data decisions when downstream analysis reveals that the current evidence is inadequate?**

难点不在于分别调用四个 agent，而在于：

1. 只看问题时，系统并不知道最终需要哪些数据字段、粒度、时间范围和连接关系；
2. 一个语义相关的数据源不一定足以回答问题；
3. 数据源问题经常只有在 join、统计分析或报告验证时才暴露；
4. 线性 `discover → prepare → analyze → report` 流程无法把这些下游信号可靠地传回上游；
5. 系统还必须知道何时已有足够证据、何时应继续搜索、何时应停止并报告不可回答。

## 4. 唯一中心机制：Closed-Loop Data Discovery

系统不把四个阶段实现成一次性流水线，而先从问题产生一个可执行的 **Analytical Sufficiency Contract (ASC)**，并维护完整生命周期状态：

```text
s = <question,
     sufficiency_obligations,
     unresolved_data_needs,
     selected_sources,
     materialized_tables,
     analysis_artifacts,
     report_claims>
```

可执行动作包括：

```text
Discover / Inspect / Select / Prepare / Analyze / Validate / Backtrack / Stop
```

`ASC` 包含指标、维度、实体/时间覆盖、粒度、join obligations、统计前提和 report-claim evidence。它不是一个笼统的 LLM judge 分数；各 obligation 应尽量由 profile、join、代码执行和 artifact linkage 检查。

### 4.1 Progressive discovery

系统先从问题推导当前的数据需求，例如实体、指标、维度、时间覆盖、粒度、比较基线和潜在连接键；只检查最可能满足当前需求的候选数据，而不是预先扫描并理解环境中的所有文件。

这使 Data Discovery 成为**按需、渐进的执行过程**，而不是一次性建立全局 catalog 后再开始分析。

### 4.2 Execution-grounded states

每次选择源文件、执行准备算子或运行分析代码后，系统都物化状态并保存稳定引用。充分性不能只由 LLM 对文件名或摘要打分，而应尽量由可执行检查支持，例如：

- 必需字段和数据类型是否存在；
- 时间/地域/实体覆盖是否满足问题；
- join coverage、重复率、缺失率和单位是否可接受；
- 目标 cohort 是否非空、样本量是否足以执行计划中的分析；
- 报告中的关键数值和关系是否能回到已执行 artifact。

### 4.3 Downstream-to-upstream repair

当下游出现问题时，系统产生结构化 repair goal，而不是只让同一个 code agent 重试。
默认 `registry` pilot 实现以 Discovery 为 repair target 的路径，并在换源后重放
Preparation/Analysis；`agentic` 主路径还实现 executed-candidate tree 上的 Preparation 分支/
回退，以及准备失败后重新打开 Discovery。后者尚未进入冻结效果评测。

| 下游信号 | 应回退到的阶段 | 示例 repair goal |
|---|---|---|
| 缺少所需年份/地区/实体 | Discovery | 查找补充覆盖的数据源 |
| join coverage 过低或键语义冲突 | Discovery / Preparation | 更换源或尝试另一条实体对齐路径 |
| 分析所需变量不存在 | Discovery | 查找包含该指标或可计算代理的数据 |
| 聚合粒度与问题不一致 | Preparation | 回退到聚合前状态并重建表 |
| 报告关键结论没有可执行证据 | Analysis / Discovery | 补做分析；若数据不够则继续找数 |

目标抽象是 **lifecycle-wide backtracking**：错误或不足可以从 Report/Analysis 跨越阶段边界回到 Preparation，甚至回到 Data Discovery。当前冻结 Demo 的实证范围仍是 Analysis → Discovery source repair 与后续 rematerialization；Preparation tree 与其 Discovery reopen 路径属于已实现、待系统评测的 agentic 能力。

### 4.4 Evidence-aware stopping

系统只在以下两种情况下停止：

1. 所有必须满足的数据需求都有物化证据，且报告关键 claim 能回到执行 artifact；
2. 已达到安全/预算边界，系统明确输出缺失的数据需求和当前不能回答的部分。

“拒绝编造一个完整报告”是全自动系统可信度的一部分，而不是失败兜底文案。

## 5. 三篇支撑论文如何凝练成这个机制

| 支撑工作 | 已有贡献与输入假设 | 新系统继承什么 | 新系统新增什么 |
|---|---|---|---|
| CoDA-Bench | Agent 获得任务和包含大量相似干扰文件的环境，自行探索；它是 benchmark，不是 discovery system | question-only/noisy-environment 的任务形式、数据与评测基础 | 面向 report 的渐进式发现策略，以及由下游充分性信号驱动的重新发现 |
| DeepPrep | 给定 source tables 和 target schema；以物化 table state 支持 preparation 内部的 tree reasoning 和 non-local backtracking | 可执行准备算子、物化状态、分支与回退基础 | 把搜索树从“准备阶段内部”扩展到 source selection、analysis artifacts 和 report validation；回退可跨阶段 |
| DeepAnalyze | 输入中已经指定外部数据源文件名；自动完成准备、分析、可视化和报告 | 真实代码执行、分析、图表和 analyst-grade report 能力 | 不再假设已知文件；把 analysis/report 反馈转换为上游 data repair goals |

缺失的桥梁正好是：

> **CoDA 给出“只给问题、数据隐藏在噪声中”的起点；DeepAnalyze 给出“从已知数据到报告”的终点；DeepPrep 的执行树提供回退基础。新工作把它们提升为一个由 analytical sufficiency 控制的、跨整个数据生命周期的搜索过程。**

这比“把三个代码库接到同一个前端”更像一个独立系统研究问题。

## 6. 与最近近邻工作的边界

| 近邻 | 它已经做了什么 | 本方向必须展示的区别 |
|---|---|---|
| [DeepAnalyze](https://arxiv.org/abs/2510.16872) / DA-Studio | 从用户指定/上传的数据到分析报告；可查看 action trace 和 artifacts | 每次任务不绑定数据；在 noisy environment 中找源；下游不足自动触发上游修复 |
| [ReActInsight / UniDataBench](https://aclanthology.org/2026.acl-long.1556/) | 对一个任务的多种数据格式做全局 metadata exploration，发现跨源 join，分解高层目标并 self-correct code | 大量 file-level distractors；不预扫全部环境；self-correction 不只修代码，而能跨阶段更换数据源/准备路径 |
| [Carnot](https://arxiv.org/abs/2608.09532) | 把 data-lake 上的自然语言 deep-research query 编译为可检查、可编辑、可优化 DAG | 核心目标不是人工 plan editing 或成本优化，而是无人干预的 sufficiency diagnosis 和自动跨阶段 backtracking |
| [QwenPaw-Data](https://arxiv.org/abs/2607.11019) | 以 metadata/knowledge/trace graph、skills 和 artifact runtime 支撑企业端到端分析 | 不把 asset graph 或端到端 orchestration 当 novelty；证明 question-only noisy discovery 与 automatic repair 的特定执行语义 |
| [AutoSciRub](https://arxiv.org/abs/2608.31076) | 从开放研究任务自动归纳可执行 rubric，以证据缺口指导研究报告迭代 | 不声称“自动生成要求”本身新；要求被编译为 source/table-level checks，并驱动真实 Discovery 与后续 Preparation/Analysis 重放 |
| [EviMem](https://arxiv.org/abs/2604.27695) | 通过 evidence-gap diagnosis 做对话记忆的迭代检索 | 不声称 evidence-gap retrieval 一般性新颖；重点是结构化数据生命周期、可执行准备状态和分析报告 |

因此，不应再写：

- “the first end-to-end autonomous data analysis system”；
- “the first agent that automatically discovers multiple data sources”；
- “the first system that derives requirements/rubrics from a question”；
- “the first tree-based or self-correcting data agent”。

当前可辩护的联合命题是：

> **A question-only analytics engine that progressively discovers data in an uncurated environment and uses execution-grounded sufficiency signals to backtrack across discovery, preparation, analysis, and reporting.**

在完成更系统的相关工作检索和真实对比实验前，不加 `the first`。

## 7. Demo 的 3--5 分钟核心故事

示意问题（最终必须换成真实、可公开的 CoDA-style case）：

> “Which European countries improved their renewable-electricity share the most from 2018 to 2022, and how does the change relate to GDP per capita?”

观众唯一必须做的动作是输入这个问题，不上传文件、不选择表、不写 schema。

1. **Question only**：系统把问题解析为数据需求，但这些需求只用于展示系统状态，不要求用户确认。
2. **Progressive discovery**：在数百个相似文件中按需检查少量候选，选择能源、GDP 和国家映射数据。
3. **Real downstream failure**：执行后发现首个能源文件缺少 2022，或 country join coverage 不足。界面明确显示这是一个数据充分性失败，而不是笼统的 LLM retry。
4. **Automatic backtracking**：系统自行回到 Discovery，寻找补充源或替换源；随后回到早期物化状态，重新准备和分析。
5. **Question-to-report**：系统输出报告、图表、使用的数据源、关键转换和每条主要结论的执行证据。

现场的 wow moment 是屏幕上出现一条清楚的反向边：

```text
Report/Analysis insufficiency
        └──> Data Discovery repair
                  └──> new materialized branch
                            └──> completed report
```

这仍然满足 Demo 的 audience interaction：观众可以输入自己的问题，并点击查看自动执行过程；但查看和干预是可选的，完成任务不依赖用户修正系统。

## 8. 建议的三项贡献表述

在系统完成后，贡献可按下面三层组织；当前只能作为目标，不能使用完成时态：

1. **Problem formulation**：定义 uncurated data environment 上的 question-only analytics，强调 zero per-task data handoff，以及“报告或明确不足诊断”的双结果；不把 question-only 本身声称为首次提出。
2. **System abstraction**：提出 executable Analytical Sufficiency Contracts 与 closed-loop data discovery，把 discovery、preparation、analysis 和 reporting 纳入一个物化执行状态空间，并支持 downstream-to-upstream source repair 与下游 rematerialization。
3. **Demonstration and evidence**：实现一套 question-to-report 系统，在 CoDA-style noisy environments 上展示自动恢复，并测量正确性、发现成本、恢复率、时延和用户干预次数。

## 9. 最小评测设计

系统实现前先冻结下面的比较，否则“完全自动”只能是产品口号：

| 研究问题 | 核心指标 | 最关键对照 |
|---|---|---|
| 只给问题时能否找到足够数据并完成报告？ | task success、source recall/precision、report correctness/completeness | 通用 code agent、线性三阶段 pipeline |
| 跨阶段回退是否真的有用？ | recovery rate、修复后的 task/report gain | 去掉 lifecycle backtracking 的 ablation |
| progressive discovery 是否避免无谓扫描？ | inspected files/bytes、tool calls、tokens、latency | full-environment content profile |
| 系统是否真的脱手？ | mandatory human interventions per task | human-selected data / human-approved plan |
| 数据不够时是否会乱答？ | answerability/abstention precision and recall | 无 sufficiency gate 的 agent |

其中，`sufficiency` 不能只有一个 LLM judge 分数。至少应包含一组确定性的 coverage、schema、join、execution 和 artifact-link checks，再辅以报告级评价。

## 10. 从可运行原型到论文级证据的五个验证门槛

1. 在真实 CoDA-style 环境中找到至少若干**自然发生**的案例：错误源选择只能在 preparation/analysis 后被发现；不能全部靠人工注入。
2. 证明一次下游信号能够稳定定位到可修复的上游 source/prep decision。
3. 相比线性 pipeline，跨阶段回退在 task/report success 上有可重复的增益。
4. 相比全量 content profile，progressive discovery 明显减少读取/调用成本，且没有不可接受的成功率下降。
5. 一个精简案例能够在 3--5 分钟内稳定完成；网络/API 失败时有离线 replay 或预计算备份。

`community_43` 的完整 15 题已覆盖 10 个 no-repair、4 个 cross-source repair 和 1 个
local data gap，并与 linear、同预算 static-retry、full-profile 对照；`community_52` 另有
2 题 transfer probe。Static retry 复用初始检索词并达到 13/15、21 profiles、7 repair
edges；violation-guided closed loop 达到 15/15、18 profiles、4 edges。这满足第 1--3 项的
初步机制检查，并为第 4 项提供 logical profile exposure 证据，但尚未
测量物理 I/O、tokens 或稳定 latency。所有 family 都在看过任务后注册，因此仍不等于
held-out、model-based 的论文级泛化证据。

## 11. 当前实现快照与下一决策

作者已确认下面这一整句对应的方向与标题：

> **我们将 Demo 定位为 Closed-Loop Data Discovery for Question-Only Analytics：用户每次只给一个分析问题；系统在预先授权但未经整理的数据环境中渐进找数、备数和分析，并用执行可核验的 sufficiency violations 自动重新打开 source decision、重放后续 Preparation/Analysis，最终生成 evidence-grounded report 或明确的 typed insufficiency diagnosis。**

目前已固定三篇支撑工作的代码 revision，下载两个已开发 CoDA communities，并完成 17 个
注册任务、Question-only Web 原型、容器化部署骨架、controller 对照、论文初稿和系统总览图。
受约束的 model compiler 与非 Turing-complete dataframe plan executor 已通过合成双源闭环测试；
另在查看题目/数据前预选了完整 `community_45` 作为 13 题留出集，其 archive 仍未解盲；完整题集、
路径、无密钥模型配置、解盲 redactor 与首轮/评分状态机均已进入 implementation freeze。下一阶段的
关键动作是在公开数据上验证新 provider credential，经授权完成首轮模型运行，再补 model-matched baselines 与
物理成本指标。当前仍不承诺 arbitrary web search、零组织级配置或一般任务上的绝对无人监督。

## 12. 本轮核验来源

- 三篇本地支撑 PDF：CoDA-Bench、DeepPrep、DeepAnalyze（逐页核对输入假设与贡献边界）。
- [VLDB 2026 accepted demonstrations](https://vldb.org/2026/demonstrations.html)。
- [2025--2026 六会 Demo 标题完整语料与定位分析](demo-title-analysis-2025-2026.md)。
- [Graphy'our Data](https://lai.me/files/sigmod-demo-cr.pdf)，SIGMOD 2025 Demo。
- [Sentence to Model](https://slavanov.com/research/sigmod25.pdf)，SIGMOD 2025 Demo。
- [QueryArtisan](https://www.vldb.org/pvldb/vol18/p5263-tang.pdf)，VLDB 2025 Demo。
- [TableCopilot](https://www.vldb.org/pvldb/vol18/p5399-cui.pdf)，VLDB 2025 Demo。
- [Data Agents: Levels, State of the Art, and Open Problems](https://arxiv.org/abs/2602.04261)，SIGMOD 2026 Tutorial。
- [UniDataBench / ReActInsight](https://aclanthology.org/2026.acl-long.1556/)，ACL 2026。
- [DeepAnalyze](https://arxiv.org/abs/2510.16872)。
- [Carnot](https://arxiv.org/abs/2608.09532)，VLDB 2026 Demo。
- [QwenPaw-Data](https://arxiv.org/abs/2607.11019)。
- [AutoSciRub](https://arxiv.org/abs/2608.31076)。
- [EviMem](https://arxiv.org/abs/2604.27695)。
- [Data-Free Model Extraction](https://arxiv.org/abs/2011.14779)，用于核验 `data-free` 的既有术语含义。

检索接口与失败记录见 [question-only-query-log.md](question-only-query-log.md)。
