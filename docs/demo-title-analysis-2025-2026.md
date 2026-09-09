# 2025--2026 Demo 标题审计与 Question-Only Analytics 定位升级

状态日期：2026-09-06（Asia/Shanghai）  
结论状态：**作者已于本轮对话确认完整标题；定位审计保留为选题依据，系统原型已进入实现。**

## 0. 结论先行

当前方向值得保留，但中心贡献需要再收紧一次。

不应再把 novelty 放在：

- 用户只给自然语言问题；
- 自动找数据；
- 端到端完成准备、分析和报告；
- 使用 LLM、多 Agent、DAG 或一般性的 self-correction。

这些点在 2025--2026 Demo 中已经分别、甚至成组出现。标题审计最初建议的机制型短标题是：

> **Ask, Don't Upload: Closed-Loop Data Discovery for Question-Only Analytics**

作者随后确认的投稿标题为：

> **Ask, Don't Upload: A Question-Driven Agentic System for Closed-Loop Data Discovery, Preparation, and Analysis**

完整标题牺牲了一部分简洁性，但更明确地覆盖现场演示的三个可见阶段，并用
`Question-Driven` 表达“每个任务只输入问题”的交互边界。论文 novelty 仍必须落在
`Closed-Loop`：下游可执行检查触发上游 source repair 与后续 rematerialization，而不是落在
`Agentic` 或三个阶段的简单串联。

对应的核心命题是：

> **The system treats data discovery as a revisable part of analytical execution: downstream evidence gaps generate executable repair goals that automatically reopen discovery and replay preparation and analysis.**

中文一句话：

> 用户每次只给分析问题；系统不仅自动找数、备数和出报告，而且把下游执行暴露的缺字段、覆盖不足、join 失败、样本不足和无证据 claim 变成上游重新找数/备数的任务，直到报告有足够执行证据，或明确说明缺什么数据而无法回答。

相较旧标题 **Question-Only Analytics via Sufficiency-Guided Lifecycle Search**，新标题把 `lifecycle search` 这个较抽象的术语替换为 reviewer 一眼能识别的数据库问题 `Closed-Loop Data Discovery`。`Question-Only` 保留为体验 hook；`analytical sufficiency` 下沉为技术机制，而不是把“只输入问题”误写成首创。

## 1. 六个官方列表：301 篇

“近两年”按会议年份 2025、2026 处理。只纳入官方 accepted list、program 或 proceedings 中明确属于 Demo / Demonstration Track 的论文。

| Venue | 2025 | 2026 | 两年合计 |
|---|---:|---:|---:|
| VLDB | 55 | 92 | 147 |
| SIGMOD | 69 | 39 | 108 |
| ICDE | 26 | 20 | 46 |
| **合计** | **150** | **151** | **301** |

六个事实源分别是 [VLDB 2025 PVLDB 正式目录](https://www.vldb.org/pvldb/vol18/FrontMatterVol18No12.pdf)、[VLDB 2026 accepted demonstrations](https://www.vldb.org/2026/demonstrations.html)、[SIGMOD 2025 accepted demos](https://2025.sigmod.org/sigmod_demo_papers.shtml)、[SIGMOD 2026 accepted demos](https://2026.sigmod.org/sigmod_demos.shtml)、[ICDE 2025 Demonstration Papers](https://ieee-icde.org/2025/demonstrations/) 和 [ICDE 2026 accepted demos](https://icde2026.github.io/demo-papers.html)。完整逐题清单见 [demo-title-corpus-2025-2026.md](demo-title-corpus-2025-2026.md)。

其中，[VLDB 2025 卷首](https://www.vldb.org/pvldb/vol18/FrontMatterVol18No12.pdf) 明确报告 150 投、55 录；[SIGMOD 2025 chairs' welcome](https://2025.sigmod.org/SigmodPods25-welcome.pdf) 报告 171 投、69 录。其他四组数量由官方逐题列表计数。301 条完整标题没有精确重复。

## 2. 标题信号：什么已经拥挤

下面是预先固定的字面关键词组匹配，类别允许重叠。它只能反映录用 program 的问题表达，不能证明关键词导致录用，也不能把 `0 title hits` 当成研究空白。

| 标题信号 | 2025（150） | 2026（151） | 合计（301） |
|---|---:|---:|---:|
| GenAI / Agent / NL / RAG | 27 | 43 | 70（23.3%） |
| Query / SQL / Optimizer | 30 | 39 | 69（22.9%） |
| Interactive / Visual / Human-facing | 24 | 43 | 67（22.3%） |
| Analysis / Report / Explanation | 35 | 30 | 65（21.6%） |
| Discovery / Search / Acquisition / Integration | 18 | 24 | 42（14.0%） |
| Trust / Diagnosis / Robustness | 22 | 18 | 40（13.3%） |
| Preparation / Quality / Cleaning / ETL | 20 | 17 | 37（12.3%） |
| Pipeline / Workflow / Dataflow / Lifecycle | 7 | 14 | 21（7.0%） |
| Autonomous / Automated / Self-driving 等措辞 | 7 | 10 | 17（5.6%） |
| End-to-End（精确词组） | 1 | 2 | 3（1.0%） |

三个变化尤其值得注意：

1. GenAI/Agent/NL 类标题从 2025 的 27/150 增至 2026 的 43/151；`LLM` 精确词族已有 37 篇，`Agent` 精确词族已有 17 篇。**Agent 已经是基础设施，不是定位。**
2. 交互/可视类从 24/150 增至 43/151，pipeline/workflow 类从 7/150 增至 14/151。最新 taste 确实偏好能看到状态、过程和修复效果的可操作系统。
3. Discovery 类有 42 篇，Analysis/Report 类有 65 篇，但两组在标题层面只交叉 5 篇；Discovery、Preparation、Analysis 三组同时命中的标题只有 1 篇。这个交叉仍值得做，但不能据此声称正文层面无人覆盖。

### 题名措辞本身的 taste

- 258/301（85.7%）使用冒号结构，通常是“系统名/记忆点：具体能力或机制”。
- 标题词数中位数是 9。已确认标题更长，因此摘要、Figure 1 和开篇必须尽快把
  `Closed-Loop` 的机制讲清，避免标题中的功能枚举稀释核心贡献。
- 52/301（17.3%）直接写 `Demo`、`Demonstration`、`Demonstrating` 或 `in Action`；因此标题没有必要机械地再加 “A Demonstration of”。
- 只有 5 篇使用问号。`Ask, Don't Upload` 的命令式 hook 足够醒目，同时没有偏离主流的冒号结构。

## 3. `0 title hits` 有价值，但不是 novelty 证明

301 个标题中，下列精确表达均为 0：

```text
question-only, data-free, answerability, sufficiency, insufficient,
progressive, closed-loop, backtracking, upstream, downstream,
data acquisition
```

另外，`report` 和 `raw data` 各只命中同一篇 Graphy，`minimal` 只命中 MinPrep，`on-demand` 只命中 RadlER。

这说明 `Question-Only` 和 `Closed-Loop` 是尚未被标题模板化的清晰措辞，可以帮助定位；但最近论文正文已经覆盖自然语言到数据、数据到报告、数据湖 deep research、渐进探索和 evidence-gap retrieval。它们只能成为**命名入口**，不能单独成为贡献。

## 4. 与本方向最接近的真实 Demo

| 近邻 Demo | 它已经覆盖的边界 | 对本方向的直接约束 |
|---|---|---|
| [Graphy'our Data, SIGMOD 2025](https://lai.me/files/sigmod-demo-cr.pdf) | 把大规模原始文档离线建成 Fact/Dimension 图，再渐进探索并生成高质量 report。 | 不能声称“raw data → report”或 progressive exploration 本身新；差异要落在异构结构化数据、执行检查和自动上游修复。 |
| [Sentence to Model, SIGMOD 2025](https://slavanov.com/research/sigmod25.pdf) | 用户给自然语言 data-collection request；Agent 搜索 Web、KG 或组织网络，构造/富化表，并在预算下训练预测模型，强调 minimal human intervention。 | “用户不提供数据 + 自动找数/富化”已经出现；本系统必须用**下游分析证据反向改变 source selection**，输出是分析报告/缺口诊断而非数据集+模型。 |
| [QueryArtisan, VLDB 2025](https://www.vldb.org/pvldb/vol18/p5263-tang.pdf) | 自然语言查询数据湖，检索相关 metadata/sample，生成并优化 processing graph，自动纠错，再做多 Agent 深度分析、可视化和 final report。 | 这是最强正面近邻。“NL query + heterogeneous lake + processing + analysis + report”不可再作为主张；差异必须是 source choice 可被下游失败重新打开，而非只在既定 graph 内纠代码。 |
| [TableCopilot, VLDB 2025](https://www.vldb.org/pvldb/vol18/p5399-cui.pdf) | 支持 NL-only、NL+query-table 的发现，并接 TableQA/处理；核心是 top-k table matching。 | `Question-Only` 只能描述入口；新意应是从分析任务推导动态充分性要求，以及 discovery 之后仍可自动 rediscover。 |
| [Carnot, VLDB 2026](https://arxiv.org/abs/2608.09532) | 把 data-lake natural-language deep-research request 编译为执行图；用户检查、修改和增量执行，优化成本/延迟。 | 不应把 NL deep research、DAG、可检查执行或局部重算当新意；本系统强调默认无人干预、下游触发的自动 source/prep repair。 |
| [Guixu, VLDB 2026](https://www.vldb.org/pvldb/vol19/p4562-wu.pdf) | 面向 autonomous AI agent 的任务/预算驱动数据发现与采购。 | 不做 valuation/on-chain，也不声称 autonomous discovery 首创；研究对象是“何时已有足够数据支撑特定分析报告”。 |
| [DA-Studio, VLDB 2026](https://arxiv.org/abs/2606.31423) 与 [DeepEye, SIGMOD 2026](https://arxiv.org/abs/2603.28889) | 已覆盖 end-to-end data agent、DAG/trace、人工编辑重跑和报告等体验。 | 不能只是给 DeepAnalyze 增加 discovery tab；核心 demo 必须出现一次自动跨阶段 rediscovery，并证明它改变了报告是否可答。 |

另一个重要反例是 [A Demo of Interactive Thematic Data Collection on the Live Web](https://www.vldb.org/pvldb/vol19/p4554-west.pdf)：它明确把“构建高覆盖可复用文档集合”与“找到足够证据后停止并回答/生成报告”的系统区分开。我们的工作属于后者，因此不要泛化成 Web crawler，也不要把覆盖最大化当目标；目标应是**以最少检查成本满足具体分析的可执行数据需求**。

由此可得一个更严格的判断：

> **Question-only discovery-to-report 是产品范围，不是论文 novelty；analysis-grounded source repair 才是可以从三篇支撑论文中凝练出的研究机制。**

## 5. 优化后的系统抽象

### 5.1 输入输出

部署时已有授权环境 `E = repositories + connectors + policies + budget`。每次任务只有自然语言分析问题 `q`，没有 dataset/file/schema/join/prep/plan 的人工绑定。

系统输出：

```text
evidence-grounded report + data/evidence manifest
```

或：

```text
explicit data-gap diagnosis + inspected alternatives
```

### 5.2 Analytical Sufficiency Contract

系统先把问题编译成一个可执行的 **Analytical Sufficiency Contract (ASC)**：

```text
ASC(q) = <measures, dimensions, entity/time coverage, granularity,
          join obligations, statistical preconditions, claim evidence>
```

这里的 `contract` 不是 LLM 给出的一个总体分数，而是一组可以被数据 profile、join 结果、代码执行和 report artifact 检查的 obligation。例如：

- 2018 与 2022 两个时间点都存在；
- 国家粒度一致且 country ID join coverage ≥ 预设阈值；
- renewable share 的单位与分母定义一致；
- GDP per capita 和目标指标有足够共同样本；
- 每个主要数值 claim 指向已经执行的 table/query/chart artifact。

`Answerability` 在数据库理论中已有严格的 query-answerability 含义，因此不建议现在把 “Answerability Contract” 放进标题，除非后续真的给出相应形式化保证。用 `Analytical Sufficiency Contract` 更准确；正文仍需说明它是 operational contract，而非完备性证明。

### 5.3 Closed-loop runtime

```text
Question
   ↓
ASC obligations → progressive discovery → materialized preparation
                                            ↓
                                      analysis + report
                                            ↓
                                  execution-grounded validator
                                      ↙              ↘
                       all obligations met       violated obligation
                              ↓                         ↓
                         final report       source/prep repair goal
                                                        ↖
                                              cross-stage backtrack
```

关键差异不是“Agent 再试一次”，而是 repair goal 必须指明：

```text
which obligation failed
which upstream source decision caused it
which alternate source/path/state should be explored next
which downstream artifacts must be invalidated and replayed
```

这把 DeepPrep 的物化状态与 non-local backtracking，从 preparation 内部提升到 `source → table state → analysis artifact → report claim` 的跨阶段运行时；同时用 CoDA-Bench 的 noisy environment 让 source selection 成为真实问题，再复用 DeepAnalyze 的执行与报告能力作为下游反馈端。

## 6. 已确认题目与历史备选

### 作者已确认

> **Ask, Don't Upload: A Question-Driven Agentic System for Closed-Loop Data Discovery, Preparation, and Analysis**

这个版本的取舍是：

1. `Ask, Don't Upload` 立即展示“完全脱手”的体验，但没有做不真实的 `data-free` 承诺。
2. `Question-Driven` 明确每个分析任务的唯一输入，同时不声称自然语言入口本身首创。
3. `Closed-Loop` 指向相对 QueryArtisan、Sentence-to-Model、DA-Studio 的机制差异。
4. `Data Discovery, Preparation, and Analysis` 与界面及现场脚本中的三个阶段一致。
5. `Agentic System` 符合当前系统形态，但正文不得把使用 Agent/LLM 本身列为 novelty。

### 历史短标题

> **Ask, Don't Upload: Closed-Loop Data Discovery for Question-Only Analytics**

它更短、更突出机制，仍可用作项目副标题或 Figure 1 中的一句话说明，但不再是当前投稿标题。

它最初被推荐的原因是：

1. `Ask, Don't Upload` 立即展示“完全脱手”的体验，但没有做不真实的 `data-free` 承诺。
2. `Closed-Loop Data Discovery` 直接说明相对 QueryArtisan、Sentence-to-Model、DA-Studio 的机制差异。
3. `Question-Only Analytics` 定义系统类别，不把 LLM/Agent 当贡献。
4. 标题约 9 词，采用最新 Demo 中最常见的“hook/name：具体机制”结构。

### 只有在相应证据成立时才启用的备选

- **Ask, Don't Upload: Executable Sufficiency Contracts for Question-Only Analytics**  
  若后续 ASC 的自动生成准确率、contract violation 定位和 stopping/abstention 是最强实验结果，可改用这个更技术化的标题。
- **From Question to Evidence: Analysis-Guided Data Rediscovery**  
  更短、更强调一次 source replacement 的 demo moment，但弱化了 preparation 与完整报告体验。

不建议：

- `Data-Free Analysis System`：机器学习里已有稳定歧义，而且系统实际仍使用数据；
- `An End-to-End Autonomous Data Agent`：与 70 个 GenAI/Agent/NL 标题和多篇直接近邻一起落入拥挤区；
- `Question-to-Report`：Graphy 和 QueryArtisan 已直接覆盖；
- `Self-Correcting Analytics`：容易被理解成 SQL/code retry，无法体现跨阶段 source repair。

## 7. 三项贡献应改写成什么

1. **Problem/interface**：形式化 zero per-task data handoff 的 Question-Only Analytics，但不声称它首次出现；明确运行边界是预授权、未经整理的数据环境。
2. **Mechanism/runtime**：提出 executable Analytical Sufficiency Contracts 和 Closed-Loop Data Discovery；下游执行产生 typed violations，触发 source/prep backtracking、依赖失效与选择性 replay。
3. **Demonstration/evidence**：在 CoDA-style noisy environments 中展示“初始来源语义相关但分析上不足”的真实任务，比较线性 pipeline、全量 content profile 和 closed-loop runtime，并同时评估 report success、repair、成本与正确拒答。

建议使用的非首创式主张是：

> We demonstrate a question-only analytics system that closes the loop between data discovery and downstream analysis: execution-grounded sufficiency violations trigger automatic source repair and downstream rematerialization before a report is accepted.

在完成系统性 related-work 检索和对照实验前，不写 `the first`。

## 8. 必须过的 novelty gate

新定位比旧定位更清楚，也更容易被证伪。实现前应先验证：

1. 至少存在一组自然任务，其中 top-1/语义最相关来源会生成“能运行但分析不足”的结果，而不是简单文件不存在或代码报错。
2. 当前原型中，下游检查能把失败稳定归因到 source obligation，而非只输出模糊的 LLM critique；preparation-targeted attribution 是后续扩展。
3. 与线性 `discover → prepare → analyze → report` 相比，跨阶段 rediscovery 显著提高完整报告成功率或正确 abstention。
4. 与 full-profile baseline 相比，progressive discovery 在完整内容画像、tool calls、tokens 或时延上有实际节省；所有模式的 path/header 索引成本须单独披露。
5. 3--5 分钟现场路径中至少出现一次可见的 `report/analysis → discovery` 反向边，并在换源后明确显示哪些指标/claims 被修复或仍不可答。

如果第 1--3 项不成立，这个系统仍然只是优秀的自动化产品，但不足以成为有清晰数据库研究贡献的 VLDB Demo。

## 9. 可复核材料

- 全部 301 个标题：[demo-title-corpus-2025-2026.md](demo-title-corpus-2025-2026.md)
- 官方来源、纳入规则、接口与失败：[demo-title-query-log-2025-2026.md](demo-title-query-log-2025-2026.md)
- Crossref 原始响应：[demo-title-crossref-raw.json](demo-title-crossref-raw.json)
- OpenAlex HTTP 429 原始响应：[demo-title-openalex-raw.json](demo-title-openalex-raw.json)
- 可重复采集脚本：[collect_demo_titles.py](../scripts/collect_demo_titles.py)

标题统计是定位证据，不是完整 related-work review；下一阶段若作者确认此定位，仍需围绕 `closed-loop data discovery`、`analysis-guided data acquisition`、`query answerability`、`data programming/backtracking` 和 `agentic deep research` 做正文级系统检索。
