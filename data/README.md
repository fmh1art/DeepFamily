# Data layout

Only manifests, documentation, and deliberately small fixtures belong in Git.
Downloaded datasets remain local because CoDA-Bench is large and its source
datasets can have their own licenses.

The source-by-source public-pilot audit and the download-only redistribution
policy are recorded in `docs/licensing-and-redistribution.md`.

- `external/`: immutable downloads from third parties.
- `derived/`: profiles, indexes, and other reproducible derivatives.
- `pilots/`: checked-in pilot specifications; no copied source data.
- `manifests/`: archive pins, per-CSV SHA-256 manifests, and the audited public
  source-provenance registry used by downloader and runtime integrity gates.

The registered pilots use CoDA-Bench `community_43` and `community_52`.
Reproduce both pinned archives with
`scripts/fetch_research_assets.sh --coda-pilots` (`--coda-pilot` remains a
backward-compatible alias). The command verifies each archive before safe
extraction and then verifies all 13 extracted CSVs against their community
manifest. Registered runtime environments repeat the selected-file check
before Preparation; source bytes are never part of the project artifact.

The main `agentic` Demo instead searches the **30-community open release**,
pinned by `manifests/coda-bench-v1-open-release.json`: 30,292 discoverable files
(16,315 CSVs), 196 source datasets and 996 open-runtime tasks. Use
`make coda-open-status` to inspect installation coverage and
`make coda-open-assets` to install/verify the open communities. Allow at least
210 GB free space. This path excludes sealed community 45 even if its archive
is present locally. The two small public pilots reproduce the controlled
registry experiments; they are not the complete Discovery pool.

The prospectively selected held-out set is `community_45`. Download its opaque
archive with `scripts/fetch_research_assets.sh --coda-heldout`. This command
verifies the checksum but intentionally does not list or extract the archive;
follow `docs/heldout-protocol.md` before unblinding it. The mutable state record
is `pilots/heldout-v1.json`; its checksum-bound static companion,
`pilots/heldout-v1-plan.json`, is part of the implementation hash and freezes
the selection, paths, input pins, and non-secret execution configuration.
