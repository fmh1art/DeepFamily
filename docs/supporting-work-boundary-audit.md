# 三篇支撑工作的能力边界与重复投稿审计

状态日期：2026-09-06（Asia/Shanghai）  
用途：在选定 Demo 定位前，区分“已有论文能力”“可复用工程资产”和“新 Demo 必须真实新增的能力”。本文件不声称任何待实现功能已经存在。

> **状态更新：** 本文最初围绕已否决的 ClaimDelta 方向撰写。三篇支撑论文的输入假设与能力边界仍有效；当前系统定位与新的复用方式见 [question-only-positioning.md](question-only-positioning.md)。

## 1. 总结性判断

三篇支撑工作能够覆盖完整数据生命周期，但不能直接拼接成 ClaimDelta：

- **CoDA-Bench 提供 Discovery 的问题与评测环境，不提供一个可直接复用的数据发现系统。**
- **DeepPrep 提供可执行的数据准备树和物化中间状态，但输入已经包含 source tables 与 target schema。**
- **DeepAnalyze 提供从已指定数据源到分析报告的执行能力，但不负责从 noisy lake 中发现源文件，也没有跨阶段的 structured claim lineage。**

因此，方案 A 是否成立，取决于能否新增并展示 `discovery decision → preparation state → analysis artifact → claim delta`，而不是能否把三个已有界面放进同一页面。

## 2. 原文证据与能力矩阵

| 支撑工作 | 原论文已经解决的问题 | 原论文的关键输入假设 | 可以复用的资产 | ClaimDelta 仍缺少的能力 | 不能再次包装成新意的内容 |
|---|---|---|---|---|---|
| CoDA-Bench | 在包含大量相似文件的 Linux sandbox 中联合评测 code intelligence 与 data intelligence | Agent 获得任务与整个文件环境，自行探索并输出答案/代码 | data communities、tasks、文件噪声、答案与 solution/evaluation artifacts | 面向用户的数据源候选、选择理由、稳定 source ID、交互式替换与下游影响追踪 | benchmark 构造、Kaggle community、联合评测 code/data intelligence |
| DeepPrep | 给定源表和目标 schema，自主构造并执行 data preparation pipeline | **Source tables 与 target schema 已给定** | operator library、tree-based reasoning、materialized table states、runtime feedback、branch/backtrack | 把 Discovery 选中的文件注册为可追踪 source decision；把 prep states 与 downstream artifacts/claims 连通 | autonomous preparation、tree-based exploration、materialized state、non-local backtracking |
| DeepAnalyze | 从数据源完成 preparation、analysis、modeling、visualization 与 report generation | 论文明确写明外部数据源的 **filenames are specified in inputs** | sandbox/tool execution、analysis code、charts/tables、report generation | 无 oracle 的文件发现；结构化 claim protocol；claim-to-artifact links；branch alignment 与 impact delta | autonomous data science、curriculum-based agentic training、data-grounded trajectory synthesis、analyst-grade report |

证据位置：

- CoDA-Bench 附件 PDF 第 1 页摘要与 Introduction：任务要求 Agent 在数百个候选文件中主动探索；该工作被定义为 benchmark。
- DeepPrep 附件 PDF 第 2 页 `Our Proposal` 和 `Problem Statement`：系统输入是 source tables `S`、target schema `Σ*` 与 operator types `O`；执行树的节点已经是物化表状态。
- DeepAnalyze 附件 PDF 第 3--4 页：贡献集中在 agentic model/training；Architecture 明确说明外部数据源文件名由输入指定。

## 3. 方案 A 必须新增的五项系统能力

### N1. Discovery decision objects

系统不能只返回文件名。每次候选与选择都要形成稳定对象，例如：

```text
SourceDecision {
  decision_id,
  task_requirement_id,
  candidate_source_ids,
  selected_source_ids,
  evidence_refs,
  decision_status
}
```

这是后续追踪、替换和比较的锚点。若只有 LLM terminal log，就仍然只是 CoDA-style agent trajectory。

### N2. Cross-stage identity

至少需要稳定标识以下对象，并在服务边界中传递：

```text
source_version_id → prep_state_id → analysis_artifact_id → claim_id
```

其中 source 必须包含版本/校验信息，prep state 必须对应真实物化状态，artifact 必须对应执行产生的表、数值或图，而不是仅有自然语言描述。

### N3. Structured claim protocol

报告输出应把可核验结论与普通叙述分开。每条 claim 至少包含：

```text
Claim {
  claim_id,
  text,
  value_or_relation,
  artifact_refs,
  derivation_step_refs,
  status
}
```

`artifact_refs` 必须在生成时建立；事后让另一个 LLM 猜测证据，只能叫 attribution heuristic，不能作为可靠 lineage。

### N4. Branch alignment and claim delta

用户替换数据源或准备决策后，系统需要比较两个真实执行分支，并输出：

- unchanged：证据和结论等价；
- changed：可对齐但数值、方向或文本关系改变；
- invalidated：原 claim 的依赖不再存在或执行失败；
- added：新分支产生的新 claim。

这是方案 A 相比静态 claim-to-source attribution 的主要技术边界，但 branch compare 与 decision sensitivity 本身也已有 Dagger、Boba 等先例。ClaimDelta 必须进一步证明这些 alternatives 是从 Agent 对未知数据源和准备路径的实际探索中自动捕获的，并且比较对象是 artifact-grounded structured claims。第一版即使采用全量重跑，也可以计算 delta；只有在 dependency closure 与缓存复用确实实现并测量后，才能使用 “selective replay” 表述。

### N5. A proof-oriented interaction

界面必须让观众完成一次可验证干预：点击 claim、看到证据路径、替换一个上游选择、执行新分支、并排查看 delta。单纯展示三个 tab、聊天记录或自动生成报告，不足以证明上述系统机制。

## 4. 投稿时的 claim 红线

在实现和测量前，不应使用以下表述：

- “the first autonomous end-to-end data analysis system”——DeepAnalyze/DA-Studio 已经覆盖。
- “the first tree-based/backtracking data preparation agent”——属于 DeepPrep 原贡献。
- “the first claim-to-source provenance system”——传统 provenance 与近期 source-aware claim verification 均有相邻工作。
- “a novel data discovery algorithm”——CoDA-Bench 是 benchmark；除非新系统确实设计并评测了 discovery 方法。
- “selective/incremental replay”——除非实现 dependency closure、状态复用，并与 full rerun 测量比较。
- “faithful claim lineage”——除非 claim 的 derivation/artifact references 来自真实执行，而不是事后模型解释。

当前更稳妥的预期表述是：

> We demonstrate a cross-stage evidence and comparison layer that exposes how alternative discovery and preparation decisions change downstream analytical artifacts and structured claims in noisy data environments.

这仍然是 future-tense 定位，不是已完成贡献。

## 5. 论文状态与披露风险

| 材料 | 当前附件显示的状态 | 投稿前必须确认 |
|---|---|---|
| CoDA-Bench | 匿名 early draft；页脚写有 ICML under review / do not distribute；附件数字与当前公开 release 不一致 | 最终公开版本、正式作者/引用、可公开使用的数据 release、commit/checksum；不得把匿名附件上传为 Demo artifact |
| DeepPrep | 有作者信息并声明 code/data/artifacts available | 最终发表状态、正式 BibTeX、代码与数据 license、Demo 使用的确切 commit |
| DeepAnalyze | Preprint；模型、代码和训练数据声明 open-sourced | 最新版本/发表状态、正式引用、代码/模型 license，以及与 DA-Studio Demo 的关系 |

无论 2027 Demo CFP 最终如何表述，论文都应主动引用三篇支撑工作和 DA-Studio，并用一段明确说明：哪些模块来自既有工作、ClaimDelta 新增了哪些数据对象、执行语义和观众交互。若其中任何论文在投稿时仍处于并行审稿或发表流程，还需按当时的 VLDB policy 做 related-submission disclosure。

## 6. A/B 决策门槛

建议在用户确认方案 A 后，先做不超过一个小型 CoDA community 的最小验证：

1. 一次分析能否产出 2--3 条带真实 artifact references 的 structured claims；
2. 改变一个 source/prep decision 后，能否稳定对齐两个分支的 claims；
3. 能否正确区分 changed / unchanged / invalidated / added；
4. 核心闭环能否在 3--5 分钟内稳定完成。

若第 1--3 项无法做到，方案 A 的 novelty 会退化为日志可视化，应立即转向方案 B，而不是继续扩展前端功能。
