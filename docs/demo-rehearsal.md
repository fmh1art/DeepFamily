# Demo rehearsal and video runbook

Status date: 2026-09-09 (Asia/Shanghai). The VLDB 2027 site currently lists
only the Research Track; its Demo CFP and Demo dates are not yet published.
The four-page and optional five-minute-video assumptions below therefore come
from the VLDB 2026 Demo CFP and must be rechecked before submission.

## What the audience should remember

One analytical question is the only task-level input. The system turns it into
an executable Analytical Sufficiency Contract (ASC), progressively discovers
and prepares evidence, and either releases an evidence-linked report or stops
with a typed data-gap diagnosis. The distinctive visual event is a downstream
analysis violation creating an `Analysis -> Discovery` repair edge and a new
materialized state.

The main path now uses the question-only agentic workbench. The registered
offline path remains a separate, reproducible repair demonstration. Live-model
smokes establish that selected questions can traverse the implementation;
they do not establish unseen-domain generalization or universal coverage.

## Main path: real-model question to report

Start this mode from the project root with the private provider key already
configured as described in the README:

```bash
./scripts/run_demo.sh agentic
./scripts/run_demo.sh status
```

Readiness should report `coda-open-v1` and 16,315 CSVs. The environment endpoint
should report `planner_mode=agentic`, 30 installed open communities and 30,292
discoverable files. Keep the browser on the active run throughout processing.

Use the bare Chinese question `最适合移民的国家是哪一个`, whose saved observation is
documented in [the stage I/O validation record](stage-io-validation.md). No dimensions,
weights, filenames, or schemas were included in that task input. The earlier question
in `agentic-smoke-evidence.md` named its dimensions and is a different observation;
do not merge the two runs into a claim about accuracy. The following is an interaction
sequence, not a promise of fixed wall-clock timing:

| Stage | Attendee action | Visible evidence | Technical point |
|---|---|---|---|
| Ask | Enter the question and start once. | A run starts with no selected file or upload. | Only the task goal is supplied. |
| Discovery | Select earlier hops while exploration proceeds. | Current action at left; all communities and encountered files at right; current and earlier paths distinguished. | Routing and inspection precede CSV selection. |
| Preparation | Select a candidate; compare input/output. | Input schemas, operators, actual validation/execution status, prepared schema and five-row preview. | Distinguish a schema-invalid proposal from an executed candidate. |
| Analysis | Inspect SQL/Python and execution outputs. | Code is compiled from the validated plan; executed results link to artifacts. | Debug appears only if an actual execution failure or mismatch occurs. |
| Report | Read the summary, dimension sections, charts/table and conclusion. | Explicit data scope, weighting limitations and evidence references. | Integrated conclusions remain conditional on available evidence. |

The saved bare-question run `run_e2f9348452df475c` has one successful preparation
candidate, four operators, and no schema rejections or Debug cells; it does not
demonstrate non-local backtracking. Its final report uses 2020 data; it does not establish which country
is suitable under current immigration policy. Retain the before-fix run in the
development record: a completed lifecycle alone does not prove report quality.

If the provider is slow, inspect progress while the same request continues.
Switch the presentation to an already completed tab or explicitly labeled
offline fallback when needed; elapsed presentation time does not itself mean
the run has failed. Do not submit duplicate requests just because polling is
quiet. No live-model latency bound has been established.

## Offline fallback preflight

For the agentic stages, [the recorded-run figure pack](agentic-replay-figure.md)
provides current-UI community, preparation, and report views without another
provider call. Each image is labeled as a recorded run, not a live request.
It illustrates one successful preparation path, not backtracking; the separate
registry fallback below exposes the controlled cross-stage repair.

The [144-second recorded agentic video](agentic-video.md) now shows this same bare-question
run through the current UI without calling the provider. It includes community hops,
input/output schemas, the operator path, executed SQL, report sections, a comparison
chart, and the qualified conclusion. It is a silent, captioned sequence of current-UI
excerpts with fixed editorial timing—not continuous live-interaction footage. Generate
it with `make demo-video-agentic` while the loopback agentic Web is already running;
this target never starts or stops Compose. Keep the existing registry video separate.

```bash
./scripts/run_demo.sh
curl --noproxy '*' --fail http://127.0.0.1:8080/readyz
```

Confirm that readiness reports `coda-community-43` and ten CSV assets. Open
`http://127.0.0.1:8080`, choose **Join repair**, and execute it once. Keep these
fallbacks locally available:

- `paper/figures/demo-ui.png` — executed task-959 UI with paper-only A--E section markers;
- `experiments/results/coda-community43/runs/task-959-closed_loop.json` —
  persisted closed-loop state;
- `experiments/results/coda-community43/runs/task-179-closed_loop.json` —
  persisted honest-stopping state;
- `artifacts/demo/fallback-walkthrough.mp4` — automatically assembled,
  captioned stable-frame walkthrough generated by `make demo-video`.

This fallback does not require the provider once its pilot data are installed.
Start it before a separate fallback presentation; changing server mode can
interrupt a still-running agentic request.

## Three-minute offline repair path

| Time | Audience/presenter action | Visible evidence | Spoken point |
|---:|---|---|---|
| 0:00–0:20 | Show the empty workspace and authorized environment. | Ten discoverable assets, pinned revision/archive digest, no attached file. | “The task starts with a question inside an audited data boundary, not a dataset handoff.” |
| 0:20–0:45 | Select **Join repair** and press **Run hands-off analysis**. | ASC obligations; first source with upstream/license metadata and verified digest. | “The question becomes testable obligations, and selected bytes must match the registered source.” |
| 0:45–1:30 | Inspect the lifecycle and **Repair impact** strip. | `missing_analytical_columns`, `Analysis -> Discovery`, report-gated initial state, targeted second source, accepted replay. | “Execution—not another free-form model guess—invalidates the first source decision.” |
| 1:30–2:10 | Scroll to the report, select the Black/Hispanic claim, inspect its lineage, and export the evidence JSON. | 21 joined rows, 100% join coverage, coefficient, executed artifact, materialized state, both checksummed source profiles, and a client-side no-source-row export. | “A report is released only after its obligations pass; every number remains navigable to executed evidence, and that proof can leave the interface without exporting source rows.” |
| 2:10–2:50 | Return to the composer, select **Honest data gap**, and run it. | `data_gap`; no completed report. | “Autonomy includes knowing when the authorized environment cannot support the question.” |
| 2:50–3:00 | Invite a choice between other verified pilots. | Audience controls the next question without choosing data. | “Interaction changes the analytical goal while the data workflow remains hands-off.” |

## Audience interaction and claim boundary

For the current deterministic mode, let an attendee choose among verified
pilots and ask them to predict whether the run will complete, repair, or stop.
Free-form questions use the separate agentic mode described above. Do not
present the registry as a free-form model or silently route an unsupported
question to a hand-authored result.

The presenter may expose persisted state or evidence references, but should not
ask the attendee to fix schemas, choose a join path, or repair the source set;
that would undermine the question-only contract.

## Failure matrix

| Failure | Detection | Recovery shown to the audience |
|---|---|---|
| Browser cannot reach the service | `/readyz` fails | Play `fallback-walkthrough.mp4`; use the two persisted JSON states for questions. |
| Public network/provider fails | Model-mode request fails | Switch to the offline deterministic environment; state that the fallback is a registered mechanism demonstration. |
| Live run exceeds presentation time | Inspect its current persisted status | Present a completed tab or labeled fallback; a pending model call is not a terminal failure. |
| Projector makes text unreadable | UI labels cannot be read from the back | Use 125–150% browser zoom and keep only the lifecycle/source/report panels in view. Automated reflow passes at an effective 150%; this does not replace an in-room sightline check. |
| A question is unsupported | Typed capability/data-gap diagnosis | Treat the diagnosis as an intended terminal outcome and explain the unmet obligation. |

## Draft video pipeline

Run the following from the repository root:

```bash
make demo-video
```

Before the first generation, install Chromium and its host libraries following
Playwright's platform instructions; `ffmpeg` is also required for MP4 encoding.

The target builds and starts the production containers, drives both the repair
and data-gap paths in Chromium, and captures ten lossless screenshots only after
their production UI/API states pass Playwright assertions. It then holds the
title, six captioned steps, caption-free transition/diagnosis, and closing card
for fixed durations, assembles them directly into a broadly playable H.264 MP4,
runs a technical media gate, and always shuts the containers down. Generated
storyboard and video files live under ignored `artifacts/demo/`; they are
evidence/fallback material, not the final narrated submission video or evidence
of continuous interaction timing.

The earlier checked registry fallback (not the current agentic recording) is exactly 70.00 seconds at 1600x900, 25 fps,
H.264/yuv420p, and 4,666,798 bytes. Its current SHA-256 is
`14d70864dbace804fb47dd7589907a1ba98eab34a682a178769bd9da9f2ae5f6`.
The visual review sampled the title, all six captions, the caption-free scenario
transition, the typed diagnosis, and the closing card (2, 7, 14, 22, 30, 42,
49, 52, 55, 59, 66, and 69 seconds). Exact sequentially decoded frames at 55
and 69 seconds were also inspected, and a complete stream decode reported no
errors. These are locally verified build facts, not assumptions about the
still-unpublished VLDB 2027 video limits.

The checked draft intentionally has no audio. The 169-word recording script and
audio handoff checklist are in `docs/video-narration.md`. Set
`ASKDU_ARTIFACT_URL` to the credential-free public HTTPS artifact URL before the
final capture; otherwise the closing card explicitly says that the URL is
pending. After recording one continuous narration track, run:

```bash
make demo-video-narrated NARRATION_FILE=/absolute/path/to/narration.wav
```

The mux is atomic and immediately runs submission mode. That gate requires
exactly one AAC narration stream at 44.1 kHz or higher, checks that it spans the
walkthrough, and measures mean/peak volume so a digital-silence track cannot
pass merely by existing. It additionally checks H.264, 1600x900, yuv420p,
duration, and size. These technical checks do not establish intelligibility,
synchronization, or claim correctness, so two authors must still watch the
complete export with sound. The current 300-second and 50-MiB limits are
provisional 2026 assumptions and can be overridden with `VIDEO_MAX_SECONDS` and
`VIDEO_MAX_BYTES`; replace them after the 2027 CFP is published.
