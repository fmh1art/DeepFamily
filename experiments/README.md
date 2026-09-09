# Experiments

Experiment scripts consume revision-pinned external data and write generated
outputs to ignored `experiments/results/` directories. Each result records the
dataset revision, system version, task/mode, exact-match outcome, selected
sources, verified-source count, logical profile exposure, runtime, and
persisted run-state path.

## Community 43 controller evaluation

```bash
make experiment-community
```

This runs all 15 questions assigned to CoDA-Bench `community_43` under four
controllers:

- `linear`: progressive discovery with no downstream-to-upstream repair;
- `static_retry`: use the same two-round repair budget as `closed_loop`, but
  reuse the unchanged initial discovery terms on every retry;
- `closed_loop`: progressive discovery with up to two typed repair rounds;
- `full_profile`: content-profile all authorized CSVs before analysis and do
  not repair.

The workload includes ten no-repair tasks, four cross-source repair tasks, and
one local data gap. All modes inspect authorized paths and CSV headers before
selection; logical profile counts and bytes concern full-content hashing and
row counting, not metadata I/O or wall-clock time. Each selected source must
also match the audited per-CSV SHA-256 manifest before Preparation. Generated
reports retain upstream/provider/license provenance; raw data remain external.

## Community 52 transfer probe

```bash
make experiment-transfer
```

This executes the two registered skewness-analysis tasks from a second domain.
It checks that the lifecycle, catalog, materialization, artifact, and report
interfaces support another community. Because the compiler rules and trusted
operators were added after inspecting these tasks, it is not a held-out
generalization test.

Run both with `make experiment-all`. The exact results, benchmark
irregularities, and permitted claim boundary are recorded in
[`docs/evaluation.md`](../docs/evaluation.md).

Benchmark answers and required-source oracles are available only to post-run
evaluation. They are never passed to the compiler, discovery, preparation,
analysis, or reporting components.

## Production-path demo responsiveness

```bash
make demo-latency
```

This starts the production Compose topology and exercises the four registered
live scenarios through Nginx and `POST /api/v1/runs`. Each scenario receives
one warm-up followed by ten serial measured requests. Requests are paced at
2.05 seconds so the measurement respects, rather than disables, the deployed
30-runs-per-minute per-IP limit. The output reports every raw sample plus the
median, nearest-rank P95, minimum, and maximum.

This is a same-host rehearsal measurement, not a competing-system benchmark.
It excludes image build, container startup, TLS, WAN delay, browser rendering,
and model calls, and it does not flush OS caches. Override
`DEMO_LATENCY_OUTPUT` to retain a separately named run.

## Prospective community 45 held-out evaluation

This existing protocol runs `planner_mode="model"`, not the full `agentic`
discovery/tree/report pipeline. Its future results must retain that scope.
The separate full-pipeline open-set protocol is described below; it is not held out.

All 13 `community_45` tasks were selected before inspecting their questions,
answers, reference code, archive members, schemas, or rows. The opaque archive
can be reproduced with `make heldout-download`; do not list or extract it
outside the guarded protocol.

The recorded implementation freeze is currently superseded: current source does
not match its digest, and preflight must reject it. See `docs/heldout-protocol.md`.
Do not replace a recorded hash simply to make the gate pass. After reconciling
the intended implementation, freezing it, and receiving separate author
authorization, follow the guarded unblinding sequence in that document:

Use a freshly rotated server-side credential; never place it in this repository.
The provider smoke is locked to public `community_43`. The preflight refuses a
missing/mismatched freeze, input hash, path, or model configuration without
listing/extracting the held-out archive. Crossing from preflight to unblinding
requires separate author authorization.

The unblinding guard emits only ordered task IDs and question text, plus an exact
manifest of the extracted root. Before constructing the model service, the
runner rechecks that manifest's own hash, its file count, the exact file census,
and every data-file digest. It refuses code/configuration drift and an
already-started or partial output directory, then seals every generated
pre-oracle file and atomically records `first_pass_sealed`. The scorer accepts
only that state, verifies the seal, writes an oracle-opening marker, then opens
benchmark answers and reports both whitespace-normalized exact match and
ordered numeric-token match. It records `scored` atomically and rejects a second
score. No result exists yet; the reported 17-task numbers must remain unchanged
until this sequence has actually run.

## Full-agentic open-set paired evaluation

`agentic_open_evaluation.py` runs actual tool-mediated Discovery, preparation
candidates, analysis, and report synthesis over the full open pool. Its proposed
sample has one hash-selected question per open community, two controller modes,
and three repetitions (180 cases). This development-exposed open sample is not a
held-out or task-weighted generalization estimate.

The design and bounded commands are in
[docs/agentic-open-evaluation.md](../docs/agentic-open-evaluation.md).
Real API execution has not begun. Every invocation requires an explicit new-case
or judgement allowance; partial batches cannot be scored as complete studies.
Failures and interrupted attempts remain in the denominator and are not rerun.

## Real-provider development observations

[`evidence/agentic-development-smoke-2026-09-09.json`](evidence/agentic-development-smoke-2026-09-09.json)
records three persisted development runs, including the country report before
and after an evidence-packet fix. These selected, post-hoc observations are not
a frozen evaluation, a complete attempt history, or an accuracy denominator.
The SHSAT question is already known, and the country question explicitly lists
dimensions. See [the evidence note](../docs/agentic-smoke-evidence.md) for
actual candidate statuses, code/execute/report counts, and a read-only check
against the running service. No data from community 45 are included.

Later question-only attempts without author-supplied dimensions or weights are
recorded separately in
[evidence/agentic-question-only-smoke-2026-09-09.json](evidence/agentic-question-only-smoke-2026-09-09.json)
and [docs/stage-io-validation.md](../docs/stage-io-validation.md). They remain
development checks, not a frozen success-rate estimate.
