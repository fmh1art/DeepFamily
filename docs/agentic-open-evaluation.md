# 完整 agentic 流程的开放集配对评测

状态：2026-09-09，收到用户“全部权限，自动……完成任务”的继续授权后，已创建冻结计划，
固定排程的前 6 个真实 case 已执行完，正在同一冻结方案下继续后续批次。
40 项评测/计量离线测试通过；尚未封存完整预测或评分，不把前 6 个 case 当成完整效果评测。
本协议不替代 community_45 的独立解盲协议。

本轮执行计划为 `experiments/results/agentic-open-v1/plan.json`，包含 30 个问题、180 个 case；
plan SHA-256 为 `a0ccd26a553a963ad1cc66ebe02c74663ce6ec6c15395129953307b9103b0664`，
代码摘要为 `c9c27b70f76a79e80f69cc5de5c5684a95e8ac04dad0d10d9d4938a5911ca9bf`。
运行使用 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`，串行 worker；
私有配置只读取已有密钥，所有阶段固定同一 ModelHub 模型。实时进度应通过下文 `status`
命令读取并同时检查活跃进程锁，不能把本文状态当作当前进程仍存活的证据。

冻结时的实现另存于
`experiments/results/agentic-open-v1/implementation/ask-dont-upload-artifact-v0.4.0-preview.tar.gz`，
archive SHA-256 为 `4074166366e87dd3f39552c3187dcf4a2f996fafece2e6bc6afa4628bd6a33e2`。
282 项实际成员审计和逐字节重建通过；解包后的 evaluation surface 摘要与上述计划一致。
该内部源码快照不包含私有配置、数据池或评测结果，不等于公开发布的 artifact。

### 首批运行检查（不是答案效果结论）

固定排程前 6 个 case 的终态为 4 个 `completed`、2 个 `insufficient/data_gap`。合计
75 次逻辑调用、75 次 HTTP 尝试，均返回 200；有回执的 prompt/completion/total tokens 分别为
467,522 / 29,382 / 496,904，75 次均有 total-token 回执。6 个 case 的 driver wall time
之和为 492.847 秒，不包含批次之间的等待或准备时间，不等于网页服务的端到端延迟。

其中 task-1008 的两种模式均返回数据缺口，闭环模式实际产生一次 repair，但未得到报告；
失败原样保留。此处不读取参考答案、不评定其他四份报告正确，也不据此推算全部评测的成本
或推广为完成率。后续批次会继续记录缺失回执和失败，不把本批的 100% 回执覆盖当成保证。

## 要回答的问题

在相同公开数据池、模型、声明式执行器及每次运行的资源上限下，允许跨阶段 repair 是否
改善 question-only 任务的完成情况和报告答案？它评测真实 Discovery → Preparation → Analysis
→ Report，而不是固定 registry pilot，也不是只评测 `planner_mode=model` 的编译器。

入口是 `experiments/agentic_open_evaluation.py`；所有模型阶段及评分使用现有私有配置中的同一
指定 ModelHub 模型，不加载三篇支撑论文的训练模型。

## 预先确定的设计

| 项目 | 设计 |
|---|---|
| 总体 | CoDA-Bench 固定公开 release 的 30 个社区、996 个任务；不访问 community_45 内容 |
| 取样 | 每个公开社区按 `SHA-256(protocol_id:community_id:task_id)` 最小值取一题；不依据问题或答案难度选题 |
| 规模 | 30 题 × 2 种控制器 × 3 次重复，共 180 次运行 |
| 无跨阶段 repair | `max_repair_rounds=0`；保留同样的阶段内 agent 搜索 |
| 闭环 | `max_repair_rounds=2`；允许执行反馈触发跨阶段 repair |
| 排程 | 每个题目/重复的两种模式相邻运行；交替模式先后顺序，各重复内按固定哈希排序 |
| 模型随机性 | 网关适配器未传 temperature，也没有固定 provider seed；三次重复不等于确定性复现 |
| 解释单位 | 每题/社区为一个单位，重复嵌套于题目；只报告描述性配对差异 |

这是开发过程中已暴露的开放集样本，不是 held-out 集，不是 996 个任务的加权准确率估计。
两种模式使用同一最大资源包络，不保证实际调用次数或消耗相等。闭环可能花更多调用；必须
连同完成情况报告实际计量记录，不能仅以更高完成率声称效率更高。

## 资源与费用边界

每次运行上限：16 次 Discovery turns、每轮 6 次 Preparation turns、68 次逻辑模型调用、
900 秒 worker wall time、8 GiB 地址空间。Provider 单请求超时 120 秒，最多 2 次 transport
retry，因此一次逻辑调用可能包含 3 次 HTTP 尝试。评分每份报告最多 2 次逻辑调用。

完整 180 次运行的理论逻辑调用上限为 12,240 次，另有最多 360 次评分调用；这不是费用报价。
`model-calls.json` 记录阶段、请求/响应摘要、字符量、输出 token 请求上限、耗时，以及逐次
HTTP 尝试和 provider 返回的 token 用量。它不记录完整 prompt、HTTP URL/headers、原始响应
或 credential。字符量不是 token；provider 报告的 token 也不是网关账单金额。
客户端超时不能保证远端服务立即停止计费，未返回用量的请求不能按零成本处理。

`run` 必须显式给出 `--max-new-cases`，`score` 必须给出 `--max-new-judgements`；没有额度时
在读取运行配置、建立模型客户端之前拒绝执行。本轮完整评测已获授权，先执行固定排程的
前 6 次，查看调用计量与耗时后继续后续批次；这不会缩小 180 次的冻结研究设计，也不能
据此发布完整评测结论。鉴权等系统性故障应先暂停并诊断，不通过反复追加调用掩盖故障。

### 用量记录怎么读

计量实现位于 `backend/src/askdu/adapters/provider_metering.py`，通过 SDK 的公开
`http_client` 参数接入原来的网关适配器，不改变模型、提示词、temperature 或重试上限。
官方 SDK 文档说明了默认重试及自定义 HTTP client 接口；本地固定版本还支持项目正在使用的
HTTPX client，未因文档更新而迁移依赖。[OpenAI Python SDK](https://developers.openai.com/api/reference/python)

| 记录 | 含义与边界 |
|---|---|
| `logical_calls` | agent 的 `complete` 调用次数；仍由 68 次上限控制，评分上限为 2 次 |
| `http_attempts_started` / `additional_http_attempts` | 进入 HTTP dispatch 的尝试及同一次逻辑调用的追加尝试；不是服务器已接收或已计费的证明 |
| `http_attempts_not_sent` | 已准备记录、但计量写入失败而明确未送入 transport 的尝试 |
| `unresolved_*` | 进程结束时仍停在 started 的调用/请求；包括被强制终止的情况，不补造结果 |
| `http_status_counts` | 实际收到的 HTTP 状态分布，保留 429、5xx 等失败尝试 |
| `tokens.*.observed_total` | 有效回执的已观察合计；没有回执时为 `null`，不是 0 |
| `attempts_with_value` / `attempts_without_value` | 每个 token 字段的覆盖数；合计必须和缺失范围一起解释 |

只接受非负整数形式的 `prompt_tokens`、`completion_tokens`、`total_tokens`，以及可选缓存、
缓存写入和 reasoning 分项。完整主字段必须满足 prompt + completion = total；负数、布尔值、
字符串、矛盾合计等标为 invalid，不纳入合计。缺字段标为 partial/absent；不可解析回执为
unavailable。缓存/reasoning 是分项，不能再加进 total。字段含义可对照
[Chat Completions usage](https://developers.openai.com/api/reference/ruby/resources/chat/subresources/completions/methods/retrieve)。

例如本地模拟的 `429 → 200`，若只有 200 返回 13 个 prompt、7 个 completion token，则记录
1 次逻辑调用、2 次 HTTP 尝试、已观察 total=20，同时明确另 1 次尝试没有用量；不能称为
“整个调用已证实仅消耗 20 token”。这是协议示例，不是本项目的真实 provider 测量。

新 journal 在模型调用前写入零调用状态，并在每次逻辑调用/HTTP 尝试开始前及返回后原子保存。
已有 journal 不覆盖；找不到 journal 的旧中断不能推断成零调用。写入失败会锁止后续请求，
且不会把返回后的日志异常抛回 SDK transport 触发额外重试；用量解析异常也不触发额外请求。
仅保留异常类名，不保留可能含敏感内容的异常消息。接入仅限同步、非 streaming、无 redirect
的冻结评测路径；不同案例拥有独立 journal，HTTP client 的调用上下文相互隔离。

每个运行的 `result.json` 包含 `model_usage` 和 journal 摘要；driver 对 timeout/crash/interrupted
同样收集最后持久化状态，不从分母删除。`driver_wall_seconds` 包含子进程启动和终止等待，旧的
中断案例没有可证明的耗时则为 `null`；worker 自身完成时另有 `wall_seconds`。调用耗时包含 SDK
等待和本地计量开销，不当作纯模型推理延迟。评分的用量保存在 `judgements/<case>/usage.json`，
最终 `scores.json` 的 `judge_usage` 与运行用量分开；无报告而未调用 judge 时明确为 not_called。

2026-09-09 的离线验证覆盖真实 SDK 配合 MockTransport 的重试、返回用量但无有效 completion、
字段缺失/异常、超时、硬终止子进程、写入失败、并发上下文隔离、worker 超时竞态与评分续跑。
上述离线验证本身没有核验真实 ModelHub 回执。新冻结批次将直接记录实际用量和缺失范围；
没有给旧 smoke 日志补写 token。计量 schema 随新 plan 冻结；已有失效的 held-out 摘要仍保持
失效，不借此解盲。

## 冻结、暂停、续跑与评分

1. `prepare` 验证公开 metadata 哈希；只提取已选公开 task IDs 的 question，不提取答案。
   它写入独占的新输出目录，冻结题目、顺序、两种控制器、预算、provider 标识摘要和代码摘要。
2. `run` 验证冻结摘要及全部社区/文件 census；每个子进程只收到 question 与完整授权 catalog，
   不收到已知社区作为选源提示，也不收到答案。
3. 每个案例启动前写入不可复用的 started marker。已完成案例直接复用；无终态的旧尝试标记
   interrupted，不重跑。进程锁仍被存活 driver/worker 持有时，第二个 driver 必须退出。
4. 达到批次上限时返回 `paused_at_batch_limit`，保存下一个未运行案例，不创建完整 summary/seal。
   重复同一个 `run` 命令只执行下一批新案例；暂停不等于失败，也不允许丢弃已失败案例。
5. 只有完整排程的全部终态都存在时才能 seal。源码漂移会拒绝后续调用，不能中途修好失败题后
   继续冒充同一个冻结版本。
6. `score` 先验证完整 seal、排程和 metadata 哈希，再读取答案。评分同样分批，保留已写入的
   verdict；未写完的既有评分尝试标为 unscorable，不追加模型重试。全部评分前不发布聚合分数。

数据完整性边界：目前验证固定 archive/release、已安装目录 census，并记录实际选中文件的
哈希；没有对全部解压后的 148 GB 数据树重新做逐字节 seal。物理 I/O、API 实际费用和独立
人工报告事实核查仍是单独的评测工作。

## 评分不是 UI 成功率

分别记录报告可用性、各阶段状态、修复次数、执行 artifacts、引用完整性、答案字符串及数值
序列的一致性。同模型的独立评分上下文比较完整报告与答案，是需要人工审计的 proxy：
不把 `completed`、合法 artifact ID、漂亮图表或相同数字当作语义正确性的充分证据。

评分模型不收到模式标签，问题、reference、报告和 artifacts 都按不可信数据处理。未发布报告
仍保留在分母；unscorable 单独计数且不从分母消失。不能据此宣称因果解释、推荐或所有自然
语言句子已被证明正确，也不做确认性显著性检验。

## 命令

从项目根目录执行；这些是评测命令，不是启动网页的必需步骤。

已冻结且已获授权的本次研究可使用统一入口：

```bash
# 只读进度，不调用模型。已有 driver 运行时不要再启动第二份。
./scripts/run_agentic_open_study.sh status

# 尚无活跃 driver 时：每批六例，续跑全部排程，封存后评分，再校验/生成汇总。
# 会调用真实付费模型；不新建或改写冻结计划，不重跑已经开始的 case。
./scripts/run_agentic_open_study.sh run
```

脚本遇到 runner 异常、鉴权 401/403、封存或汇总不一致时停止并保留现场。
最终自动生成 `experiments/results/agentic-open-v1/audited-summary-v1/summary.md` 和
`summary.json`；未完整封存及评分前不会生成。这不自动修改论文主张，也不替代独立人工审计。
若人工修改过已有汇总，脚本会拒绝覆盖；需要保留原件并为新版本选择另一个输出目录。

本轮新增的 23 项离线回归覆盖完整 census、封存/评分记录一致性、缺失用量、失败与不可评分
案例的分母、配对汇总、无损重入，以及 supervisor 的阶段顺序和错误停止。它们使用合成 fixture，
不调用真实模型。最新 `make quality` 为 286 项后端测试通过（保留两条第三方 deprecation
warning），另有 6 项前端视频辅助测试；Ruff、mypy、TypeScript 和生产构建通过。
对正在运行的真实批次调用汇总器时，它正确拒绝了尚未封存的结果，没有生成提前效果表。

这两个新增脚本属于编排与只读汇总，未修改冻结评测实现；完成上述工作后，源码摘要仍与
`c9c27b70f76a79e80f69cc5de5c5684a95e8ac04dad0d10d9d4938a5911ca9bf` 一致。

底层命令如下，通常不需要逐项执行：

```bash
# 离线保护检查：使用合成数据与 fake model，不调用真实 API。
uv run --project backend pytest backend/tests/test_agentic_open_evaluation.py backend/tests/test_provider_metering.py -q

# 授权并确认评测设计后仅执行一次：创建冻结计划，不调用模型。
uv run --project backend python experiments/agentic_open_evaluation.py prepare

# 本轮已获授权；同一命令再次执行会续跑下一批，不重跑已启动案例。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --project backend python experiments/agentic_open_evaluation.py run --max-new-cases 6

# 状态检查不调用模型；同时查看 live_process_holds_lock 和 progress，不能只看旧状态文件。
uv run --project backend python experiments/agentic_open_evaluation.py status

# 仅完整 predictions seal 后、评分额度也获确认时执行。
uv run --project backend python experiments/agentic_open_evaluation.py score --max-new-judgements 6

# 完整评分后只读校验（不需要 API key，不调用模型，也不重新读取 benchmark 答案）。
uv run --project backend python scripts/summarize_agentic_study.py
```

输出默认在 `experiments/results/agentic-open-v1/`。不要删除 started marker、篡改冻结摘要、重排
失败案例或覆盖既有结果来恢复运行；代码变化后的研究需要新的输出目录和明确的新版本标记。
