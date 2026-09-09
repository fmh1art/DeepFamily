# 阿里云 ECS 部署边界

当前容器拓扑可以部署为研究 Demo，但公开上线前仍需完成域名、TLS、访问控制和
中国大陆网站备案等外部工作。它们与应用内的“用户注册”不是同一件事。本目录提供的
配置只覆盖部署边界，不假装已经完成实名、证书签发或云控制台配置。

## 两种互斥入口

### A. 单台 ECS + 宿主 Nginx（默认、推荐）

```text
Internet
  -> ECS security group :80/:443
  -> host Nginx (TLS + actual-client-IP rate limit)
  -> 127.0.0.1:8080
  -> container Nginx -> private FastAPI
                     -> read-only demo data
                     -> named runtime volume
```

保持 `ASKDU_BIND_ADDRESS=127.0.0.1`。宿主入口直接看到客户端地址，因此
`host-nginx.conf.example` 以 `$binary_remote_addr` 做真实的逐 IP 限流，并覆盖而不是相信
客户端传来的 `X-Forwarded-For`。容器内 Nginx 仍保留第二层上限；经过宿主反代后，它看到的
是 Docker/宿主代理地址，所以这层是 defense-in-depth 的全局上限，不能冒充逐客户端配额。

### B. Alibaba Cloud ALB + ECS 私网端口

```text
Internet :443
  -> ALB (TLS + WAF/listener client controls)
  -> ECS_PRIVATE_IP:8080 (source restricted to the ALB-documented Local IP range)
  -> container Nginx -> private FastAPI
```

将 `ASKDU_BIND_ADDRESS` 设为该 ECS 网卡的**精确私网 IP**，不能使用 `127.0.0.1`，也不能使用
`0.0.0.0`/`::`。8080 的安全组来源必须按该 ALB 实例详情中的 Local IP/交换机网段配置；
不同代际实例的来源范围不同，不能猜测或向公网开放。实际客户端级限流必须在 ALB/WAF 完成，
除非另行配置只信任 ALB 地址段的 real-IP 解析。不要无条件信任公网 `X-Forwarded-For`。
两种入口都不公开 FastAPI、数据库、对象存储或未来 worker 的端口。

`ecs-preflight` 用 `ECS_INGRESS_MODE=host-nginx|alb` 明确区分二者：host 模式只接受 loopback，
ALB 模式只接受具体私网地址，从而阻止“ALB 指向 loopback”与“临时开放 wildcard 8080”两类
难以复核的配置。

## 阿里云控制台与备案边界（2026-09-06 核验）

- 阿里云当前安全组指南允许公网网站按需开放 80/443，但建议 SSH/管理端口仅允许可信 IP；
  8080 等内网业务端口应以源安全组授权。参见[使用安全组](https://help.aliyun.com/zh/ecs/user-guide/start-using-security-groups)。
- ALB 到后端 ECS 的转发与健康检查来源应按实例代际核对：阿里云当前文档说明，升级后的实例
  使用 ALB 所在交换机网段的 Local IP，旧实例使用其列明的内部地址段。参见
  [创建和管理服务器组](https://help.aliyun.com/zh/slb/application-load-balancer/create-and-manage-a-server-group)。
- 单机方案让宿主 Nginx 作为 SSL 终端，与阿里云的
  [ECS Nginx HTTPS 指南](https://help.aliyun.com/zh/ecs/user-guide/ssl)一致。证书及私钥只放在
  ECS 的 `/etc/nginx/certs/`（或同等私有路径），不进入仓库、镜像或 artifact。
- 若网站放在中国内地服务器，公开服务前须先完成 ICP 备案；阿里云当前个人网站指南还要求
  开站后 30 日内办理公安联网备案。域名需先实名并与备案主体一致。参见
  [个人网站备案快速入门](https://help.aliyun.com/zh/icp-filing/basic-icp-service/getting-started/quick-start-for-icp-filing-for-personal-websites)。
- 租 ECS 时不要默认任何实例都可用于备案。阿里云当前列出的 ECS 条件包括中国内地节点、
  包年包月累计大于 3 个月和公网带宽；免费试用与按量付费实例不直接满足该服务码条件。
  使用 SLB 时，备案填写其后端 ECS IP，而不是 SLB 公网 IP。下单前以
  [备案前期准备](https://help.aliyun.com/zh/icp-filing/basic-icp-service/user-guide/overview)的最新页面为准。

## 上线前必须完成

1. 为 ECS 使用非 root 运维账户、SSH key、最小安全组和系统补丁；公网只按所选入口开放端口。
2. 将域名解析到公开入口并配置 HTTPS；若服务器位于中国大陆，按阿里云和
   当地要求完成 ICP 备案/公安备案。代码无法代替这些实名行政流程。
3. 在 ECS secret manager、systemd environment file 或 CI/CD secret 中注入
   已轮换的 LLM key。浏览器 bundle、Git、Docker image 和日志中都不得出现 key；
   聊天中曾出现的 credential 不得继续用于公网部署。
4. 保持 `docs/licensing-and-redistribution.md` 已审计的 download-only 数据策略。
   CoDA-Bench 的总卡片为 MIT，不自动覆盖每个原始 Kaggle 数据集的再分发条件；
   上线前还要按最终固定 revision 复核一次。
5. 推荐的宿主 Nginx 已有基础 per-IP rate/connection limit，API 也限制并发 run；公开的
   model 模式仍要增加身份级配额、集中审计日志、监控和离线 replay。公开 Demo
   不应允许 API 进程直接执行模型生成的代码。当前模型路径仅执行本地校验过的
   白名单 dataframe DSL；若未来加入任意代码生成，必须迁入隔离 worker。
6. Compose 已限制容器日志轮转，并为两个服务配置优雅停止窗口。仓库提供停机 runtime
   快照和仅空新卷恢复命令；上线前仍应接入主机磁盘告警、容器重启告警、`/readyz`
   外部探测、备份加密与异地复制，并保留上一版 image digest 与私有配置以便回滚。
7. 公网配置必须显式设置 `ASKDU_RUN_RETENTION_HOURS=1..720`（示例为 24）。页面会在提交前
   显示该值，`/readyz` 健康探测驱动限频的过期清理，完成态可主动删除当前活动 runtime
   中的 state、物化表、artifact 和 report。离线快照不在该删除事务内，必须另定保留与销毁策略。

## 应用内用户注册

初步原型没有开启用户账户，因为论文核心路径应先在无需登录的受控 Demo
环境中验证。加入注册时应作为独立 identity 模块实现，并至少具备：邮箱验证、
Argon2id 密码哈希、短时 access token、可撤销 refresh session、CSRF/速率限制、
隐私政策，以及把现有匿名删除升级为带所有权校验的账户级删除。当前 opaque run ID 同时允许
读取和删除对应 run，只是 bearer capability，不是用户身份。身份模块只授予 environment/run 权限，不接受用户
提供服务器文件路径或 LLM credential。

## 当前启动

以下命令假设已经把审核后的 release checkout/artifact 放在 `/opt/askdu`，并由专用的非 root
部署账户维护。先从该目录建立一个仓库外、仅部署账户可读的私有配置文件：

```bash
askdu_deploy_user="$(id -un)"
askdu_deploy_group="$(id -gn)"
sudo install -d -m 700 -o "$askdu_deploy_user" -g "$askdu_deploy_group" /etc/askdu
sudo install -m 600 -o "$askdu_deploy_user" -g "$askdu_deploy_group" \
  infra/ecs/production.env.example /etc/askdu/askdu.env
sudoedit /etc/askdu/askdu.env
```

至少替换 `demo.example.com`，并让 `ASKDU_CORS_ORIGINS` 使用完整 HTTPS origin、
`ASKDU_TRUSTED_HOSTS` 包含不带 scheme/port 的域名。若启用 agentic planner，只把轮换后的
API key 写入这个 `0600` 文件或 secret manager，不得回填仓库模板。
保留策略也必须显式保持在 1--720 小时；模板的 24 小时适合匿名预览，但上线负责人仍需按
实际隐私政策确认。严格预检拒绝缺失、0、非整数或超过 720 小时的值。

即使使用无 secret 的 registry 模式，严格预检也要求真实 env 文件位于仓库外且权限不超过
`0600`，避免以后切换 model 模式时沿用错误边界。仓库中可重复的结构检查不会读取 secret，
也不会要求外部数据；它使用 Docker 中已按 digest 固定的 Nginx 和一个临时自签证书做真实
语法解析，因此主机还需提供 OpenSSL。`--allow-example-origin` 只允许这一个受检模板，不能用来
绕过真实预检：

```bash
make ecs-config-check
```

### A. 单机宿主 Nginx 安装与预检

取得证书后，复制并编辑宿主入口。配置中的域名、证书路径必须全部替换：

```bash
askdu_domain="demo.your-real-domain.tld"
askdu_fullchain="/absolute/private/path/fullchain.pem"
askdu_privkey="/absolute/private/path/privkey.pem"
sudo install -d -m 700 "/etc/nginx/certs/$askdu_domain"
sudo install -m 600 "$askdu_fullchain" "/etc/nginx/certs/$askdu_domain/fullchain.pem"
sudo install -m 600 "$askdu_privkey" "/etc/nginx/certs/$askdu_domain/privkey.pem"
sudo install -m 644 infra/ecs/host-nginx.conf.example /etc/nginx/conf.d/askdu.conf
sudoedit /etc/nginx/conf.d/askdu.conf
```

真实 ECS 启动前运行严格预检：

```bash
make ecs-preflight \
  ECS_ENV_FILE=/etc/askdu/askdu.env \
  ECS_PUBLIC_ORIGIN=https://demo.your-domain.example \
  ECS_INGRESS_MODE=host-nginx \
  ECS_HOST_NGINX_CONFIG=/etc/nginx/conf.d/askdu.conf
```

严格预检会解析最终 Compose 配置但不输出环境值，并拒绝示例域名、与入口模式不一致的绑定、
缺少域名的 Host/CORS 列表、公开 API 端口、可写容器根目录、未降权容器、可写源数据挂载，
仓库内或权限过宽的 env 文件，以及不能覆盖伪造 forwarding header/缺少外层限流的宿主配置。
它还会检查 1--720 小时 run retention，并逐个校验部署所需的 10 个 CSV 与固定 SHA-256 清单，因此应在
`fetch_research_assets.sh` 成功后运行。

```bash
./scripts/fetch_research_assets.sh --all
docker compose --env-file /etc/askdu/askdu.env build
sudo install -m 644 infra/ecs/askdu-compose.service.example \
  /etc/systemd/system/askdu-compose.service
sudo systemctl daemon-reload
sudo systemctl enable --now askdu-compose.service
curl --fail --noproxy '*' http://127.0.0.1:8080/readyz
sudo nginx -t
sudo systemctl reload nginx
curl --fail https://demo.your-domain.example/readyz
```

systemd 的停止动作是 `docker compose stop web api`，不会执行 `down -v`，因此保留当前和旧的
runtime 卷。模板固定使用 `/opt/askdu` 与 `/etc/askdu/askdu.env`；若实际路径不同，应先编辑
unit 并人工复核。默认本地地址为 `http://127.0.0.1:8080`。生产域名、证书和数据库配置只能
放在 ECS 私有配置中，不能提交到仓库。

### B. ALB 预检

将 env 中的 `ASKDU_BIND_ADDRESS` 改为 ECS 实际私网 IP，并用下面的模式运行；不要传
`ECS_HOST_NGINX_CONFIG`：

```bash
make ecs-preflight \
  ECS_ENV_FILE=/etc/askdu/askdu.env \
  ECS_PUBLIC_ORIGIN=https://demo.your-domain.example \
  ECS_INGRESS_MODE=alb
```

随后在 ALB 443 listener 安装证书、将后端健康检查指向 `/readyz`，并把 ECS 8080 入站规则
限制为控制台所示的 ALB Local IP/交换机源范围。ALB/WAF 的客户端级限流、访问日志与告警
属于云侧配置，仓库预检只能拒绝错误绑定，不能伪造云控制台已经配置完成。

默认 Compose 使用无需模型的 `registry` 模式。ECS 上启用研究主路径时设置
`ASKDU_CATALOG_MODE=coda_open_release`、`ASKDU_PLANNER_MODE=agentic`，并在权限为 `0600` 的
私有 environment/secret 中只填写轮换后的 `ASKDU_LLM_API_KEY`。endpoint、model、API style、
auth 与 token 字段已固定为项目指定的 ModelHub profile；正式模式发生漂移会拒绝启动，
`ASKDU_LLM_ALLOW_TEST_PROVIDER=true` 也会被 ECS preflight 拒绝。这些配置不会由浏览器请求
覆盖或通过环境摘要接口返回。默认不继承 ECS 进程代理；只有经过审计的可信代理才设置
`ASKDU_LLM_TRUST_ENV_PROXY=true`。

上线前先在本机或隔离 staging 运行 `make provider-contract`，再用轮换后的 secret 运行
`make provider-smoke`。后者被代码固定在公开 `coda-community-43`，不会触碰 held-out。

上线域名还必须加入 `ASKDU_TRUSTED_HOSTS`。若前面使用 ALB/CDN，应在可信入口做客户端级
访问控制；只有明确固定代理网段后才可在后端配置 real-IP 解析，不能无条件信任公网请求传入的
`X-Forwarded-For`。

## Runtime 快照、升级与回滚

runtime volume 保存问题、执行状态、物化表、analysis artifact 和报告，必须按私有数据处理。
在线服务按 `ASKDU_RUN_RETENTION_HOURS` 清理活动卷，页面删除也只作用于该活动卷；二者都不会
追溯或修改先前生成的快照。因此备份必须有独立的保留/销毁期限，且用户可见政策不能把活动卷
删除误述为所有备份副本已消失。快照工具不会把它加入 Git
或公开 artifact，也不提供加密；目标目录必须位于仓库外且不能向 group/other 开放。先停止
Web/API，避免一边写入一边备份：

```bash
docker compose --env-file /etc/askdu/askdu.env stop web api
sudo install -d -m 700 -o "$USER" -g "$(id -gn)" /var/backups/askdu
make ecs-runtime-backup \
  ECS_ENV_FILE=/etc/askdu/askdu.env \
  RUNTIME_BACKUP_DIR=/var/backups/askdu
```

命令使用无网络、只读根文件系统、无 Linux capabilities 且不携带应用环境变量的 API image
读取卷；归档内含排序后的精确目录/文件 census、每文件大小和 SHA-256。输出归档与 checksum
均为 `0600`，创建后会立即自验。应再把二者加密复制到独立存储，并定期做实际恢复演练。

恢复不会清空或覆盖任何现有卷。显式提供记录的摘要和一个不存在的新卷名：

```bash
make ecs-runtime-restore-new-volume \
  ECS_ENV_FILE=/etc/askdu/askdu.env \
  RUNTIME_SNAPSHOT_ARCHIVE=/var/backups/askdu/<snapshot>.tar.gz \
  RUNTIME_SNAPSHOT_SHA256=<recorded-sha256> \
  RUNTIME_RESTORE_VOLUME=askdu-runtime-restore-YYYYMMDD
```

私有 `0600` 文件通过 stdin 进入一次性 staging volume，无需放宽宿主权限。恢复器拒绝链接、
特殊文件、路径穿越、重复成员、census/digest 漂移和非空目标；完成后从新卷重新生成快照，
必须与原归档逐字节一致。随后：

1. 在 `/etc/askdu/askdu.env` 把 `ASKDU_RUNTIME_VOLUME_NAME` 改为新卷名；
2. 运行 `make ecs-preflight ...`，再用相同 env file 启动 Compose；
3. 验证 `/readyz`、旧 run 和新 run；
4. 保留旧卷。若升级失败，停止服务、把卷名切回旧值并重新启动即可回滚。

不要自动删除旧卷。确认新版本、异地快照和回滚演练均通过后，再由运维人员针对一个明确卷名
单独制定清理窗口。

不接触真实 runtime 即可复现同一 Docker 边界的正向和拒绝路径；该目标只创建带随机后缀的
临时卷，并在退出时清理：

```bash
make ecs-runtime-snapshot-smoke
```

## 依赖安全核查

在联网的 staging 环境运行：

```bash
make dependency-audit
```

该目标从固定的 `uv.lock` 导出带哈希的生产依赖，以固定的 `pip-audit 2.10.1` 分别在
Python 3.10.20（实验环境）和 Python 3.12 标记环境（与生产镜像的 3.12.14 minor 版本一致）
中查询漏洞记录，并对前端生产
依赖运行 `npm audit --omit=dev`。2026-09-06 的本地执行结果均为未发现已知漏洞。它只是
依赖数据库在执行时刻的快照，不覆盖基础镜像、OS 包、错误配置、业务逻辑或许可证兼容性；
公网部署前和每次依赖升级后都必须重新运行，并另行扫描最终容器镜像。
