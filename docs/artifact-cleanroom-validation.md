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

## 新版 UI 与整段指南复现（2026-09-09 后续验证）

本节绑定更新后的源码快照，覆盖报告导出、三阶段输入/输出和长答案自适应展开。
上面的历史包及其 247/250 项测试记录保持不变。

### 先保留发现的失败

第一次新版包位于
`artifacts/release/current-ui-20260909.Alcpjk/ask-dont-upload-artifact-v0.4.0-preview.tar.gz`，
SHA-256 为 `c3a79706f64a1c4866bce410aa77f96780ab4fb1edfd774f6ec1050f6c35a274`。
它在独立目录完成了 62 次注册实验和 16 项 E2E，但带回环模型地址运行质量检查时为
285 passed、1 failed：默认配置测试把进程中的 `ASKDU_LLM_BASE_URL` 当作默认值。
`_env_file=None` 只禁用 dotenv，不禁用进程环境变量。

修改 `backend/tests/test_llm.py`：默认值测试在临时清空的环境中执行，另加一项环境覆盖测试，
继续断言测试 provider 放行开关默认为关闭；没有修改运行时配置或 provider 校验规则。
中间包 `artifacts/release/current-ui-fixed-20260909.P6Mc8t/` 的 archive SHA-256 为
`426a396bcfb64c22547f2f55d75e4648623ec97f7c1bcd8d62087d4d3d8a304f`。
按旧指南的全部环境设置执行时，它又暴露了 10 个 Host 校验失败：提前设置的 Web 白名单
不含本地 TestClient 的 `testserver`，请求在进入被测 API 前即返回 400。

最终修正了指南的配置作用域：本地质量/provider 测试先清除继承的 Host/CORS 设置，
完成后再给隔离 Web 设置 `localhost,127.0.0.1,api`；同时清除继承的 `VIRTUAL_ENV`。
没有向生产白名单添加测试域名，也没有放宽安全断言。上述两个失败包均保留。

### 最终实际测试输入及过程

最终预览包：
`artifacts/release/current-ui-verified-20260909.7qvc82/ask-dont-upload-artifact-v0.4.0-preview.tar.gz`。

SHA-256：`e6949e5f19db01cd70edd3fe7698578b25261b3667085bd22d89dad0faa39658`；
290 个实际 tar 成员，内容审计、checksum 和独立逐字节重建通过。

全新解压目录：
`/tmp/askdu-current-cleanroom-verified.EWZgGv/ask-dont-upload-v0.4.0`。
没有复制私有 `.env`、数据、运行结果、`.venv` 或 `node_modules`。
复用已校验的 Node 24.20.0 可执行文件及主机 Docker/依赖缓存，因此仍不是新操作系统验证。

验证直接提取并执行该可信自建包中 `ARTIFACT.md` 的第一段 Bash 代码，整段退出码为 0；
没有手工跳过失败步骤或在解压后修改源文件。执行前确认 8082、Compose 项目及其命名 volume
未被使用。完整 stdout/stderr 保存在包旁的 `cleanroom-reproduce.log`，SHA-256 为
`567a338d5519d0924edaeca8b43510f2fe08cf7aad2f097a688b9809371ab578`。

| 检查 | 最终包内实际结果 |
|---|---|
| 环境安装 | `make backend-sync frontend-install` 创建独立 Python 3.10.20 环境并执行 `npm ci`；Node 24.20.0 |
| 公开 pilot | 固定 revision 的 metadata、43/52 archives 与 13 个 CSV 校验通过；没有下载 community 45 |
| 论文构建 | 固定模板和 TeX Live 容器构建 4 页 PDF，记录 18 项输入 |
| 质量 | `make quality`：287 个后端测试通过、2 个依赖弃用警告；6 个 Node 辅助测试、Ruff、mypy、TypeScript、前端构建通过 |
| 注册实验 | community 43 的 60 个 task/mode 组合及 community 52 的 2 个 probe 重新执行；汇总、完整 census 和论文数字核验通过 |
| 延迟证据 | 独立重算已保存的 40 个原始样本并通过一致性检查；本次没有新增延迟测量 |
| Provider | 15 项离线/回环 HTTP 合约与配置测试通过 |
| ECS 模板 | `make ecs-config-check` 通过；不是实际 ECS/TLS 部署验证 |
| 浏览器 | `askdu-artifact-reproduction` 项目、独立 runtime volume、8082、registry、空模型密钥；16 项 E2E 通过，包括中英文长答案、实际溢出判断、展开和完整导出 |
| 包的可复现性 | 全部命令执行后再次 `make artifact-verify`，仍产生上述相同 SHA-256 的 290 成员包，并通过独立重建 |

16 项 E2E 包含真实 registry 执行和明确构造的 agentic UI 轨迹，不是 16 次真实模型成功。
本轮 artifact 复现没有新增真实模型调用；既有 180-case 真实模型评测在独立服务中继续。

重建 PDF 另存为包旁 `cleanroom-main.pdf` 和 `cleanroom-main.build.json`，没有覆盖工作区论文。
PDF 为 1,131,611 bytes，SHA-256：
`e89c8d2089b2ab447a7d819aeaeae3270c73c7baa1af59378d245c4603214eb4`。
额外执行的 `paper-build-check`、`paper-capture-check`、`check_submission.sh --draft` 均通过；
所有字体嵌入。四页在 100 dpi 下与逐页查看过的中间包构建渲染逐字节一致。
已有 underfull/balance 排版警告仍存在，作者及 artifact URL 占位符仍保留。
PDF 构建元数据可变化，逐字节确定性的结论仅适用于源码包。

最终包与本轮结束时工作区的两套实现摘要一致：

- Demo surface：`c8849756ca9967e0d4a7406632f75ccd4939414fd253dc59d9e1c93e55066032`。
- 冻结 evaluation surface：`c9c27b70f76a79e80f69cc5de5c5684a95e8ac04dad0d10d9d4938a5911ca9bf`。

测试完成后仅停止并移除隔离容器和网络，`askdu-artifact-reproduction-runtime` volume 保留。
原 8080 API 容器 ID 及启动时间未变化，仍为 `ready`、`coda-open-v1`、16,315 CSV。
本节是在验证完成后追加的记录，不声称该既有压缩包包含这段事后记录。

## 未完成的边界

- 没有从头下载 30 个完整开放社区，没有新增真实模型请求或执行 180-run 效果评测。
- 未打开 sealed community 45；旧冻结失效仍是 readiness failure。
- 未执行远端 GitHub Actions，本地检查不等于 hosted CI 全绿。
- 根代码许可证、作者信息、公开上传、正式 Demo CFP、非作者试演及真人旁白等仍未完成。
  内部预览可复现不等于完成投稿。
