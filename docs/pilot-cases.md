# Representative pilot cases

Status date: 2026-09-06. P1--P4 are downloaded and execute end to end. The full
test census additionally covers ten no-repair questions and one local data gap
in `community_43`, plus two single-source questions in `community_52`. These
registered deterministic families support a mechanism claim only, not general
effectiveness.

## P1 — Missing analytical dimensions triggers Discovery

- Source: CoDA-Bench `community_43`, task 959.
- Input: a question asking for Pearson correlations between SHSAT test-taker
  counts and Asian, Black/Hispanic, and White percentages for Grade 8 in 2016.
- First source: `D5 SHSAT Registrations and Testers.csv`.
- Downstream violation: the source contains the target count, year, and grade,
  but none of the demographic percentage measures.
- Repair: reopen Discovery and add `2016 School Explorer.csv`.
- Preparation: normalize percentages; filter grade/year; join `DBN` to
  `Location Code`; record match coverage and materialized row count.
- Analysis: execute the three correlations and link outputs to artifacts.
- Expected benchmark answer: retained only as an evaluation oracle and never
  exposed to the discovery or analysis components.

This is a real progressive-acquisition case. The first source is useful rather
than simply wrong, and downstream requirements force a new source decision.

## P2 — Missing filter dimension triggers Discovery

- Source: CoDA-Bench `community_43`, task 175.
- Required sources: the SHSAT registration/tester table and School Explorer.
- First source: SHSAT registration/tester data supplies year and grade.
- Downstream violation: `Economic Need Index` is absent.
- Repair: reopen Discovery, add School Explorer, join on `DBN` to
  `Location Code`, then remove missing Economic Need Index rows.
- Executed result: 21 records, exactly matching the benchmark oracle.

## P3 — Missing demographic dimensions triggers Discovery

- Source: CoDA-Bench `community_43`, task 955.
- Required sources: SHSAT offers and School Explorer.
- First source: the SHSAT offers table supplies offer outcomes and school DBNs.
- Downstream violation: the required Black/Hispanic, White, and Asian
  percentage columns are absent.
- Repair: add School Explorer and join `School DBN` to `Location Code`.
- Executed result: `38.94%`, `30.35%`, and `28.34%`, exactly matching the
  benchmark oracle.

## P4 — Missing category coverage triggers Discovery

- Source: CoDA-Bench `community_43`, task 960.
- Question scope: find burger calorie extrema across Shake Shack, McDonald's,
  and Burger King, plus the minimum-calorie Shake Shack burger.
- First source: `shake shack nutrition.csv`, which is useful for the second
  part but cannot cover the other requested restaurants.
- Downstream violation: `missing_category_coverage` names McDonald's and Burger
  King as unresolved categories.
- Repair: reopen Discovery and add `fastfood.csv`, then normalize both source
  schemas into restaurant/item/calories.
- Executed result: `American Brewhouse King; 1550; Veggie Shack, vegan,
  lettuce wrap`, exactly matching the benchmark oracle.

## Stopping controls

- Task 179 asks for attendance fields from
  `schproma/source/schma19962016.csv`, which is absent from the pinned archive.
  It must terminate with `data_gap` and no report.
- An unregistered question must terminate with `capability_gap`; it must not be
  mislabeled as missing data.
- The ten no-repair questions must complete without any backward lifecycle
  edge. This guards against a controller that performs repair theatrically on
  every run.

## Evidence rule

A current pilot counts as closed-loop only when a recorded downstream check
produces a typed violation and the subsequent branch changes a source decision,
then rematerializes Preparation and Analysis. Curated distractors are permitted for repeatability, but the failure
must be possible from the unmodified downloaded environment and disclosed as a
pilot design choice.

Aggregate results and the two benchmark reference-code conflicts are recorded
in `docs/evaluation.md`.
