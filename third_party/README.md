# Third-party research assets

The source repositories in this directory are local, ignored clones. They are
not vendored into the Ask, Don't Upload codebase. Exact revisions and reuse
constraints are recorded in `docs/asset-inventory.md` and
`docs/licensing-and-redistribution.md`.

This separation is intentional:

- CoDA-Bench supplies benchmark tasks and noisy data environments.
- DeepPrep supplies design ideas for execution-grounded preparation search.
- DeepAnalyze/DA-Studio supplies reusable analysis and sandbox patterns.
- Ask, Don't Upload owns the analytical-sufficiency contract, lifecycle state,
  cross-stage repair controller, API, and user experience.
