# Research asset inventory

Status date: 2026-09-06. Repositories were cloned from their official public
locations with the current session proxy. No model weights were downloaded.

| Asset | Official source | Pinned revision | Local role | Reuse status |
|---|---|---|---|---|
| CoDA-Bench code | `https://github.com/ruc-datalab/CoDA-Bench` | `24f2eee08c60d3a6826654ed39a621631b68a73a` | Task schema, evaluator, discovery environment | MIT; code can be reused with notice |
| CoDA-Bench data | `https://huggingface.co/datasets/RUC-DataLab/CoDA-Bench` | `63828a2b652e26a9770555a0cc41e6c8aafdb5d9` | Primary Discovery workload | Dataset card says MIT; the public pilot source audit is complete, but individual data remain download-only |
| DeepPrep code | `https://github.com/ruc-datalab/DeepPrep` | `0b6e4431def5364e9bf23a255c6e44a4034e2e8a` | Design reference for materialized states and backtracking | No top-level license found; do not copy into the public system until clarified |
| DeepAnalyze code | `https://github.com/ruc-datalab/DeepAnalyze` | `d14468b9ef91372359ddcd70da57e0e0f4eb0d1b` | Analysis/report and Docker-sandbox reference | MIT; reusable with notice |

## Downloaded pilot

The local data directory contains CoDA-Bench metadata plus the pinned
`community_43` and `community_52` archives. Archive checksums are stored in
`coda-community-43.sha256` and `coda-community-52.sha256`; extracted CSVs are
independently pinned in `coda-community-43-csv.sha256` and
`coda-community-52-csv.sha256`. The audited mapping from each source directory
to its upstream record, provider/creator, and declared-or-unknown license label
is `coda-public-source-provenance-v1.json`. All five files live under
`data/manifests/` and are included without source bytes in the artifact.

The archive contains 31 files after extraction (about 88 MiB), including 10
CSV files across nine noisy source directories. It supplies 15 benchmark tasks.
The archive itself contains a `data/community_43` prefix; the local downloader
normalizes it to `data/external/coda-bench/communities/community_43`.

The `community_52` archive is 84,441 bytes and expands to six files (about
348 KiB), including three CSV files. It supplies two transfer-probe tasks in a
different data domain and is normalized to the corresponding `communities/`
directory by the same safe extractor.

The downloader verifies the archive before extraction and then checks every
extracted public-pilot CSV against its per-file manifest. At runtime, each
selected registered file is checked again before Preparation. This binds the
reported execution to the audited bytes; it does not grant redistribution
rights, so the source data remain external and download-only.

The prospectively selected `community_45` archive is 11,166,232 bytes with
SHA-256 `756b7c3cdd7ca207186d98cc8bbba6e86913f1a360893611c2052ba892768280`.
It was downloaded only after the selection record was written and remains
opaque: it has not been listed or extracted. Its 13 tasks are reserved by
`data/pilots/heldout-v1.json`; the unblinding guard is documented in
`docs/heldout-protocol.md`.

## Availability findings

- CoDA-Bench v1.0 advertises 1,009 tasks, 31 communities, and about 43 GB of
  compressed community data. Development therefore uses community-level,
  revision-pinned downloads rather than a full snapshot.
- The DeepPrep README links more than one Hugging Face dataset identifier. At
  audit time, `RUC-DataLab/DP-Synthesized` returned HTTP 401 without
  authentication. This dataset is not required for the first pilot.
- DeepAnalyze model weights and training data are intentionally omitted. The
  codebase includes a server-side OpenAI-compatible adapter and bounded model
  planner, but the reported deterministic pilots do not instantiate or call it.
- The supplied API credential must never be committed. Before public
  deployment, rotate any credential previously shared in chat and inject the
  replacement through the ECS secret/environment configuration.

## Attribution boundary

The new project does not claim CoDA-Bench's benchmark construction,
DeepPrep's preparation-tree contribution, or DeepAnalyze's autonomous report
generation as new. Its target contribution is the cross-stage sufficiency
contract and the controller that turns downstream evidence into upstream data
repair.

The source-by-source evidence and enforced packaging decision are recorded in
`docs/licensing-and-redistribution.md`. In particular, neither the public pilot
data nor the three local research clones are bundled with a project release.
