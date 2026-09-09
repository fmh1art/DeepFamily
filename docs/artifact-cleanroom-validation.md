# 内部 artifact：打包与干净目录复现

日期：2026-09-09。操作指南：[ARTIFACT.md](../ARTIFACT.md)。

## 本次修复

- 仅内部预览允许项目已固定、不含凭据的完整 ModelHub endpoint；公开模式仍拒绝。
  未修改运行中的接口、模型或私有配置。
- 内容检查读取实际 tar 成员，不依赖 Git-ignore；检查密钥样式赋值、非法/重复路径、链接、
  特殊文件及私有内容，并限制检查规模。这是启发式检查，不是完整的密钥检测器。
- 校验器要求配置示例、完整开放数据池 manifest、三阶段 UI、报告及计量代码存在；
  checksum 必须指向所验压缩包。失败不会覆盖之前的包及 checksum。
- 指南和 CI source-quality job 先构建论文再做质量检查；指南明确隔离项目/volume/端口。
  没有放宽失效的 held-out 冻结门禁。

## 实际测试输入

本机保留的内部预览副本：
`artifacts/release/cleanroom-20260909/ask-dont-upload-artifact-v0.4.0-preview.tar.gz`。

SHA-256：`fcb421d4a11250d8018dca8ecfd2137269114564c2b0f0129c64cb6f5d651851`。
包含 274 个成员；checksum、内容审计及解压后的逐字节重新打包通过。
主输出路径后续可以更新，不以同名新包冒充这里绑定的测试输入。

解压目录为 `/tmp/askdu-artifact-cleanroom.zeAKkZ/ask-dont-upload-v0.4.0`，没有复制工作区的
`.env`、运行记录、数据、`.venv` 或 `node_modules`。这是已有 Docker/工具/缓存主机上的
干净目录验证，不是全新 ECS/操作系统安装验证。

| 检查 | 结果 |
|---|---|
| Python | `make backend-sync` 按 lockfile 创建独立 Python 3.10.20 环境；uv 可复用主机缓存 |
| Node | 临时安装官方 Node 24.20.0 Linux x64，核对官方 SHA-256；不改变全局环境 |
| 数据 | `make pilot-assets` 下载固定 revision 的 metadata、community 43/52；两个 archive 和 13 个 CSV 校验通过 |
| 论文 | `make pdf-modern` 重新取得固定模板、构建 4 页 PDF、绑定 18 项输入；单独 `check_submission.sh --draft` 的页数/字体检查通过 |
| 质量 | 解压包内 `make quality`：247 passed、2 个已知依赖弃用警告；Ruff、mypy、TypeScript、前端构建通过 |
| 注册实验 | `make experiment-all` 重跑 community 43 的 60 个 task/mode 组合、community 52 的 2 个 probe；汇总及论文数字校验通过 |
| Provider contract | 14 项无真实模型凭据的 HTTP 合约测试通过 |
| ECS 模板 | `make ecs-config-check` 通过；不代表实际 ECS/TLS 部署完成 |
| 浏览器 | 独立项目 `askdu-artifact-cleanroom-20260909`、独立 volume、8082、registry、空密钥，13 项 E2E 通过 |

Node 安装包摘要：`2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2`。
重建 PDF：1,131,611 bytes，SHA-256
`6d32a1cc14a5fb11374de53fd767a0de60f42d73fecb88a56ae70ab24ecf48db`。
PDF 可以带不同构建元数据；其保证是输入/产物绑定和排版校验，不是逐字节确定性。
逐字节重建的结论仅用于源代码预览包。

上述验证当时，被测包与当时工作区的 demo-surface digest 一致：
`531b09c17c44c117eda5d038745768e947bec6d18b8ac659c8b48d805b522fee`。
之后增加的 checksum-target、必需报告模块和公开模式回归只改动打包/CI/测试/文档。
该次打包验证结束时工作区 `make quality` 为 **250 passed**，其中 **33 项打包回归**；与旧包中的
247 项分开记录，不把后加的测试冒充已在旧包中执行。

随后进行了报告导出后端修改，并刷新截图/PDF；上述历史包不覆盖这些变化，也不再与最新
演示面摘要相同。最新工作区的 263 项测试及单独下载检查见
[report-export-validation.md](report-export-validation.md)，不能视为重新执行过本节干净目录流程。

测试结束后只停止隔离容器及网络，独立 volume 保留。原 8080 agentic 服务未重启，
`/readyz` 仍为 `ready`、`coda-open-v1`、`csv_assets: 16315`。

## 未完成的边界

- 没有从头下载 30 个完整开放社区，没有新增真实模型请求或执行 180-run 效果评测。
- 未打开 sealed community 45；旧冻结失效仍是 readiness failure。
- 未执行远端 GitHub Actions，本地检查不等于 hosted CI 全绿。
- 根代码许可证、作者信息、公开上传、正式 Demo CFP、非作者试演及真人旁白等仍未完成。
  内部预览可复现不等于完成投稿。
