# Ask, Don't Upload backend

The backend owns the analytical-sufficiency contract, lifecycle state graph,
cross-stage repair controller, data adapters, and versioned HTTP API. The
analytical implementation under `src/askdu` is the current evaluation surface;
`deployment/` composes public-only retention, deletion, and cache policy. The
new agentic path was added after the earlier draft freeze, so a fresh public
evaluation freeze is required before any future held-out run.

## Local setup

```bash
uv sync --project backend
uv run --project backend askdu doctor
uv run --project backend askdu run \
  --question "What are the Pearson correlation coefficients between the number of students who took the SHSAT and the percentage of Asian, Black/Hispanic, and White students for Grade 8 in 2016, using SHSAT registration and tester data that includes grade level information?"
```

Start the API:

```bash
cd backend
uv run uvicorn deployment.api:app --host 127.0.0.1 --port 8000
```

The default environment points at the downloaded CoDA-Bench `community_43`.
Override it with `ASKDU_DATA_ROOT`. Runtime state is written under `runtime/`,
which is ignored by Git.

`ASKDU_CATALOG_MODE=coda_open_release` instead constructs a manifest-allowlisted
catalog over the 30 installed public v1.0 communities. It never discovers a
community merely because a directory exists. CSV/TSV/JSON/JSONL/Parquet/XLS/XLSX
are tabular execution candidates; PDF, image and other files remain discoverable
metadata but are outside the current executor.

`/healthz` reports process liveness; `/readyz` additionally constructs the
configured service and indexes its authorized catalog. `ASKDU_TRUSTED_HOSTS`
controls accepted Host headers, and `ASKDU_MAX_CONCURRENT_RUNS` bounds admitted
analysis workloads. The reverse proxy adds a separate per-IP request and
connection limit. Detailed unexpected exceptions remain in the private runtime
state and are redacted from API responses.

`ASKDU_RUN_RETENTION_HOURS=0` disables automatic expiry for local work. A public
deployment must select 1--720 hours. Only terminal runs are swept, and the API
also supports explicit deletion of a completed run from the active runtime.
The opaque run ID is a bearer capability rather than user identity; snapshots
and backups require their own deletion policy.

`ASKDU_PROVENANCE_MANIFEST` registers audited public environments. The service
validates its revision/archive/per-CSV pins at startup and recomputes a selected
file's SHA-256 before Preparation. A mismatch fails closed. Provenance and
declared-or-unknown license metadata appear in API assets and generated reports;
an unregistered environment receives no inferred license. The API deliberately
has no source-data download route.

## Agentic model provider

`ASKDU_PLANNER_MODE=agentic` builds exactly one server-side model client shared
by Discovery, Preparation/Analysis planning, and repair. Formal operation pins
the supplied complete ModelHub endpoint, `gpt-5.5-2026-04-24`,
`azure_chat`, `api_key`, and `max_completion_tokens`; only the key
comes from private configuration. A non-project provider requires an explicit
loopback-test override that ECS preflight rejects.

Discovery returns typed filesystem actions. Preparation returns an executed
candidate tree whose branches contain `DeclarativeAnalysisPlan v1.0`; local
validation rejects unknown assets, columns, fields, operations, cross-community
selection, and mutable table graphs. The bounded executor never evaluates
generated Python, SQL, shell, expression strings, or filesystem paths.

The default remains `registry`: its reported deterministic tasks neither
construct this adapter nor call an external model. CoDA-Bench, DeepPrep and
DeepAnalyze checkpoints are never loaded. Provider transport and agent loops
have synthetic/loopback coverage; a real-provider open-pool smoke case is also
recorded locally, but it is not a systematic task-quality result. Never expose
credentials through Vite/browser variables.
