# Frozen held-out evaluation protocol

Current status (2026-09-09, Asia/Shanghai): **the recorded implementation freeze
is superseded by subsequent code changes and is NOT eligible for unblinding**.
The readiness verifier correctly rejects the current surface. No replacement
freeze is written merely to pass that gate. Read-only checks find no generated
held-out question file, extracted community_45 directory, or extracted-file
manifest; the protocol still records `unblinding: not_started` and `results: not_run`.
Reconcile and explicitly freeze the intended implementation before requesting
author authorization for unblinding. The separate full-agentic open-set design is
documented in [agentic-open-evaluation.md](agentic-open-evaluation.md).

Historical snapshot: implementation frozen while still blinded on 2026-09-09
(Asia/Shanghai), after deployment, provider-transport, source-provenance
hardening, a controlled repair-guidance ablation, evidence-chain hardening,
paper-aligned execution observability, stage schemas/previews and structured
report synthesis. That snapshot passed 158 backend tests. Its historical
pre-unblinding evaluation-surface digest was
`7b196aae34d11f6a8c3c9a4c95a6d96f4a17a8d09a4285197ec72a5a56b74edc`.
The eight earlier freezes are retained as superseded history in the
machine-readable record, `data/pilots/heldout-v1.json`.

## Purpose

The existing 17-task evidence is a deterministic regression study: its task
families were registered after inspection. It cannot support a claim of
open-ended question understanding. This protocol creates a prospective test
for the model-based question compiler and declarative execution path.

The existing runner explicitly uses `planner_mode="model"`. It does not
evaluate the newer `agentic` tool-mediated discovery, preparation tree, or
final report-writer path. Updating an implementation digest does not change
that protocol. Evidence for the full agentic pipeline requires a separately
specified evaluation design before its first run; do not relabel this plan or
pool its future results with the three-stage real-provider smoke observations.

## Selection

The held-out set is every task assigned to CoDA-Bench `community_45` at pinned
revision `63828a2b652e26a9770555a0cc41e6c8aafdb5d9`: task IDs 31, 32, and
260--270 (13 tasks total). The community was selected using metadata only:
community and task identifiers, task count, dataset labels indicating an IPL
match-data domain, and approximate archive size. No task was excluded.

At selection time, no community_45 question, answer guideline, oracle,
reference program, archive member list, schema, or data row had been inspected.

## Two-stage freeze

1. **Selection freeze (complete):** record the complete task set and pinned
   source before reading task content.
2. **Implementation freeze (historically completed while blinded; now superseded):** the generic compiler
   and safe declarative executor passed the first freeze. Before any held-out
   access, that freeze was reopened first to add deployment hardening and then
   again to correct queried provider-endpoint handling, isolate credentials from
   inherited proxies, and add a public-fixture provider smoke guard. A third
   pre-unblinding reopening added an audited source registry, per-CSV integrity
   verification, provenance disclosures, and registered-catalog admission
   checks; its final review then required exact coverage between registered CSV
   datasets and source records. The final pre-unblinding reopening added a
   same-budget static-retry controller over already inspected community 43 to
   isolate the effect of violation-conditioned repair terms. A final
   pre-unblinding reopening hardened the evidence chain: it added an immutable
   task/path/model plan, included the question-redaction guard in the frozen
   surface, required an exact extracted-file census before model construction,
   and made seal/score transitions atomic and recoverable. The latest blinded
   reopening added persisted CoDA-style discovery hops, DeepPrep-style operator
   candidate traces, and a safe compiled DeepAnalyze-style notebook loop for the
   Demo UI. A subsequent reopening added stage input/output schemas and bounded
   table previews, same-provider structured reports and reference checks, and
   corrected double clipping of report evidence found in an open-data smoke.
   The 158-test suite passed, and read-only existence checks confirmed no
   held-out question, extraction, manifest, or first-pass artifact. The production
   default remains violation-conditioned, and no community-45 payload was
   inspected. After all checks passed, the replacement digest above was
   recorded; all earlier digests are historical only.

The hashed evaluation surface consists of `backend/src`,
`backend/pyproject.toml`, `backend/uv.lock`, Python programs below `experiments`
(excluding `experiments/results`), the static
`data/pilots/heldout-v1-plan.json`, and both the surface-hash and guarded
unblinding scripts. The plan itself has SHA-256
`435c27971027c0f8ef3bbfe3c48713cc3afd80993e8bdc6ca050314e16768416` and
binds the complete task census, pinned inputs, all output paths, model name,
provider-endpoint digest, transport mode, zero temperature, retry budgets, and
serial execution without storing a credential. Documentation, mutable protocol
state, run outputs, and answer-bearing evaluator inputs remain outside the
surface. Any implementation change after unblinding creates a new, separately
labeled development round; it must not overwrite the first-pass result.

The later `backend/deployment` package is an operational wrapper outside this
declared surface: it adds public HTTP retention, deletion, and cache policy by
implementing the core's existing persistence boundary. It does not enter the
held-out runner, which imports `backend/src/askdu` directly. In contrast, the
demo/rehearsal surface hash includes both the wrapper and frozen core so a user
trial cannot silently substitute a different deployed system.

The generated `data/pilots/heldout-v1-questions.json`, extracted community data,
`data/manifests/coda-community-45-extracted.sha256`, and all run/score outputs
are Git-ignored and explicitly denied by the sanitized artifact builder. The
non-answer-bearing frozen protocol record remains publishable. This boundary
was exercised before unblinding with synthetic same-path sentinels only.

## Permitted development evidence

- Synthetic in-memory tables and fake model responses.
- The already inspected community_43 and community_52 tasks and data.
- Provider connectivity tests that contain no held-out material.
- Downloading and checksum-verifying the opaque community_45 archive without
  listing or extracting it.

## Evaluation order after implementation freeze

1. With a fresh server-side credential, run the public-community provider smoke
   and `make heldout-preflight HELDOUT_FREEZE_SHA256=<recorded-digest>`. The
   latter checks the frozen surface, opaque input hashes, paths, and exact
   non-secret model configuration without listing or extracting the archive.
2. Only after explicit author authorization, the guarded command verifies the
   same invariants, mechanically redacts the pinned benchmark metadata to task
   IDs plus question text, and extracts the held-out archive. The redactor must
   parse the source metadata to produce that file, but neither the model runner
   nor its prompt receives answers, guidelines, or reference code.
3. Record a SHA-256 manifest for every regular file below the complete extracted
   root. Immediately before model-service construction, independently verify
   the manifest hash, file count, exact file census, and every file digest.
4. Execute all 13 questions once, in frozen order and serially, with the fixed
   model, endpoint digest, decoding parameters, prompt version, compilation
   attempts, repair budget, and environment. Creating `FIRST_PASS_STARTED.json`
   is the irreversible first-pass marker; an incomplete run is never retried
   under the first-pass label.
5. Seal every generated pre-oracle file, verify the task/configuration bindings,
   and atomically advance the protocol to `first_pass_sealed` before opening an
   oracle. A fully written seal whose protocol update was interrupted may only
   recover that identical state transition; it does not call the model again.
6. The scorer accepts only `first_pass_sealed`, writes an exclusive
   oracle-opening marker, verifies the benchmark hash, computes exact and
   numeric-token scores, and atomically advances to `scored`. If only the final
   state update was interrupted, it must reproduce the existing score exactly;
   duplicate scoring is refused.
7. Publish every task result, including failures and abstentions. Do not tune on
   these first-pass failures while retaining the “held-out” label.

## Claim policy

Until the above run is complete, the paper must describe this evaluation as
planned and retain the current narrow claim boundary. A successful first pass
would provide evidence for unseen-task transfer within one new CoDA community;
it would still not establish arbitrary Web-scale discovery or universal data
analysis.
