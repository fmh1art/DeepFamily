# Answer at a glance 排版优化

日期：2026-09-09。

问题：此前 `ReportPanel` 将完整 executive summary 放入 `h2`，继承 18–24 px 的较粗标题样式。
长答案因此形成大块加粗文字，抢占报告首屏。此次仅调整前端展示，不修改原始分析报告、
模型提示词、评测实现或下载内容。

## 新展示

- 独立的 13 px 摘要标题，正文为 16 px、400 字重、1.75 行高，最长 100ch 阅读行宽。
- 勾选标记缩至 32 px，并使用浅色底；卡片移除阴影。
- 长答案默认最多 5 行，保留省略号和明确的展开按钮；短答案不显示多余按钮。
- 根据真实布局而非字符数判断折叠，监听窗口宽度变化，兼容中英文。
- 展开/收起支持键盘和可访问状态；完整文本保留在 DOM 和 Markdown 导出中。

实现：[ExecutiveAnswer.tsx](../frontend/src/components/ExecutiveAnswer.tsx)、
[ReportPanel.tsx](../frontend/src/components/ReportPanel.tsx)、
[styles.css](../frontend/src/styles.css)。

## 验证

`make frontend-check` 通过：6 项前端视频辅助测试、TypeScript 和生产构建。
独立 registry 测试服务 `askdu-summary-ui-review`（8082、独立 runtime volume、无模型密钥）
通过全部 16 项浏览器测试，其中新增 3 项覆盖：

1. 用户截图中的英文长答案：5 行预览、完整展开、键盘切换、390 px 窄屏和完整下载。
2. 中文长答案的相同交互及下载检查。
3. 同一段文字宽屏无需折叠、窄屏出现按钮、恢复宽屏后按钮消失。

既有短答案测试额外确认没有展开按钮。摘要正文固定为 16 px、400 字重；折叠时正文高度
不超过 141 px，桌面摘要卡片高度小于 250 px。桌面和手机截图已实际查看，位于
`frontend/test-results/executive-answer-*-desktop.png` 与 `*-mobile.png`。
这些是 UI 回归 fixture，不是新模型运行或大学排名事实评估。

此次只重新部署 Web 容器；不需要重新下载数据，也不改动 API 配置或停止后台评测。
评测 implementation SHA-256 保持
`c9c27b70f76a79e80f69cc5de5c5684a95e8ac04dad0d10d9d4938a5911ca9bf`。
旧论文截图/视频仍是历史 UI 制品，未冒充此次新版截图；相应演示面绑定需要在下一次更新
投稿素材时重新采集。本次没有声称整体 paper/readiness 门禁通过。
