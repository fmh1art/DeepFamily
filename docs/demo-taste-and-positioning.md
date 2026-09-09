# VLDB 2027 Demo：审稿 taste、近一年样本与定位决策稿

状态日期：2026-09-06（Asia/Shanghai）  
本稿用途：冻结“为什么做、展示什么、如何区别于最近 Demo”的方向；不代表系统已经实现。

> **状态更新：** 作者已否决本文早期的 ClaimDelta / ContractDA 两个候选。当前推荐方向已改为 [Question-Only Analytics](question-only-positioning.md)。本文保留为 Demo taste、近一年样本和绘图调研档案，不再代表当前选题。

## 0. 先给结论

### 热点判断

近一年更值得追的并不是宽泛的 **LLM for Data Analysis**，而是：

> **可控、可检查、可验证的 agentic data workflow。**

2026 年 VLDB 与 SIGMOD 的录用题目中，LLM/Agent/NL/RAG 和 interactive/visual/human-facing 都是高频信号；但 DA-Studio、DeepEye、BobFlow、Carnot 已经把“端到端分析、工作流可视化、代码/节点编辑、局部重跑”覆盖得很充分。因此，仅把 CoDA-Bench、DeepPrep、DeepAnalyze 串成一个前端，会落入已经拥挤的 “all-in-one data agent” 定位。

### 推荐定位（方案 A）

工作标题：

> **ClaimDelta: Revealing How Discovery and Preparation Decisions Change Analytical Claims**

可用于摘要或视频的 hook 是：**Beyond file uploads: what changes in the answer when an upstream data decision changes?**

中文定位：

> 用户只给分析目标而不指定正确文件。系统不会把 Data Discovery 与 Preparation 中多个合理候选静默压缩成一条唯一轨迹，而是保留可干预的上游决策；完成分析后，用户能够看到哪些最终 claims 在合理替代方案下保持稳定、发生数值偏移、方向翻转或失去支持。

这个定位的主角不是“三个模块”，而是一个新的、观众可直接操作的系统抽象：

> **自动捕获 Agent 上游选择的 alternative-aware decision graph，以及把执行分支对齐到 structured claims 的 inspect → fork → replay → compare 影响闭环。**

边界必须说严谨：静态的 `claim → source ID` 归因、workflow what-if debugging 和人工定义的 multiverse analysis 都已有相邻工作。方案 A 的差异点应是 **no-oracle discovery、Agent 隐式决策的自动捕获、跨 preparation/analysis 状态的依赖链，以及这些决策对 structured claims 的 on-demand impact delta**。首版不应声称枚举全部组合或证明统计稳健性。

它恰好利用三篇支撑工作，而不是简单拼接它们：

| 支撑工作 | 可继承能力 | 在新 Demo 中的角色 |
|---|---|---|
| CoDA-Bench | 在大量相似干扰文件中寻找相关数据；有 discovery ground truth | 提供“不预先上传正确文件”的真实 Data Discovery 场景与数据 |
| DeepPrep | tree-based reasoning、物化中间表状态、非局部回退、数据准备算子 | 提供可检查、可分支的 Data Preparation 状态骨架 |
| DeepAnalyze | 多文件执行、分析、可视化与报告生成 | 提供 Data Analysis 和 claim/artifact 出口；不复刻 DA-Studio 的论文定位 |

### 备选定位（方案 B）

工作标题：

> **ContractDA: Contract-Guided Data Discovery, Preparation, and Analysis**

把自然语言目标编译为一个用户可编辑的 analysis contract，显式描述所需实体、属性、粒度、质量条件、目标 schema 和分析输出。Discovery 按 contract 覆盖度寻找数据，Preparation 满足 schema/quality 约束，Analysis 检查输出是否符合目标；用户修改一项约束即可观察三阶段共同重规划。

方案 B 的优点是架构清楚、与 DeepPrep 的 target schema 自然衔接；缺点是现场“惊喜点”弱于方案 A，而且 Trace Integrity 等近期工作已经使用 execution contracts 绑定 intent、schema、operator plan、query 与 final answer。除非能提出更具体且可执行的 contract semantics，否则不再建议把它作为同等强度的投稿方向，只保留为工程降级方案。

### 两个方案的拍板矩阵

| 维度 | 方案 A：ClaimDelta | 方案 B：Contract-Guided |
|---|---|---|
| 与三篇支撑工作的咬合 | 强：分别承担 discovery、materialized prep state、analysis claim/artifact | 强：以 target schema/quality contract 串联三阶段 |
| 相对相邻工作的区分度 | 有条件较强：自动捕获 discovery/prep alternatives + structured claim delta | 偏弱：与 execution contract、policy/data contract 相邻 |
| 现场 wow moment | 强：系统先标出 fragile claim；一次上游替换让它翻转，并显示决策证据链 | 中等：改一项 contract 后三阶段共同重规划 |
| 数据管理内核 | lineage/provenance、版本、依赖失效与复用 | constraint/contract、规划与验证 |
| 主要实现风险 | claim 协议与跨阶段 lineage 必须真实可靠 | contract 语义可能过宽，贡献容易显得只是 orchestration |
| 建议 | **主方案；先做 G1--G5 验证** | **仅作技术降级备选** |

### 不建议的定位

> “一个覆盖 Data Discovery、Data Preparation、Data Analysis 的端到端自主数据科学平台。”

它描述的是功能清单，不是可评审的技术定位。与 DA-Studio、DeepEye、Carnot 和 BobFlow 的重合太大，也无法回答“观众为什么必须来看这个 Demo”。

## 1. 对 Demo paper 常见理解的纠正

| 原理解或常见误区 | 更准确的要求 / taste |
|---|---|
| 一篇 research paper 加一个前端就是 demo paper | 支撑论文能证明技术深度，但 Demo 仍需独立说明系统新意、架构和独特的 audience experience。前端只是让核心机制可见、可操作的媒介。 |
| 覆盖功能越多越好 | 四页中 breadth 很容易稀释贡献。优秀 Demo 通常只有一个中心交互命题，其余功能为它服务。 |
| “使用 LLM/Agent”本身足够新 | 2026 录用集中已经非常拥挤。新意应落在数据管理抽象、执行语义、可靠性、交互机制或真实部署，而不是模型标签。 |
| Demo 不需要实验 | 不要求 research paper 规模的评测，但一张小表、一个延迟/规模数字或一个可复现的 before/after，能显著提升可信度。BobFlow 就在四页中保留了轻量结果表。 |
| 把底层研究论文引用一下即可，不必自包含 | 公开的 VLDB Demo 评审意见明确批评“反复提到但没有解释/没有展示”的机制；Demo paper 仍需自包含。 |
| 视频是 optional，可以最后再做 | 形式上可选，策略上应视为评审材料。视频要展示真实交互和核心差异，而不是产品宣传片。 |
| 观众看系统自动跑完就是互动 | 官方更偏好高互动。好的互动是观众做出选择后，系统内部状态和最终结果发生可解释的变化。 |
| 只要界面漂亮即可 | 真实系统、可解释架构、稳定执行和失败备份同样重要。系统型论文重视 credible prototype、robustness、manageability 和能解释行为来源的测量。 |

公开的 VLDB 2020 Demo 评审很有代表性：优点包括强支撑工作、清楚且详细的 demo 计划、问题与方案表述明确；弱点包括标题含糊、没有截图/视频、Demo 描述过短、论文不自包含，以及放入没有解释清楚的图。该案例最终录用，但三位 reviewer 的分歧说明“技术不错”不能替代清楚的现场体验设计。

## 2. 官方硬要求与当前不确定项

### VLDB 2027 已确认

- 会议时间地点：2027-08-23 至 2027-08-27，Athens, Greece。
- 所有 track 都必须严格使用官方 PVLDB 模板；遗漏 copyright、reference format、artifact 等 mandatory blocks 或偏离格式，可能 desk reject。

### VLDB 2027 尚未确认

截至状态日期，官网尚未发布 2027 Demonstration Track 的 CFP、截止日期、chairs、页数和视频细则。官网 Important Dates 当前只有 Research Track 行。因此下面的 4 页、匿名方式和视频限制只能作为规划假设，不能当作 2027 最终规则。

### 用于规划的 VLDB 2026 Demo 规则

- 4 页，**所有内容**均计入页数，且按 camera-ready format 投稿。
- single-anonymous：论文中保留作者和单位。
- 必须说明系统、novelty/significance、架构、功能、准确的 demo scenarios、目标用户如何体验，以及界面和交互选项。
- 高 audience interaction 的 proposal 优先。
- 鼓励附最长 5 分钟、最大 50 MB 的视频，格式为 MPEG/AVI/MP4。

### SIGMOD 2026 对 taste 的交叉验证

SIGMOD 的官方 CFP 更直接地把两个评分维度写为 **audience experience** 和 **system novelty**，并要求回答：观众究竟看到什么、能否亲手交互、是否有有趣的场景/脚本。它还要求说明 novel intellectual content、architecture、target users/use cases，并明确优先考虑以前没有展示过的系统；视频或论文需要区分已经实现与计划实现的部分。

这意味着 DeepAnalyze 已有 DA-Studio 被 VLDB 2026 Demo 接收，是必须主动处理的重复风险。新的系统和论文不能只是 DA-Studio 加一个 discovery tab。

## 3. 近一年录用题目统计

### 数据与方法

- 样本：VLDB 2026 官方 Demonstrations 页面 92 篇，SIGMOD 2026 官方 Accepted Demo Papers 页面 39 篇，共 131 篇。
- 采集日期：2026-09-06。
- 方法：只在标题上使用预先定义的关键词组匹配；类别允许重叠。
- 限制：这是录用集合而非全部投稿，不能据此推断录用率或声称某关键词导致录用；它只能说明最新 program 中哪些表达和问题密集出现。

| 标题信号 | VLDB | SIGMOD | 合计 | 占 131 篇 |
|---|---:|---:|---:|---:|
| Query / SQL / Optimization | 28 | 11 | 39 | 29.8% |
| LLM / Agent / NL / RAG | 22 | 15 | 37 | 28.2% |
| Interactive / Visual / Human-facing | 20 | 15 | 35 | 26.7% |
| Discovery / Integration / Preparation | 8 | 11 | 19 | 14.5% |
| Analysis / BI / Data Science | 8 | 6 | 14 | 10.7% |
| Vector / Graph / Multimodal | 9 | 7 | 16 | 12.2% |
| Trust / Provenance / Verification | 9 | 1 | 10 | 7.6% |
| Benchmark / Diagnosis / Evaluation | 5 | 5 | 10 | 7.6% |

进一步看保守的交集：

- AI/Agent 与 interactive 同时出现：12 篇（9.2%）。
- AI/Agent 与 discovery/preparation 同时出现：5 篇（3.8%）。
- interactive 与 discovery/preparation 同时出现：3 篇（2.3%）。
- 三组同时命中：0 篇。这里的 0 只表示标题未同时写出这些词，并不表示论文内容没有交叉。

### 对选题的含义

1. Agent 是流量入口，不是区分点。
2. “让 agent 的内部过程变得可见、可改、可验证”是明显的近期 taste。
3. Discovery/Preparation 仍是数据库社区认可的硬问题，比泛化的聊天式分析更容易建立 data-management relevance。
4. 最有机会的交叉点不是再做一个端到端 agent，而是把 **noisy-lake discovery** 与 **可追溯的 downstream claims** 联结起来。

## 4. 代表性 Demo 精读：内容与绘图

下面均为 2026 年真实录用 Demo；论文接收身份以两会官方列表为准。

| 工作 | 核心内容与现场动作 | 图的组织 | 对我们的启示 / 重合风险 |
|---|---|---|---|
| [BobFlow](https://www.vldb.org/pvldb/vol19/p4718-bai.pdf), VLDB 2026 | 用 dataflow 代替 script 作为人机共同抽象。用户检查历史 operator，针对 NaN 处理给反馈，从旧版本分支并看到最终 rating 改变。 | 5 图 + 1 小表。Fig.1 先做 Script ReAct vs Dataflow ReAct 对比；Fig.2 架构；Fig.3 真实界面跨三任务演进；Fig.4 reasoning loop；Fig.5 放大关键修复动作。 | 很强的范本：首图说明问题，末图证明互动，还有轻量数字。也说明“历史分支/回退”不能单独作为我们的新意。 |
| [Carnot](https://www.vldb.org/pvldb/vol19/p4642-russo.pdf), VLDB 2026 | 把 deep-research query 编译为 DAG；用户先检查计划，再通过 chat 或 notebook 修改 operator；系统复用不受影响的缓存并按成本/延迟约束重优化。 | 只有 2 张大图：一张端到端架构，一张三栏真实 workspace。正文把 demo 拆成 plan inspection、chat steering、notebook editing 三段。 | 证明两张信息密度高且可读的图可以胜过许多小图。局部重算也已被覆盖，我们必须强调 discovery choice 与 claim impact。 |
| [Guixu](https://www.vldb.org/pvldb/vol19/p4562-wu.pdf), VLDB 2026 | 任务/预算驱动的数据发现与采购。观众比较零预算与 2 美元预算，检查候选数据的评分、knapsack 选择和链上交易。 | 4 图：首屏 overview、三阶段 valuation pipeline、on-chain lifecycle、整宽 UI。两个场景只改变一个关键变量——预算。 | 好 Demo 常让观众改变一个条件，观察清楚的系统决策差异。我们不应做预算/估值方向，以免正面重合。 |
| [DA-Studio](https://arxiv.org/pdf/2606.31423), VLDB 2026 | 上传多格式文件，流式查看 action trace，预览中间 artifacts，编辑/重跑代码并导出报告。它直接由 DeepAnalyze 支撑。 | 3 图：首图概览输入→workflow→报告；五层架构图；用 1–5 标注的真实界面，和正文五步完全对应。 | 是最直接的自我重复风险。新的 Demo 应复用分析能力，但不能继续以“sandboxed, inspectable end-to-end analysis”为主张。 |
| [DeepEye](https://arxiv.org/pdf/2603.28889), SIGMOD 2026 | workflow-centric data agent；用户通过 `@` 显式绑定数据/知识源，观看 DAG 并行执行，生成视频、dashboard、report；再编辑 SQL node，触发 schema mismatch validator 并重跑。 | 2 张图：一张详细架构，一张 A–G 标注的整页界面/输出拼图。两个场景分别展示自动化和 human-in-the-loop。 | “异构源 + DAG + 人工改节点 + 多模态输出”已经被占位。我们的入口必须是自动发现未知相关文件，而非用户先绑定正确源。 |
| [AmbiSQL](https://arxiv.org/pdf/2508.15276), SIGMOD 2026 | 检测 Text-to-SQL 歧义，向用户生成多选澄清，再把有/无澄清的 SQL 并排比较。支持 40 个即点即用案例和用户自带数据库。 | 3 图：两阶段 pipeline、三面板主界面、澄清控件与 before/after SQL close-up。 | “并排差异”是非常强的 demo proof。我们的最终屏应并排展示上游修复前后哪些 claims/metrics 改变，而不只是展示日志。 |
| [SemDisc](https://mirmahathir.com/papers/semdisc_demo.pdf), SIGMOD 2026 | query-by-example 发现 semantic/equi hybrid join paths；观众可上传 data lake、改索引参数、浏览 join graph、提交 query table、检查 hidden tables 和物化结果。 | 4 图：首图用一个完整例子定义三个难点；架构图；索引机制图；带 A–F 对应正文的真实 UI。 | Discovery 论文也必须给可操作对象，而不只是搜索框。我们的差异是从相关文件/路径继续到 preparation 和最终 claim lineage。 |
| [PROXAI](https://www.vldb.org/pvldb/vol19/p4706-lazzaro.pdf), VLDB 2026 | 从异常 ML prediction 的 SHAP 信号进入细粒度 provenance，追到 preprocessing root cause，修改后再训练并验证异常消失。 | 4 图：架构、feature importance、XAI 与 provenance 的交互连接、自然语言 provenance query。 | “provenance debugging”也不是空白。我们的边界应是 agentic source selection → table states → analytical claims，而非 ML prediction/XAI。 |

另有若干不是本轮 Demo 样本、但与 novelty 直接相邻的工作：[ProvenanceGuard](https://arxiv.org/abs/2606.18037) 已做 atomic claim-to-source attribution；[Trace Integrity](https://arxiv.org/abs/2608.26036) 已提出 execution contracts、structured artifacts 和 final-answer linkage；[QwenPaw-Data](https://arxiv.org/abs/2607.11019) 已包含 metadata/knowledge/trace graphs 与 artifact-centric runtime；[Dagger](https://www.vldb.org/pvldb/vol13/p2993-rezig.pdf) 支持数据流水线的 what-if split/compare；[Boba](https://idl.uw.edu/papers/boba) 则系统化执行并可视化多个合理分析路径及决策敏感性。完整压力测试见 [novelty-stress-test.md](novelty-stress-test.md)。

这些先例意味着我们不能声称“把 claim 连回 source”“保留多个分支”“做 what-if compare”或“显示 decision sensitivity”本身是新贡献。必须展示 **这些能力如何自动作用于 Agent 在未知数据源发现与准备阶段产生的隐式候选决策，并如何落到可对齐的自然语言分析 claims**。

### 从这些图中归纳出的版面 taste

优秀四页 Demo 通常让图承担三种不同责任：

1. **首图定义差异**：用一个具体失败或 before/after 说明为什么现有方式不够。
2. **架构图解释可行性**：只画产生核心体验所需的组件、状态和数据流，不把依赖库/logo 列表当架构。
3. **带编号的真实 UI 证明可演示性**：图上的 A–F 或 1–5 与 demo scenario 文本严格一一对应。

若有空间，第四类素材应是一个非常小的可信度证据（准确率、延迟、代价或规模），不是另一张装饰性 dashboard。所有截图应在双栏打印尺寸下仍能读出关键标签。

### 我们建议的三张主图

- **Figure 1 — The hidden upstream error**：同一个自然语言问题，经两个相似候选数据源产生两个貌似合理但相反的结论；中心放“click claim to trace”。这是整篇的 hook。
- **Figure 2 — Decision-to-claim impact graph**：`goal → candidate/selected sources → materialized prep states → analysis artifacts → claims`，同时给出 decision × claim impact matrix，突出 alternative-of、derives-from、supports 和 invalidation/replay 边。
- **Figure 3 — One repair, visible consequence**：三联真实界面截图：系统标出可能受上游歧义影响的 claim；点击追溯；选择 discovery/prep alternative 后并排比较 stable / shifted / flipped / unsupported claims。
- **Table 1（若版面允许）**：只给 2–3 个可核验数字，例如发现规模、局部 replay 相对全量重跑的延迟、claim lineage 覆盖率或一个小型任务正确率。指标必须先定义、后测量，不能现在预写结果。

## 5. 方案 A 的最小论证

### Problem

近期 data-agent systems 通常从用户已经上传或显式绑定的正确数据开始，或在执行时把每个候选选择立即压缩成一条轨迹，并把透明性停留在 action/code/operator 层。现实任务首先要在大量相似文件中找到数据；多个来源或准备路径可能都看似合理，却产生互相冲突的报告。用户不仅缺少从 claim 回到 source decision 的证据，也不知道一条 claim 是否会随着合理上游选择而改变。

### Proposed system abstraction

拟议的 alternative-aware decision/evidence graph 包含五类节点：

1. 用户目标及结构化需求；
2. 候选和已选数据源；
3. 数据准备 operator 与物化 table state；
4. 分析代码与 artifacts；
5. 报告 claims、metrics 和 charts。

系统计划维护 `candidate-of / selected-from / derives-from / uses / supports / alternative-of` 等关系。与传统单轨迹日志不同，系统保留 Discovery/Preparation 阶段已有证据支持的候选选择；用户或系统按需选择一个局部 alternative 后生成真实执行分支，再在 table、metric、chart、claim 四个层级对齐。首版允许全量重跑；只有实现并验证依赖闭包后才声称 selective replay。

这里的“claim-level”必须落到可实现协议：报告不输出无法追踪的自由文本，而应输出结构化 claim，显式引用产生它的分析 artifact、代码步骤和数据状态。否则只能称为 action trace，不能称为 claim lineage。

### Target user

需要在组织级文件湖中完成一次性分析、但不完全掌握文件位置和数据质量的 analyst/domain expert。不是以训练模型或调参为主的 ML engineer，也不是数据库应用生成开发者。

### 一条 3–5 分钟的现场故事

1. **Goal only**：观众输入一个 CoDA-Bench 风格问题，不提供文件名。系统展示候选源、选择证据和被保留的合理 alternative，而不是只留下最终文件名。
2. **Prepare and analyze**：系统展示 DeepPrep 风格的物化准备状态，并生成一个图表和两三条结构化结论；每条结论标出当前已执行 alternatives 下的 impact 状态。
3. **Challenge a claim**：观众点击一条 sensitive/fragile 结论，界面高亮支撑它的文件、行/列摘要、准备节点、分析 artifact 与相关 decision alternative。
4. **Repair upstream**：观众换一个候选源或修改一个准备决策，产生新分支；依赖节点被选择性重跑。
5. **Compare impact**：界面并排标出 stable / shifted / flipped / unsupported / added claims，并解释变化来自哪个 source/prep decision。

最关键的“wow moment”必须是：**观众只改一个上游选择，系统立即显示某条最终结论翻转或数值显著变化，并能给出完整证据链。**

### 与最近工作的边界

| 最近系统 | 它已经做了什么 | 方案 A 必须证明的差异 |
|---|---|---|
| DA-Studio | uploaded files 上的 trace、artifact preview、code edit/rerun、report export | 从无 oracle 文件的 discovery 开始；提供 claim→source 关系与跨阶段差异，而不只是 action trace |
| DeepEye | 显式绑定异构源、DAG inspection、node editing、validation、多模态输出 | 自动发现未知相关源；比较 source/prep alternatives 对最终 claims 的影响 |
| BobFlow | operator-level dataflow、历史版本反馈与分支 | 文件不是预先给定；分支对象包含 candidate source 与 table state；最终比较单位包含 claim，不只 operator output |
| Carnot | plan inspection、cell edit、缓存复用、局部重执行、成本优化 | 核心不是 operator optimization，而是 discovery provenance 与 claim impact |
| TINE | agentic app 的 branch-per-instruction，绑定 Git、DB branch、runtime trace | 对象是分析证据与结论，不是 app revision；比较的是数据/结论语义变化 |
| PROXAI | XAI-guided ML pipeline provenance debugging | 从分析 claim 出发，跨 data discovery/preparation/analysis；不以预测解释或 retraining 为中心 |
| ProvenanceGuard | MCP trace 上的 atomic claim-to-source attribution 与 factuality verification | 不把静态 attribution 当作新意；核心是 noisy-lake discovery/preparation decision 的分支干预与 downstream claim delta |
| Trace Integrity | execution contract、structured artifact、operator/query verification 与 final-answer linkage | 不把 structured trace 当作新意；比较多条各自可执行的有效轨迹对 claim 的不同影响 |
| QwenPaw-Data | heterogeneous asset grounding、metadata/knowledge/trace graph、artifact-centric runtime | 不把 graph 或 traceability 当作新意；聚焦 unknown-file discovery alternatives 与 claim impact interaction |
| Dagger | 对已有 data-science pipeline 做 data-centric split/compare 和 what-if debugging | 不把 what-if primitive 当作新意；决策来自 Agent 对未知源/准备路径的自动探索，比较对象包含 structured report claims |
| Boba | 用户用 DSL 显式定义 analytic decisions，执行 multiverse，并可视化 outcome sensitivity | 不声称完整 multiverse；自动捕获 Agent 的隐式 discovery/prep alternatives，按需执行，并对齐语义 claims 而非预定义 point estimates |
| AvalancheBench | 用 latent-world ground truth 评估早期分析错误如何传播到后续结论 | 它是 benchmark；方案 A 必须是用户可干预的运行系统，并用真实 execution branches 展示影响 |
| Guixu / SemDisc | task-aware dataset selection；semantic join-path discovery | 它们止于获得数据；方案 A 把选择一直连接到最终分析结论和修复影响 |

### 预期贡献写法（当前只能用 future tense）

1. An alternative-aware evidence model that automatically captures plausible source and preparation decisions made during agentic analysis and links them to materialized states, artifacts, and structured claims.
2. An interactive inspect–fork–replay–compare workflow that aligns on-demand execution branches and exposes stable, shifted, flipped, unsupported, and added claims after an upstream intervention.
3. A working end-to-end demonstration on noisy, CoDA-Bench-style data environments, backed by DeepPrep and DeepAnalyze execution capabilities.

## 6. 决策门槛与风险

方案 A 值得确认，但确认的是研究/演示方向，不是现在就宣称能实现全部功能。进入开发前应通过四个 feasibility gates：

- **G1：claim protocol** — 能否让分析输出稳定地产生“claim + artifact references”，而不是事后让 LLM 猜证据。
- **G2：cross-stage identity** — 文件、table state、code artifact、claim 是否都有稳定 ID，可跨服务传递。
- **G3：selective replay** — 上游改变后能否可靠计算 dependency closure；如果第一版只能全量重跑，论文中不能声称 selective replay。
- **G4：live latency** — 在一个精简 CoDA community 上能否把核心闭环控制在 3–5 分钟，并准备完全离线的固定案例。
- **G5：adjacent-work delta** — 能否用一个真实交互同时证明“候选决策由 Agent 自动产生”“源文件未知”“输出是 structured claims”，从而与 Boba、Dagger、Trace Integrity 区分；缺一项都会显著削弱定位。

当前已知版本风险：附件中的 CoDA-Bench 早期稿与当前公开仓库的任务数/社区数不同。开发和论文必须固定到一个公开 release、记录 commit/checksum，并重新测量所有数字。DeepAnalyze 已有 DA-Studio，相关工作和 novelty statement 必须主动披露。

## 7. 历史确认项（已废弃）

以下表述已被作者否决，仅保留决策记录：

> **选择方案 A（ClaimDelta）。把系统定位为“无需用户预先给出正确文件，自动保留 Agent 在 Discovery/Preparation 中的合理候选决策，并揭示这些选择如何改变最终分析 claims 的 alternative-aware data agent”；Data Discovery、Preparation、Analysis 是工作流，agent-decision capture + cross-stage evidence + structured claim delta 才是论文中心。**

当前后续动作以 [question-only-positioning.md](question-only-positioning.md) 为准。

## 8. 主要来源

### 官方规则与录用列表

- [VLDB 2027 overview](https://www.vldb.org/2027/)
- [VLDB 2027 formatting guidelines](https://www.vldb.org/2027/formatting-guidelines.html)
- [VLDB 2027 important dates](https://www.vldb.org/2027/important-dates.html)
- [VLDB 2026 Call for Demonstrations](https://www.vldb.org/2026/call-for-demonstrations.html)
- [VLDB 2026 accepted demonstrations](https://vldb.org/2026/demonstrations.html)
- [SIGMOD 2026 Call for Demonstration Proposals](https://2026.sigmod.org/calls_sigmod_demos.shtml)
- [SIGMOD 2026 accepted demo papers](https://2026.sigmod.org/sigmod_demos.shtml)

### 写作与系统 taste

- [公开的 VLDB 2020 Demo reviews](https://dbis.cs.tu-dortmund.de/publikationen/2020/like-water-and-oil/vldb-2020-reviews/)
- [ACM SIGMOD Blog: Systems & Databases—Let’s Break Down the Walls](https://wp.sigmod.org/?p=1009)
- [ACM SIGMOD Blog: On Data Exploration in the Era of Big Data](https://wp.sigmod.org/?p=2277)
- [University of Washington: How to Give a Demo Presentation](https://courses.cs.washington.edu/courses/cse403/24wi/project/demo.html)

### 三篇支撑工作的当前公开制品

- [DeepPrep repository](https://github.com/ruc-datalab/DeepPrep)
- [DeepAnalyze repository](https://github.com/ruc-datalab/DeepAnalyze)
- [CoDA-Bench project page](https://coda-bench.github.io/)
- [CoDA-Bench repository](https://github.com/ruc-datalab/CoDA-Bench)

## 9. 文献元数据核验说明

本轮按 paper-lookup 工作流查询了 Crossref 与 OpenAlex，并以论文 PDF 首页、会议官方录用列表和作者仓库交叉核验：

- Crossref endpoint：`https://api.crossref.org/works?filter=doi:<DOI>&select=DOI,title,author,published,container-title,type,URL&rows=1`
- OpenAlex endpoint：`https://api.openalex.org/works/https://doi.org/<DOI>?select=id,doi,title,publication_year,primary_location,authorships`
- 查询 DOI：BobFlow、Carnot、Guixu、DeepEye、SemDisc。
- Crossref 返回了 DeepEye 与 SemDisc 的 ACM proceedings metadata；三个 `10.14778/...` PVLDB DOI 在 Crossref 查询中返回空集合，因此相关元数据采用官方 PVLDB PDF。
- OpenAlex 在本轮查询时返回当日额度不足，未将其作为任何事实依据。原始响应见 [metadata-query-log.md](metadata-query-log.md)。
