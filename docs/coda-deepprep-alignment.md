# CoDA-Bench、DeepPrep 与 DeepAnalyze 对齐说明

本文记录 `Ask, Don't Upload` 的数据边界、agent 流程、模型边界和当前能力缺口。目标是让实现
“继承论文方法思想”与“复用论文训练模型”清楚分离，避免 Demo paper 做出超出证据的声明。

## 1. 一条不可变的模型约束

Discovery、Preparation/Analysis planning、repair 和最终 report synthesis 共用同一个服务端
`ChatModel` 实例，并且
正式 agentic 模式固定为：

```text
endpoint  https://aidp.bytedance.net/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview
model     gpt-5.5-2026-04-24
API style azure_chat
auth      api_key header
```

系统不加载 CoDA-Bench、DeepPrep 或 DeepAnalyze 的 checkpoint、tokenizer、LoRA、reward model
或推理服务。三个第三方仓库仅用于核对数据组织和方法语义；运行时源码也没有导入它们。
数值变换、join、aggregation 和统计分析由本地的受限 declarative engine 执行，不由 LLM
伪造结果。

API key 只能放在仓库外或未提交、权限为 owner-only 的私有 env 文件中。它不会进入前端、
镜像、run state、agent trace、报告或日志。持久化 trace 只保存请求/响应 SHA-256、动作类型、
状态和有界摘要。

## 2. CoDA 数据口径：论文草稿与公开 v1.0 不相同

本地支撑论文草稿描述的是构建期口径：1,202 个任务、53 个 community、829 个入选 Kaggle
dataset；这不能直接当作当前可下载 artifact 的规模。

当前实现固定到 CoDA-Bench 公开 v1.0 revision
`63828a2b652e26a9770555a0cc41e6c8aafdb5d9`。官方 release metadata 给出 1,009 个任务、
31 个 community、199 个 source dataset、约 45.61 GB 压缩数据。开发期严格排除一个 sealed
evaluation community，因此可进入本 Demo 的 open runtime 是：

| 范围 | Community | Task | Source dataset | 压缩 archive |
|---|---:|---:|---:|---:|
| 官方完整 v1.0 | 31 | 1,009 | 199 | 45,609,628,644 bytes |
| 本系统 open runtime | 30 | 996 | 196 | 45,593,031,762 bytes |
| Sealed evaluation | 1 | 13 | 3 | 不进入开发索引 |

这些数字及 30 个公开 archive 的 byte size/SHA-256 记录在
`data/manifests/coda-bench-v1-open-release.json`。同步器只接受该 allowlist 中的 community，
不会通过扫描父目录把额外环境加入 catalog。参考：
[CoDA-Bench v1.0 release](https://github.com/ruc-datalab/CoDA-Bench/blob/main/RELEASE_v1.0.0.md)、
[公开数据页](https://huggingface.co/datasets/RUC-DataLab/CoDA-Bench)。

2026-09-07 在该固定 revision 完整解压后的实际 catalog census 为：30,292 个可发现文件、
148,210,537,081 source bytes，其中 17,207 个当前标为 tabular。格式分布为 16,315 CSV、
817 JSON、50 XLSX、12 XLS、8 TSV、5 Parquet、4,067 PDF、2,979 image 和 6,039 other。
这是“文件池”口径；196 是 upstream source dataset 标识的口径，两者不能互换。首次无缓存
header/path 索引实测约 21 秒。

## 3. Data Discovery 如何对齐 CoDA-Bench

CoDA-Bench 的关键评测设置不是“把目标 CSV 直接交给模型”，而是只给问题和一个 community
文件系统，让 agent 自己探索、读取并执行分析。我们的运行路径保留以下约束：

1. Agent 初始只看到问题、授权根目录以及可用 action schema；prompt 不注入目标路径、schema、
   reference answer 或 benchmark solution。
2. `list_directory` 浏览目录；`search_catalog` 只对路径文本排序，不提前泄漏列名。
3. `inspect_asset` 后才返回 format、columns、dtypes 和最多五行有界 preview；未 inspect 的
   asset 不能被选择。
4. `select_sources` 只接受真实 catalog asset ID，且一次 run 的来源必须位于同一个 CoDA
   community。
5. 任意猜测路径、越权 asset、跨 community 选择或非法 action 都由本地环境拒绝，错误观察
   返回 agent 进行有界修正。
6. 数据文件以 read-only volume 挂载；agent 没有 shell、任意 Python/SQL 或网络工具，只有
   allowlisted discovery action 和 declarative plan。

这些动作不是只写入一条笼统日志。服务端为根目录和每次 action 持久化一个
`DiscoveryHop`：`parent_hop_id`、当前 scope、目标 path/community、query terms、排名前沿、
inspect 后的 schema、最终选择及环境拒绝原因都会保存。Web UI 左侧逐步展示当前 hop 的输入、
输出和 observation，右侧的网络图同步高亮 current edge、历史路径、frontier 和最终文件，因此
观众可以看到 agent 如何从 30 个 community 的根逐跳缩小到某个文件。图中完整呈现 community
层，文件层只呈现本次真实遇到的节点，避免把 30,292 个文件画成不可读的点云。它不展示模型
私有思维链，只展示真实 tool action 与环境 observation。

公开 Demo 增加了一层全局 community routing：agent 可以先在 30 个公开 community 的虚拟根
目录中查找，再把一个 community 固定为本次执行边界。这是面向“用户只给问题”的系统扩展，
不是 CoDA 原 benchmark 的逐 task 已知-community 设置。做严格 benchmark 对比时应使用单个
community catalog；做网页 Demo 时使用 federated open catalog。

## 4. Data Preparation 如何对齐 DeepPrep

DeepPrep 的核心贡献是 tree-based agentic reasoning：候选 preparation pipeline 经过实际执行，
中间结果成为树节点；失败后可以回到较早节点并扩展另一分支，而不是把错误线性累积到底。
本系统独立实现了一个受限版本：

```text
inspected sources
      |
      v
expand(full declarative candidate) -- local validate/execute --> immutable state
      |                                                       |
      |<------ observed schema, metrics, artifacts, violation-+
      |
      +--> expand(parent_candidate_id=earlier node)  # branch/backtrack
      |
      +--> finish(candidate_id)                      # only a successful node
```

对应关系如下：

| DeepPrep 概念 | 本系统对应实现 | 差异 |
|---|---|---|
| Tree-based reasoning | `expand` / `finish` JSON action 与 `parent_candidate_id` | 每个分支提交完整 declarative candidate，不复制其训练 prompt |
| Execute then observe | 每次 expand 都先通过 schema/asset 校验，再由本地 engine 执行 | 禁止直接运行模型生成代码 |
| Materialized table node | immutable `MaterializedState`，记录 parent/source/schema/rows/evidence | 完整表留在 runtime；最多五行执行预览只进入 UI，不进入 evidence export |
| Non-local backtracking | 新 candidate 可引用任意已有成功节点为 parent | 有严格 turn、prompt、response 上限 |
| Execution feedback | observed columns、row count、metrics、artifacts、typed violation | 反馈被裁剪并视为不可信数据 |
| Termination | `finish(candidate_id)` | 只能选择已执行且无 violation 的节点 |

### 算子覆盖

| DeepPrep 原仓库算子族 | 当前 declarative 对应 |
|---|---|
| `DATA_CLEANING_OPS` | `StandardizeString`、`DropNulls`、`MissingValueImputation`、`Deduplicate` |
| `COLUMN_TRANSFORMATION_OPS` | `AddNewColumn`、`CastType`、`Explode`、`Rename`、`DropColumn`、`SplitColumn`、`Concatenate` |
| `TABLE_TRANSFORMATION_OPS` | `Join`、`Union`、`Pivot`、`Stack`、`Sort`、`GroupBy`、`TopK`、`Filter`、`SelectCol` |
| Statistics | count、aggregation、distinct、extreme、correlation、share、rows 与 arithmetic analysis specification |
| `OTHER_OPS` | 可见的 `Terminate`；不接受任意 `CodeGeneration` |

`StandardizeDatetime` 可由显式 cast/derive 表达，Append/Union 可由 concat 表达，
WideToLong/Stack 可由 melt 表达，Count/CalculateStatistic 在 analysis specification 中表达。当前未
宣称等价覆盖 ErrorDetection、OutlierDetection、Transpose、Subtitle，以及 DeepPrep 的任意
`CodeGeneration`。最后一项被有意排除，因为网页服务不能直接执行外部模型生成的任意代码。

每个 model turn 都对应一个 `PreparationAttempt`。成功的 `expand` 会记录 candidate、parent、
完整 operator chain、每个 operator 的输入/输出表、参数、行列变化和 immutable state；失败的
action 记录 rejected branch 与有界执行错误；`finish` 只能把已执行且无 violation 的 candidate
改为 selected。Web UI 按 `parent_candidate_id` 缩进绘制这棵树，并把长错误放入可展开的
`Bounded rejection feedback`，所以“分支/回退”来自后端状态，不是前端推测。树上方还直接并列
输入 CSV schemas、selected operator chain 以及输出表 schema/真实有界预览，使 preparation 的
输入输出变化不再需要从日志中猜测。

## 5. Data Analysis 如何对齐 DeepAnalyze

DeepAnalyze 原始执行器不是一次返回最终文字。`third_party/DeepAnalyze/deepanalyze.py` 循环接收
模型输出：中间 `<Analyze>`/`<Understand>` 继续进入下一轮，提取 `<Code>` 后实际执行，将结果或
错误作为 `<Execute>` 反馈给下一轮，直到出现 `<Answer>`。其 Jupyter UI 进一步把
`<Analyze|Understand|Answer>` 映射为 Markdown cell，把 `<Code>` 映射为 code cell 并执行。

本系统保留这个“分析—理解—写代码—执行—调试—回答—报告”的可观察循环，但采用适合公网
Demo 的安全边界：

| DeepAnalyze 语义 | 本系统运行事件 | 执行保证 |
|---|---|---|
| `<Analyze>` | `Analyze` cell | 展示已验证 analysis plan 的任务分解 |
| `<Understand>` | `Understand` cell | 展示所选物化表的行数、列和 profile |
| `<Code>` | `Code` cell | 从严格 typed plan 编译可见、参数化 SQL 或受限 Python |
| `<Execute>` | `Execute` cell | SQL 在内存 SQLite 实际执行；受限 Python 只执行系统编译代码 |
| 执行错误反馈 | `Debug` cell | 保存真实异常/结果不一致，并切换到已验证 dataframe fallback |
| `<Answer>` | `Answer` cell | 只接受已链接 executed artifact 的 claims |
| `<Finish>` / analyst report | `Report` cell | 结构化多维报告经 artifact 引用校验后生成 Markdown |

每个 cell 都是持久化的 `AnalysisNotebookStep`，包含 sequence、phase、language、source code、
bound parameters、output、runtime、耗时，以及 state/artifact/evidence references。浏览器通过
异步 run API 轮询，因此 code、execute、debug 和 report 会随执行逐步出现。

所有 analysis artifacts 完成后，同一个指定 LLM 接收问题、prepared schema、source metadata 和
有界执行结果，输出严格的 `ReportNarrative`：标题、executive summary、一个或多个维度 section、
integrated conclusion 与 limitations。每个 section 只能引用已执行 artifact，而且 section 集合
必须覆盖全部公开 artifact；无效 JSON、未知引用或漏项最多纠正一次，仍失败则生成确定性的
grounded fallback。`Report` notebook cell 持久化该真实结构，而不再只有 `report_id`。

对“哪个国家最适合移民”一类问题，prompt 明确要求按数据实际支持的多个维度分别产生 analysis，
报告再综合这些维度。若用户没有指定权重，系统保留各维度取舍并声明限制；若数据只支持幸福指数，
结论只能说“按当前幸福指数最佳”，不能扩写成普遍意义上的“最适合移民”。

这里有一个必须明确写进论文的差异：外部 LLM 生成的是受限声明式 plan，不是可直接执行的
任意源码；可见 SQL/Python 由本地 compiler 从通过校验的 plan 生成，并再次与 authoritative
dataframe executor 的结果核对。这样复现了 DeepAnalyze 的执行反馈循环，却没有把 API 进程变成
任意代码沙箱。系统也不加载 DeepAnalyze-8B。

## 6. Closed-loop repair

Preparation 在 turn budget 内无法形成可执行成功分支时，会生成 typed violation，并把有界执行
反馈交回 Discovery。Discovery 必须 inspect 并增加同一 community 内的新 source，随后重新运行
preparation tree。没有新来源、跨 community、预算耗尽或 operator 不足都会返回明确 diagnosis，
不会生成貌似完整的 report。

这比原有固定 pilot 的 `Analysis -> Discovery` repair 多覆盖一条
`Preparation -> Discovery -> Preparation` 路径。最终报告仍须通过本地 obligation checks，
每个 claim 指向 executed artifact、materialized state 和 source evidence。

## 7. Provider 数据边界

正式 agentic 模式会向指定 ModelHub provider 发送：问题文本、路径/文件 metadata、inspect 后的
schema/dtypes、最多五行有界 table preview，以及后续本地执行观察。它不会发送整个文件、API
key、服务器路径、reference answer 或 benchmark solution。网页会在提交前明确披露这一边界。
“Don't Upload”表示用户只提出问题，不需要把本地文件上传或手选数据；它不应被误写成“模型
provider 永远看不到任何数据值”。

## 8. 当前可以与不可以宣称的能力

可以宣称：

- 数据池与 CoDA-Bench 公开 v1.0 open runtime 的全部 30 个 community 对齐，并有固定 revision、
  size 与 SHA-256 清单；
- question-only、tool-mediated discovery，不向 agent 提供目标文件 oracle；
- 同一个指定 LLM provider 驱动 discovery、preparation/analysis planning、repair 与 report synthesis；
- DeepPrep 风格的 executed candidate tree、materialized state、branch/backtrack；
- DeepAnalyze 风格的持久化 notebook loop，其中 SQL/Python cell 被实际执行、验证，错误进入
  可见 Debug cell；
- 本地受限执行、typed failure，以及含多维 sections、综合结论和限制的 evidence-grounded report。

尚不能宣称：

- 已覆盖论文草稿中的 53 个 community 或 1,202 个任务；
- 已在全部 996 个公开任务上达到某个准确率；
- 当前 declarative engine 能解决任意 PDF、图像、多模态或任意代码任务；
- 当前实现与 DeepPrep 源码、训练策略或 31 个 operator 完全等价；
- 当前实现与 DeepAnalyze 的任意代码执行环境或其训练模型等价；
- provider contract 测试等于真实 API 上的端到端质量评测。

在论文中应把“完整公开数据池已安装”“支持的文件/算子范围”和“实际求解率”分成三个指标。
正式效果数字只能来自冻结代码和协议后的公开任务评测。
