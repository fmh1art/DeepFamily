# ClaimDelta Novelty Stress Test

状态日期：2026-09-06（Asia/Shanghai）  
目的：用最不利的 reviewer 解释检验方案 A。这里只确定可辩护的研究空位，不代表系统能力已经实现，也不是系统性文献综述。

> **归档说明：** 作者已否决 ClaimDelta 方向。当前定位见 [question-only-positioning.md](question-only-positioning.md)；本文只保留为相邻工作与 reviewer 风险档案。

## 1. 结论先行

三个版本的判断不同：

| 版本 | Reviewer 最容易给出的判断 | 当前建议 |
|---|---|---|
| “Discovery + Preparation + Analysis 的端到端 Agent” | 已有系统的功能拼接；与 DA-Studio、DeepEye、QwenPaw-Data 高度重合 | 放弃 |
| “给每个最终 claim 提供 source-to-claim lineage” | provenance、claim attribution、structured trace 都已有直接先例 | 不足以单独投稿 |
| “自动保留 Agent 在未知数据发现/准备中的合理候选决策，并展示它们对 structured claims 的影响” | 与现有单轨迹审计、人工 multiverse、已有 pipeline debugging 有可解释边界 | **有条件保留为主方案** |

最强的一句话不再是“trace every claim”，而是：

> **Most data agents silently commit to one plausible data path and return one plausible report. ClaimDelta keeps ambiguous discovery and preparation decisions explicit, then reveals which analytical claims survive reasonable alternatives.**

其中 `survive` 必须由真实执行分支和结构化 claim 对齐证明，不能由 LLM 自评。

## 2. 最相关的相邻工作

| 相邻工作 | 已经占据的能力 | 对 ClaimDelta 的直接威胁 | 尚可保留的边界 |
|---|---|---|---|
| [DA-Studio](https://arxiv.org/abs/2606.31423) | uploaded files 上的端到端分析、action trace、artifact preview、code edit/rerun、report | 不能再以 inspectable end-to-end analysis 为主贡献 | 输入文件未知；保留 discovery alternatives；比较 semantic claims |
| [DeepEye](https://arxiv.org/abs/2603.28889) | 显式 source binding、DAG、validation、node editing、多模态输出 | workflow-centric/steerable data agent 已被占位 | 候选源由 Agent 在 noisy lake 中发现，而非用户先绑定 |
| [Trace Integrity](https://arxiv.org/abs/2608.26036) | execution contracts、structured artifacts、schema/operator/query verification、final-answer linkage | structured trace 和 auditable answer 不是新意 | 比较多条各自有效的执行分支；研究决策敏感性而非单轨迹有效性 |
| [QwenPaw-Data](https://arxiv.org/abs/2607.11019) | heterogeneous assets、metadata/knowledge/trace graphs、artifact-centric runtime、end-to-end enterprise analytics | graph、traceability、retrieval-to-report 都不能单独构成定位 | unknown-file alternatives 到 structured claim delta 的特定交互 |
| [ProvenanceGuard](https://arxiv.org/abs/2606.18037) | atomic claim-to-source attribution 与 source-aware factuality verification | 静态 claim→source ID 已有近期直接工作 | source/prep decision intervention 后的真实 downstream change |
| [Kosmos](https://arxiv.org/abs/2511.02824) | 为科学报告中的 statements 引用代码或 primary literature | “报告结论可追踪”不是独有价值 | 追踪数据决策的替代分支，而不只是单个结论的引用 |
| [Dagger](https://www.vldb.org/pvldb/vol13/p2993-rezig.pdf) | 已有 Python data-science pipeline 的 inter/intra-module debugging；split/compare what-if | what-if pipeline debugging 和比较不是新意 | pipeline 尚未给定；决策来自 Agent 的 discovery/prep；比较 structured report claims |
| [Boba](https://idl.uw.edu/papers/boba) | 用户用 DSL 声明合理 analytic decisions，执行所有组合并可视化 decision sensitivity/outcomes | multiverse、decision graph、sensitivity view 都已有成熟系统 | 自动捕获 Agent 隐式决策；从 noisy discovery 开始；按需局部分支；semantic claim alignment |
| [Approximation and Progressive Display of Multiverse Analyses](https://arxiv.org/abs/2305.08323) | 用采样/近似缓解 multiverse 组合爆炸并逐步显示敏感性 | 若声称高效探索全部 alternatives，会直接进入其问题空间 | 首版限定为 on-demand local alternatives，不宣称穷举或近似全空间 |
| [AvalancheBench](https://arxiv.org/abs/2605.24183) | 用 latent-world ground truth 评估早期分析错误向结论传播 | “早期错误影响结论”已成为明确评测问题 | 从 benchmark 诊断转为可交互系统；观众修改决策并观察真实分支 delta |
| [“Skill Issues”: Data-Centric Optimization of Lakehouse Agents](https://arxiv.org/abs/2606.01185) | branching lakehouse、Git-like data primitives、state verification | branch/commit/state verification 不是新概念 | 分支围绕 source/prep ambiguity；最终对象是 analytical claims 而不是 agent skill reward |
| [Debugging Transactions with Reenactment](https://www.vldb.org/pvldb/vol10/p1857-niu.pdf) | 用 provenance 重放历史状态并支持修改代码/数据的 what-if | replay 与 provenance-assisted debugging 均有数据库先例 | 不宣称 replay 新颖；重点放到 Agent decision capture 与 claim semantics |

## 3. 不能拆开声称的新意

下列任一单点都不足以构成 2027 Demo 定位：

- 一个覆盖三阶段的 Agent；
- 一个 provenance/lineage graph；
- structured artifacts 或 execution contract；
- branch、version、replay 或 partial rerun；
- what-if compare；
- multiverse/decision sensitivity visualization；
- claim-to-source citation；
- 用户编辑节点后重跑。

ClaimDelta 只有作为下面这个**联合命题**才可能成立：

> 在用户没有给定正确文件时，系统自动记录 Agent 在 Data Discovery 和 Preparation 中产生且有证据支持的候选决策；对用户选择的局部 alternative 执行真实分支；然后把跨阶段 artifacts 对齐为 structured analytical claims，展示该上游决策造成的 semantic delta。

这里的潜在新意是问题交叉与系统语义，而不是上述基础机制中的任意一个。

## 4. Reviewer 攻击与最低答辩条件

| 可能的评审意见 | 如果现在投稿，为什么会成立 | 必须提供的反证 |
|---|---|---|
| “This is just an integration of three prior systems.” | 当前没有新增运行制品 | 一个跨三个阶段保持稳定 ID 的 decision/evidence store，以及真实 claim delta |
| “This is Boba for LLM agents.” | 决策图、alternatives、sensitivity view 的外观非常相似 | 决策由 Agent exploration 自动捕获；未知文件 discovery；无需用户编写 multiverse DSL；输出为 artifact-grounded semantic claims |
| “This is Dagger with an LLM UI.” | fork/compare 也是 data debugging | pipeline 在开始时不存在；source selection 是一等决策；展示从 source candidate 到 report claim 的跨阶段影响 |
| “Trace Integrity already provides structured, replayable traces.” | N1--N3 与 execution contract 重合 | 两条都通过 integrity 检查的有效轨迹，仍因合理上游选择产生冲突 claims；ClaimDelta 解释这个差异 |
| “The claim mapping is another hallucinated explanation.” | 若 lineage 是报告生成后再让 LLM 补的，批评完全成立 | claim 在生成时引用真实 artifact/step IDs；至少在固定任务上人工核验 mapping |
| “You cannot enumerate the decision space.” | Discovery × Preparation alternatives 会组合爆炸 | 明确只做 evidence-backed、on-demand local alternatives；不声称 complete multiverse |
| “The selected alternative is artificial.” | 手工制造错误会削弱可信度 | 从 CoDA 环境中的真实相似候选和 Agent 实际 trajectory 提取 alternative，并说明为何两者都 plausible |
| “Where is the database contribution?” | 若只展示聊天与报告，问题成立 | 版本化 data objects、cross-stage lineage、branch materialization、invalidation/reuse、claim alignment 的明确系统设计与测量 |
| “Why should users trust the stability label?” | 文本 claim 对齐容易出错 | 约束 claim schema；人工标注小型 gold set；报告 alignment/delta precision，而非只给案例 |
| “This was already demonstrated as DA-Studio.” | 同一 DeepAnalyze codebase 和相似 UI 会造成强烈印象 | 新入口、新数据对象、新核心屏幕和不同 audience action；论文主动披露 DA-Studio 并逐项区分 |

## 5. 建议的最小语义，不是实现承诺

### Decision

一个 decision 至少包含：阶段、候选项、当前选择、产生候选的 evidence、以及稳定 source/prep IDs。只有实际被 Agent 考虑或由任务证据支持的候选才进入图，不能随意生成 alternatives。

### Structured claim

为了可对齐，claim 不能只有自由文本。建议至少规范为：

```text
ClaimKey = (entity, metric, cohort, time_scope, comparator)
ClaimPayload = (relation, value, unit, artifact_refs, derivation_refs)
```

自然语言句子是 presentation；`ClaimKey + ClaimPayload` 才是系统比较对象。

### Claim delta

在两个已执行分支之间，对同一个 `ClaimKey` 给出：

- `stable`：relation/value 在定义的容差内一致；
- `shifted`：可对齐，但数值超出容差；
- `flipped`：方向、排序或符号改变；
- `unsupported`：新分支中原 derivation 不再成立；
- `added`：只在新分支出现。

这些标签的定义和容差必须在实验前固定。对于无法可靠结构化的开放文本，只显示两分支报告，不应自动贴上 faithful delta 标签。

## 6. 对方案 B 的重新评级

ContractDA 与 DeepPrep 的 target schema 很契合，但 Trace Integrity 已把 execution contracts 用于 intent、schema、operator plan、query 与 answer linkage，QwenPaw-Data 也覆盖 governable semantics/method/runtime assets。因此，普通的“可编辑 analysis contract 驱动三阶段”目前只能评为偏弱。

若方案 A 的 structured claim/delta 无法通过最小验证，更合理的选择可能不是立即转 B，而是重新定义一个更窄、具有可执行语义的 contract 问题。当前仍把 B 保留为工程 fallback，不建议以其现有表述直接写论文。

## 7. 当前拍板建议

建议确认的是经过压力测试后的 A+：

> **ClaimDelta is an alternative-aware data agent that automatically captures plausible discovery and preparation decisions in noisy data environments and reveals how on-demand interventions change artifact-grounded analytical claims.**

这是“值得先验证”的方向，不是“新颖性已经证明”。在拿到以下三项证据前，不写正式贡献句：

1. 一个真实 CoDA case 中，Agent 自然产生至少一个 plausible source/prep alternative；
2. 两个分支都能生成带真实 artifact references 的 structured claims；
3. claim alignment/delta 能被人工 gold annotation 验证。

若三项成立，方案 A 有清楚的 Demo hook；若不成立，应停止扩展 UI 并重新选题。

## 8. 检索范围与限制

本轮通过 Semantic Scholar API、arXiv 官方页面、VLDB/PVLDB 官方 PDF 与作者项目页检索。Semantic Scholar 的宽查询返回 16 条记录；后续四个定向查询及一次重试均遭遇公共池 429。arXiv Atom API 出现 TLS 连接错误，因此相关元数据改由 arXiv 官方页面核验。查询记录见 [novelty-query-log.md](novelty-query-log.md)。

这是定位压力测试而非系统性文献综述。Data-agent 方向变化很快，投稿前还必须再次检查 2026 年下半年至 2027 Demo CFP 截止日前的新论文和已接收 Demo。
