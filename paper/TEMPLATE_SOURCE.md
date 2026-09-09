# Template provenance and local fetch policy

The following local build-cache files are synchronized with the official
`vldbproceedings/VLDB-Template` repository and contain no project-owned
semantic changes:

- `acmart.cls`
- `pvldb.sty`
- `ACM-Reference-Format.bst`

Source: https://github.com/vldbproceedings/VLDB-Template

Pinned upstream commit: `39c95f5c6fcbe652a83be24e4eff8f2134cd3fbc`

Fetched: 2026-09-06

They are intentionally ignored by Git and excluded from both preview and
public Ask, Don't Upload artifacts. `acmart.cls` is a generated LPPL work whose
header refers distributors to `acmart.dtx`; the pinned VLDB repository does
not include that source file or a repository-level license for `pvldb.sty`.
The project therefore does not place these upstream files under its future
root code license or redistribute them as if they were project-owned.

Restore them directly from the pinned official revision with:

```bash
make paper-assets
```

`scripts/fetch_paper_template.sh` first refuses to overwrite a modified local
copy, retries once without environment proxy variables if needed, and verifies
the following SHA-256 values before installation:

| File | Local SHA-256 |
|---|---|
| `acmart.cls` | `2f949e6e3f2a79f2cdc218b9dcdbaa7dd451adb4ee0be1af6dc7ebe00b318ea7` |
| `pvldb.sty` | `bbf67313dfc26c82c71160e073ed23f826cb4f85a1359dc6eebcb276dbeb5354` |
| `ACM-Reference-Format.bst` | `0590db3b8d255a3af91982ab710f3ace5fcaa52434020c9af8a4f141b00b68f3` |

The `acmart.cls` bytes were independently regenerated from the upstream
`acmart` v2.19 tag (`062edc8119be9067a346ce874281eab48b2c29a4`) and matched exactly. Its
source declares LPPL 1.3-or-later, copyright 2016--2026 Association for
Computing Machinery, and Boris Veytsman as current maintainer. The bibliography
style identifies itself as public domain. These upstream rights remain
separate from the project license.

The custom `main.tex` preserves the mandatory `\usepackage{pvldb}` and
`\vldbtopmatter` blocks from the template. Vendor template files must remain
semantically identical to the pinned source; compatibility is provided by the
containerized TeX toolchain rather than by patching those files.

`scripts/check_submission.sh` pins the byte-level local copies. The local
`pvldb.sty` adds only a final POSIX newline because the upstream file omits one;
its TeX content is otherwise identical at the pinned commit.

`paper/Dockerfile` pins its TeX Live base image by digest and installs missing
packages from the frozen TeX Live 2024 repository. `make pdf-modern` builds the
image, then compiles with networking disabled. Before submission, compare the
pinned commit with the official repository and update all vendor files together
if the proceedings chairs release a newer template.
