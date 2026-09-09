# Demo 事实采集表

状态日期：2026-09-09。本文只记录可追溯事实，并严格区分已实现能力、用户确认内容、
上下文推断和后续建议。当前定量效果证据来自 `community_43` 的完整 15 题机制评测和
`community_52` 的 2 题跨域可执行性探针；它证明已注册的确定性闭环与停机行为，不能证明
系统对一般分析任务有效。另有模型规划器/白名单 DSL 的合成离线测试、浏览器到 loopback
mock provider 的完整集成验证，以及一个尚未解盲的 13 题前瞻性协议；这些均尚未构成
模型效果结果。新增完整 open-pool agentic 实现及真实 provider 开发案例见
`docs/coda-deepprep-alignment.md` 与 `docs/agentic-smoke-evidence.md`；后者记录修复前后的
报告缺陷，不能作为冻结评测的准确率。下文 task 959 和末尾三分钟路径属于离线注册模式，
当前 agentic 主路径见 `docs/demo-rehearsal.md`。

## A. 原文 / 已有数据

### A1. 系统身份

- 当前界面与代码中的系统名：**Ask, Don't Upload**；Python 包与命令名为 `askdu`。
- 已确认论文标题：**Ask, Don't Upload: A Question-Driven Agentic System for
  Closed-Loop Data Discovery, Preparation, and Analysis**。
- 一句话描述：用户每个任务只提交分析问题；系统在预授权数据环境中发现和准备数据，
  执行分析，并把下游的 typed sufficiency violation 转成上游修复，最后返回带 artifact
  lineage 的报告或明确的数据缺口诊断。
- 当前制品：本工作区中的 `backend/`、`frontend/`、`compose.yaml` 和
  `scripts/fetch_research_assets.sh`；尚无公开代码仓库或线上地址。
- 当前开发版本：`0.4.0`；已报告的确定性实验已随本版本重新运行。复现命令见根目录 `README.md` 和
  `experiments/README.md`。
- 作者、单位和联系方式：`TODO（需作者提供）`。

### A2. 已执行的问题与数据管理失败案例

- 代表性已执行任务：CoDA-Bench `community_43` 的 task 959。唯一任务输入是原始英文分析问题，
  请求计算 2016 年 Grade 8 的 SHSAT 参加人数与 Asian、Black/Hispanic、White 学生占比
  的 Pearson correlation。
- 数据来源：Hugging Face `RUC-DataLab/CoDA-Bench`，固定 revision
  `63828a2b652e26a9770555a0cc41e6c8aafdb5d9`。该注册 pilot 环境包含 10 个可发现 CSV；
  archive、逐 CSV SHA-256 和来源/许可 metadata 分别见 `docs/asset-inventory.md`、
  `data/manifests/coda-community-43.sha256`、
  `data/manifests/coda-community-43-csv.sha256` 和
  `data/manifests/coda-public-source-provenance-v1.json`。
- 初始发现结果：`D5 SHSAT Registrations and Testers.csv`（140 行、7 列）。它包含
  year、grade 和 SHSAT 人数，但不包含三个 demographic percentage。
- 可执行失败：Preparation 过滤出 21 条 2016/Grade-8 记录；Analysis 随后产生
  `missing_analytical_columns` violation，而不是代码异常或模糊的 LLM critique。
- 闭环修复：运行时生成 `analysis -> discovery` repair edge，新增
  `2016 School Explorer.csv`（1,272 行、161 列），清洗百分比，并以
  `DBN` 与 `Location Code` 连接。该次物化有 21 行，left-side join coverage 为 100%。
- 为什么是 data management 问题：初始来源在语义上相关且可执行，但不足以满足分析所需
  的 measures/dimensions；是否继续检索、选择哪个来源、如何物化连接、何时允许报告，
  都由可检查的数据与 lineage 约束决定，而不是单纯的前端交互。

### A3. 已实现能力

| 能力 | 输入 | 输出 | 状态 | 证据位置 |
|---|---|---|---|---|
| Question-only API boundary | 只有 `question` 的 JSON | 持久化 `RunState` | 可运行 | `backend/deployment/api.py`、`backend/tests/test_api.py` |
| Analytical Sufficiency Contract | 两个 community 的 17 个已注册问题 | typed obligations | 可运行；当前为规则编译器 | `backend/src/askdu/application/compiler.py` |
| Model plan compiler | 问题与授权 catalog metadata | 严格 JSON ASC + declarative plan | 合成与 loopback contract 通过；该模式 held-out 尚未运行 | `backend/src/askdu/application/model_compiler.py`、`backend/tests/test_provider_contract.py` |
| Agentic open-pool Discovery | 问题与工具 schema | 逐跳目录/路径检索、inspect 与选中来源 | 已安装 30 个 community、30,292 个文件；实际开发 smoke 可运行 | `backend/src/askdu/application/agentic_pipeline.py`、`docs/agentic-smoke-evidence.md` |
| Agentic preparation tree | inspect 后的来源与候选计划 | 带 operator/state 的 candidate tree、输入/输出 schema 与表预览 | 支持候选执行与 parent/backtrack；所记录的真实 smoke 只触发 schema 拒绝后成功，未验证非局部回退 | `backend/src/askdu/application/agentic_pipeline.py` |
| Agentic notebook/report | 验证过的计划与实际 artifacts | 编译后 SQL/Python、执行观察、可选 Debug、多维报告 | 同一外部模型完成报告合成；引用完整性可校验，正文 factuality 未评测 | `backend/src/askdu/application/report_writer.py`、`docs/coda-deepprep-alignment.md` |
| Bounded declarative execution | catalog asset IDs 与白名单 plan | 物化状态、artifacts、report/diagnosis | 合成双源 join/aggregate 闭环通过 | `backend/src/askdu/adapters/declarative.py` |
| 受控数据发现 | 预授权 CSV 根目录、审计清单与 search terms | 排序、profile、来源/许可 metadata、摘要门和 source decision | 可运行；registered mismatch 会在 Preparation 前失败 | `backend/src/askdu/adapters/catalog.py`、`backend/src/askdu/adapters/provenance.py` |
| Registered Data Preparation | 已发现的 CSV 来源 | 过滤、去重、规范化、join、年度聚合与物化状态 | 可运行于 17 个已注册任务 | `backend/src/askdu/adapters/coda_pilot.py` |
| Closed-loop repair | 缺列或缺 category coverage 的 violation | repair goal 与 `analysis -> discovery` 边 | 可运行于 tasks 175/955/959/960 | `backend/src/askdu/application/orchestrator.py` |
| Registered Data Analysis | 准备后的物化状态 | count、means、Pearson、extrema 或 skewness artifacts | 可运行于 17 个已注册任务 | `backend/src/askdu/adapters/coda_pilot.py` |
| Report / abstention | artifacts 或未满足 obligations | 带 claim lineage 的 Markdown report，或 typed insufficiency diagnosis | 可运行 | `backend/tests/test_orchestrator.py` |
| Portable evidence export | 已完成的公开 `RunState` | 与 report artifact 字节一致的 Markdown；无源数据行/凭据的版本化 JSON bundle | 生产浏览器下载、内容与 SHA-256 验证通过 | `frontend/src/reportExport.ts`、`frontend/e2e/demo.spec.ts` |
| Anonymous run lifecycle | 当前 server retention policy 与 opaque run ID | 提交前披露、统一过期清理、活动 runtime 单 run 删除 | 浏览器 create/export/delete/404 与文件树清理测试通过；不等于身份认证或备份删除 | `backend/deployment/repository.py`、`backend/deployment/service.py`、`frontend/src/App.tsx` |
| Web demo | 一个自然语言问题 | catalog pin、contract、lifecycle、带 provenance 的 sources/report 和安全导出 | 生产构建与真实浏览器验收通过 | `frontend/src/App.tsx` |
| 单机容器部署 | 固定数据卷、入口模式和私有配置 | 宿主 TLS Nginx/ALB -> 容器 Nginx -> FastAPI | 本机容器链路与两种入口的静态预检通过 | `compose.yaml`、`infra/ecs/README.md`、`scripts/check_ecs_deployment.py` |

### A4. 当前可引用的执行结果

设置：同一台开发机，Python 3.10.20、pandas 2.3.3、revision-pinned CoDA-Bench；
每个 task/controller 组合执行一次确定性运行。主实验由
`make experiment-community` 生成，完整口径见 `docs/evaluation.md`。

| 模式 | 正确终态 | 精确报告 | 正确拒答 | Repair edges | 逻辑 source profiles | 逻辑 profile bytes |
|---|---:|---:|---:|---:|---:|---:|
| Linear | 11/15 | 10/14 | 1/1 | 0 | 14 | 4,989,475 |
| Static retry | 13/15 | 12/14 | 1/1 | 7 | 21 | 11,008,557 |
| Closed loop | 15/15 | 14/14 | 1/1 | 4 | 18 | 7,476,177 |
| Full profile | 15/15 | 14/14 | 1/1 | 0 | 150 | 1,355,590,320 |

Static retry 与 closed loop 都允许两轮回退，但前者继续复用初始检索词，只修复四个跨源
任务中的两个，并产生 7 条 repair edges/21 个 profiles；typed closed loop 修复全部四个，
只产生 4 条 edges/18 个 profiles。Full profile 也能完成，但每个任务都画像 10 个 CSV。
所有模式都会先索引授权路径和 CSV header，因此这里的 profile 指
完整内容 hash 与行数统计的逻辑工作量，不是物理 I/O 或稳定延迟。

`community_52` 的 transfer probe 另得到 2/2 精确匹配、2 个正确来源、0 repair，
逻辑画像 292,948 bytes。它不是 held-out generalization，因为任务 family 是检查问题后
注册的。三处 benchmark 口径异常（tasks 179/590/961）已在 `docs/evaluation.md` 明示。

工程验证事实：158 个后端测试通过（包括真实 CoDA integration cases、纯合成 held-out
完整性/状态机 cases、runtime snapshot、run retention/deletion 安全边界和试演协议绑定测试），
Ruff、Mypy strict、前端 TypeScript check 和 production build 均通过；Docker Compose
的 Web -> Nginx -> API -> runtime 链路已在本机验证；ECS 预检还覆盖了互斥入口、宿主 TLS
反代、私有 env 与保卷 systemd 生命周期。它们是实现质量证据，不是研究效果
指标。

## B. 用户确认内容

- 论文标题使用已确认的完整标题，不再使用历史短标题作为投稿主标题。
- 最终 Demo 应可部署到网站；作者后续计划租用阿里云 ECS，并自行处理域名和网站备案。
- 项目应保持清晰、高质量、可部署的结构。
- Data Discovery、Data Preparation、Data Analysis 是三个必须可见的功能阶段。
- 每个任务的理想用户输入只有分析问题；系统应自动找数、备数、分析并生成 report。
- 三篇支撑材料位于 `supported_research_paper/`。代码复用与投稿边界见
  `docs/supporting-work-boundary-audit.md`。
- 作者、单位、作者排序、可公开范围和正式系统名是否与标题 hook 完全一致：`TODO`。

## C. 根据上下文推断（必须由作者复核）

- 拟议目标用户是“有分析问题但不愿手工选择/上传数据、指定 schema 和 join path 的分析者”。
  这是根据产品目标推断，尚无用户研究。
- 最适合的现场 persona 是教育政策分析者；依据是当前 task-959 pilot，而不是作者已确认的
  长期应用领域。
- 核心 novelty 候选是 analysis-grounded source repair 与 downstream replay，而不是 question-only、
  LLM、Agent 或 end-to-end UI 本身；依据见 `docs/demo-title-analysis-2025-2026.md`。

## D. 建议性扩展（尚未实现）

- 真实 provider 开发 smoke 已有记录；下一步需在固定任务、代码、同模型/预算和重复次数下
  评测 agentic 效果及报告 factuality，不能从精选成功案例推出准确率。
- `docs/heldout-protocol.md` 的 implementation freeze 已更新，但其 runner 使用 `model`
  模式。该 13 题首轮仍未解盲/运行；完整 agentic Discovery/tree/report 的评测须另行明确协议。
- 当前已有 linear、same-budget static-retry、closed-loop、full-profile controller；仍需补无 typed contract、无 source
  backtracking 等基线，并在引入随机模型后做等模型/预算的重复运行。
- 当前 API 已支持后台运行与轮询进度；仍需持久化作业队列与隔离 worker，SSE/WebSocket
  可作为后续传输改进。
- 公网入口已有基础 per-IP rate/connection limit、并发 admission、匿名 run 保留/删除，以及
  停机 runtime 快照/仅新卷恢复；仍需实现身份级配额、集中审计、监控、加密异地备份和独立
  identity 模块。应用账号注册与
  ICP/公安备案是两件不同的事。
- 已实现带标题卡、六段字幕和结尾卡的自动 fallback；仍需最终配音、正式 artifact URL、
  公开托管，并按正式 CFP 重新编码。

## 论文论证画布

### 问题与缺口

- 产品范围：在预授权但未为当前问题整理的数据环境中，用户每次只提交分析问题。
- 最近系统已经覆盖 NL-to-data、data-lake processing、Agent analysis 和 report；因此
  “question to report”不能单独构成 novelty。
- 具体缺口：初始 source/prepare decision 可能可执行却不满足 downstream analysis；
  线性流水线通常只能失败、输出不完整结论，或依赖人工重新选数。
- 研究机制：把 measures、coverage、join、statistical preconditions 和 claim evidence
  编译为可执行 ASC；typed violation 指向 responsible upstream stage，触发 source/prep
  repair、依赖失效和选择性 replay。

### 核心贡献候选（已有初步机制证据）

1. **系统/架构贡献**：跨 `source -> materialized state -> analysis artifact -> report claim`
   的显式 state/lineage model，以及 violation-guided closed-loop controller。
2. **交互贡献**：每个任务只有问题输入，但现场观众能检查 contract、source decision、
   reverse edge、join coverage 和 claim evidence，而无需先操作上传/表选择界面。
3. **实证贡献**：在 CoDA-style noisy environments 上衡量 report success/correct abstention、
   repair success 与 logical profile exposure；当前 15 题主评测和 2 题 transfer probe 可写成
   初步机制证据；另有四个现场场景、共 40 次预热后生产 HTTP 请求的描述性响应性记录，
   但尚无 held-out generalization、token cost、公网/模型延迟或跨系统性能比较。

### 最接近工作

| 工作 | 相同范围 | 当前主张的机制差异 | 核验位置 |
|---|---|---|---|
| QueryArtisan | NL 查询异构 data lake，生成 processing graph、分析和 report | 本系统要求 downstream obligation 自动重开 source decision，而不只在既定 graph 中修代码 | `docs/demo-title-analysis-2025-2026.md` §4 |
| Sentence to Model | NL data-collection request，自动找数/富化，minimal human intervention | 本系统以 evidence-grounded analytical report/diagnosis 为终态，并用下游证据改变 source selection | 同上 |
| DA-Studio / DeepEye | end-to-end data agent、trace/DAG、人工编辑与重跑、report | 本系统的 demo moment 是无需人工指定修复的跨阶段 rediscovery | 同上 |
| Graphy'our Data | raw documents 到渐进探索和 report | 本系统处理结构化多源选择、join 与 execution-grounded upstream repair | 同上 |

## 当前可执行的现场脚本

| 阶段 | 观众操作 | 系统即时反馈 | 展示的技术点 | 建议时间 | 失败时备选 |
|---|---|---|---|---:|---|
| 1. 建立场景 | 打开页面，查看预授权 `community_43`，不选择或上传文件 | 显示 10 个可发现 CSV、固定 revision/archive digest 与 download-only 边界 | question-only + audited environment boundary | 20 s | 播放自动生成的稳定帧本地 fallback |
| 2. 提交问题 | 保留或编辑 task-959 问题，点击 Run | 返回 ASC；source card 显示上游、license metadata 与 verified digest | question -> executable obligations + input integrity | 40 s | CLI `make pilot` |
| 3. 观察修复 | 打开 lifecycle 和 **Repair impact** | 并列显示 report-gated 初始状态、`analysis -> discovery`、新增第二来源及 accepted replay | 核心 closed-loop 机制 | 50 s | 打开持久化 run JSON |
| 4. 核验证据 | 点击 Black/Hispanic claim | 展开 coefficient → executed artifact → materialized state → 两个 checksummed source profiles | report acceptance 与 claim-level lineage | 40 s | 打开生成的 Markdown report |
| 5. 检查拒答 | 选择 task 179 的 attendance 问题 | 全目录中找不到引用来源，返回 `data_gap` 且不生成 report | evidence-based stopping | 30 s | 打开对应持久化 run JSON |

### 现场约束

- 当前 17 个已注册 pilot 路径都不依赖网络、GPU 或外部 LLM API，可以离线运行。
- 离线 registry 计时使用同步请求；同机 Nginx--FastAPI 路径在每个现场场景预热一次后串行测得 40 个样本，
  中位/P95/最大为 21.475/57.882/58.374 ms。该记录不包含容器启动、TLS、WAN、浏览器渲染
  或模型调用，不能解释为公网 SLA 或跨系统性能优势。
- 已配置并发上限、请求 timeout 与基础 per-IP 限流，但容器冷启动和公网负载尚未测量。
- 已有真实界面截图和可复现的带字幕稳定帧 fallback 生成流水线；最终配音、正式 artifact URL、
  公开托管和自动 reset endpoint 尚未完成。run state 使用唯一 ID 追加保存。
- 请求只允许 question，不接受文件路径或浏览器提供的 connector secret；问题文本会持久化，
  页面已在提交前披露 server retention，并提供活动 runtime 单 run 删除；公网 ECS 强制
  1--720 小时保留窗口。opaque run ID 仍只是 bearer capability，身份归属和备份删除尚未实现。

## 图表与表格素材状态

- Figure 1（双栏）：Question-only 边界与 `question -> ASC -> discovery -> preparation ->
  analysis -> violation -> discovery -> report` 闭环；已生成可复现的矢量 PDF 和 300-dpi PNG，
  `paper/figures/system-overview.capture.json` 将两个输出的摘要绑定到源脚本。
- Figure 2（双栏）：在当前 UI 中回放已登记的真实中文问题运行，a–c 展示社区逐跳探索、
  执行后的准备路径/schema/表格节选以及 SQL/报告结构；明确标记为 recorded run，未发生的
  Debug/回溯不补造。复现方式与边界见 [agentic-replay-figure.md](agentic-replay-figure.md)。
  旧 task-959 A–E 图保留为离线 repair 素材。`make paper-capture-check` 核对两组素材；
  `paper/main.build.json` 将正文、模板、图件和验证器的 18 项输入绑定到四页 PDF。
- Table 1：三阶段 agentic 演示路径、观众动作、即时反馈和技术机制。
- Table 2：完整 15 题 controller comparison；已有可重复脚本与口径说明，但仍需更多
  communities 和 held-out/model-based 评测后才能支持 general effectiveness。
