# Reproducible evaluation record

Status date: 2026-09-06. This document is the source of truth for implemented
task coverage and measured prototype results. It separates mechanism evidence
from claims that still require a broader evaluation.

## Data and execution boundary

- CoDA-Bench metadata and community archives are pinned to Hugging Face
  revision `63828a2b652e26a9770555a0cc41e6c8aafdb5d9`.
- The main evaluation uses all 15 questions assigned to `community_43`, whose
  authorized environment contains 10 CSV files.
- A transfer probe uses both questions assigned to `community_52`, whose
  authorized environment contains three CSV files in a different domain.
- The archive and all 13 public-pilot CSV files are revision/checksum pinned.
  Every source selected by these experiments is hashed against the audited
  per-file manifest before Preparation; a mismatch fails the run rather than
  entering the result table.
- A prospective model-based evaluation reserves all 13 tasks in
  `community_45`. Selection occurred before inspecting question text, answers,
  reference code, schemas, archive members, or rows. Its opaque 11,166,232-byte
  archive has been checksum-verified but not listed or extracted; see
  `docs/heldout-protocol.md`. A checksum-bound static plan now freezes the task
  census, inputs, paths, non-secret model configuration, exact extracted-data
  verification, and sealed/scored state transitions before unblinding.
- The compiler and operators are deterministic and were registered after task
  inspection. Benchmark answers and required-source sets are read only by the
  post-run evaluator. No LLM, benchmark answer, or reference code is available
  to Discovery, Preparation, Analysis, or Reporting at runtime.
- Each task/mode pair is executed once. Exact match is therefore appropriate
  for regression evidence; statistical significance and stochastic variance
  are not claimed.

## Community 43 task census

The complete local task set contains ten questions answerable from the first
selected source, four questions that need a second source, and one question
whose referenced source is absent from the pinned archive.

| Class | Task IDs | Expected runtime behavior |
|---|---|---|
| No repair | 176, 177, 178, 180, 956, 957, 958, 961, 962, 963 | Produce an evidence-grounded report after one source profile |
| Cross-source repair | 175, 955, 959, 960 | Detect a typed violation, reopen Discovery once, then report |
| Local data gap | 179 | Stop with `data_gap` and no report |

Tasks 175, 955, and 959 repair missing analytical columns through a second
school table. Task 960 repairs missing category coverage: the first Shake
Shack source cannot answer an extreme over Shake Shack, McDonald's, and Burger
King, so the violation drives discovery of `fastfood.csv`.

## Controller comparison

All four modes use the same task compiler, catalog ranking, preparation
operators, and analysis operators.

- `linear`: progressive discovery with zero downstream-to-upstream repairs.
- `static_retry`: progressive discovery with the same two-round budget as the
  closed loop, but every retry reuses the initial discovery terms instead of
  terms extracted from the executable violation.
- `closed_loop`: progressive discovery with at most two typed repair rounds.
- `full_profile`: index all authorized paths and CSV headers, then content-
  profile all ten files before analysis; no repair is allowed.

`make experiment-community` produced the following aggregate after the latest
full rerun at version `0.4.0`:

| Mode | Correct terminal outcomes | Exact reports | Correct abstentions | Repair edges | Logical source profiles | Logical profile bytes | Mean source precision | Mean source recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Linear | 11/15 | 10/14 | 1/1 | 0 | 14 | 4,989,475 | 1.000000 | 0.857143 |
| Static retry | 13/15 | 12/14 | 1/1 | 7 | 21 | 11,008,557 | 0.880952 | 0.928571 |
| Closed loop | 15/15 | 14/14 | 1/1 | 4 | 18 | 7,476,177 | 1.000000 | 1.000000 |
| Full profile | 15/15 | 14/14 | 1/1 | 0 | 150 | 1,355,590,320 | 0.128571 | 1.000000 |

All 14, 21, 18, and 150 logical profiles in the four respective rows passed the
registered per-CSV digest check. This is an input-integrity assertion, not an
additional effectiveness metric.

Static retry recovers tasks 955 and 960 but exhausts its two-round budget on
tasks 175 and 959 because unchanged query terms rank unrelated sources ahead of
the missing School Explorer table. It therefore performs seven repair edges
and requests 21 profiles. The violation-guided closed loop recovers all four
linear failures with four repair edges and 18 profiles. Full profile also
resolves them, but exposes every task to all ten sources. This supports a narrow
mechanism claim: conditioning rediscovery on an executed deficiency improves
termination and avoids wasted retries within this registered environment.
Because the deterministic compiler was created after task inspection, this is
a controlled mechanism ablation rather than evidence of language or retrieval
generalization.

“Logical source profiles” counts files whose complete contents a task requests
for hashing and row counting. “Logical profile bytes” sums their sizes
independently per task and intentionally ignores the in-process profile cache.
All modes first inspect paths and CSV headers. These are workload-exposure
measures, not physical I/O, token usage, or wall-clock latency.

## Production-path rehearsal latency

`make demo-latency` separately measures the four booth scenarios through the
production Nginx-to-FastAPI HTTP route. On 2026-09-06, each scenario received
one unmeasured warm-up followed by ten measured requests, in serial task order
with 2.05 seconds between requests. The interval respects the deployed
30-runs-per-minute per-IP admission limit. The host used an Intel Xeon Platinum
8457C with 64 logical CPUs; the service ran version `0.4.0`, registry planner,
and the pinned ten-CSV community-43 environment.

| Scenario | Task | Median (ms) | Nearest-rank P95 (ms) | Max (ms) |
|---|---:|---:|---:|---:|
| Join repair | 959 | 56.143 | 58.374 | 58.374 |
| Coverage repair | 960 | 30.759 | 31.799 | 31.799 |
| Direct answer | 176 | 13.286 | 13.683 | 13.683 |
| Honest data gap | 179 | 7.678 | 8.442 | 8.442 |
| **All 40 requests** | — | **21.475** | **57.882** | **58.374** |

Every measured response also satisfied its expected terminal status,
report-versus-diagnosis boundary, and repair-edge count. Raw samples, protocol,
machine metadata, and limitations are retained in
`experiments/evidence/demo-path-latency-v0.4.0.json`.

This is descriptive rehearsal evidence on one host, not a competing-system
performance comparison. It excludes image build, container startup, TLS, WAN
delay, browser rendering, and model calls. Warm-ups remove first-request
effects, and host filesystem/OS page caches were not flushed. Consequently it
supports only the narrow claim that the current deterministic booth scenarios
are responsive on the measured local production path.

## Community 52 transfer probe

`make experiment-transfer` executes two additional registered task families:
yearly unemployment aggregation/skewness and wage-attribute skewness. Both
questions selected their intended source, produced reports, and exactly
matched their oracle. Together they requested two logical source profiles
(292,948 bytes), both digest-verified, no repair, and no mandatory human
intervention.

This is a cross-domain executability probe, not a held-out generalization
test: both rules and trusted operators were added after inspecting the tasks.

## Benchmark irregularities

- **Task 179:** its reference uses
  `schproma/source/schma19962016.csv`, but that file is absent from the pinned
  `community_43` archive. The system therefore targets a correct local
  `data_gap` diagnosis, not the benchmark answer string.
- **Task 961:** the supplied reference fills missing income with zero and
  yields income means inconsistent with the question's eligibility rule. The
  implemented operator excludes missing and zero income, matching the answer
  guideline and oracle (`$33,858` and `$63,987`).
- **Task 590:** the supplied reference defines “negative” as skewness below
  `-1` and prints `0.00%` on the pinned data. The question, answer guideline,
  and oracle classify skewness below zero: 2 of 120 attributes, or `1.67%`.

These exceptions are explicit evaluation-policy decisions. They must remain
visible in any paper table or released evaluator.

## Claim boundary

The current evidence supports deterministic lifecycle execution, the
violation-guidance ablation, typed repair, correct local abstention, artifact
lineage, and deployment feasibility for 17 registered questions across two
communities. It does **not** establish
open-ended language understanding, autonomous code synthesis, arbitrary Web
discovery, statistical superiority, or general effectiveness. Those claims
require a completed frozen held-out run, additional communities and source
types, model-matched baselines, repeated stochastic trials, and comparative
physical-cost measurements. Version 0.4 contains a strict model-to-plan
compiler and bounded declarative executor with synthetic execution tests plus a
loopback HTTP provider-contract test. Those implementation facts are not a
live-provider or held-out accuracy result, and none of the controller-table
values above have been changed by them.
