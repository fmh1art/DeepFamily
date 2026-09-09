# Metadata query log

Query date: 2026-09-06 (Asia/Shanghai). These responses are retained to make the literature lookup auditable. OpenAlex results were not used because the API returned a quota error.

## Crossref

Endpoint template:

```text
https://api.crossref.org/works?filter=doi:<DOI>&select=DOI,title,author,published,container-title,type,URL&rows=1
```

The three PVLDB DOI queries returned the following raw response shape:

```json
{"status":"ok","message-type":"work-list","message-version":"1.0.0","message":{"facets":{},"total-results":0,"items":[],"items-per-page":1,"query":{"start-index":0,"search-terms":null}}}
```

DOIs with this response:

- `10.14778/3827998.3828105` — BobFlow
- `10.14778/3827988.3828086` — Carnot
- `10.14778/3827998.3828066` — Guixu

DeepEye raw response (the query used the `select` fields above):

```json
{"status":"ok","message-type":"work-list","message-version":"1.0.0","message":{"facets":{},"total-results":1,"items":[{"DOI":"10.1145/3788853.3801612","title":["DeepEye: A Steerable Self-driving Data Agent System"],"author":[{"given":"Boyan","family":"Li","sequence":"first"},{"given":"Yiran","family":"Peng","sequence":"additional"},{"given":"Yupeng","family":"Xie","sequence":"additional"},{"given":"Sirong","family":"Lu","sequence":"additional"},{"given":"Yizhang","family":"Zhu","sequence":"additional"},{"given":"Xing","family":"Mu","sequence":"additional"},{"given":"Xinyu","family":"Liu","sequence":"additional"},{"given":"Yuyu","family":"Luo","sequence":"additional"}],"published":{"date-parts":[[2026,5,30]]},"container-title":["Companion of the International Conference on Management of Data"],"type":"proceedings-article","URL":"https://doi.org/10.1145/3788853.3801612"}],"items-per-page":1,"query":{"start-index":0,"search-terms":null}}}
```

SemDisc raw response (Crossref preserves small-cap title markup in its source metadata):

```json
{"status":"ok","message-type":"work-list","message-version":"1.0.0","message":{"facets":{},"total-results":1,"items":[{"DOI":"10.1145/3788853.3801604","title":["SemDisc: An End-to-End Query-by-Example Semantic Join Discovery System"],"author":[{"given":"Mir Mahathir","family":"Mohammad","sequence":"first"},{"given":"El Kindi","family":"Rezig","sequence":"additional"}],"published":{"date-parts":[[2026,5,30]]},"container-title":["Companion of the International Conference on Management of Data"],"type":"proceedings-article","URL":"https://doi.org/10.1145/3788853.3801604"}],"items-per-page":1,"query":{"start-index":0,"search-terms":null}}}
```

## OpenAlex

Endpoint template:

```text
https://api.openalex.org/works/https://doi.org/<DOI>?select=id,doi,title,publication_year,primary_location,authorships
```

All five queries returned the same raw error form (the numeric retry interval varied):

```json
{"error":"Rate limit exceeded","message":"Insufficient budget. This request costs $0.0001 but you only have $0 remaining. Resets at midnight UTC.","costUsd":0.0001,"dailyRemainingUsd":0,"prepaidRemainingUsd":0,"creditsRequired":1,"creditsRemaining":0,"onetimeCreditsRemaining":0}
```

