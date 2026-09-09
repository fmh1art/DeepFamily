# Question-only positioning query log

Query date: 2026-09-06 (Asia/Shanghai).

This log records the academic lookup attempts used to refine the question-only analytics positioning. It complements `novelty-query-log.md`; the purpose is reproducibility, not a systematic literature review.

## Semantic Scholar Graph API

Endpoint:

```text
GET https://api.semanticscholar.org/graph/v1/paper/search
```

First query:

```text
query=autonomous data analysis agent data discovery preparation report
limit=10
fields=paperId,title,year,authors,venue,externalIds,url,abstract
```

The request yielded no response body after approximately 30 seconds. A status-only diagnostic query was then made with:

```text
query=autonomous data analysis agent
limit=1
fields=paperId,title,year
```

Raw HTTP status and response metadata:

```text
HTTP/1.1 429
Content-Type: application/json
x-amzn-ErrorType: TooManyRequestsException
```

After the required retry interval, one retry used:

```text
query=Data Agents Levels State of the Art and Open Problems
limit=5
fields=paperId,title,year,authors,venue,externalIds,url,abstract
```

Raw response:

```json
{"message":"Too Many Requests. Please wait and try again or apply for a key for higher rate limits. https://www.semanticscholar.org/product/api#api-key-form","code":"429"}
```

No further Semantic Scholar retries were made. Relevant papers were verified through their official arXiv, ACL Anthology, VLDB/PVLDB, or project pages instead.

## arXiv Atom API

Endpoint attempted:

```text
GET https://export.arxiv.org/api/query
```

Parameters:

```text
search_query=all:"autonomous data analysis"
start=0
max_results=10
sortBy=submittedDate
sortOrder=descending
```

Raw transport error:

```text
curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to export.arxiv.org:443
```

The Atom endpoint was not retried. Official `arxiv.org/abs/...` and `arxiv.org/html/...` pages were used as the fallback.

## Web and primary-source queries

Searches included:

```text
"DataUnbound" data analysis system
"Question-Only Data Analysis"
"question-to-report" data analysis agent
2025 2026 autonomous data analysis agent data discovery preparation report
site:arxiv.org 2025 2026 autonomous data analysis data discovery preparation report agent
site:arxiv.org "Data-Free" model extraction distillation
2025 2026 LLM agent autonomous data source discovery uncurated files analysis report
site:arxiv.org/abs 2026 "data discovery" "data preparation" "data analysis" agent
"sufficiency-guided" data discovery
"analytical sufficiency" data discovery
"data sufficiency" agent analytics
"evidence gap" data discovery agent
```

The sources used in the positioning document were opened on primary or official pages:

```text
https://aclanthology.org/2026.acl-long.1556/
https://arxiv.org/html/2511.01625
https://arxiv.org/abs/2510.16872
https://arxiv.org/abs/2602.04261
https://arxiv.org/abs/2604.27695
https://arxiv.org/abs/2607.11019
https://arxiv.org/abs/2608.09532
https://arxiv.org/abs/2608.31076
https://arxiv.org/abs/2011.14779
https://vldb.org/2026/demonstrations.html
```

Key negative finding: exact searches did not establish `Question-Only Analytics` as a standard academic term, while `data-free` is already widely used in model extraction/distillation for settings without original or surrogate data. This supports using the former as a carefully defined problem label and avoiding the latter.
