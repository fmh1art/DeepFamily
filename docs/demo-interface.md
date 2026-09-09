# Demo 界面模块说明

本文档介绍 Ask, Don't Upload `0.4.0` Web Demo 的界面结构、每个模块所表达的数据管理机制，
以及它们和运行状态、源码之间的对应关系。启动方式见根目录 `README.md`，完整现场流程见
`docs/demo-runbook.md`。

本次三阶段输入/输出、真实中文多维报告与回归检查记录见
[stage-io-validation.md](stage-io-validation.md)。

## 1. 界面设计目标

当前界面默认采用浅色主题：纸白色卡片、浅蓝灰背景、深蓝灰正文、青绿色验证状态和琥珀色
repair 状态。颜色只用于辅助区分，关键状态同时通过文字、边框、图标或位置表达。

标题和栏目标签使用自然大小写，例如 `Question-only analytics`、`Execution contract` 和
`Verified report`，不再通过 CSS 强制转换为全大写。`ASC`、`API`、`CSV`、`SHA-256` 等技术
缩写仍保留标准写法。

界面遵循四个原则：

1. **Question-only**：任务级必填输入只有分析问题，不提供上传、选表、schema 或 join path
   控件。
2. **Mechanism-visible**：Discovery、Preparation、Analysis、violation 和 repair 都必须留下可
   检查的状态或事件，不能只显示一个最终答案。
3. **Evidence before report**：只有 ASC obligations 通过后才显示报告；每个 quantitative claim
   均能导航到执行 artifact、物化状态和来源摘要。
4. **Progressive disclosure**：主路径只显示问题、三阶段机制和报告；隐私边界、原始参数、
   搜索记录、lineage 和技术审计保留在明确命名的折叠区中。

## 2. 页面总览

| 区域 | 主要输入 | 界面输出 | 对应源码 |
|---|---|---|---|
| 顶部导航与环境状态 | 当前部署环境 | 在线状态、可发现文件数和简短运行模式 | `frontend/src/App.tsx` |
| Hero | 无 | 一句 Question-only 价值主张；运行后自动移除 | `frontend/src/App.tsx` |
| 问题输入区 | 一个自然语言分析问题 | pilot、运行按钮与可展开的隐私/模型边界 | `frontend/src/App.tsx` |
| Catalog provenance | 环境 provenance manifest | benchmark、revision、digest 和数据池覆盖；收入 Technical details | `CatalogProvenanceBar.tsx` |
| Paper-aligned agent workbench | 三阶段结构化执行事件 | Discovery hops、Prep candidate tree、Analyze notebook cells | `ResearchWorkflowPanel.tsx` |
| Analytical sufficiency | 编译后的 ASC | measures、dimensions、coverage、join 与 evidence obligations | `ContractPanel.tsx` |
| Lifecycle trace | lifecycle events 与 agent traces | 正向/repair 边、repair goal、agent action 状态与请求/响应摘要 | `LifecyclePanel.tsx` |
| Selected evidence | source decisions 与 profiles | 已选数据源、行列数、摘要、许可 metadata 和选择轮次 | `SourcesPanel.tsx` |
| Repair impact | 修复前后物化状态 | 初始失败、repair target、补充来源和重放后的 acceptance proof | `RepairImpactPanel.tsx` |
| Verified report / diagnosis | analysis artifacts 与 sufficiency state | 通过验证的报告，或 `data_gap` / `capability_gap` 诊断 | `ReportPanel.tsx` |
| Claim lineage | 用户选择的 report claim | Claim → artifact → state → source 证据链 | `ReportPanel.tsx` |
| Transparency notice | 发布和依赖清单 | 数据、代码、依赖与再分发边界 | `AboutNotice.tsx` |

以上组件位于 `frontend/src/components/`；共享 API 类型位于 `frontend/src/types.ts`，浏览器请求
封装位于 `frontend/src/api.ts`。

## 3. 顶部导航与环境状态

页面顶部左侧显示产品名，右侧只保留在线圆点、可发现文件总数和
`Agentic/Model/Registry mode`。环境 ID、格式分布和 community 覆盖不再挤入顶栏，需要时在
**Technical details** 中查看。

该区域的数据来自 `GET /api/v1/environments/current`，不是前端写死的运行结果。绿色状态只表示
环境接口成功返回；服务端的完整数据可用性由 `/readyz` 检查。

## 4. 问题输入区

`Your analytical question` 是核心交互入口。用户可以点击 **Run hands-off analysis →**，也可以
按 `Ctrl/Command + Enter`。输入长度为 10--4,000 个字符。

### Registry 模式

页面显示四个由后端返回的 **Verified pilots**：

- `959 — Join repair`；
- `960 — Coverage repair`；
- `176 — Direct answer`；
- `179 — Honest data gap`。

这些按钮只负责填入分析问题，不会把数据集、join path 或预制结果发给前端。

### Model 模式

页面不显示 registry pilot，并在提交按钮之前披露：问题文本及授权 catalog 的文件名、列名、
大小等 metadata 会发送给服务器配置的 provider；source rows 和 credential 不进入 planner
prompt。该披露不代表 provider 已通过开放域效果验证。

### Agentic 模式

页面同样不显示 registry pilot。用户只输入问题；Discovery 通过目录、路径搜索和 inspect action
选择来源，Preparation/Analysis agent 再通过实际执行反馈建立候选树。提交前披露会明确说明：
除问题和 catalog metadata 外，inspect 时最多五行的有界 table preview 以及派生执行观察也会
发送到指定 provider；完整文件和服务器 credential 不会发送。

### Run storage 与 provider 披露

保留策略和 provider 披露合并到输入框下的 **Privacy & model use**，默认折叠。
完成态可通过 **Delete run** 删除问题、物化表、analysis artifacts 和报告。报告产生后，
完整输入表单自动收起为 **Ask another question**，避免与结果竞争。

## 5. Catalog provenance

该栏不再在空首页占据一整行；运行后收入 **Technical details**。单一注册 pilot
环境展开后显示：

- benchmark 名称和 community；
- 固定 upstream revision；
- archive SHA-256；
- 当前发现数量与 manifest 注册数量；
- upstream benchmark 链接。

数量或摘要不匹配时不会伪装成正常来源。未注册环境显示 `Unregistered environment`，且明确
说明不推断许可证。

`coda-open-v1` federated 环境显示固定 release revision、公开 30 个 community 中的已安装数量、
996 个 open task 和 196 个 source dataset。其索引只能由 open-release manifest 中的 archive
构造；sealed evaluation community 不会因磁盘上存在同名目录而被加入。

## 6. Paper-aligned agent workbench

该工作台只在 `agentic` planner 模式显示，避免把固定 registry pilot 误标成论文 agent pipeline。
`POST /api/v1/runs?background=true` 会先返回 `202` 与 run ID；后端在受并发限制的 worker 中执行，
每次 tool observation 或 notebook cell 都原子写入 run state，浏览器再轮询
`GET /api/v1/runs/{run_id}`。因此阶段画布会随真实运行推进，而不是提交结束后播放动画。

工作台只在真实 run 存在时出现，不再在空首页显示三个“等待”面板。顶部使用
`Discover → Prepare → Analyze → Report`
阶段导航，正文一次只展示一个全宽阶段；运行期间默认自动跟随当前 agent，用户切换去查看历史
阶段后可点击 **Follow the live agent** 恢复跟随。阶段 tab 只保留论文名、阶段名和计数；
当前画布用一句 **Core mechanism** 解释该阶段 novelty，并只显示三个核心统计。页面不展示模型私有思维链，也不
加载论文模型权重。

### 6.1 Data discovery：CoDA-Bench path walk

阶段顶部先明确显示输入和输出：左侧是用户的数据需求及系统提取的 search terms，右侧是经过
inspect 后最终选中的相关 CSV，包括文件名、相对路径和行列规模。Discovery 主画布再分为两栏：
左侧只展开当前 hop 的输入、输出和具体观察；右侧保留整张 community-level 网络图。第一步从
`Environment root` 开始，之后每个 hop 对应一个真实 action：

- `List directory`：从当前目录展开下一层 community/dataset/source；
- `Search catalog`：按问题词扩展一个有界、带分数的路径前沿；
- `Inspect asset`：展示 inspect 后的相对路径和 schema；
- `Select sources`：只标记已经 inspect 且位于同一 community 的 evidence set；
- `Rejected` / `Insufficient`：保留越权、跨 community、未 inspect 选择或数据缺口反馈。

左栏的编号时间轴可逐步前进或回看。右栏会同步把当前节点和边加粗，将已走路径保留为 history，
并以另一种状态标记本轮 frontier 与最终 selected files。因此第二步既能看到第一步的历史，也能
立即识别本步从哪里跳到哪里。网络图在 root hop 中呈现当前公开安装的完整 community 层；为避免
把 30,292 个文件压成不可读的一团，文件层只增量呈现本次搜索实际遇到、检查或选择的节点，标题
同时报告 community 数和 encountered-file 数。候选 frontier、inspect schema 和 rejection feedback
都位于当前 hop 左栏。该画布直接读取 `RunState.discovery_hops`，没有前端伪造的搜索轨迹。

### 6.2 Data preparation：DeepPrep operator tree

阶段顶部先把 transformation 本身画清楚：输入区逐个展示 Discovery 选中 CSV 的 schema，中间按
顺序展示最终 selected branch 的 operators，输出区展示 analysis-ready table 的表名、state ID、
行列规模、执行后 schema 和最多五行的真实预览。输入 schema 来自 Discovery inspect observation；
输出 schema 与 preview 在本地 executor 完成 materialization 后写入 `MaterializedState`。旧运行若
没有该有界预览，UI 会明确显示 unavailable，而不是补造样例数据。

输入和输出 schema 默认显示少量字段，可以点击 **Show all … fields** 展开全部字段；没有记录的
类型显示 `type not recorded`，不猜测类型。**Schema changes** 对比输入字段名并集与输出字段，列出
新增/移除（包含可能的重命名），并对比同名字段记录的输入和输出类型，不把这个比较伪装成
逐字段 lineage；不同执行器的类型标签也可能不同。未选中的候选只标记为
**Candidate preview**。Analysis 输入依据 notebook 的实际 state references 选择，不以“最后写入的
物化状态”代替最终选中的数据。

Prep 大画布中的一个 branch 是一次完整 preparation candidate，不是单个随意操作。每次 `expand` 都从
原始 source tables 构造完整 chain，交给本地 executor 校验并执行，然后把 materialized
observation 反馈给下一轮。

实现参考的不是 `third_party/DeepPrep/app` 中较早的线性 history list，而是
`third_party/DeepPrep/chatapp/operator_tree.py` 与 `chatapp/static/`：采用与原实现一致的
trie-like 规则，把完全相同的 operator 前缀合并为一个节点，保留失败分支，并高亮 selected
solution path。点击节点后，右侧 inspector 展示输入/输出表、实际行数变化和 schema
delta，详细参数默认折叠。树下方的 **Search history** 也默认折叠，展开后再按 turn 展示 reason、parent、
完整 chain、observation 与 rejection feedback。具体包括：

- `candidate_id` 与 `parent_candidate_id`，后者明确标记 branch/backtrack；
- operator sequence，例如 `Filter → Join → GroupBy → TopK → Terminate`；
- DeepPrep operator family、参数、输入/输出表、行数及 schema delta；
- `materialized`、`rejected`、`selected` 状态；
- state ID、typed violation 与可展开的执行错误。

`finish(candidate_id)` 只能选择已经执行且无 violation 的节点。该画布直接读取
`RunState.preparation_attempts`，而不是根据 lifecycle 文本在浏览器中重建一棵“示意树”。

### 6.3 Data analysis：DeepAnalyze notebook loop

阶段顶部左侧以同一个 materialized state 展示 Analysis 的真实输入表及 schema/preview，右侧展示
最终 report 的标题、executive summary、各分析维度和 integrated conclusion。Notebook 中每个
`Execute` cell 继续展示其直接输出；最后一个默认展开的 `Report` cell 展示实际生成的报告对象，
而不再只保存一个 report ID。

Analysis 大画布按 sequence 展示持久化 notebook cells：

```text
Analyze → Understand → Code → Execute → ... → Answer → Report
                              ↘ Debug → safe fallback
```

Notebook 主路径只显示 phase、标题、状态和一行摘要。`Code` 的参数化 SQL/受限 Python
以及 `Execute` 的真实结果收入 **View code and output / View execution details**；展开后仍可查看运行时、
耗时和 artifact/evidence link。SQL 在内存 SQLite 中执行，Python 只执行系统 compiler 生成的
受限 cell；两者必须与 authoritative dataframe result 一致。如果执行异常或结果核对失败，UI
插入红色 `Debug` cell，再记录 `bounded_dataframe_fallback`，而不是隐藏修复。SQL/Python 保留
代码块，执行数组则渲染成可读表格；`Answer` cell 只显示通过 release gate 的 finding 数量，原始
claim payload 默认折叠，避免再次把长 JSON 当成答案。

执行 artifacts 全部产生后，同一个服务器端 LLM 进入 DeepAnalyze 风格的 `<Finish>` 阶段，把已执行
证据组织为 `executive summary → dimensional sections → integrated conclusion → limitations`。报告
schema 要求每个 section 引用合法 artifact ID，且所有公开 artifacts 至少进入一个 section；未知
引用、漏掉执行结果或无效 JSON 会被拒绝并在有限重试后使用 deterministic grounded fallback。
最后只有通过 ASC、artifact-reference 和 lineage validation 才出现 `Answer` 和 `Report`。

对于“最适合移民的国家是哪一个”这类宽泛问题，planner 被要求把授权数据中实际可支持的生活质量、
成本、安全、就业等维度分别计划和执行，再由报告层综合。系统不会在用户未给权重时偷偷构造一个
“客观万能总分”；如果数据只覆盖某一个指标，结论必须限定为“在该指标和当前数据范围内最佳”，
并把缺失维度写入 limitations。

该安全适配保留 DeepAnalyze 的 code–execute–feedback–report 语义，但不会直接执行外部模型返回
的任意 Python/SQL。该栏目直接读取 `RunState.analysis_notebook`。

### 6.4 回放和报告阅读细节

- Discovery 左侧为当前步骤，右侧为社区全景，桌面各占一半，窄屏上下排列。
- 回放第 N 步时，只呈现前 N 步实际遇到的文件和已成功选择的输出，不提前泄露后续结果。
  根目录暴露的完整社区层保持可见；目录节点与社区节点分开，不把子目录计为新社区。
- 若下游反馈触发重新选源，输出区和 selected 节点以该步骤之前最新的成功选源为准；旧选择仍可
  回放，但不会累计成新的最终文件集合。被拒绝的动作不能替换成功输出。
- 琥珀色带方向的箭头显示当前工具关注位置的转移，虚线显示历史转移；淡色连线是目录归属，
  **不是** benchmark 提供的社区语义相似度或邻接图。整个文件池以社区聚合呈现，不绘制 3 万个小点。
- 实际遇到的文件不再受前 24 个节点的截断限制。回放期间新事件不会抢走当前步骤，可点击
  **Follow latest hop** 恢复跟随。
- 报告以通栏正文阅读；每个分析维度下的证据链接直接跳到对应计算表/图。不同量纲的独立指标
  不会被强行画在同一标量比较坐标轴上。完整报告可下载为与服务器持久化内容一致的 Markdown。
  新报告的 Markdown 正文使用 `E1` 等证据链接，每份计算结果仅在 **Evidence results** 中呈现
  一次，记录与数组使用表格；展示精度不改写原始数值。旧报告不自动迁移，验证记录见
  [report-export-validation.md](report-export-validation.md)。
- Report writer 使用相同配置的 LLM，额外接收已执行的筛选、聚合和分析定义，用于解释方法与
  适用范围。引用校验确认 artifact 存在且覆盖完整，不等价于自动证明每句自然语言判断正确。
- 报告顶部的 sources/rows 和来源说明从报告 artifact 的实际 state/source 引用计算，不使用
  最后尝试的候选，也不把仅 inspect、未用于报告的文件算作证据来源。涉及多个物化表时显示
  prepared datasets 数量，不把可能重叠的行数相加成一个虚假的分析样本。

## 7. Analytical sufficiency contract

问题提交后，系统首先显示 ASC。每条 obligation 包含：

- 类型，例如 Measure、Dimension、Coverage、Join、Statistical 或 Evidence；
- 实际执行的 check；
- `Pending`、`Satisfied` 或 `Violated` 状态；
- 对“什么条件足以发布报告”的文字描述。

model planner 成功返回声明式计划时，本模块还显示计划版本、编译类型、纠正次数以及 Sources →
Transforms → Analyses 的数量。所有计划都必须在读取数据前通过本地白名单校验。

## 8. Lifecycle trace

生命周期面板按持久化顺序显示 stage transition：

```text
Question → Discovery → Preparation → Analysis → Report
```

普通 forward edge 使用青绿色；repair edge 使用琥珀色和反向箭头。以 task 959 为例，Analysis
发现缺少 demographic columns 后产生：

```text
Analysis ↶ Discovery
```

随后面板显示 `Missing analytical columns` repair goal、搜索目标和完成状态。这里的 repair 是
服务端实际状态机事件，不是前端动画。

在 agentic 模式下，面板还显示 `Agent turns`：agent、turn、action、accepted/rejected/observed
状态、有界摘要，以及请求/响应 SHA-256 前缀。UI 不持久化或展示完整 prompt、模型原始响应与
API key；该区域用于证明真实的 tool action、环境拒绝和 branch/backtrack，而不是展示思维链。

## 9. Selected evidence

该模块按 source decision 的轮次展示每个被选来源：

- 文件名和授权环境中的相对路径；
- profile 得到的行数、列数与字节数；
- 文件 SHA-256；
- upstream title、provider 和 creator；
- declared/unknown license metadata；
- `Download-only` 与 integrity 状态；
- 是否由 downstream repair 新增。

面板底部汇总最终物化行数和 join coverage。UI 只显示 profile/provenance，不提供源数据下载
链接，也不把 source rows 放进浏览器导出。

## 10. Repair impact

只有真实发生并完成 repair 时，该模块才出现。它把一次闭环压缩成三个并列状态：

1. **Initial pass**：初始来源数、准备后 schema 和阻止报告发布的 violation；
2. **Analysis ↶ Discovery**：typed violation 及其明确 repair targets；
3. **Replayed state**：新来源数、恢复的变量/类别和 join coverage 或 artifact proof。

该模块用于回答“为什么必须闭环”，避免观众只能从很长的事件列表中自行推断修复效果。

## 11. Verified report 与诊断

### 报告终态

当全部必要 obligations 通过时，页面移除 Hero、自动收起输入表单，并把报告放在三阶段回放之前。
页面不是
只显示 artifact 的第一行字符串，而是生成一个完整的 report layout：

- 原问题与 **Answer at a glance** 决策结论；
- 按实际执行维度组织的 narrative sections、综合结论与 scope limitations；
- 仅保留 source 数、最终 prepared rows 和 grounded findings 三个范围指标；
- scalar/list artifacts 的指标卡与可比较数值条形图；
- table artifacts 的横向比较图、完整计算表格和人类可读的首要发现；
- 可按需展开的 grounded findings、四层 lineage、source profiles 和 SHA-256 摘要。

**Answer at a glance** 使用独立的小标题和 16 px 常规字重正文，不再把完整答案作为大号标题。
正文行高为 1.75，限制阅读行宽；按实际排版高度判断是否超过 5 行。短答案直接完整显示，
长答案默认显示 5 行与省略号，点击 **Read full answer / Show less** 展开或收起。
窗口宽度变化时重新判断，不依赖英文字符数，也适用于中文。按钮支持键盘操作并声明
`aria-expanded` 与受控段落；正文原文始终保留，不重新调用模型、改写结论或截断下载文件。

用户可以下载与服务器 report body 一致的 Markdown，并导出版本化 evidence JSON。JSON 使用
显式 allowlist，只包含公开 RunState 字段。Claim tabs、lineage、source profiles、report locator 和原始
Markdown 统一收入 **Evidence & lineage**，不再占据报告主视图。

### 无报告终态

当证据不足或能力不支持时，页面显示 typed diagnosis，例如：

- `data_gap`：授权环境缺少满足问题的数据；
- `capability_gap`：当前 planner/executor 不支持该问题 family。

诊断会列出未满足 obligations 和已尝试 repair 数量，不显示一个看似成功的空报告。

## 12. Claim lineage

报告中的每条 claim 都是一个可选择的 tab，但整个区域默认收入 **Evidence & lineage**。
包含序列化 table payload 的长 claim 会先转换为
可读 finding，例如 “Finland ranks first … 7.824”，完整精确值仍保留在 table、Markdown 和
evidence export 中。选择后，右侧按四层展示：

```text
Claim → Executed artifact → Materialized state → Source profiles
```

用户可看到 claim ID、artifact 名称和值、state 行列信息、来源相对路径及摘要。键盘用户可以用
方向键、Home 和 End 在 claims 之间切换。

## 13. Transparency notice

页面底部的 **Data & software notice** 默认仅显示一行摘要，展开后解释三个发布边界：

1. 当前代码仍是 research preview，根许可证待作者确定；
2. 第三方数据保持 external/download-only，界面访问不改变其所有权；
3. Python、Web 和容器 OS 依赖分别进入版本化 inventory 与人工复核流程。

这里还提供 dependency inventory JSON 和当前 environment provenance API 的只读入口。

## 14. 响应式与可访问性

- 页面支持键盘完成 question-to-lineage 主路径，并提供 skip links 和可见 focus ring。
- 状态变化通过 `aria-live` 播报；loading、error、success 与 diagnosis 使用对应语义角色。
- 在 1,366×768 以及等效 150% browser zoom 下，普通卡片和阶段导航会重排；较窄 viewport 下
  导航变为单列，tree inspector、report chart/table 和 claim lineage 依次堆叠。
- `prefers-reduced-motion` 会关闭非必要动画。
- Playwright + axe 覆盖初始态和完成态；颜色不是唯一状态编码。

## 15. 论文截图模式

`make capture-ui` 运行真实 task 959 后，给 workspace 临时添加 `paper-capture` class：隐藏输入区
和非论文重点，只保留 Catalog provenance、Selected evidence、Repair impact、Verified report
与 Claim lineage，并显示 A--E callouts。截图仍来自同一生产 UI 和 API，不是单独绘制的 mockup。

截图摘要、尺寸、场景、当前 demo surface 与采集脚本记录在
`paper/figures/demo-ui.capture.json`；`make paper-capture-check` 会拒绝陈旧或被修改的图。
