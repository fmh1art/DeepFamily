# Ask, Don't Upload artifact guide

This repository is the artifact workspace for the VLDB 2027 demonstration
paper **Ask, Don't Upload: A Question-Driven Agentic System for Closed-Loop
Data Discovery, Preparation, and Analysis**.

Status: internal reproducibility preview, version 0.4.0, 2026-09-09. It is not
yet a public release: the authors have not selected a source-code license or a
permanent archival URL, and the prospective held-out evaluation remains
blinded. Its historical implementation freeze no longer matches the current
core; the readiness gate correctly fails. On 2026-09-09 the user authorized
continuation of the previously described work: the separate 30-question,
180-case open agentic study is now frozen; its first six cases have finished and
later batches are running.
It has not yet produced sealed/scored results and is not part of the completed
reproduction claims below. See `docs/agentic-open-evaluation.md` for the plan
and a process-aware status command. Community 45 remains unopened.

The main interactive system is now the **agentic** three-stage workflow over
the 30 open CoDA communities. The smaller **registry** path below reproduces
the paper's controlled mechanism experiments without credentials. These are
different evidence boundaries, not interchangeable system-quality results.

The measured clean-directory reproduction and its exact tested archive are
recorded in [docs/artifact-cleanroom-validation.md](docs/artifact-cleanroom-validation.md).

## Claims covered by the current artifact

| Claim boundary | Reproduction command | Authoritative output |
|---|---|---|
| A typed downstream violation can reopen Discovery and recover four registered cross-source tasks. | `make experiment-community` | `experiments/results/coda-community43/summary.json` |
| On all 15 registered community-43 tasks, closed loop reaches 15/15 correct terminal outcomes, versus 11/15 for linear execution. | `make experiment-community` | Same summary, `aggregate.closed_loop` and `aggregate.linear` |
| With the same two-round budget, static retry reuses initial query terms and reaches 13/15 with 21 profiles and 7 repair edges; violation-guided repair reaches 15/15 with 18 profiles and 4 edges. | `make experiment-community` | Same summary, `aggregate.static_retry` and `aggregate.closed_loop`; controlled registered-task ablation |
| Full profiling also reaches 15/15, but requests 150 logical source profiles versus 18 for closed loop. | `make experiment-community` | Same summary; logical workload-exposure metrics, not physical I/O |
| Two registered tasks from community 52 execute and exactly match their answers. | `make experiment-transfer` | `experiments/results/coda-community52-transfer/summary.json` |
| Both OpenAI-style base URLs and exact queried Chat Completions endpoints have a locally verified server-side contract. | `make provider-contract` | HTTP-level request/retry/authentication tests with no live credential |
| A free-form browser question can traverse the production Web/API path, reject an invalid model plan, request a bounded correction, execute the corrected plan, and render a report without a live credential. | `make provider-browser-smoke` | One Playwright check against a loopback-only deterministic mock provider; two request/response hashes and 21-row result, but no model-quality evidence |
| The production Web/API path exposes two repair families, honest stopping, provenance, stage input/output schemas, hop replay, preparation trees, report charts/downloads, adaptive long-answer expansion and per-run deletion. | `make e2e` on an isolated registry stack | 16 Playwright checks; real registry execution plus explicitly constructed agentic UI trajectories and long-answer fixtures, not 16 real-model successes |
| A question-only Chinese development run produced a community walk, prepared table, executed notebook and multidimensional report. | Inspect the registered observation and figure manifests | `experiments/evidence/agentic-question-only-smoke-2026-09-09.json` includes failed and successful development attempts; `paper/figures/agentic-replay-v1/` contains current-UI replay, not new inference. Private raw logs are excluded. |
| Logical model calls, SDK HTTP attempts and partial/missing provider token receipts remain distinguishable. | `uv run --project backend pytest backend/tests/test_provider_metering.py backend/tests/test_agentic_open_evaluation.py -q` | Offline transport, interruption, persistence and evaluation-runner checks; the ongoing open study separately records real receipts, not yet a complete coverage/cost result |
| The ECS configuration separates host-Nginx/loopback and ALB/private-IP ingress, keeps the API private, validates the outer TLS/rate-limit template, requires a 1--720 hour public run-retention window, and preserves container/data/runtime isolation. | `make ecs-config-check` | Secret-free structural rendering of `compose.yaml`, Nginx syntax parsing with the digest-pinned production-family image, and a checked volume-preserving systemd template; strict real preflight also verifies private config, Host/CORS, retention, installed ingress, and all ten mounted CSV digests |
| Mutable runtime state can be backed up and restored without overwriting the active named volume. | `make ecs-runtime-snapshot-smoke` | Private deterministic snapshot with exact census/per-file digests; restore into a fresh empty volume and byte-for-byte re-snapshot verification |
| The four registered booth scenarios remain responsive through the serial production HTTP path. | `make demo-latency` | Raw samples and descriptive latency distribution in `experiments/results/demo-path-latency.json` |
| A captioned stable-frame fallback can be regenerated from asserted production-path states and checked for portable media properties. | `make demo-video` | Local H.264/yuv420p 1600x900 MP4; generated media are intentionally excluded from the source archive |
| The paper builds with the pinned PVLDB template within the provisional four-page limit. | `make pdf-modern` then `./scripts/check_submission.sh --draft` | `paper/main.pdf`; full `make draft-check` additionally audits readiness and currently fails on the stale held-out freeze |

The numeric comparison results are deterministic, task-registered mechanism results. They do not show
open-ended language generalization, arbitrary Web discovery, physical I/O or
stable latency improvements, a completed user study, or performance on the
still-blinded community-45 evaluation.

`scripts/mux_demo_narration.py` provides an atomic author-audio handoff and
rejects a candidate unless it has one timeline-covering, measurably non-silent
AAC track. The preview intentionally contains neither a synthetic test tone nor
an author recording, and therefore does not claim that the final submission
video has been completed or human-reviewed.

## Requirements

- Docker with Compose v2, plus OpenSSL for the throwaway host-Nginx syntax-check certificate;
- Python 3.10.20 and `uv` 0.11.1 for local checks/experiments;
- `python3`, Bash, GNU tar/coreutils, gzip, ripgrep and make for artifact tooling;
- `hf` CLI (`huggingface_hub==1.0.1`) for downloading the pinned public pilots;
- Node.js 24.20.0 for the Web client;
- Chromium plus Playwright host libraries for browser tests;
- `ffmpeg` only for the optional fallback video;
- `zstd` for archive extraction and `curl` for readiness/template downloads;
- Poppler (`pdfinfo`, `pdffonts`) for submission-format checks;
- network access for missing dependencies, container images and external data/templates.

The paper itself is built inside a digest-pinned TeX Live 2024 container; no
host TeX installation is required.

The production container starts `backend/deployment/api.py`. This mutable
public-service layer implements retention/deletion around the
`backend/src/askdu` analytical core. The demo-surface digest covers both; the
historical blinded-evaluation freeze must not be rewritten merely to match new code.

## Reproduce the implemented evidence

Use a **fresh extracted preview on a development machine**, with the requirements
above installed. Do not paste the default Compose targets into an active demo
deployment: browser/smoke targets start and stop their Compose project.
The following scoped subshell selects an isolated project, empty model key,
separate runtime volume and port 8082; the service at 8080 is not touched.
Choose another unused port if necessary. It does not run live-model evaluations.

```bash
(
  set -euo pipefail
  # Keep private configuration and all existing demo resources out of this run.
  export COMPOSE_DISABLE_ENV_FILE=1
  unset VIRTUAL_ENV COMPOSE_FILE COMPOSE_ENV_FILES COMPOSE_PROFILES
  # Unit-test clients use their own default Host/CORS configuration.
  unset ASKDU_TRUSTED_HOSTS ASKDU_CORS_ORIGINS
  export COMPOSE_PROJECT_NAME=askdu-artifact-reproduction
  export ASKDU_RUNTIME_VOLUME_NAME=askdu-artifact-reproduction-runtime
  export ASKDU_HTTP_PORT=8082 ASKDU_BIND_ADDRESS=127.0.0.1
  export ASKDU_E2E_BASE_URL=http://127.0.0.1:8082
  export ASKDU_CATALOG_MODE=single ASKDU_PLANNER_MODE=registry
  export ASKDU_LLM_API_KEY= ASKDU_LLM_BASE_URL=http://127.0.0.1:9
  export ASKDU_RUN_RETENTION_HOURS=0

  make backend-sync frontend-install
  make pilot-assets
  # Required BEFORE quality: tests validate the generated paper/build manifest.
  make pdf-modern
  make quality
  make experiment-all
  make provider-contract ecs-config-check
  (cd frontend && npx playwright install chromium-headless-shell)
  # Apply the isolated Web boundary only after in-process API tests finish.
  export ASKDU_CORS_ORIGINS=http://localhost:8082
  export ASKDU_TRUSTED_HOSTS=localhost,127.0.0.1,api
  make e2e
  make artifact-verify
)
```

`make draft-check` is a **separate submission-readiness audit**, not a passing
installation test: it currently reports the stale prospective freeze and five
pending author/external gates. Do not change the recorded freeze to make it green.
Optional `provider-browser-smoke`, latency, snapshot and video commands must also
use an isolated Compose environment; they are not prerequisites for launching
the Web UI. Install Playwright's host libraries if browser launch reports them missing.

`make experiment-all` ends with `make verify-results`. The verifier checks the
task/mode census, exact aggregates, repair and abstention invariants, and the
corresponding numeric claims in `paper/main.tex`. It also independently
recomputes every checked production-path latency summary from the 40 raw
samples and checks the paper/evaluation values. An experiment process merely
exiting successfully is not treated as sufficient evidence.

`make demo-latency` writes a new machine-specific run below the ignored
`experiments/results/` directory. The checked version-0.4.0 measurement is
retained separately at
`experiments/evidence/demo-path-latency-v0.4.0.json`, so reproduction does not
overwrite the paper's source evidence.

`make paper-assets` downloads the three paper-template build files from the
pinned official VLDB template commit and verifies their exact digests. They are
ignored by Git and excluded from this artifact because `acmart.cls` remains an
LPPL-derived upstream work and the pinned VLDB repository does not provide a
standalone repository license for `pvldb.sty`. `make pdf` and `make pdf-modern`
invoke this target automatically and refuse to overwrite a modified local
template file.

`make pilot-assets` downloads only the revision-pinned CoDA-Bench metadata and
communities 43 and 52 required by the reported evidence. It does not download
the reserved held-out archive or any supporting-work repository. Large data
and optional third-party clones remain outside the release archive. It verifies
both archives and all 13 extracted CSVs; the runtime repeats the check for every
selected source. Checksums, revisions, known benchmark irregularities, and the
logical-profile metric definition are documented in `docs/asset-inventory.md` and
`docs/evaluation.md`. The source-by-source license evidence and conservative
download-only redistribution decision are documented in
`docs/licensing-and-redistribution.md`.

The expected aggregate is:

| Controller | Correct terminal | Exact reports | Correct abstentions | Repair edges | Logical profiles | Logical bytes |
|---|---:|---:|---:|---:|---:|---:|
| Linear | 11/15 | 10/14 | 1/1 | 0 | 14 | 4,989,475 |
| Static retry | 13/15 | 12/14 | 1/1 | 7 | 21 | 11,008,557 |
| Closed loop | 15/15 | 14/14 | 1/1 | 4 | 18 | 7,476,177 |
| Full profile | 15/15 | 14/14 | 1/1 | 0 | 150 | 1,355,590,320 |

Community 52 should report two tasks, two exact matches, two expected sources,
two logical profiles, and 292,948 logical bytes. Run identifiers and elapsed
times are intentionally not expected to match across executions.

Every logical profile in both public evaluations must also be counted as a
verified source profile. This asserts byte identity with the audited manifest;
it is not an additional effectiveness result.

## Continuous integration and supply-chain pins

`.github/workflows/ci.yml` is configured to reproduce the public pilot evidence and check the
frozen held-out implementation digest, validates both guarded ECS ingress profiles,
exercises the production Compose path
with Playwright, builds and inspects the paper, and compares two independently
built artifact checksums. It does not accept a model-provider secret and does
not download or extract community 45. The source-quality job builds the generated
paper prerequisite before `make quality` on a fresh checkout. This is not a claim
of green hosted CI: the historical freeze check remains red and the workflow
has not been executed on GitHub from this local workspace.

All third-party GitHub Actions are pinned to full commit SHAs. The production
Dockerfiles use both exact version tags and multi-platform manifest digests:
Python 3.12.14, Node.js 24.20.0, unprivileged NGINX 1.30.4, and uv 0.11.1.
The reported experiments remain pinned to Python 3.10.20 so that their recorded
environment and paper claims are reproduced exactly; the production API runs
on the separately tested Python 3.12 image.

## Agentic mode, model mode and secrets

The reported results use the deterministic registry planner and require no
model credential. To launch the full question-only system on a separate demo
installation, use `./scripts/run_demo.sh agentic` as described in `README.md`.
It downloads/verifies the 30 open communities (about 46 GB compressed and
148 GB extracted; allow at least 210 GB free) and pins the shared ModelHub
endpoint/model for Discovery, Preparation, Analysis and reporting. No trained
paper-model weights are used. The launcher binds to 8080 and can replace the
default Compose services, so do not use it for an isolated artifact check.

The smaller `model` planner and mock-provider smoke are additional integration
paths, not substitutes for the full `agentic` workflow. Put any replacement credential in an untracked
`.env` or a server-side secret manager; never add it to source, browser
configuration, an image, a report, or an artifact archive.

Any credential previously placed in a chat transcript must be rotated before
use. `make provider-contract` verifies the backend HTTP boundary without a
secret. `make provider-browser-smoke` additionally drives a free-form question
from Chromium through the production Web/API path and a loopback-only,
deterministic mock provider; the mock rejects planner payloads containing fields
beyond the question, plan schema, and authorized catalog metadata. Its first
response deliberately references an unauthorized asset; local validation
rejects it before data access, and the mock returns a valid complete plan only
after receiving bounded credential-free feedback. This proves integration,
correction, and disclosure behavior, not language-model quality.
`make provider-smoke` is hard-locked to the public community-43 fixture. It
uses the real provider and must be explicitly authorized; it does not establish
held-out model quality. The separate 180-run open evaluation was authorized and
frozen on 2026-09-09; its first six cases have finished and later batches are
running, not yet sealed or scored. See
`docs/agentic-open-evaluation.md` for the protocol and cost boundary, and use its
process-aware status command to distinguish a running process from a saved record.

## Prospective held-out boundary

`data/pilots/heldout-v1.json` records the blinded protocol and frozen
evaluation-surface digest. Its checksum-bound static companion,
`data/pilots/heldout-v1-plan.json`, freezes the complete task census, pinned
inputs, data/output paths, and non-secret model configuration; both the plan and
question-redaction guard are part of the hashed implementation surface. The
internal preview contains these non-answer-bearing records but not the archive,
question text, schema, data, answer, oracle, reference program, or run result.
Do not list or extract community 45 outside `scripts/unblind_coda_heldout.py`
and the explicit authorization procedure in `docs/heldout-protocol.md`.

The historical freeze currently fails against the source; do not run the
unblind/first-pass/scoring commands or replace its digest as a maintenance fix.
After the authors resolve that protocol boundary, the non-unblinding preflight checks the frozen
surface, opaque asset hashes, paths, and declared model configuration without
listing or extracting the archive. The later runner verifies the exact
extracted-file census before model construction; first-pass sealing and
post-oracle scoring each advance the protocol atomically and reject duplicate
execution.

## Build a sanitized preview archive

```bash
make artifact-preview
make artifact-verify
```

This creates a deterministic archive and checksum below `artifacts/release/`.
The builder uses an explicit inclusion list and audits the **actual archive
members**, independently of Git-ignore rules. It rejects credential-shaped
assignments (a conservative heuristic, not a complete secret detector), duplicate
or unsafe paths, links and special members. Inspection is bounded to 10,000
members, 64 MiB per file and 256 MiB total uncompressed bytes. It excludes `.env`, downloaded data, held-out contents, local
third-party clones, supporting-paper PDFs, experiment outputs, runtime state,
browser dependencies, caches, the generated video, and LaTeX build products.
The root `.env.example`, full-release manifest, stage UI, report writer and
metering/evaluation code are required members. Only the internal preview may
retain the exact credential-free ModelHub endpoint already pinned in the project;
public mode rejects it, including shell/Compose default assignments. Other
concrete provider configurations remain rejected in both modes. These checks
do not change the working demo's endpoint, model or private environment file.
`backend/tests/test_artifact_bundle.py` covers the preview/public separation,
hidden ignored credentials, excluded private/held-out files and deterministic rebuilding.
The verifier checks the checksum and member boundary, extracts the archive into
a fresh temporary directory, invokes the packaged builder from that directory,
and requires the rebuilt archive to match byte-for-byte. Before extraction it
rejects unsafe paths, links, special filesystem members, private environment
files, and missing core files. The rebuild step executes the packaged builder:
use it for this trusted workspace's own output, not as a sandbox for untrusted
third-party archives. Byte-identical packaging alone does not prove app execution;
run the reproduction commands above for that separate check.

The preview archive is for internal inspection only. Before publication, the
authors must select and add a code license, keep external pilot data on the
audited download-only path, complete the manual container-OS notice/license
review, provide a permanent public repository/archive URL, replace paper author
placeholders, and rerun the submission checker under the final VLDB 2027 Demo
CFP. A concrete provider configuration must also be removed through an
author-reviewed release configuration change. Once exactly one root license
exists and those content checks pass, `make artifact-public-verify`
packages that license, invokes the sanitized builder in public-release mode,
and clean-room rebuilds the release byte-for-byte. Preview and release suffixes
cannot silently cross verification modes.

`make readiness-draft` audits the non-paper evidence without treating honest
development-time `PENDING` states as failures. `make check` is intentionally
stricter: in addition to page/template/author checks, it refuses submission
while the official Demo CFP, root license and OS review, prospective held-out
score, accepted non-author rehearsal, technically and human-reviewed narrated
video, or checksummed public artifact/HTTPS URL is absent. Example rehearsal
and video-review records contain no claim that those human steps occurred. A
real rehearsal record must additionally match both the current production
demo-surface digest and the exact participant-prompt/facilitator-scoring
protocol digest. Its six per-task outcomes and aggregate count must agree, the
separate task-960 repeat must pass, and its open-blocker count must match the
structured issue list. Use `make rehearsal-surface` and
`make rehearsal-protocol` immediately before the session, then use
`make rehearsal-check REHEARSAL_RECORD=/absolute/path/to/record.json` after
recording the pseudonymous outcome; replacing a stale digest is not a valid
substitute for rerunning the rehearsal.

The checked production inventory is reproduced with:

```bash
make dependency-license-audit
```

It compares the actual images against
`experiments/evidence/dependency-license-inventory-v0.4.0.json`: backend Python
and shipped frontend dependencies require non-empty license metadata; Debian
and Alpine OS packages are inventoried separately. If dependencies have changed,
the recorded inventory must be reviewed instead of treating an older count as current.
The check highlights compound/reciprocal metadata for human review and does not
claim container compatibility or replace required notices. Build-only `uv`,
`uvx`, Node, and npm tooling is absent from the final runtime stages. A
byte-identical copy is publicly readable at
`/notices/dependency-license-inventory-v0.4.0.json` from the deployed Web image
and linked from its Data & software notice; it contains metadata, not source
data.

For point-in-time vulnerability checks from a networked staging machine, run:

```bash
make dependency-audit
make image-vulnerability-audit
```

The first command checks the locked Python and production npm dependency sets.
The second rebuilds and exports the final API and Web images, then scans their OS
and language packages with digest-pinned Trivy 0.74.0. It rejects detected,
fixable High/Critical findings while deliberately reporting its run-time database
boundary (`--ignore-unfixed`). Neither check replaces the manual legal review
above or establishes that lower-severity or not-yet-known vulnerabilities are
absent.

The same two checks run weekly through `.github/workflows/security-watch.yml`
after the repository is pushed and GitHub Actions is enabled. Every referenced
third-party Action is commit-pinned; the Trivy container is multi-architecture
digest-pinned inside `scripts/audit_container_images.sh`.
