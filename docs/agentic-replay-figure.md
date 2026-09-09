# 论文三阶段图：真实运行回放素材

当前 `paper/main.tex` 的 Figure 2 使用
[overview.png](../paper/figures/agentic-replay-v1/overview.png)。它从当前 React 组件中采集真实历史
运行的 DOM 片段，再重新排版用于论文；**不是新推理结果，也不是整个网页原封不动的截图**。

## 图中如何读

| 面板 | 所展示的证据 | 节选边界 |
|---|---|---|
| a · Discover | 第 5 步在 community 28 内 inspect，保留完整社区层与当时已遇到的文件；下方是最终选中的 CSV | 网图取第 5 步，文件输出取第 12 步；连线表示目录归属或工具关注位置转移，不表示语义相似性 |
| b · Prepare | CastType → DropNulls → Sort → Terminate、记录的输入/输出类型、准备后表格 | 实际 80 行、10 列；总览只显示前 3 行、前 2 列。Country 的 `object → string` 是运行时类型标签差异，不冒充字段级 lineage |
| c · Analyze → Report | 已执行 SQL cell 与原始中文报告的 5 个章节标题 | 不是仅按该 SQL 的单指标结果写报告；完整运行有 10 个 Code、10 个 Execute 和 10 个 artifacts，报告还综合其他维度 |

问题仅为“最适合移民的国家是哪一个”，没有额外给定维度、权重、文件路径或答案。
该选定的完成态只有一条成功准备路径，**没有 Debug 或非局部回溯**；图注和图内均保留这一边界。
报告涉及 2020 年数据，不证明当前移民适合性。开发中的失败尝试没有删除，也没有并入准确率。

中文章节依次涵盖：范围和方法；总体生活质量；购买力、安全和医疗；成本、住房、通勤、污染和
气候；候选方案的优势与代价。报告主体还包含综合结论、数据年份、未指定权重和缺失政策信息。

## 复现命令

前提：本机 agentic Web 已运行于 `http://127.0.0.1:8080`，前端依赖和 Playwright Chromium 已安装，
`frontend/dist` 与正在提供的 JS/CSS 一致。此流程不重启服务、不切换 planner，也不读取私有 `.env`。

```bash
# 项目根目录；只回放已有的、校验过摘要的本地运行记录，不调用 LLM。
make capture-agentic-replay

# 使用官方固定模板重新构建并核对稿件；不改模型或数据。
make pdf-modern
make paper-build-check
./scripts/check_submission.sh --draft
```

必须有本地原始记录 `runtime/stage-io-report-smoke-schema-20260909.json`，其 SHA-256 为
`a48471eb8791c103a81d1529e90d92063dd0f4fd3b08f07b5e218e493a50ba02`。
若它不存在，采集会失败，不会替代为合成轨迹，也不会自动花费 API 额度重新运行。
完整原始日志不进入公开 artifact；已生成素材仍可通过公开的观察摘要记录独立做一致性校验。

采集期间浏览器只允许同源只读请求，运行 POST 在浏览器内被拦截为历史记录。
脚本核对实际提供的 JS/CSS 与本地构建文件，并验证原始运行和报告摘要。
`capture.json` 绑定采集脚本、排版样式、公开观察记录、当前 demo surface 和所有输出字节。
这里的当前 surface 不是历史推理开始时的实现冻结；原始 smoke 没有记录起始实现摘要。

## 文件与检查

所有输出位于 `paper/figures/agentic-replay-v1/`：

- `overview.png`：论文用三面板节选，宽 3,000 像素；PDF 中实测 431 ppi，正文最小字号约 6.5 pt。
- `overview.pdf`：浏览器导出的独立 PDF；正文嵌入的是 PNG，不改变论文模板字体。
- `overview-gray.png`：灰度可读性检查；历史路径为虚线，当前路径加粗并带方向。
- `discovery.png`、`preparation.png`、`analysis.png`、`report.png`：较完整的当前阶段/模块截图，均带 Recorded run 标签。
- `capture.json`：采集与输出摘要。哈希一致性不是报告事实正确性的证明。

旧 `paper/figures/demo-ui.png` 和 A–E 校验保留为 task-959 离线 repair 素材，不再充当论文 Figure 2。
`make paper-capture-check` 同时核对两组素材，不用新回放绕过旧素材的校验。
PDF 构建记录现绑定 18 项输入；源脚本、图片、模型观察记录或正文漂移会要求重新检查和构建。

本次完成灰度与四页逐页检查，`make quality` 为 188 项后端测试通过，另有两条既有第三方弃用警告；
论文数值校验和 draft 排版检查通过。没有新增真实模型调用、解盲或修改已有实验数字。
正式投稿仍需完成作者信息、评测、许可证、公开 artifact、试演和视频等门槛，不能以四页通过代替。

## 计量变更后的素材复核（2026-09-09）

评测调用计量接入后，已重新采集两组截图并重建 PDF，未修改正文或实验数字。
复核发现旧脚本在添加 print CSS 后过早读取布局，高度曾短暂为 944 px；稳定截图后的实际高度
为 625.265625 px。现在先由浏览器等待截图布局稳定，再验证相同画布的尺寸与像素数，保留
原有 750 px 高度门槛；失败时输出临时布局诊断，所有校验通过后才写入图件，manifest 最后写入。
因此布局检查失败不再先覆盖旧的部分素材；文件系统写入中断仍会由摘要校验拒绝，不宣称多文件
发布本身是原子的。

该次计量变更复核的 `make quality` 为 **217 项后端测试通过**，13 项浏览器回归在隔离的 8082 registry 服务
通过；当前 8080 仍是 agentic 模式且健康。两组图、18 项 PDF 构建输入、稿件数值均通过校验。
PDF 仍为 4 页，Figure 2 为 431 ppi，已检查四页及灰度图。`make draft-check` 的排版部分通过，
完整 readiness 仍为 5 pending、1 个旧实现冻结失效，不冒充投稿已就绪。本次没有真实模型调用。

## 报告导出变更后的素材复核（2026-09-09）

报告导出后端变更后，重新采集 registry 截图和既有 agentic 记录的回放素材，绑定当前源码。
回放使用同一份原始执行记录，没有重写其报告，也没有新增模型调用。正文、图件布局和
实验数值均未修改；完整 `make quality` 为 **263 项后端测试通过**。

按 PDF 和 scientific-visualization 检查流程重新查看四页 PDF 及灰度图：正文/图件无裁切，
当前路径和历史路径仍可用实线/虚线区分。`check_submission.sh --draft` 的四页与嵌入字体
检查通过，截图与 18 项 PDF 构建输入校验通过。新 PDF 为 1,131,611 bytes，SHA-256
`07cd83ab89dd0945b8669b840f0048f814a4512ce532fdb2ff562509a1c780cb`。
这些是素材和排版校验，不改变尚未完成的投稿门槛。

## 摘要排版变更后的素材复核（2026-09-09）

`Answer at a glance` 改为正常字重正文和按实际溢出展开后，重新采集 task-959 图和同一份
历史 agentic 记录。旧 PDF、构建记录和完整 figures 目录保存在本机
`artifacts/paper-history/before-summary-refresh-20260909.05maJq/`，未删除或改写原始运行。
图 D 现在显示新的摘要排版；Figure 2 的三阶段总览像素未变，当前源码绑定与独立阶段截图
已更新。采集没有真实模型请求，不把回放当成新评测。

registry 采集与回归使用独立的 `askdu-paper-summary-refresh` 项目、8082 端口和独立 volume，
5 项采集测试及全部 16 项浏览器回归通过。采集后仅移除该测试项目的容器和网络，volume
保留。8080 agentic API 的容器 ID 和启动时间未变，`/readyz` 仍为 `coda-open-v1`、16,315 CSV。

`make quality` 为 286 项后端测试、6 项前端辅助测试通过；保留两条第三方弃用警告。
两组截图、18 项 PDF 构建输入、已报告结果和 `check_submission.sh --draft` 均通过。
逐页查看重新渲染的四页 PDF，并检查灰度图：没有裁切，历史虚线与当前实线路径可区分。
图 2 实测 431 ppi，字体全部嵌入；LaTeX 仍有既有的 underfull / balance 提示，未声称零警告。
新 PDF 为 1,131,611 bytes，SHA-256
`cd46675d7f6b9c6cd96e49f85e0dbb68c2b5f90948b6daf11de834e5829aa18d`。

本轮未改正文、实验数字或冻结评测实现。`make readiness-draft` 仍为 5 pending、1 fail
（旧 held-out 实现冻结失效）；视频未同步重录。完整模型评测由独立进程继续进行，尚未
封存及评分，不将其过程状态填入论文效果表。
