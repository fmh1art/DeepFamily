# 报告导出格式与验证

日期：2026-09-09。界面说明见 [demo-interface.md](demo-interface.md)，三阶段与真实运行记录见
[stage-io-validation.md](stage-io-validation.md)。

## 改动

新报告保留“摘要 → 分维度分析 → 综合结论 → 局限”，各段通过 `E1`、`E2` 等链接引用
后面的 **Evidence results**。每份执行结果只展示一次，避免同一张表在多个章节重复出现。

- 记录、记录数组和普通数组导出为真正的 Markdown 表格，不再混用列表前缀和 JSON 代码块。
- 稀疏记录使用所有记录的字段并集；缺失值明确显示 `Not available`，不补零。
- 展示时遵循显式精度，否则用 12 位有效数字消除浮点尾数噪声，微小数值可用科学计数法。
  整数保持精确；原始 artifact 数值、canonical answer、报告正文和证据链不因此改变。
- 表头和结果单元格中的竖线、换行、Markdown 和 HTML 特殊字符按数据处理；这不是对整份
  模型生成正文的通用 HTML 安全审计。
- 下载内容仍逐字等于服务器持久化的 `report.markdown`，并绑定报告文件 SHA-256。

这项修改适用于更新后生成的报告。旧运行和旧报告没有迁移或重写；重新提交问题才会产生
新格式的完整运行结果。没有新增 PDF 导出功能，下载格式仍为 Markdown。

## 已执行的检查

| 检查 | 结果 |
|---|---|
| 报告格式专项 | 13 项测试通过，覆盖表格解析、字段并集、空值、数值精度、特殊字符、证据去重及持久化摘要 |
| 相关后端回归 | 报告格式、writer、agentic pipeline 和 model planner 合计 35 项通过 |
| 完整质量检查 | `make quality`：263 项后端测试通过，Ruff、mypy、TypeScript 和前端构建通过；保留 2 条既有依赖弃用警告 |
| 浏览器回归 | 独立 `askdu-report-export-check` 项目、8082、无真实模型密钥：13 项 E2E 和 5 项截图测试通过 |
| 下载合约 | 1 项本地 mock-provider 浏览器测试通过：实际下载字节等于持久化 Markdown，SHA-256 一致，证据锚点存在，无 mock 密钥泄漏 |

另用已有真实运行 `run_e2f9348452df475c` 的执行 artifacts 和原始 narrative **仅重新排版**：
CommonMark 加表格扩展解析出的表格从 0 张变为 10 张，JSON 代码块从 13 个变为 0 个。
原始数值、章节与综合结论不变。浏览器打开该排版副本后，10 张表格和证据跳转正常，
没有发出网络请求。这不是新的模型成功运行或效果评测。

- 原始记录：`runtime/stage-io-report-smoke-schema-20260909.json`，SHA-256
  `a48471eb8791c103a81d1529e90d92063dd0f4fd3b08f07b5e218e493a50ba02`。
- 独立排版副本：`runtime/report-export-review-20260909/runs/run_export_review/reports/report.md`，
  SHA-256 `462391b36ab7963493005a1f64c32c063b7bce4252d1cd47d33add486ba07f1f`。

确认没有活跃运行后，通过 `./scripts/run_demo.sh agentic` 更新了 8080 本机服务；数据及运行
volume 保留。部署模块与工作区源文件摘要一致，`/readyz` 返回 `ready`、`coda-open-v1`、
`csv_assets: 16315`。这些回归和格式检查均未新增真实模型调用。
