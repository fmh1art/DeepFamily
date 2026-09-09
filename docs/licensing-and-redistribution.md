# Licensing and redistribution boundary

Status date: 2026-09-06. This is an engineering release audit, not legal
advice. It records the evidence available at the pinned revisions and chooses
the conservative packaging policy for Ask, Don't Upload.

## Release decision

The public source artifact may contain only project-owned source, manifests,
documentation, tests, and small project-owned specifications. It must not
contain downloaded CoDA-Bench community archives or extracted files, local
clones of the three supporting repositories, supporting-paper PDFs, model
weights, runtime state, provider configuration, or held-out contents.

The checksum-pinned `acmart.cls`, `pvldb.sty`, and
`ACM-Reference-Format.bst` paper-template files are also treated as local
upstream build caches rather than project-owned source. They are ignored by
Git and excluded from every artifact. `make paper-assets` obtains them from the
pinned official VLDB template revision and verifies exact hashes before a
paper build. This avoids applying the future root license to the LPPL-derived
`acmart.cls` or silently assuming a redistribution grant for `pvldb.sty`.

Reproducers obtain the public pilot data from its upstream repository by
running `make pilot-assets`; the downloader verifies the pinned revision and
archive/per-CSV checksums. The deployed Web application may analyze the
server-side copy, but must not expose a bulk-download endpoint for the
underlying source files.

This policy is stricter than the labels on most pilot sources. It avoids
treating the CoDA-Bench dataset-card license as a sublicense for every nested
Kaggle or government dataset.

## Project-owned code

There is currently no root `LICENSE`. Until the authors choose one, the
repository is not an authorized public software release and
`scripts/build_artifact_bundle.sh --public` must refuse to build it.

The authors should choose the copyright holder and license explicitly. Two
common candidates are Apache-2.0, which includes an express patent grant and a
notice mechanism, and MIT, which is shorter and matches two supporting code
repositories. This document does not make that choice on the authors' behalf.

### Engineering recommendation pending author approval

For the project-owned source artifact, the current engineering recommendation
is **Apache-2.0**. Its official terms include both an express copyright grant
and an express contributor patent grant with a patent-litigation termination
condition ([Apache-2.0, Sections 2--3](https://www.apache.org/licenses/LICENSE-2.0)).
That explicit patent treatment is useful for a data-system artifact that may
receive multiple contributions. The current package contains no copied source
from CoDA-Bench, DeepPrep, or DeepAnalyze, so there is no technical need to
choose MIT merely to match two upstream reference repositories. MIT remains a
reasonable alternative if the owners prioritize its much shorter notice and
accept that it contains no comparable express patent-license section; the
canonical OSI text is available at
[opensource.org/license/mit](https://opensource.org/license/mit).

This recommendation is not authorization to add a license. Before doing so,
the authors must confirm:

1. the exact legal copyright-holder string and year;
2. that every project-owned file may be licensed by that holder, including any
   applicable university or employer IP policy;
3. that no unattributed source or generated asset was copied from DeepPrep or
   another unlicensed source; and
4. whether to adopt Apache-2.0 or MIT after considering any institutional
   release requirements.

If Apache-2.0 is selected, use the unmodified official license text and add a
small top-level `NOTICE` identifying only genuine project/third-party
attributions. Apache's application guidance describes the top-level
`LICENSE`, source notices, and `NOTICE` treatment
([ASF guidance](https://www.apache.org/legal/apply-license)). A root license
governs only the project-owned work: it does not relicense Python/npm
dependencies, downloaded data, or Debian/Alpine packages, and it does not
close the separate container-OS review gate.

The proposed scope is the project-owned software, configuration, tests, and
engineering documentation—not the paper manuscript or its publication
figures. `paper/main.tex` and project-authored paper figures should receive a
separate `paper/COPYRIGHT.md` aligned with the eventual PVLDB publication
agreement; the current template footer anticipates CC BY-NC-ND 4.0 and cannot
be silently replaced by the software license. This scope split also needs
author approval before release.

After a choice is made, the release checklist is:

1. add the unmodified license text at repository root and confirm the exact
   copyright holder and year;
2. identify any files whose ownership or license differs from the root;
3. rerun the checked application/container inventory, retain required notices,
   and complete the remaining manual OS-package review before publishing
   container images;
4. run `make artifact-public`, inspect the member list, and archive its
   checksum alongside the tagged source revision.

## Pinned production dependency inventory

The deterministic evidence file
`experiments/evidence/dependency-license-inventory-v0.4.0.json` was generated
from the two actual production images plus the checked lockfiles. Its SHA-256
is `4dbbdd6e48edc35cb84070d26be194076a1c57a886de6ca04e611cbdca78af30`.
Running the following command rebuilds the digest-pinned images, then inspects
them with container networking disabled and rejects any version, license-label,
lockfile, Dockerfile, or package-census drift:

```bash
make dependency-license-audit
```

The captured scope and result are deliberately narrower than a legal opinion:

- the API runtime has 40 third-party Python distributions. Every distribution
  has a license expression, short license field, or OSI classifier in its
  installed metadata. Six entries (`certifi`, `numpy`, `python-dateutil`,
  `sniffio`, `tqdm`, and `uvloop`) are routed to manual notice review because
  their metadata is reciprocal, compound, dual, or has multiple classifiers;
- the shipped Web bundle has three production npm packages (`react`,
  `react-dom`, and `scheduler`), all recorded as MIT in the lockfile;
- the final API image contains 105 Debian packages, all with an installed
  `/usr/share/doc/<package>/copyright` file. Their license expressions have not
  been normalized, so compatibility and notice obligations remain manual;
- the final Web image contains 21 Alpine packages, all with an `apk` license
  field. Twelve reciprocal or compound labels are highlighted for manual
  review; a highlighted label is a review route, not a claim of incompatibility;
- build-only Node and `uv` stages are not part of the final runtime layers. In
  particular, the API Dockerfile now copies only the built virtual environment,
  rather than shipping the `uv` and `uvx` executables and build cache.

The evidence therefore closes application-level metadata completeness and
drift detection. It does **not** declare the container images legally cleared,
replace the license texts, determine whether aggregation creates derivative
works, or satisfy source/notice obligations automatically. Before publishing
images, the authors must have counsel or a qualified reviewer inspect the exact
base-image notices and assemble the required notices/source-offer materials.
`make dependency-audit` and `make image-vulnerability-audit` are separate
point-in-time vulnerability lookups for locked application dependencies and
final production images, respectively; neither answers licensing questions.

The exact same JSON is shipped as the read-only Web record
`/notices/dependency-license-inventory-v0.4.0.json`. The audit rejects a byte or
semantic mismatch between that public copy and the canonical evidence. The
site's **Data & software notice** links this record and the current environment
provenance API; neither endpoint exposes source-data bytes.

## Supporting research repositories

The supporting repositories are ignored local clones and are not vendored in
the artifact.

| Asset | Pinned revision | Evidence at that revision | Current treatment |
|---|---|---|---|
| [CoDA-Bench](https://github.com/ruc-datalab/CoDA-Bench) | `24f2eee08c60d3a6826654ed39a621631b68a73a` | Top-level MIT license; README separately warns that individual Kaggle datasets may have their own licenses. | Reference, cite, and download externally. Preserve its MIT notice if code is copied in the future. |
| [DeepPrep](https://github.com/ruc-datalab/DeepPrep) | `0b6e4431def5364e9bf23a255c6e44a4034e2e8a` | No top-level license file or license statement was found. Public visibility alone is not a reuse grant. | Design reference only; do not copy or redistribute code without permission or a later explicit license. |
| [DeepAnalyze](https://github.com/ruc-datalab/DeepAnalyze) | `d14468b9ef91372359ddcd70da57e0e0f4eb0d1b` | Top-level MIT license. | Reference only in the current implementation. Preserve its MIT notice if code is copied in the future. |

No source file from these clones is included by the current explicit artifact
allowlist. Architectural inspiration and scientific attribution are handled
through the paper citations and the contribution-boundary documentation, not
through silent code copying.

## Public pilot data audit

The audit covers only the already-opened `community_43` and `community_52`
pilots. It deliberately does not inspect `community_45`.

The `dataset-metadata.json` files packaged in the pinned public communities
label ten sources as `CC0-1.0`, one as `CC BY 4.0`, and one as `unknown`.
Those labels are recorded as provenance, not independently verified title
opinions. The CoDA-Bench dataset card is marked MIT, while its repository
explicitly says individual Kaggle datasets can have separate licenses.

| Community | Source dataset | Packaged label / attribution evidence | Redistribution decision |
|---|---|---|---|
| 43 | [2017--2018 SHSAT Admissions Test Offers by Schools](https://www.kaggle.com/datasets/infocusp/2017-2018-shsat-admissions-test-offers-by-schools) | `unknown`; Kaggle owner `infocusp` | Do not redistribute in this artifact; upstream download only unless the rightsholder later supplies permission. |
| 43 | [Data Science for Good: PASSNYC](https://www.kaggle.com/datasets/passnyc/data-science-for-good) | `CC0-1.0` | Upstream download only under the project-wide conservative policy. |
| 43 | [Fastfood Nutrition](https://www.kaggle.com/datasets/ulrikthygepedersen/fastfood-nutrition) | `CC BY 4.0`; creator `Ulrik Thyge Pedersen` | Upstream download only. If later redistributed, retain creator/source/license attribution and identify modifications. |
| 43 | [NY GED Plus Locations](https://data.cityofnewyork.us/d/pd5h-92mc) | Mirror says `CC0-1.0`; official metadata attributes NYC Department of Education | Upstream download only; preserve agency/source provenance in reports. |
| 43 | [2010--2016 School Safety Report](https://data.cityofnewyork.us/d/qybk-bjjc) | Mirror says `CC0-1.0`; official metadata attributes NYC Department of Education | Upstream download only; preserve agency/source provenance in reports. |
| 43 | [Queens Library Branches](https://data.cityofnewyork.us/d/kh3d-xhq7) | Mirror says `CC0-1.0`; official metadata attributes Queens Library | Upstream download only; preserve agency/source provenance in reports. |
| 43 | [School District Breakdowns](https://data.cityofnewyork.us/d/g3vh-kbnw) | Mirror says `CC0-1.0`; official metadata attributes NYC DYCD | Upstream download only; preserve agency/source provenance in reports. |
| 43 | [NYSERDA LMI Census Population Analysis](https://data.ny.gov/d/bui8-bb6g) | Mirror says `CC0-1.0`; official metadata attributes NYSERDA and notes Census-derived data | Upstream download only; retain source and statistical-limitations context in reports. |
| 43 | [Shake Shack Nutritional Information](https://www.kaggle.com/datasets/prasertk/shakeshack) | `CC0-1.0`; Kaggle owner `prasertk` | Upstream download only. |
| 52 | [Health Insurance Coverage in the USA, 1979--2019](https://www.kaggle.com/datasets/asaniczka/health-insurance-coverage-in-the-usa-1979-2019) | `CC0-1.0`; Kaggle owner `asaniczka` | Upstream download only. |
| 52 | [USA Unemployment Rates by Demographics and Race](https://www.kaggle.com/datasets/asaniczka/unemployment-rates-by-demographics-1978-2023) | `CC0-1.0`; Kaggle owner `asaniczka` | Upstream download only. |
| 52 | [Wages by Education in the USA, 1973--2022](https://www.kaggle.com/datasets/asaniczka/wages-by-education-in-the-usa-1973-2022) | `CC0-1.0`; Kaggle owner `asaniczka` | Upstream download only. |

Relevant interpretation boundaries:

- [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) permits sharing and
  adaptation subject to attribution, a license link, and modification notice;
  it does not clear unrelated privacy, publicity, or trademark rights.
- [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) is a copyright
  waiver to the extent allowed by law; it does not waive patent, trademark,
  privacy, or publicity rights.
- [NYC Open Data terms](https://opendata.cityofnewyork.us/overview/) say users
  also accept provider-specific terms and that datasets are informational and
  provided without warranties. Its FAQ states that Open Data use is
  unrestricted.
- [OPEN-NY terms](https://data.ny.gov/api/views/77gx-ii52/files/ef0c1840-ad54-4240-92fd-6397c49fde46?filename=OPEN-NY_20Terms_20of_20Use.pdf)
  describe reuse without attribution, share-alike, or preapproval requirements,
  subject to lawful use.

## Product and paper obligations

Implemented controls:

- `coda-public-source-provenance-v1.json` binds the two public environments to
  the benchmark revision, archive and checksum-manifest digests, source records,
  and the project-wide download-only policy; startup rejects inconsistent
  counts, unsafe paths, or a modified checksum manifest.
- The downloader checks all extracted public-pilot CSVs, and the runtime checks
  every selected registered CSV again before Preparation. A mismatch fails
  closed and its internal detail is redacted from public API responses. An
  unlisted CSV is excluded from Discovery in a registered environment, while a
  missing registered CSV fails catalog readiness.
- Catalog/source cards and generated Markdown reports expose dataset title,
  upstream URL, provider/creator, declared-or-unknown license metadata,
  content digest, integrity status, and download-only treatment. The API also
  carries the registered expected digest. Unregistered
  catalogs explicitly receive no inferred license.
- The versioned API and Web UI expose no source-data or bulk-download route;
  the artifact builder excludes downloaded data and third-party clones.
- The deployed page contains a visible **Data & software notice** that
  distinguishes project ownership, external data, and dependencies. Its public
  machine-readable inventory is checked against the release evidence.

Remaining release obligations:

- Complete the manual Debian/Alpine package review described above and package
  all required notices before distributing either container image. A passing
  metadata-drift check is necessary evidence, not legal clearance.
- Paper citations establish scholarly attribution but do not replace software
  license notices or dataset-license compliance.
- The held-out archive stays governed by `docs/heldout-protocol.md`; license
  review begins only after explicit unblinding authorization and must happen
  before any held-out payload is published.
- Re-run this audit against the exact release revisions immediately before a
  public artifact or container image is published, because upstream metadata
  and terms can change.
