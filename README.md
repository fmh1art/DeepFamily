# Ask, Don't Upload

**Ask, Don’t Upload: A Question-Driven Agentic System for Closed-Loop Data Discovery,
Preparation, and Analysis** 是面向 VLDB Demo Track 的研究原型。用户只给分析问题，系统在
服务器已有的授权数据池中发现和准备数据、执行分析，并返回有证据 lineage 的报告或明确的
数据/能力缺口。

## 运行

只想查看稳定、无需 LLM 的公开 pilot：

```bash
./scripts/run_demo.sh
```

运行真实 question-only agentic pipeline：先创建不提交到 Git 的 owner-only `.env`，只填入
`ASKDU_LLM_API_KEY`，再启动：

```bash
umask 077 && touch .env && chmod 600 .env
${EDITOR:-vi} .env
./scripts/run_demo.sh agentic
```

`agentic` 首次运行会下载、校验并解压 CoDA-Bench v1.0 的全部公开范围：30 个 community、
996 个任务对应环境、196 个 source dataset，压缩 archive 共 45,593,031,762 bytes。Sealed
evaluation community 不会被下载、扫描或加入 catalog。

当前完整安装实测得到 30,292 个可发现文件（148,210,537,081 bytes），其中 17,207 个是当前
executor 可读取的表格文件；“196 个 dataset”不是“只有 196 个文件”。首次安装应为 archive、
解压数据和临时空间预留至少约 210 GB。

成功后打开 <http://127.0.0.1:8080>。常用管理命令：

```bash
./scripts/run_demo.sh status
./scripts/run_demo.sh logs
./scripts/run_demo.sh stop
```

`agentic` 页面会实时显示一个三阶段工作台：CoDA-Bench 风格的逐跳 Discovery、DeepPrep 风格的
operator candidate tree/回退，以及 DeepAnalyze 风格的 `Analyze → Understand → Code → Execute
→ Debug → Answer → Report` notebook。每阶段都明确展示输入和输出：Discovery 的问题到相关
CSV 与 community 网络路径、Preparation 的输入/输出 schema 与执行表预览、Analysis 的 prepared
table 到多维度报告。展示内容来自持久化工具观察和真实执行结果，不是前端
动画或思维链。空首页只保留问题输入；完成后优先显示报告，参数、搜索记录、lineage 和
技术审计按需展开。

一键脚本固定把所有 LLM stage 指向：

```text
https://aidp.bytedance.net/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview
gpt-5.5-2026-04-24
```

Discovery、Preparation/Analysis planning、repair 和最终 report synthesis 共用一个服务端模型
客户端；系统不会加载
CoDA-Bench、DeepPrep 或 DeepAnalyze 的训练模型。论文/仓库只用于对齐数据组织、agent 流程、
tree reasoning 与 operator 语义。数值计算由本地受限 executor 完成。

## 验证

```bash
make backend-sync
make frontend-install
make quality
make e2e
make provider-contract
```

`provider-contract` 使用隔离 loopback provider，只验证 transport、统一模型边界、非法 action
拒绝和 secret 不落盘；它不代表真实模型质量。真实 API key 不得写进源码、README、命令行、
前端、镜像或日志。

## 主要目录

- `backend/src/askdu/`：catalog、agents、declarative executor、closed-loop repair 与报告。
- `frontend/`：亮色 Web UI、agent/lifecycle trace、source、report 与 lineage。
- `data/manifests/`：固定的公开 release、archive digest 与 provenance。
- `scripts/run_demo.sh`：唯一的本地启动/状态/日志/停止入口。
- `infra/ecs/`：后续阿里云 ECS、TLS、systemd、备份与恢复模板。
- `paper/`：Demo paper 初稿与图件。

详细说明：

- [CoDA-Bench / DeepPrep / DeepAnalyze 对齐与能力边界](docs/coda-deepprep-alignment.md)
- [界面模块](docs/demo-interface.md)
- [真实模型案例与证据边界](docs/agentic-smoke-evidence.md)
- [完整运行手册](docs/demo-runbook.md)
- [系统与部署架构](docs/architecture.md)
- [ECS 部署](infra/ecs/README.md)
