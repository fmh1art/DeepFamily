# VLDB 2027 Demo 投稿计划

状态日期：2026-09-09（Asia/Shanghai）。本次重新核对官网、Important Dates 和 Formatting
Guidelines；导航和日期表仍未列出 Demo CFP。任何会变化的规则都应在投稿前重新核验。

## 1. 规则证据矩阵

| 项目 | 当前结论 | 证据级别 | 行动 |
|---|---|---|---|
| 大会地点与日期 | Athens, Greece；2027-08-23 至 2027-08-27 | VLDB 2027 官网已确认 | 安排至少一位作者现场参会的预算与签证窗口 |
| 论文模板 | 所有 track 必须严格使用 PVLDB 模板；缺失 mandatory blocks 可能 desk reject | VLDB 2027 Formatting Guidelines 已确认；2026-09-06 核对官方模板 `39c95f5c6fcbe652a83be24e4eff8f2134cd3fbc` | 仓库已固定该版本；投稿前再次同步官方更新 |
| Demo CFP 与截止日期 | 尚未在 VLDB 2027 官网发布 | 官方站当前状态 | 至少每月核查一次，发布后立即更新本文档 |
| 页数 | 暂按 4 页且包含全部材料规划 | 仅来自 VLDB 2026 Demo CFP | 2027 CFP 发布后复核 |
| 匿名方式 | 暂按 single-anonymous、正文含作者与单位规划 | 仅来自 VLDB 2026 Demo CFP | 2027 CFP 发布后复核 |
| 评审重点 | 系统新颖性/意义、明确 demo 场景、架构、功能、用户交互；高互动优先 | 仅来自 VLDB 2026 Demo CFP | 作为设计基线，2027 CFP 发布后复核 |
| 视频 | 暂按建议提交，最长 5 分钟、最大 50 MB、常见视频格式 | 仅来自 VLDB 2026 Demo CFP | 先按 3--5 分钟设计脚本，最终复核 |
| CMT 与 conflicts | 预计需逐作者注册并声明冲突 | 仅来自 VLDB 2026 Demo CFP | CFP 发布后确认站点和具体规则 |

官方来源：

- https://www.vldb.org/2027/
- https://www.vldb.org/2027/formatting-guidelines.html
- https://www.vldb.org/2027/important-dates.html
- https://github.com/vldbproceedings/VLDB-Template
- https://www.vldb.org/2026/call-for-demonstrations.html

本次官方状态审计同时检查了官网导航、Important Dates、Formatting Guidelines 和
官方模板仓库。2027 官网导航及日期表仍只列 Research Track；不能从 Research Track 的
submission guidelines 推断 Demo Track 的匿名、截止日期或附件规则。模板主分支当前仍为
上述固定提交；`make paper-assets` 获取的三个本地 vendor 缓存与其内容一致，`pvldb.sty`
只多一个文件末尾换行。这些缓存不进入 Git 或 artifact，详见
`paper/TEMPLATE_SOURCE.md`。

以后每月或投稿前运行 `make cfp-status`。该命令只读取官方页面和模板仓库，并与
`docs/vldb2027-status.json` 的人工确认快照比较；CFP 链接、日期表、格式警告或模板 HEAD
任一变化都会失败并要求人工复核，不会静默改写论文规则。
仓库还提供只读权限的 `.github/workflows/cfp-watch.yml`；推送到 GitHub 默认分支后，它会
每周运行同一检查。定时失败只是人工复核信号，不会自动接受新规则或修改快照。

## 2. 论文的最小可接受论证

四页 demo paper 不是产品说明书。审稿人需要在很短篇幅内回答四个问题：

1. **Problem**：一个具体且重要的数据管理任务为什么仍然困难？
2. **System**：系统通过什么架构或机制解决该困难，技术新意在哪里？
3. **Experience**：现场观众具体做什么，交互如何显露而非掩盖核心技术？
4. **Evidence**：哪些实现、测量、案例或部署事实说明系统真实可用？

建议篇幅预算（待真实内容进入后按版面调整）：

| 内容 | 目标占比 |
|---|---:|
| Abstract + Introduction + Contributions | 25% |
| System Overview / Architecture | 30% |
| Demonstration Scenario / Audience Interaction | 30% |
| Positioning + Evidence + Conclusion + References | 15% |

## 3. 工作里程碑

具体截止日期尚未公布，因此用“完成条件”管理进度，不用未经确认的投稿日期倒推。

当前快照：M1 的标题与问题定位已确定。M2 已有完整开放数据池、共享外部模型的三阶段
agentic 流程、逐跳社区图、输入/输出 schemas、实际 prepared-table 预览和多维报告；摘要
排版更新后，浏览器检查为 16 项 E2E；最新 `make quality` 为 286 个后端测试，Ruff、mypy、TypeScript
和前端构建均通过。真实 provider 的成功和失败开发记录见
`docs/agentic-smoke-evidence.md` 与 `docs/stage-io-validation.md`；其中包含只给中文问题、
不提供维度和权重的多维报告完成态。这些选定案例不构成模型准确率。

M3 保留完整 15 题 controller comparison、第二社区 probe、同预算 static-retry 消融、
两张图和 40 次注册模式 HTTP 测量。13 题前瞻性评测尚未执行、尚未解盲；其历史实现冻结
摘要与当前源码不一致，门禁正确拒绝，不再将它标为可解盲。该协议仍是 `model` 模式，
不能声称评测了完整 `agentic` 三阶段。

完整流程的独立开放集设计见 [agentic-open-evaluation.md](agentic-open-evaluation.md)：
30 社区各取一题、2 种控制器、3 次重复，共 180 次运行；脚本支持显式批次额度、续跑、
完整封存后评分。现已接入逐逻辑调用、逐 HTTP 尝试和 provider token 回执计量，并区分
缺失用量、超时与硬终止；40 项评测/计量专项离线测试通过。2026-09-09 收到继续执行的全面
授权后，已创建 30 题/180 case 冻结计划，前 6 个真实 case 已执行完并继续后续批次；
完整结果尚未封存或评分，首批的 4 个报告和 2 个数据缺口只用于运行检查。
真实网关的回执覆盖率须据实际 journal 汇总。该研究是开发暴露的开放集样本，不是 held-out，
也不能把 smoke 并入效果表。

续跑与封存后汇总已补充统一脚本及 23 项离线回归；最新 `make quality` 为 286 个后端测试和
6 个前端视频辅助测试通过，类型检查及生产构建通过。评测实现的冻结摘要未变，汇总器在
真实批次尚未封存时正确拒绝发布结果；这些新增测试数量不冒充前述历史 artifact 的复现记录。

M4 正文已按当前 agentic 实现同步。Figure 2 已替换为当前 UI 对真实历史运行的三阶段节选，
展示社区图、准备路径及表格、SQL 与多维报告；旧 task-959 图保留作离线素材。
图中标记了 recorded run 和没有发生 Debug/回溯的边界，见
[agentic-replay-figure.md](agentic-replay-figure.md)。通过精简正文仍保持四页，没有改
实验数字、模板、字号或页边距。PDF 已逐页查看；数值、引用、截图/PDF 指纹及
`./scripts/check_submission.sh --draft`（页数、字体）通过。但完整 `make draft-check`
**仍失败**：readiness 的 `prospective_heldout` 检查报告旧实现冻结失效，另有 5 项 pending。
稿件仍有作者和 artifact URL 占位。正式 CFP、许可证、留出评测、非作者试演、真人配音/
双作者试听和公开 artifact 都尚未完成；四页排版通过不等于投稿就绪。

内部 artifact 的下一步已完成干净目录复现：从不含数据/私有配置的预览包重新下载 pilot、
安装环境、构建 PDF、复现 62 个注册 task/mode/probe 运行，并通过 13 项隔离浏览器测试。
打包验证阶段新增 33 项回归，当时工作区 `make quality` 为 250 passed；被测历史包与当时
演示面的绑定及测试版本差异见 [artifact-cleanroom-validation.md](artifact-cleanroom-validation.md)。
内部预览可逐字节重建，但没有公开发布，也不替代真实模型评测或作者交付。

随后修复了新报告 Markdown 的表格解析、重复证据和结果单元格展示，新增 13 项回归。
历史执行结果仅重排，不重复调用模型；实际浏览器下载与持久化报告及 SHA-256 一致。
已更新 8080 agentic 服务，原始记录和旧报告保留。详情见
[report-export-validation.md](report-export-validation.md)。

当前 agentic 演示另有 144 秒、13 场景的无声回放视频和英文旁白稿，见
[agentic-video.md](agentic-video.md)。使用已登记的真实历史运行和当前 UI，不新增模型请求；
固定画面停留时间不算实时延迟，单路径不冒充回溯。旧 registry 修复视频保留且分开标记。
两者都不替代真人录音、双作者审阅和最终投稿视频。

### M1 — 选题冻结

- 完成 `docs/demo-brief.md` 的 A1--A3。
- 能用一句话说明目标用户、痛点、系统机制和可观察收益。
- 找到至少 3 个最接近系统/论文，明确非营销式差异。

### M2 — 可演示闭环

- 从干净环境按文档启动系统。
- 一位新用户能在 3--5 分钟走完核心任务。
- 每个关键能力都有屏幕上可观察的结果。
- 网络/API/数据失败均有离线或预录备份。

### M3 — 证据与图表冻结

- 记录数据、硬件、软件、参数、基线和重复次数。
- 完成界面/交互总览图与系统架构图。
- 所有数字均能追溯到脚本、日志或原始表格。

### M4 — 四页英文初稿

- Abstract、Introduction、System、Demonstration、Conclusion 连成单一论证。
- 不含未核验引用、虚构数字、空泛的 “novel/effective/efficient”。
- 严格检查通过；至少一次非作者试演并记录问题。

### M5 — 投稿包

- 根据正式 VLDB 2027 Demo CFP 复核页数、匿名、视频、CMT、冲突和版权规则。
- PDF 字体嵌入、图中文字可读、链接可访问、作者顺序锁定。
- 视频与论文使用相同术语和相同主张。
- 一名作者负责最终 CMT 字段，另一名作者独立复核上传文件。

## 4. 投稿门槛

在以下项目全部满足前，不把稿件称为“可投稿”：

- [ ] 正式 2027 Demo CFP 已核验并记录。
- [ ] `paper/main.tex` 中无 `TODO`、占位作者或占位系统名。
- [x] 正文当前核心主张均有代码、数据、测量或已核验引用支撑；结果校验器还会独立重算汇总并核对主演示场景。
- [ ] PDF 使用官方当前模板且在正式页数限制内。
- [x] 演示脚本包含观众主动操作、技术反馈和失败备选。
- [ ] `community_45` 冻结首轮已封存并在不改写 first pass 的前提下评分。
- [ ] 至少一名此前未接触项目的非作者完成六任务与独立 repeat，记录与当时 demo surface
  及参与者提示/主持人评分协议 SHA-256 绑定、逐任务结果与汇总一致，且无阻塞问题遗留。
- [ ] 根级代码许可证、容器 OS 人工复核及 public artifact 已完成。
- [ ] 所有作者、单位、ORCID（如使用）、邮箱和 conflicts 已逐人确认。
- [ ] 真人旁白视频通过技术门禁，并由两名作者完整试听。
- [ ] 至少两名作者独立检查最终 PDF 与上传附件。

## 5. 作者交接顺序

下面这些动作涉及身份、法律选择、私密凭据或不可逆的 held-out 解盲，不能由开发流程代替
作者授权。按此顺序执行，可以避免生成与论文不一致的公开制品。

| 顺序 | 作者输入或授权 | 安全记录位置 | 完成证据 |
|---:|---|---|---|
| 1 | 轮换任何曾出现在聊天、终端历史或日志中的 provider credential | 私有环境文件或云端 secret；不得写入仓库、论文或 artifact | 用新凭据执行 `make provider-smoke`；公开包的 secret scan 仍通过 |
| 2 | 确认作者顺序、单位、城市/国家、邮箱、可选 ORCID 和 CMT conflicts | `paper/main.tex` 与 CMT；不要用推断值填充 | `./scripts/check_submission.sh --submission` 不再报告作者/TODO 占位符 |
| 3 | 确认项目版权持有人、根代码许可证和论文/代码/数据三类边界 | 根 `LICENSE` 及 `docs/licensing-and-redistribution.md` | `make dependency-license-audit` 与 readiness 的 `release_licensing` gate 通过 |
| 4 | 明确授权首次 held-out 解盲 | 按 `docs/heldout-protocol.md` 的冻结哈希与原子状态机执行；不手工浏览数据 | first pass 封存后再评分，`prospective_heldout` gate 通过 |
| 5 | 提供 credential-free HTTPS artifact URL | 上传经验证的 release archive 后写入 `\\vldbavailabilityurl{}` | `make artifact-public-verify` 与 `public_artifact` gate 通过 |
| 6 | 安排非作者试演、作者录音和双作者终审 | 仅保存去标识试演记录和视频 review JSON | rehearsal、narrated video 与最终 `make check` 全部通过 |

`make draft-check` 和 `make check` 现在都会先运行 `make verify-results`：它重新计算两个
community 的汇总，核对论文中的所有已报告数字，并拒绝把尚未纳入冻结评测的
Preparation-targeted repair 写成已验证效果。两者还会运行 `make paper-capture-check` 与
`make paper-build-check`：前者把旧离线图和 Figure 2 绑定到各自的可执行采集脚本、当前演示面、
历史运行观察及输出字节，后者通过
`paper/main.build.json` 把固定 builder 与 18 项正文、模板、图件和验证输入绑定到最终 PDF，
从而拒绝过期或被替换的稿件。
