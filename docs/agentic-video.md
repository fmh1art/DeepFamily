# 当前三阶段 Demo：历史真实运行回放视频

日期：2026-09-09。此视频是**内部无声审阅稿**，不是最终投稿视频，也不是新的一次模型运行。

## 直接查看

[播放 2 分 24 秒回放](../artifacts/demo/agentic-replay-tyI28z/walkthrough.mp4)。

该文件位于本机忽略目录，未公开上传。与它同目录的 `capture.json` 记录原始运行、来源记录、
采集脚本、当前演示面、服务实际提供的 JS/CSS、13 张画面及视频的 SHA-256。

| 时间 | 画面 | 要说明的机制 |
|---|---|---|
| 0:00–0:16 | 标题和实际问题输入 | 仅给“最适合移民的国家是哪一个”，未附文件、字段、分析维度或权重 |
| 0:16–0:36 | 根目录与第 5 个 Discovery hop | 30 个社区全景；当前跳转与历史路径；真实路径和 schema 检查 |
| 0:36–0:46 | Discovery 输入/输出 | 最终选中的 CSV，限定其 2020 年数据范围 |
| 0:46–1:00 | Preparation 输入/输出 | 完整 10 字段 schema、类型变化；明确标注只节选前 3 行和前 3 列的执行预览 |
| 1:00–1:10 | 算子树与节点检查 | 一条成功路径，4 个算子；该运行没有树回溯 |
| 1:10–1:22 | SQL 和对应执行结果 | 可检查的 Code–Execute 反馈；该运行没有 Debug |
| 1:22–1:48 | 报告摘要及两个维度章节 | 数据范围内的多维比较；可导航的证据引用 |
| 1:48–2:00 | 实际计算结果图 | 清晰呈现国家间的生活质量比较；完整界面还提供结果表 |
| 2:00–2:24 | 综合结论、局限和收尾 | 不自创万能权重，明确政策/资格等缺口；邀请查看运行证据 |

原始运行和五节报告来自 `run_e2f9348452df475c`，详见
[stage-io-validation.md](stage-io-validation.md)。保留原文和原值；没有翻译后替换模型正文，
没有补造失败分支或动画轨迹。画面是当前 UI 的 DOM 节选，按讲解顺序重新排版，停留时间由
脚本指定；**不能据此报告模型响应耗时、成功率或未见问题泛化能力**。

CoDA 网络中的连线表示目录归属和工具关注位置转移，不是语义相似度边。Discovery 画面省略
下方候选列表/部分 schema 面板以保持可读，省略范围写在画面上。图表画面省略重复的结果表；
准备预览明确标注节选范围，不把其余列截断后假称完整表格。

## 重新生成

前提：本机 agentic Web 已在运行、`frontend/dist` 与服务提供的构建一致、原始运行记录仍在，
已安装项目要求的 Node 24、前端依赖、Playwright Chromium，以及 `ffmpeg`/`ffprobe`。
这些原始运行文件不随内部源代码包分发，所以干净解压目录不具备回放的全部输入；脚本会失败，
不会为了补素材自动请求模型。

```bash
# 在项目根目录运行。只读取现有 loopback Web，拦截提交并返回已保存的运行。
# 不启动/停止 Compose，不调用真实模型；每次生成新的目录，保留旧视频。
make demo-video-agentic
```

使用不同本机端口时设置 `ASKDU_E2E_BASE_URL`。脚本拒绝公网地址、URL 凭据和非根路径，
屏蔽 Service Worker，拦截 run POST/poll，拒绝其他 run 请求和写操作。部署不是 agentic、
构建字节不同、原始记录摘要不符、浏览器报错、外层画布溢出或编码不符均会失败。
只有全部采集和编码检查通过才写 `capture.json`；失败目录只用于诊断，不作为已验收视频。

## 本次验收记录

- 视频：144.00 秒，1600 × 900，25 fps，H.264 / yuv420p，6,863,999 bytes，无音轨。
- SHA-256：`4e8cb2cf7f963e4e59a24725f28feb103e1918f5399729ebdd1098051199c50e`。
- 6 项请求隔离/画面边界测试通过；浏览器完成 13 场景断言，错误为 0，意外网络请求为 0。
- 原始运行 SHA-256 为 `a48471eb8791c103a81d1529e90d92063dd0f4fd3b08f07b5e218e493a50ba02`，
  没有改写。录制期间真实模型调用为 0，唯一提交被浏览器本地回放拦截。
- 独立 `check_demo_video.py --mode draft` 的格式、大小和时长门禁通过。画面经过逐场景目视复核；
  正式投稿仍须真人旁白、作者完整试听以及当年规则复核，不能以技术门禁代替。
- 对成片顺序解码并提取 13 个场景中点帧，过程没有解码错误；又独立复算视频、13 张源画面、
  采集源码、当前演示面和原始运行摘要，全部与 manifest 一致。
- `make quality` 通过：263 项后端测试、6 项新增 Node 检查，Ruff、mypy、TypeScript 和前端构建
  正常；仍有 2 条既有依赖弃用警告。论文截图和构建校验保持通过，无须重建或改写论文。
- 原有 `artifacts/demo/fallback-walkthrough.mp4` 保留，作为独立 registry 闭环/数据缺口材料；
  它不是当前 agentic 轨迹。8080 agentic 服务未重启或更换模式。

`make readiness-draft` 仍报告 **5 pending、1 fail**：作者事项、正式 CFP 与公开材料未完成，
旧评测冻结与当前实现不一致。没有因生成本视频而放宽这些检查。

## 作者旁白稿

这是供作者录音和修改的英文讲稿，不代表音轨已存在。可按照上表保留阅读停顿，总时长对齐
144 秒；录制一条连续音轨，不加未经授权的音乐。

> Ask, Don't Upload starts with one analytical question. The user provides no table,
> schema, preparation plan, dimensions, or weights. This walkthrough replays a saved
> real-model development run in the current interface. Its timing is editorial.
>
> Discovery begins inside the authorized data environment. All thirty open communities
> are visible. At the fifth recorded hop, the agent inspects a quality-of-life source.
> The current transition is emphasized, while earlier transitions remain visible.
>
> The selected output is a multi-indicator CSV from 2020. Preparation places the input
> and output schemas alongside the selected operators. The preview contains actual
> executed rows; only three rows and three columns are shown here for readability.
>
> The operator tree records a successful path through type conversion, null handling,
> sorting, and termination. This particular run does not demonstrate backtracking.
>
> Analysis exposes SQL compiled from the validated plan, followed by its execution
> result. There are ten code-and-execution pairs in the recorded notebook. No debugging
> occurred in this run.
>
> The final deliverable is a report. Its summary and five sections separate overall
> quality of life from purchasing power, safety, healthcare, costs, and other dimensions.
> Evidence links connect the discussion to computed results, and the chart makes one
> comparison easy to inspect.
>
> The conclusion remains conditional. Different priorities favor different candidates.
> These dated indicators do not determine current immigration eligibility or an
> individual's best destination. The report states those missing factors explicitly.
>
> Viewers can revisit discovery, inspect an operator or code cell, and follow report
> evidence. This selected development example is not an accuracy evaluation. A separate
> deterministic demonstration shows cross-stage repair and honest stopping.

录好后可以用现有合成器生成**另一个审阅文件**，不覆盖静音视频：

```bash
# 交互输入真实录音路径；不要把尖括号占位符粘贴进 shell。
read -r -p '作者录音文件的绝对路径: ' NARRATION_FILE
uv run --project backend python scripts/mux_demo_narration.py \
  --video artifacts/demo/agentic-replay-tyI28z/walkthrough.mp4 \
  --narration "$NARRATION_FILE" \
  --output artifacts/demo/agentic-narrated-review.mp4
```

合成器的 `submission` 名称仅指音视频技术检查。当前片尾仍写明 internal review、公开 artifact
待定，因此即使合成通过也不能直接称为最终投稿文件。最终版本须确认公开 URL、术语、素材
范围和旁白，重新生成后由两名作者完整复核。原 `make demo-video-narrated` 仍针对 70 秒
registry 视频，不要把此处的 144 秒音轨交给那个默认目标。
