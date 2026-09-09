# 真实模型开发案例与可引用边界

**后续更新：** 下文三条历史记录保持原样。另有未展开问题“最适合移民的国家是哪一个”的三次
开发检查，详见 [三阶段验证记录](stage-io-validation.md) 与
[逐文件摘要](../experiments/evidence/agentic-question-only-smoke-2026-09-09.json)。最终一次产生
80 行准备数据、10 个分析 artifacts 和 5 节报告；论文现采用这个 post-fix 案例。它仍不能证明
任意宽泛问题的成功率、非局部树回退或报告建议的现实适用性。

核验日期：2026-09-09（Asia/Shanghai）。本记录从当前运行服务读取已有终态，不新增模型调用。
结构化摘要见 [观察记录](../experiments/evidence/agentic-development-smoke-2026-09-09.json)。

## 证据来源

三个记录来自生产 Nginx/API 的 `GET /api/v1/runs/{run_id}`。观察记录保存终态、时间、
来源路径及内容摘要、各阶段数量、实际 operator、report 请求/响应摘要，并为完整 API 对象
计算 canonical JSON SHA-256。它不包含源表行、完整模型请求或凭据。完整 run 仍位于当前
runtime，可以在其被删除或过期前核对；摘要不能替代完整轨迹，哈希也不是外部签名。

核验时环境为 `coda-open-v1`、`planner_mode=agentic`，安装 30/30 个公开 community、
30,292 个文件，其中 16,315 个 CSV、17,207 个可读表格。数据 release revision 为
`63828a2b652e26a9770555a0cc41e6c8aafdb5d9`。所有模型阶段使用项目启动脚本指定的同一个
ModelHub endpoint / `gpt-5.5-2026-04-24`，没有加载支撑论文训练的模型。

## 三次开发运行

| Case / run ID | Discovery hops | Prep：校验拒绝 / 选中 | 执行表 | 分析产物 / notebook steps | 报告 |
|---|---:|---:|---|---:|---|
| SHSAT / `run_b2f30ee773c04f50` | 7 | 1 / 1 | 21 行 × 8 列 | 4 / 13 | 4 节英文报告 |
| 国家比较，修复前 / `run_0c6ac396182342db` | 5 | 3 / 1 | 80 行 × 10 列 | 10 / 25 | 终态 completed，但报告缺少可读排名证据 |
| 国家比较，修复后 / `run_23578ed4a53f46e3` | 5 | 3 / 1 | 80 行 × 10 列 | 11 / 27 | 5 节中文报告，含摘要、维度比较、综合结论和局限 |

SHSAT 问题与已开发的 task 959 相同，不属于新任务。其选中流程为
`SelectCol → CastType → Filter → SelectCol → CastType → Join → DropNulls → Terminate`，
使用 SHSAT registration 与 School Explorer 两个表。

国家比较两次使用相同的完整问题：

> 最适合移民的国家是哪一个？请从生活质量、安全、医疗、生活成本、购买力、通勤、污染和气候等可用维度进行比较，最后给出综合结论；如果没有指定权重，请明确说明。

这仍是只有问题的 task 输入，但问题已经明确给出多个比较维度，并要求披露权重。
不能据此声称系统已验证能从一句未展开的“最适合移民的国家是哪一个”自动推导全部维度。
两次都选中 `community_28/countries-dataset-2020/source/Quality of life index by countries 2020.csv`。
最终候选为 `CastType → DropNulls → Deduplicate → Terminate`，得到 80 行、10 列及五行 UI 预览。

## 修复前后的观察

修复前，表格产物在 report evidence packet 中被重复执行深度裁剪，模型读到 `[depth limit]`。
虽然运行状态是 completed，报告却无法引用具体国家排名，且在正文打印了内部 artifact ID。
该记录是一个产品缺陷案例，不能计作正确回答。

修复取消 packet 的重复裁剪，补充 artifact ID 不进入正文的约束与校验；对应回归用例验证
实际行值能进入 report 请求。重跑后，报告区分数据自带的生活质量综合排名与单维排名，
并说明数据年份、未给权重和未覆盖签证等维度。这里验证的是报告结构、执行产物可达性及
缺陷修复；不把这次输出当成当前移民政策或实际移民适宜性的权威判断。

## 论文和现场讲解必须保持的区别

- 三条记录是开发者选择、开发中修订后的 smoke；不是全部尝试的清单，没有预注册采样、
  重复试验或独立报告评分，不能计算模型准确率或总体成功率。
- Prep 的拒绝原因都是 `The model action did not match the bounded schema.`，发生在数据
  执行前。这些记录只有一个成功 candidate，不能证明真实模型执行了非局部树回退。
- 三条轨迹没有 `Debug` cell。Notebook 支持 Debug 的代码/测试证据与这三次运行是否触发
  Debug 是不同的事实。
- Report 的已知引用与覆盖检查可以拒绝不存在的 artifact，但不验证每句文字的语义蕴含、
  比较偏好或因果解释。报告 factuality 仍需单独评测。
- 原论文的 60 个 controller run 和 2 个跨社区 probe 都属于确定性注册模式，不能与这些
  agentic smoke 合并成效果表，也不能把它们的毫秒级延迟用于真实模型模式。

## 只读复核

服务保持启动且 run 尚未删除时，在项目根目录运行下列命令，可检查最新案例及其摘要：

```bash
curl --noproxy '*' --fail --silent --show-error \
  http://127.0.0.1:8080/api/v1/runs/run_23578ed4a53f46e3 \
  | uv run --project backend python -c '
import hashlib, json, sys
from pathlib import Path
d = json.load(sys.stdin)
observations = json.loads(Path("experiments/evidence/agentic-development-smoke-2026-09-09.json").read_text())
expected = next(r for r in observations["runs"] if r["run_id"] == d["run_id"])
payload = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
assert hashlib.sha256(payload).hexdigest() == expected["canonical_run_sha256"]
assert d["status"] == "completed"
assert len(d["report"]["sections"]) == expected["report_sections"]
print("PASS: persisted run matches the development observation.")
'
```
