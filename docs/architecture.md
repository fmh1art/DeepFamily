# Deployable architecture v0.4

The prototype is a monorepo with explicit runtime boundaries:

```text
frontend/                React/TypeScript demo UI
backend/                 Analytical core plus public-service boundary
  src/askdu/domain/      Frozen state and contract types
  src/askdu/application/ Frozen orchestration and use cases
  src/askdu/adapters/    Frozen catalog, execution, LLM, persistence
  src/askdu/api/         Frozen evaluation-facing HTTP adapter
  deployment/            Mutable public API, retention, and deletion policy
  tests/                 Unit and vertical-slice tests for both layers
data/                    Manifests, pilot specs, ignored external data
experiments/             Baselines, ablations, and result provenance
infra/                   Containers, reverse proxy, ECS deployment
third_party/             Ignored pinned research repositories
paper/                   VLDB paper source
```

## Current runtime topology

The verified container path is:

```text
Browser -> reverse proxy -> Web UI
                         -> /api -> deployment API/lifecycle policy
                                      -> frozen analytical core
                                         -> read-only CSV environment
                                         -> immutable provenance/checksum registry
                                         -> registry compiler + trusted task operators
                                         -> or model compiler + bounded plan executor
                                         -> or agentic path walk + preparation tree
                                            + compiled analysis notebook
                                            + grounded report synthesis
                                         -> JSON/CSV/Markdown runtime volume
```

`backend/src/askdu` is also the analytical surface imported by the blinded
held-out runner. Any core change must therefore receive a new pre-unblinding
surface digest before evaluation; prior digests remain historical. Public-only policy is composed in `backend/deployment`: it substitutes
a deletion-capable implementation of the existing persistence port before any
request is admitted, then delegates compilation and execution to the frozen
`RunService`. The container starts `deployment.api`; held-out experiments import
the frozen core directly. The human-rehearsal surface hash covers both layers,
while the prospective evaluation hash intentionally covers only its previously
declared analytical surface.

The service uses a file repository and admits at most two runs concurrently by
default; excess requests receive a retryable 503 instead of opening another
dataframe/model workload. The browser creates an observable background run with
HTTP 202 and polls its persisted state. Workers are bounded in-process threads,
not a durable queue. The synchronous endpoint remains available to tests and
CLI callers. Seventeen registered
questions across two CoDA communities use trusted, fixed operators and require
no credential. An optional server-side OpenAI-compatible compiler now emits a
strict `DeclarativeAnalysisPlan v1.0`. Synthetic execution tests cover a
two-source repair, while a loopback HTTP provider test covers exact queried
endpoint preservation, API-key authentication, a retryable 429, current token
field spelling, plan compilation, execution, evidence, and reporting without a
live credential.

The declarative executor is deliberately non-Turing-complete. A model may name
only catalog `asset_id` values and exact indexed columns, construct an immutable
table graph, and choose bounded white-listed operations. Unknown fields,
unknown assets/columns, table overwrites, unsupported operations, oversized
responses, and row/byte budget violations are rejected. Model text is never
evaluated as Python, SQL, shell, or a filesystem path. For the visible
DeepAnalyze-style loop, a local compiler derives parameterized SQL or restricted
Python from the validated typed plan, executes it against the selected in-memory
table state, and verifies the result against the bounded dataframe executor.
The final model call is a schema-constrained `<Finish>` phase over those executed
artifacts. Every narrative section must resolve to known artifact IDs and all
published artifacts must be covered; invalid drafts fall back to a deterministic
artifact-to-section report rather than blocking or inventing a conclusion.

## Target public topology

Public-scale iterations can replace adapters without changing the domain contract:

```text
FastAPI -> persistent job queue -> isolated execution worker
       -> PostgreSQL metadata  -> object/artifact storage
       -> server-side OpenAI-compatible model provider
```

The current bounded dataframe DSL executes inside the API process and therefore
remains suitable only for the controlled demo workload. Uvicorn, the application
semaphore, and Nginx apply nested connection/concurrency admission bounds, but
they are not a durable queue. Arbitrary generated
code must never execute there; if later research requires code synthesis, the
public deployment will use a network-restricted, non-root worker with CPU,
memory, PID, filesystem, and time limits. That worker topology is not
implemented yet.

## Deployment invariants

- Configuration follows environment variables; `.env` is local-only. Strict
  ECS preflight requires the production env file outside the repository with
  mode `0600`, even before model mode introduces a credential. The public HTTPS
  origin is supplied independently to CORS and Trusted Host validation rather
  than retaining the localhost development default.
- No API key is accepted from or returned to the browser.
- Before the question can be submitted, the Web client must obtain and display
  the server's run-retention policy. Local configuration may use `0` to disable
  automatic cleanup; public ECS preflight requires an explicit 1--720 hour
  window. Readiness probes drive a throttled terminal-run expiry sweep; active
  runs and malformed state are preserved rather than being guessed expired.
- Run creation/fetch/deletion is `no-store`. `DELETE /api/v1/runs/{run_id}`
  removes the state document and the matching generated-table/artifact/report
  subtree from the active runtime. In the anonymous preview, possession of the
  opaque run ID permits both fetch and deletion; this is a bearer capability,
  not identity, authorization, or deletion from separately retained backups.
- Model-backed modes visibly disclose their provider boundary before submission.
  Legacy one-shot `model` sends question/catalog metadata but no source rows;
  `agentic` additionally sends at most five inspected preview rows and bounded
  execution observations. Neither sends complete files or the server credential.
- Public endpoints are versioned under `/api/v1`.
- `/healthz` is process liveness; `/readyz` constructs the service and indexes
  the authorized catalog without making an LLM call. Container health checks
  use readiness, so a missing data mount cannot look healthy.
- Trusted Host validation rejects unconfigured hostnames. Public run failures
  redact internal paths/provider details while retaining the private state on
  the runtime volume.
- Planner mode is deployment configuration; no request can choose a provider,
  model, base URL, credential, dataset path, or execution policy. Formal
  model-backed operation pins one ModelHub endpoint/model/profile for Discovery,
  Preparation/Analysis planning, and repair. A non-project provider is admitted
  only behind an explicit loopback-test flag that production preflight rejects.
- Registered public catalogs are tied to a validated benchmark revision,
  archive digest, per-CSV checksum manifest, upstream source record, and
  declared-or-unknown license metadata. A selected digest mismatch stops before
  Preparation, and unlisted CSV paths are not discoverable in a registered
  environment. A missing registered path fails catalog readiness. Unknown
  environments receive no inferred license.
- Provider addressing is explicit: the formal `azure_chat` profile extracts the
  API version from the pinned gateway URL and constructs the deployment route;
  generic `openai_base_url` and exact-POST `direct_chat_completions` adapters are
  retained for isolated compatibility tests.
  Environment proxies are disabled by default so credentials are not silently
  forwarded through an inherited proxy. Provider URLs require HTTPS except for
  loopback-only contract tests and cannot contain URL-embedded credentials.
- Source data is mounted read-only; artifacts use a separate writable volume.
  The Web/API exposes provenance and report evidence but no source-data download
  route.
- `make ecs-config-check` validates the secret-free Compose structure, host TLS
  template, and systemd lifecycle template in CI. `make ecs-preflight` requires
  one explicit ingress topology: host Nginx must proxy to a loopback binding,
  whereas ALB must target a specific ECS private address. Both reject wildcard
  bindings, and preflight verifies the mounted public CSVs against pinned digests.
- In the recommended single-ECS profile, host Nginx supplies the actual-client-IP
  request/connection limit and overwrites untrusted forwarding headers; the
  container limit remains defense in depth. ALB deployments must enforce the
  equivalent client boundary at the trusted cloud edge. The single-node runtime
  has a stopped-volume, content-verified snapshot path; restoration is
  restricted to a fresh empty named volume so switching and rollback do not
  overwrite the previous volume. This is not an online database backup or a
  substitute for encrypted off-site retention. Identity-aware quotas,
  migrations, TLS termination, and centralized audit logging remain explicit
  production concerns.
- User registration/authentication is a separate bounded module. The research
  engine never trusts a browser-supplied filesystem path or connector secret.

## Demo interface

The current main page exposes catalog provenance plus eight synchronized views:

1. a single analytical-question input;
2. an agentic-only paper-aligned workbench with explicit stage inputs/outputs,
   a CoDA-Bench Discovery community graph and hops, DeepPrep Preparation
   branches/operators plus schema transition, and DeepAnalyze notebook/report cells;
3. the Analytical Sufficiency Contract;
4. discovered sources and inspected evidence;
5. the lifecycle state graph, including backward repair edges;
6. a repair-impact before/after comparison;
7. the report or a typed insufficiency diagnosis; and
8. selectable claim-to-artifact-to-state-to-source lineage.

For completed reports, two client-side exports make the terminal state
portable without opening a source-data route. The Markdown download is the
exact persisted report body, so its SHA-256 matches the report evidence. The
versioned JSON bundle is constructed from an explicit allowlist of the public
`RunState`: contract, catalog/source metadata, hashed agent turns, discovery
hops, preparation branches/operators, analysis notebook cells, decisions,
states, analysis outputs, violations, repairs, lifecycle events, report, and evidence. It marks
source rows and server credentials as excluded. Because this allowlist lives in
the Web client, adding a future top-level API field cannot silently add it to
the export.

The default experience remains hands-off. Inspection, replay, and optional
steering support the demo but are not prerequisites for task completion.

Ten Playwright checks exercise the deployed same-origin path: four verify
the two repair families, a no-report data-gap terminal state, and the public
data/software boundary; the primary path also verifies pre-submission storage
disclosure and a create/export/delete/404 lifecycle; one verifies the model-provider
disclosure; three verify axe-clean initial/completed states, a keyboard-only
question-to-lineage path, and reflow at 1366x768 plus an effective 150% browser
zoom; one verifies the complete paper-aligned Discovery/Preparation/Analysis UI
contract, including replayable Discovery graph history, prepared schema/table
preview, a parent-linked branch, a visible Debug fallback, and structured report output.
One separate model-mode Playwright smoke test uses a loopback-only deterministic
provider in the API container's network namespace. It drives an unregistered
free-form question through Nginx, FastAPI, provider transport, strict plan
validation, bounded correction, execution, and report rendering. The first
response references an unauthorized asset and is rejected before data access;
the corrected second response is accepted only after bounded feedback. The mock
also rejects planner payload fields outside the declared metadata boundary.
This is an integration test and does not stand in for live-provider or held-out
model evidence.
The main path additionally asserts the pinned catalog, verified selected-source
digest, upstream/license links, absence of any source-data download link,
byte equality and report-evidence SHA-256 for the Markdown download, and the
no-source-row manifest and repair edge in the JSON evidence bundle.
`make capture-ui` uses the same suite to regenerate the paper screenshot and a
timestamp-free manifest binding its bytes, dimensions, A--E callouts, task-959
scenario, current demo-surface SHA-256, and the exact executable Playwright source.
`make paper-capture-check` rejects a stale screenshot, changed capture procedure,
or modified image. The generated system figure has an analogous manifest binding
its vector/raster outputs to `scripts/render_system_figure.py`. Finally,
`paper/main.build.json` binds the pinned TeX Live 2024 builder and all 13 paper,
template, figure, manifest, and verifier inputs to `paper/main.pdf`;
`make paper-build-check` rejects source, figure, verifier, or PDF drift;
Playwright is a development dependency and is absent from the final Web image.
The API image likewise uses a separate dependency-build stage and copies only
the completed virtual environment into the runtime stage; `uv`, `uvx`, and the
build cache are not shipped. The versioned dependency-license inventory and its
scope boundary are documented in `docs/licensing-and-redistribution.md`.
