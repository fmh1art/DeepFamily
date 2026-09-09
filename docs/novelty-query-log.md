# Novelty stress-test query log

Query date: 2026-09-06 (Asia/Shanghai).

This log records the academic API calls used for the ClaimDelta novelty stress test. It preserves the response status and the metadata fields needed to reproduce the lookup. Long abstract text from the successful response is summarized in `novelty-stress-test.md` rather than duplicated here.

## Semantic Scholar

Endpoint:

```text
GET https://api.semanticscholar.org/graph/v1/paper/search/bulk
```

Parameters:

```text
query=("data agent" | "data analysis agent") + (provenance | lineage | attribution | traceable)
fields=paperId,title,year,publicationDate,venue,abstract,authors,externalIds,url,openAccessPdf
sort=publicationDate:desc
```

The API returned `total: 16`. The response envelope and the records used in the stress test were:

```json
{
  "total": 16,
  "token": null,
  "data": [
    {
      "paperId": "6c9bfda6edd351dabef9cee8b6db1c4215fbfcfd",
      "externalIds": {"ArXiv": "2608.26036", "CorpusId": 291371464},
      "url": "https://www.semanticscholar.org/paper/6c9bfda6edd351dabef9cee8b6db1c4215fbfcfd",
      "title": "Trace Integrity for LLM Data Agents: A Vision for Auditable Structured Reasoning in Real-World Systems",
      "venue": "",
      "year": 2026,
      "publicationDate": "2026-08-26"
    },
    {
      "paperId": "214d2650514e3593136789f47b2e7cadcb67a7e2",
      "externalIds": {"ArXiv": "2607.11019", "CorpusId": 290142749},
      "url": "https://www.semanticscholar.org/paper/214d2650514e3593136789f47b2e7cadcb67a7e2",
      "title": "QwenPaw-Data: Bridging Facts, Methodology, and Execution for Autonomous Enterprise Data Analytics",
      "venue": "",
      "year": 2026,
      "publicationDate": "2026-07-13"
    },
    {
      "paperId": "b4baee3901fc91cf9a4ab7fadfa705ef3be36ffb",
      "externalIds": {
        "DBLP": "journals/corr/abs-2606-01185",
        "ArXiv": "2606.01185",
        "DOI": "10.48550/arXiv.2606.01185",
        "CorpusId": 288862045
      },
      "url": "https://www.semanticscholar.org/paper/b4baee3901fc91cf9a4ab7fadfa705ef3be36ffb",
      "title": "\"Skill issues\": data-centric optimization of lakehouse agents",
      "venue": "arXiv.org",
      "year": 2026,
      "publicationDate": "2026-05-31"
    },
    {
      "paperId": "9a97b81baea2dfc1dae176d759fd929dc7953181",
      "externalIds": {
        "DBLP": "journals/corr/abs-2605-24183",
        "ArXiv": "2605.24183",
        "DOI": "10.48550/arXiv.2605.24183",
        "CorpusId": 288670667
      },
      "url": "https://www.semanticscholar.org/paper/9a97b81baea2dfc1dae176d759fd929dc7953181",
      "title": "AvalancheBench: Evaluating Enterprise Data Agents Through Latent World Recovery",
      "venue": "arXiv.org",
      "year": 2026,
      "publicationDate": "2026-05-22"
    },
    {
      "paperId": "0fc30d552b48b12817ba6ec4dfa9571b2a262b8d",
      "externalIds": {
        "DBLP": "journals/corr/abs-2511-02824",
        "ArXiv": "2511.02824",
        "DOI": "10.48550/arXiv.2511.02824",
        "CorpusId": 282748827
      },
      "url": "https://www.semanticscholar.org/paper/0fc30d552b48b12817ba6ec4dfa9571b2a262b8d",
      "title": "Kosmos: An AI Scientist for Autonomous Discovery",
      "venue": "arXiv.org",
      "year": 2025,
      "publicationDate": "2025-11-04"
    }
  ]
}
```

Four narrower relevance searches were then attempted:

```text
counterfactual provenance what-if data pipeline output changes
"multiverse analysis" data provenance workflow
data debugging alternative input versions output difference provenance
analytical claim sensitivity data source selection
```

All four calls returned the same raw response:

```json
{"message":"Too Many Requests. Please wait and try again or apply for a key for higher rate limits. https://www.semanticscholar.org/product/api#api-key-form","code":"429"}
```

After waiting five seconds, one combined query was retried once:

```text
data pipeline provenance what-if compare alternative outputs
```

The retry returned the same `429` JSON response. No further Semantic Scholar retries were made.

## arXiv Atom API

Endpoint:

```text
GET https://export.arxiv.org/api/query
```

Parameters:

```text
search_query=(all:"counterfactual provenance" OR all:"what-if provenance" OR all:"multiverse analysis" OR all:"data debugging") AND (cat:cs.DB OR cat:cs.HC OR cat:cs.AI)
start=0
max_results=25
sortBy=relevance
sortOrder=descending
```

The request failed before an Atom response was received:

```text
curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to export.arxiv.org:443
```

The fallback used the primary arXiv abstract pages for the relevant records:

- `https://arxiv.org/abs/2608.26036`
- `https://arxiv.org/abs/2607.11019`
- `https://arxiv.org/abs/2605.24183`
- `https://arxiv.org/abs/2606.01185`
- `https://arxiv.org/abs/2511.02824`

## Additional primary sources

- Boba author/project page: `https://idl.uw.edu/papers/boba`
- Boba paper: `https://idl.cs.washington.edu/files/2021-BobaMultiverse-VAST.pdf`
- Approximation and Progressive Display of Multiverse Analyses: `https://arxiv.org/abs/2305.08323`
- Dagger Demo paper: `https://www.vldb.org/pvldb/vol13/p2993-rezig.pdf`
- Transaction reenactment Demo paper: `https://www.vldb.org/pvldb/vol10/p1857-niu.pdf`
