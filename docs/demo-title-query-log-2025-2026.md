# Demo-title audit query log, 2025--2026

检索日期：2026-09-06（Asia/Shanghai）。

## 范围与纳入规则

- “近两年”按会议年份 2025 和 2026 处理。
- 纳入 VLDB、SIGMOD、ICDE 官方 accepted list、program 或 proceedings 中明确属于 Demo / Demonstration Track 的论文。
- 不按标题中的 `demo` 字样反推 track，也不把 tutorial、industry、workshop、poster 或 research paper 混入。
- 2025 和 2026 分别得到 150、151 篇，共 301 篇；完整标题无精确重复。

## 官方来源

| Venue-year | 官方来源 | 条数 | 抽取方式 |
|---|---|---:|---|
| VLDB 2025 | [PVLDB Vol. 18 No. 12 front matter](https://www.vldb.org/pvldb/vol18/FrontMatterVol18No12.pdf) | 55 | `Demonstrations` 与 `Tutorials` 之间的正式目录；卷首同时报告 150 投、55 录 |
| VLDB 2026 | [Accepted demonstrations](https://www.vldb.org/2026/demonstrations.html) | 92 | `h2.demo-paper-title` |
| SIGMOD 2025 | [Accepted Demo Papers](https://2025.sigmod.org/sigmod_demo_papers.shtml) | 69 | `#maincontent li b`；[chairs' welcome](https://2025.sigmod.org/SigmodPods25-welcome.pdf) 同时报告 171 投、69 录 |
| SIGMOD 2026 | [Accepted Demo Papers](https://2026.sigmod.org/sigmod_demos.shtml) | 39 | `#maincontent li strong` |
| ICDE 2025 | [Demonstration Papers](https://ieee-icde.org/2025/demonstrations/) | 26 | 官方 program 的 Group A/B/C |
| ICDE 2026 | [Accepted Demo Papers](https://icde2026.github.io/demo-papers.html) | 20 | `.paper-list .title` |

逐题清单见 [demo-title-corpus-2025-2026.md](demo-title-corpus-2025-2026.md)，可重复采集和计数检查见 [collect_demo_titles.py](../scripts/collect_demo_titles.py)。VLDB 2025 的 PDF 目录和受 Cloudflare 保护的 ICDE 2025 页面在脚本中保留经人工逐项核对的静态转录；另四个列表由脚本实时解析。脚本对六个预期条数做硬检查，任一列表变化即报错。

## 学术元数据交叉核验

官方 program 是 track membership 的事实源；通用文献数据库通常不保存 Demo/Industry/Tutorial 轨道标签，因此只用于核验最接近本选题的论文标题、DOI、年份和 venue，不用于决定是否纳入语料。

### Crossref

数据库：Crossref REST API。

Endpoint pattern：

```text
GET https://api.crossref.org/works/{url-encoded DOI}?mailto=demo-audit@example.com
```

查询 DOI：

- `10.1145/3722212.3725106` — Graphy'our Data
- `10.1145/3722212.3725134` — Sentence to Model
- `10.14778/3750601.3750647` — QueryArtisan
- `10.14778/3750601.3750681` — TableCopilot

四个请求均返回 HTTP 200，标题和正式年份与官方列表一致。完整未裁剪响应见 [demo-title-crossref-raw.json](demo-title-crossref-raw.json)。

### OpenAlex

数据库：OpenAlex Works API。

Endpoint pattern：

```text
GET https://api.openalex.org/works/https://doi.org/{DOI}?select=id,doi,title,publication_year,primary_location,authorships
```

对上述四个 DOI 的请求均返回 HTTP 429：当前匿名账户的当日查询预算为 0。未用 OpenAlex 数据支持任何结论；完整错误响应见 [demo-title-openalex-raw.json](demo-title-openalex-raw.json)。

没有查询 Semantic Scholar、PubMed、arXiv API、CORE 或其他聚合库来拼接完整列表，因为这些数据库不可靠地编码 conference track，反而会给“所有 Demo titles”引入漏项或混项。对近邻论文内容的核验使用作者 PDF、PVLDB PDF 或 arXiv 页面，并在分析文档中逐项链接。

## 限制

- 关键词统计只读标题，类别允许重叠；它适合观察 program 的措辞与拥挤区，不足以证明研究空白或因果性的投稿 taste。
- `0 title hits` 只表示标题没有使用该词，不表示论文正文没有相应机制。
- 2026 列表按 2026-09-06 可见的官方页面冻结；若官网之后做勘误，应重跑采集脚本并复核静态转录。
