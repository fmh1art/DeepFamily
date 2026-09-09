# 三阶段输入、输出与报告：本次验证记录

日期：2026-09-09（Asia/Shanghai）。界面使用说明见 [demo-interface.md](demo-interface.md)。

最新报告导出复核：`make quality` **263 项后端测试通过**，13 项隔离浏览器回归和 1 项本地
mock-provider 下载测试通过。修复了 Markdown 表格格式和重复结果展示；已更新 8080 agentic
服务并保留历史记录，无新增真实模型调用，详情见 [report-export-validation.md](report-export-validation.md)。

较早的部署复核：`make quality` **217 项后端测试通过**，Ruff、mypy、TypeScript 和生产构建通过；
**13 项浏览器测试通过**（独立 `askdu-stage-io-review` 服务，端口 8082，无模型密钥）。
另在 8080 当前 agentic UI 中拦截提交请求，回放下文已登记的真实完成记录；确认服务提供的
JS/CSS 与本地生产构建逐字节一致，30 个社区、当前/历史跳转、80 行 × 10 列的准备结果、
schema 类型差异、10 个 Code / 10 个 Execute cell、5 节报告和 Markdown 下载均正常。
390 px 窄屏无页面横向溢出，浏览器运行时错误为 0。本次没有新增真实模型调用，也未改写历史
报告或重启 8080 服务；以下较早的测试数量保留为开发过程记录。

## 现在如何查看

```bash
# 在项目根目录执行；更新并启动完整公开 CoDA 数据池的 agentic 模式。
./scripts/run_demo.sh agentic
```

打开 `http://127.0.0.1:8080`，输入一个分析问题即可，无须上传或选表。

| 阶段 | 输入 | 过程 | 输出 |
|---|---|---|---|
| Discovery | 问题和数据需求 | 左侧回放步骤，右侧显示社区、目录、文件与当前/历史跳转 | 成功选中的 CSV 文件 |
| Preparation | 已选 CSV 的字段和类型 | 算子树、分支观察、字段变化 | 选中表的 schema、行列规模和真实数据预览 |
| Analysis | 实际被分析的准备结果 | SQL/Python、执行结果、必要时的 Debug | 分维度报告、图表、综合结论、局限及 Markdown 下载 |

网图显示完整的社区层和截至当前步骤实际遇到的文件，不是将三万余个文件全部画成小点；
箭头表示工具关注位置的转移，不声称是 CoDA 发布的语义邻接图。
回放不展示未来结果，被拒绝的选源不产生成功输出；输入/输出字段可展开。
重新选源时输出跟随最新的成功选择，不累计已经被替换的文件。Preparation 还会对比同名字段的
已记录类型；报告的来源数、行数依据实际 artifact lineage，而不是最后一个未选中候选。

## 真实模型检查

三次检查都只提交问题“最适合移民的国家是哪一个”，没有提供文件路径、列名或答案。
使用既有私有配置中的同一个 ModelHub 接口和 `gpt-5.5-2026-04-24`，未加载论文训练的模型。

1. 初次运行在 Discovery 终止：最终混选不同社区，被 CoDA 选源约束拒绝。
   原始记录：`runtime/stage-io-report-smoke-20260909.json`。
2. 明确同社区约束和剩余步数后，成功选源并生成报告，但准备计划经历四次 JSON/schema
   拒绝后才执行。这些拒绝不是已经执行的树分支或 Debug cell。
   原始记录：`runtime/stage-io-report-smoke-budgeted-20260909.json`。
3. 修复算子协议被上下文深度裁剪的问题后，新运行 `run_e2f9348452df475c` 完成：
   12 条 Discovery 记录（含根目录观察）、1 条选中的准备候选、80 行准备数据、
   10 个 Code 和 10 个 Execute cell、10 个分析 artifacts、5 个报告章节。
   Report writer 的 `finish_report` 为 accepted，未使用报告降级模板。
   原始记录：`runtime/stage-io-report-smoke-schema-20260909.json`。
  报告：`runtime/stage-io-report-smoke-schema-20260909/runs/run_e2f9348452df475c/reports/report.md`。

该真实完成态另在 Chromium 中回放：显示 30 个社区、1 个选中文件、5 个报告章节，
三个阶段均可切换并显示数据预览/报告，浏览器无运行时错误。回放不重复调用模型。
在最新版 UI 上再次检查了桌面画布，并验证 **Download report** 的内容与服务器持久化
`report.markdown` 完全一致。

最后一次选中一个多指标 CSV：`Quality of life index by countries 2020.csv`，涵盖生活质量、
购买力、安全、医疗、成本、住房、通勤、污染和气候。这不是声称单个幸福度指标能回答全部移民
问题。报告说明了数据年份、未指定权重、未覆盖移民法律/个人资格等边界。

这些是开发期功能检查，不是独立 held-out 评测、准确率或任意问题都能完成的保证。
artifact 引用校验也不等价于证明自然语言解释或决策建议完全正确。

## 回归检查与边界

- `make quality` 最终完整通过：172 项后端测试，Ruff、mypy、TypeScript 与前端生产构建通过。
  两条第三方依赖 deprecation warning 仍存在，未屏蔽。
- 13 项浏览器测试通过，覆盖三阶段、回放、28 文件 frontier、子目录、schema 展开与类型差异、
  正确物化状态、拒绝/重新选源动作、报告来源与行数、证据链接、图表数值不被遮挡、窄屏及既有无障碍检查。
  结构化轨迹 fixture 用于 UI 回归，不计入上面的真实模型检查。
- 初次功能回归曾为 `165 passed, 2 deselected`，被排除的两项是旧论文截图/构建一致性检查。
  本次已通过隔离的真实 registry Web 重新捕获论文截图，并用固定 builder 重建 PDF 和构建记录；
  最终 172 项检查没有 deselect，没有修改校验逻辑或伪造 digest。
- 该 UI 验证结束时稿件曾是 5 页；后续投稿整理已通过精简正文恢复 4 页，见
  [submission-plan.md](submission-plan.md)。PDF 构建一致性仍不等于投稿就绪。
  旧视频、试用记录及实现冻结摘要不能冒充当前版本；本次没有更新 held-out 冻结或打开 sealed community。
- SQL/Python 是系统编译并受限执行的代码；保留 DeepAnalyze 的执行—反馈—报告语义，但不是
  开放执行任意模型生成代码的沙盒。
- 最终通过 `./scripts/run_demo.sh agentic` 更新本机服务，`/readyz` 返回 `ready`、`coda-open-v1`、
  `csv_assets: 16315`。30 个公开社区已安装，旧运行记录保留；旧报告不会自动重新生成。

## 交付前再次复核

同日交付前再次执行 `make quality`，当前版本 **188 项后端测试全部通过**，Ruff、mypy、
TypeScript 和生产构建通过；仍只有上述两条第三方依赖警告。
13 项浏览器回归测试在独立的 `askdu-stage-io-finalcheck` registry 服务（8082）上全部通过，
没有停止或改用 8080 上的 agentic 服务，也没有为回归测试调用真实模型。

另将上述真实运行 `run_e2f9348452df475c` 的原始结果在 8080 当前 UI 中再次回放。
检查前核对了原始 JSON 的 SHA-256；浏览器拦截运行请求，不创建新的后端任务。
确认根步骤显示 30 个社区且没有未来文件，第 5 步同时显示当前与历史跳转，第 12 步输出
最终选中的 CSV；Preparation 显示 80 行、10 列、真实表格预览和 `Country: object → string`
的已记录类型差异；Analysis 显示 10 个 Code、10 个 Execute、0 个 Debug 和 5 节报告。
下载的 Markdown 与持久化的 `report.markdown` 逐字一致，浏览器运行时错误为 0。

这些结果区分了真实模型运行、历史记录回放和结构化 UI 回归；不把回放当成一次新的模型成功运行。

交付时 8080 服务仍为 `ready`、`coda-open-v1`，本轮回归没有触发真实模型请求。
如果浏览器仍显示旧界面，先强制刷新；旧运行不会自动补生成新的分维度报告，需要重新提交问题。
