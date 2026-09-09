# Ask, Don't Upload — System Contract v0.4

Status date: 2026-09-09. This document is an implementation contract, not a
claim that every component is already complete.

## 1. Task boundary

Deployment configuration provides an authorized environment:

```text
E = (repositories, connectors, access policies, execution budget)
```

Each run accepts only:

```text
q = a natural-language analytical question
```

The run API must not require a dataset ID, filename, schema, join path,
preparation pipeline, analysis plan, or report outline. An environment ID is
deployment context, not a per-task data handoff.

The terminal output is exactly one of:

```text
EvidenceGroundedReport
InsufficiencyDiagnosis(kind = data_gap | capability_gap | budget_exhausted)
```

## 2. Analytical Sufficiency Contract

The question compiler produces typed obligations. Version 0.2 supports:

- `measure`: required target variables and derived quantities;
- `dimension`: grouping, comparison, and conditioning variables;
- `coverage`: entity, time, geography, and cohort coverage;
- `grain`: unit of observation required by the planned analysis;
- `join`: keys, cardinality, and minimum acceptable match coverage;
- `statistical`: sample-size and method prerequisites;
- `evidence`: report claims must link to executed artifacts.

Each obligation has a stable ID, status, severity, executable check when
available, and evidence references. A free-form LLM confidence score is not a
sufficient check.

### Compiler modes

- `registry` reproduces the reported deterministic task families.
- `model` supplies the question and authorized catalog metadata to a
  server-configured model. The response must validate as
`DeclarativeAnalysisPlan v1.0`; invalid JSON or any extra/unknown field is
rejected and may receive one bounded correction attempt.
- `agentic` gives a Discovery agent only the question and bounded filesystem
  actions, then gives a tree-based Preparation planner inspected sources and
  execution observations. Discovery, Preparation planning, and repair share the
  same server-side model client. A source must be inspected before selection,
  and selected CoDA sources must remain within one community. The validated plan
  then drives a local DeepAnalyze-style code/execute/report loop. The same
  configured model performs the final schema-constrained report synthesis; it
  does not load a paper-specific model.
The credential-free browser smoke additionally exercises this boundary with an
unauthorized first-round asset ID and a feedback-conditioned valid second plan;
it is integration evidence rather than model-quality evidence.

Provider transport is also server configuration. `azure_chat` parses the
`api-version` from the configured gateway URL and lets the Azure SDK append the
deployment/chat-completions route; it authenticates with `api-key` and omits the
unsupported explicit temperature field. `openai_base_url` and
`direct_chat_completions` remain test/general adapters. Transport performs bounded
retries, never returns provider error bodies to the browser, and does not inherit
proxy variables unless an operator explicitly opts in.

When a model-backed mode is active, the Web interface must disclose the provider
boundary before submission. The planner sends the analytical question plus
authorized catalog metadata (asset IDs, file names, relative paths, column
names, and byte sizes) to the server-configured provider. Agentic inspection
additionally sends at most five bounded preview rows per inspected source and
derived execution observations; legacy one-shot model mode does not. Complete
files and server credentials are excluded. This disclosure does not imply a
provider retention guarantee; the deployer must separately review the provider's
current data-handling terms.

Formal model-backed operation pins the complete ModelHub endpoint,
`gpt-5.5-2026-04-24`, `azure_chat`, `api_key`, and
`max_completion_tokens`. CoDA-Bench/DeepPrep/DeepAnalyze model weights are not
loaded. The only non-project provider path is an explicit loopback test override,
which production preflight rejects.

The plan references assets by catalog ID, not path. It may compose only typed
filter, projection, rename, cast, arithmetic/date derivation, missing-value,
deduplication, join, concatenation, aggregation, grouping, distinct, extreme,
correlation, share, and row-selection operations. Table names are immutable;
sources, operations, response size, bytes, rows, columns, joins, outputs, and
model attempts all have explicit limits. External model text is never evaluated
as Python, SQL, shell, an expression string, network target, or filesystem path.
After validation, the local compiler may generate visible parameterized SQL or
restricted Python cells from the typed plan. SQL executes only against an
in-memory SQLite copy of the selected materialized table; Python cells expose no
imports, filesystem, network, or general builtins and are checked against the
authoritative bounded dataframe executor.

### Registered catalog boundary

The two public pilot environments are bound to an immutable provenance
registry. At service construction, the registry validates the benchmark
revision, archive digest, per-CSV checksum-manifest digest, declared CSV count,
safe relative paths, source records, and download-only policy. Indexing reads
only authorized paths and CSV headers. Once Discovery selects a file, its full
SHA-256 is recomputed and must equal the registered digest before Preparation
can read it; a mismatch fails the run closed, while the public API returns only
a stable redacted error. CSV paths absent from a registered environment's
per-file manifest are excluded from discovery rather than inheriting a nearby
source record; conversely, a registered path missing from the mounted catalog
causes indexing/readiness to fail.

The resulting `DataAsset` carries the expected and observed digest, integrity
status, upstream dataset URL, provider/creator, and the source metadata's
declared-or-unknown license label. The same object feeds the API, source cards,
lineage, and generated Markdown report. An unregistered environment receives
no invented provenance or inferred license. Source bytes remain server-side:
the API has no source-data or bulk-download route.

### Portable report boundary

A completed run offers two browser-generated files. The Markdown file is the
persisted `Report.markdown` byte sequence, whose digest is already represented
by the report evidence object. The versioned `askdu.evidence-bundle/1.1` JSON
contains only an explicit top-level allowlist from the public run response: question,
ASC, catalog and source metadata, agent-action hashes, Discovery hops,
Preparation branches/operators, Analysis notebook cells, source decisions,
materialized-state metadata (excluding the bounded UI preview), analysis
outputs, violations, repair goals, lifecycle events, structured report sections,
report claims, and evidence references. It explicitly records that complete source rows and server
credentials are excluded while analysis outputs are included. A report export
therefore does not weaken the no-source-download boundary.

## 3. Lifecycle state

Every run persists a state graph rather than only a chat transcript:

```text
Run
 ├── Contract
 ├── AgentTrace[]
 ├── DiscoveryHop[]
 ├── PreparationAttempt[]
 │    └── PreparationOperatorTrace[]
 ├── AnalysisNotebookStep[]
 ├── SourceDecision[]
 ├── MaterializedState[]
 ├── AnalysisArtifact[]
 ├── SufficiencyViolation[]
 ├── RepairGoal[]
 ├── Report
 │    ├── ReportSection[]
 │    └── ReportClaim[]
 └── LifecycleEvent[]
```

Stable identities must preserve this chain:

```text
source_version_id -> prep_state_id -> artifact_id -> claim_id
```

For public progress, `POST /api/v1/runs?background=true` persists a pending run
and returns HTTP 202 immediately. A bounded in-process worker advances it; every
Discovery hop, Preparation attempt, and Analysis notebook cell is saved before
the next step. The browser polls the versioned GET endpoint. This is observable
progress, not a durable distributed queue; process loss can interrupt an active
run, while already persisted events remain inspectable.

## 4. Violation and repair semantics

A violation is structured as:

```text
SufficiencyViolation {
  violation_id,
  obligation_id,
  type,
  observed,
  expected,
  evidence_refs,
  responsible_stage,
  repair_goal_id
}
```

The target contract maps violations to executable repair goals as follows. The
registry pilots implement the Discovery-targeted rows and then rematerialize
Preparation and Analysis. Agentic mode additionally executes Preparation branches
from immutable parent states and can reopen Discovery after unresolved preparation
violations; that path is implemented but not yet part of frozen effectiveness results.

| Violation | Repair stage | Required state change |
|---|---|---|
| Missing measure/dimension | Discovery | Add or replace a source |
| Missing time/entity coverage | Discovery | Find supplementary coverage |
| Low join coverage/key mismatch | Discovery or Preparation | Replace source or join strategy |
| Wrong grain/type/unit | Preparation | Branch from an earlier materialized state |
| Unsupported analysis prerequisite | Analysis or Discovery | Change method or acquire data |
| Unsupported report claim | Analysis or Discovery | Produce evidence or remove/qualify claim |

Repeating the same prompt or regenerating code without changing a responsible
upstream decision does not count as closed-loop repair.

## 5. Stopping rule

A run succeeds only when all required obligations pass and every quantitative
claim links to an executed artifact. In agentic mode, every report section must
reference known executed artifacts and the section set must cover every published
artifact. Broad recommendation questions must preserve separate supported
dimensions and disclose missing dimensions or unspecified weighting; a one-metric
winner cannot be presented as universally best. A run abstains when the search or safety
budget is exhausted with unresolved required obligations. It must report the
missing data and checks attempted instead of fabricating a complete answer.

## 6. Pilot acceptance tests

The representative vertical slice uses CoDA-Bench task 959 in `community_43`:

1. Input is only the analytical question.
2. Progressive discovery first selects the SHSAT registration/tester table.
3. Analysis exposes missing demographic measures.
4. The violation targets Discovery, which adds the School Explorer table.
5. Preparation cleans percentage columns, filters Grade 8 and 2016, and joins
   `DBN` to `Location Code` while materializing join evidence.
6. Analysis computes three Pearson correlations from the resulting table.
7. The report links each number to the joined-table and correlation artifacts.

Tasks 175 and 955 exercise the same missing-column repair with count and
group-mean operators. Task 960 exercises a different violation family:
insufficient restaurant-category coverage causes Discovery to add a second
nutrition source. The complete `community_43` census then checks ten no-repair
paths and one honest local data-gap path. Two `community_52` tasks reuse the
same lifecycle interfaces for yearly aggregation and skewness analysis.

Passing these 17 registered, deterministic cases establishes implementation
plumbing and the controller mechanism. It does not prove open-ended language
or operator generality. Version 0.4 additionally tests the model compiler and
bounded executor end to end on a synthetic two-source sales fixture; this is an
implementation test, not effectiveness evidence. A prospective 13-task set was
selected before reading its questions or data and is governed by
`docs/heldout-protocol.md`. The exact reported-results boundary remains fixed
in `docs/evaluation.md`.

## 7. Public admission boundary

The single-node service distinguishes liveness from data readiness, validates
Host headers, accepts at most a configured number of concurrent runs, and maps
capacity rejection to HTTP 503 with `Retry-After`. Nginx adds per-IP request and
connection limits before work reaches FastAPI. Unexpected internal exceptions
remain in private persisted state but are redacted from both run-create and
run-fetch API responses.

The public deployment wrapper outside the frozen analytical source tree
publishes `run_retention_hours` and deletion support in the environment
response, and the Web client must display that policy before enabling question submission.
Local deployments may set retention to `0`; public ECS preflight requires a
bounded 1--720 hour value. `/readyz` invokes a service-throttled expiry sweep.
Only parseable terminal states whose `updated_at` is older than the cutoff are
removed; active, malformed, or unreadable state is retained for operator
inspection.

Run-create, run-fetch, and run-delete responses are `no-store`. A successful
`DELETE /api/v1/runs/{run_id}` removes both the state JSON and that run's
materialized tables, analysis artifacts, and report from the active runtime.
Deletion of a pending or running state is rejected with HTTP 409.
The repository validates the identifier and does not follow a run-directory
symlink. Separately retained snapshots are outside this guarantee and require
their own retention/destruction policy. In this anonymous preview, the opaque
run identifier is a bearer capability: anyone who obtains it can fetch or
delete that run. These controls bound the research prototype; they do not
substitute for authentication, ownership authorization, a persistent queue,
user quotas, or an isolated arbitrary-code worker.
