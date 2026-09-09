# Ask, Don't Upload 可运行 Demo Runbook

本文档说明如何从仓库根目录启动、操作、验证和停止当前 `0.4.0` Web Demo。推荐流程使用
`coda-community-43` 的公开 pilot 与确定性 `registry` planner：不需要 GPU、外部 LLM、API
密钥或公网连接，适合开发验收和现场演示。

当前可演示的闭环是：

```text
Question -> ASC -> Discovery -> Preparation -> Analysis
                                      ^              |
                                      |  violation   |
                                      +-- Discovery -+
                                             |
                                   replay -> Report / Diagnosis
```

系统会自动完成数据发现、准备和分析。默认 `registry` pilot 展示从 Analysis 回到 Discovery、
换源后重放 Preparation/Analysis；真实 `agentic` 路径还允许 preparation candidate 在已执行
状态树上分支/回退，并在准备失败时重新打开 Discovery。后者尚未纳入冻结的论文效果数字，
演示时应把“工程能力”和“已评测结论”分开说明。

## 1. 演示模式

| 模式 | 是否需要外部 LLM | 输入范围 | 用途 |
|---|---:|---|---|
| `registry`（推荐） | 否 | 页面提供的 4 个已核验 pilot | 稳定复现系统机制、论文截图和现场演示 |
| loopback mock | 否 | 一条自由问题 | 验证浏览器、API、模型 transport、非法计划拒绝及有界纠正 |
| `model`（兼容） | 是 | 自由问题 | 单轮 declarative plan compiler；用于旧评测协议兼容 |
| `agentic`（研究主路径） | 是 | 自由问题 | 全公开 CoDA 池上的工具化 Discovery 与树式 Preparation/Analysis |

稳定现场演示可保持默认 `registry`；验证论文的新主路径时使用一键脚本的 `agentic` 命令，
不要手工拼装 provider 参数。

## 2. 一次性准备

### 2.1 基础要求

仅运行 Web Demo 需要：

- Docker Engine；
- Docker Compose v2；
- 首次获取公开 pilot 时需要 `hf`（Hugging Face CLI）和 `zstd`；
- 本机端口 `8080` 可用。

先确认命令存在：

```bash
docker --version
docker compose version
hf --version
zstd --version
```

运行测试、CLI 或实验时还需要仓库锁定的 Python 3.10.20、`uv 0.11.1` 和 Node.js
24.20.0；它们不是启动生产容器的必要条件。

### 2.2 获取公开 pilot 数据

在仓库根目录执行：

```bash
make pilot-assets
```

该命令只下载并解压公开的 `community_43` 与 `community_52`，并核对 archive 和逐 CSV
SHA-256。它可以重复运行；已存在且正确的数据会继续接受校验。

核心 Demo 不需要 `community_45`。不要为运行 Demo 执行 held-out 解盲命令，也不要查看、
列出或解压该社区。`make assets` 还会下载未解压的 held-out archive，因此这里只使用更窄的
`make pilot-assets`。

## 3. 启动默认 Web Demo

推荐直接使用一键脚本；默认配置无需创建 `.env`、激活 venv 或安装 host Node.js：

```bash
./scripts/run_demo.sh
```

脚本会校验公开 pilot（正确数据不会重复下载）、构建并启动 production-like Compose、等待
两个容器健康，再严格核对 `/readyz`。它固定使用 registry mode 和 loopback 入口，不读取
私有模型配置。

需要逐步排障时，等价的手动启动命令是：

```bash
docker compose up -d --build --wait
```

首次构建会花费较长时间；之后 Docker 会复用缓存。服务只绑定本机
`127.0.0.1:8080`，不会直接暴露到局域网或公网。

检查容器和服务：

```bash
docker compose ps
curl --noproxy '*' --fail http://127.0.0.1:8080/healthz
curl --noproxy '*' --fail http://127.0.0.1:8080/readyz
```

正常响应应包含：

```json
{"status":"ok","version":"0.4.0"}
{"status":"ready","version":"0.4.0","environment_id":"coda-community-43","csv_assets":10}
```

`/healthz` 只表示进程存活；开始演示前必须以 `/readyz` 为准，因为它还会加载授权 catalog
并检查数据环境。

打开浏览器：

```text
http://127.0.0.1:8080
```

页面右上角应显示：

```text
coda-community-43
10 discoverable assets (10 tabular) · registry planner
```

## 4. 推荐的浏览器演示流程

### 4.1 主场景：Join repair（task 959）

1. 在 **Verified pilots** 中选择 **959 — Join repair**。
2. 保留自动填入的分析问题；用户不需要上传文件、选择表、声明 schema 或指定 join path。
3. 点击 **Run hands-off analysis →**，也可以按 `Ctrl/Command + Enter`。
4. 等待状态变为 `completed`。
5. 按以下顺序检查页面：

| 页面区域 | 应看到的证据 | 要说明的机制 |
|---|---|---|
| Catalog provenance | 固定 revision/archive digest、10 个可发现 CSV | Discovery 发生在受审计的数据边界内 |
| Analytical Sufficiency Contract | 从问题编译出的可执行 obligations | 系统先定义“什么证据才足够” |
| Sources / initial state | 首先选择 140 行 SHSAT registration 表 | 初始发现结果可以被后续执行推翻 |
| Lifecycle trace | `missing_analytical_columns` 与 `Analysis ↶ Discovery` | 下游 violation 触发 typed upstream repair |
| Repair impact | 增加 1,272 行 School Explorer 来源，重放后 21/21 连接 | 修复不是 UI 动画，而是新的来源和物化状态 |
| Verified report | 三个 Pearson correlations：`0.434725`、`-0.513048`、`0.586734` | obligations 通过后才释放报告 |
| Selected claim lineage | Claim → executed artifact → materialized state → checksummed sources | 每个数值可回溯到执行证据 |

在报告区完成两项操作：

- 点击任一 grounded claim，检查右侧 lineage；推荐选择 **Black / Hispanic**。
- 点击 **Download report .md** 和 **Export evidence .json**。

Markdown 应与服务器保存的 report artifact 一致；JSON 是由公开 `RunState` allowlist 在浏览器
生成的 evidence bundle。两者都不包含源数据行或服务器 credential。

### 4.2 对照场景：Honest data gap（task 179）

1. 返回问题输入区，选择 **179 — Honest data gap**。
2. 点击 **Run hands-off analysis →**。
3. 终态应是 `data_gap`，页面显示 **The run stopped without a report**。

该场景证明系统不会在授权环境缺少必要来源时编造答案。`data_gap` 是正确终态，不是运行
故障。

### 4.3 可选对照

- **176 — Direct answer**：单来源直接完成，说明系统不会为了表演而强制 repair。
- **960 — Coverage repair**：先得到部分餐厅覆盖，再因缺少 McDonald's/Burger King 类别触发
  Discovery repair。

默认 registry 模式只承诺页面提供的已注册问题。任意其他问题可能返回
`capability_gap`；这也是显式诊断，而不是“任意问题均可完成”的证据。

## 5. 运行自动验收

### 5.1 完整浏览器 E2E

安装前端依赖和 Chromium 后执行：

```bash
make frontend-install
cd frontend && npx playwright install chromium-headless-shell && cd ..
make e2e
```

`make e2e` 会构建并启动生产 Compose，验证 repair、data gap、导出、删除、可访问性、键盘
操作和页面重排，并在成功或失败后执行 `docker compose down`。不要在正在进行的现场演示旁
并行运行它，因为它会停止同一个 Compose project。

### 5.2 不使用真实密钥的模型链路验收

```bash
make provider-contract
make provider-browser-smoke
```

第二条命令使用仅存在于 API 网络命名空间中的确定性 mock provider。首轮计划会故意引用
未授权 asset，本地校验必须在读取数据前拒绝；第二轮收到有界反馈后完成修正版计划和报告。
该测试验证 transport 与约束执行，不验证真实模型质量。

### 5.3 工程质量检查

如已安装锁定的 Python/Node 工具链：

```bash
make backend-sync
make frontend-install
make quality
```

当前基线为 155 个后端测试和 9 个同源浏览器 E2E；另含 Ruff、Mypy、TypeScript 与前端
production build。真实 provider 的效果不包含在离线测试数量中。

## 6. 运行真实 agentic pipeline

创建一个未提交、owner-only 的私有文件；只写一行 `ASKDU_LLM_API_KEY=<secret>`：

```bash
umask 077 && touch .env && chmod 600 .env
${EDITOR:-vi} .env
./scripts/run_demo.sh agentic
```

脚本完成四件事：检查私有文件权限；补齐并验证 30 个公开 CoDA community；固定
`coda_open_release + agentic`；构建、启动并检查 production-like Web/API。首次同步需要下载
45,593,031,762 bytes 压缩 archive，并需要 `uv`、`hf` 和 `zstd`。已完整安装后只做本地状态
检查，不重复下载。

所有 LLM action 固定使用：

```text
endpoint  https://aidp.bytedance.net/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview
model     gpt-5.5-2026-04-24
style     azure_chat
auth      api_key
```

正式模式若 endpoint、model、style、auth 或 token 字段漂移会拒绝启动。只有 loopback contract
test 有显式测试开关，ECS preflight 会拒绝该开关。Discovery、Preparation/Analysis planning
和 repair 共享同一个客户端；运行时不会加载三篇支撑工作的训练模型或 checkpoint。

提交前页面会披露 provider 边界：问题、catalog metadata、inspect 后最多五行有界 preview 和
本地执行观察会发送给上述 provider；完整数据文件、服务器路径、reference answer 和 credential
不会发送。所有模型 action 仍须通过本地 schema/asset/operator 校验。系统不会直接执行模型
返回的任意 Python、SQL 或 shell；Analysis 栏中的可见 SQL/Python 是从已验证 typed plan 由本地
compiler 生成并受限执行的。

### 6.1 Agentic 模式的浏览器讲解顺序

启动成功后，`/readyz` 应显示 `environment_id=coda-open-v1` 和 `csv_assets=16315`，页面右上角
只显示 `30,292 files` 和 `Agentic mode`；30/30 community、17,207 tabular assets、996 tasks 和
196 source datasets 收入技术详情，不再挤入顶栏。输入任意分析问题后，页面会先拿到 run ID，再在全宽的阶段工作台中实时
更新。工作台默认跟随当前 agent；点击顶部 `Discover / Prepare / Analyze` 可以回看任一阶段：

1. **Data discovery / CoDA-Bench path walk**：从 `Hop 00` 根目录开始，观察 search、目录进入、
   asset inspect、schema 和最终 selected evidence；被环境拒绝的跨 community 或未 inspect
   选择会作为 rejected hop 保留。
2. **Data preparation / DeepPrep operator tree**：共享 operator 前缀合并为 trie 节点，selected
   solution path 使用绿色高亮。点击节点查看输入/输出表和行数变化；参数与下方
   **Search history** 默认折叠，展开后每一
   turn 是一条完整 candidate chain，parent 指向旧 candidate 时就是实际 branch/backtrack。
3. **Data analysis / DeepAnalyze notebook loop**：按 `Analyze → Understand → Code → Execute` 查看
   紧凑的 notebook 步骤；参数化 SQL/受限 Python 和执行输出按需展开。若验证或运行失败，
   会先出现 `Debug`，再显示 safe
   fallback；最后才出现 artifact-linked `Answer` 与 `Report`。

完成后 Hero 和完整输入框自动收起，**Automatically generated analysis report** 移到三阶段回放之前。
顶部是 `Answer at a glance`，中部是 artifact 驱动的图表/报表；finding lineage、自动发现的
sources 和 Markdown 收入 **Evidence & lineage**。Contract、Lifecycle、Selected evidence、Catalog 与
Repair impact 收入 **Technical details**，需要时再展开。长拒绝原因默认折叠；运行期间删除按钮隐藏，避免后台
worker 与删除操作竞争，到达 completed/insufficient/failed 终态后才允许删除。

## 7. 停止、保留与清理

正常停止服务并保留已存 run：

```bash
./scripts/run_demo.sh stop
```

run 保存在命名 Docker volume 中，因此再次启动后仍可能存在。要删除单个完成态 run，优先
在页面点击 **Delete run**；删除前先下载需要保留的 report/evidence。

仅当确定要删除本机 Demo 的全部 run、物化表、analysis artifacts 和 reports 时，才执行：

```bash
docker compose down --volumes
```

该操作不可从活动 runtime 恢复，但不会删除下载到 `data/external/` 的公开 pilot。

## 8. 常见问题

### `/readyz` 无法访问

```bash
./scripts/run_demo.sh status
./scripts/run_demo.sh logs
```

确认两个容器均为 healthy、端口 8080 未被占用。修改端口时可在未提交的 `.env` 中设置
`ASKDU_HTTP_PORT`，然后按新端口访问。

### `/readyz` 报数据或摘要错误

重新运行：

```bash
make pilot-assets
```

不要手工修改 CSV 或绕过 SHA-256 检查。系统故意在来源不匹配时 fail closed。

### 页面没有 4 个 Verified pilots

查看页面右上角 planner；默认应为 `registry`。检查最终 Compose 配置：

```bash
docker compose config | rg ASKDU_PLANNER_MODE
```

如果意外处于 `model`，修改私有 `.env` 后重新创建容器。

### 自由问题得到 `capability_gap`

默认 registry 是已核验机制演示，不是开放域问答系统。改用页面提供的 task 959/960/176/179，
或在清楚其证据边界的前提下配置 model 模式。

### 下载或镜像构建受代理影响

数据下载脚本会先沿用当前代理；代理请求失败时只对该次请求移除代理变量并直接重试。不要把
代理凭据写入仓库配置。

## 9. 演示完成检查表

- [ ] `/readyz` 返回 `coda-community-43`、版本 `0.4.0` 和 10 个 CSV。
- [ ] task 959 显示 `Analysis ↶ Discovery`、21/21 join 与三项 correlation。
- [ ] claim lineage 能展开到 artifact、state 和两个 checksummed sources。
- [ ] Markdown report 与 evidence JSON 均可下载，且不包含 source rows。
- [ ] task 179 以 `data_gap` 停止且没有生成报告。
- [ ] agentic 模式真实问题显示逐跳 Discovery、带 parent 的 Prep branch/operator chain，以及
      Code/Execute（有故障时含 Debug）notebook cells。
- [ ] 演示结束后已执行 `make compose-down`。
- [ ] 讲解使用“verified pilot”，没有把开放域泛化或未冻结评测的 agentic Preparation repair
      说成已验证效果。

三分钟讲解顺序和失败 fallback 见 `docs/demo-rehearsal.md`；真实 ECS、TLS、安全组、ICP备案、
保留期和备份流程见 `infra/ecs/README.md`。
