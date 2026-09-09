# Non-author rehearsal records

Copy `record.example.json` to a `YYYY-MM-DD-<session>.json` file only after an
actual session, then replace every example value. The filename date must match
`occurred_at`. Do not record a participant's name, email, private question
text, audio, or screen capture in this directory.

Use the participant-facing prompts and facilitator scoring rules in:

- `participant-task-card.md`; and
- `facilitator-protocol.md` (`askdu-non-author-rehearsal-v1`).

Immediately before the session, record both the source-bound demo digest and
the exact prompt/scoring-protocol digest:

```bash
make rehearsal-surface
make rehearsal-protocol
```

Put those values in `demo_surface_sha256` and `trial_protocol_sha256`; keep
`trial_protocol_id=askdu-non-author-rehearsal-v1`. Also record the exact browser,
CSS-pixel viewport, zoom, and three observed task timings. The surface digest covers
the production UI, backend implementation and dependencies, Compose/proxy
path, and registered public-data checksums. It deliberately excludes generated
output, documentation, tests, private configuration, and downloaded bytes.
The protocol digest separately covers the participant prompts, facilitator
correction rules, pass criteria, and its own hashing method. If either covered
surface changes after the session, rerun the affected rehearsal; do not make
stale evidence appear current by merely replacing a digest.

Preflight a completed record before relying on it:

```bash
make rehearsal-check REHEARSAL_RECORD=/absolute/path/to/2026-09-06-p01.json
```

The command reports malformed evidence separately from a well-formed session
that did not meet the gate. `make readiness-draft` then validates every
non-example record. The acceptance gate requires at least one consenting
non-author with no prior project exposure to:

- complete all six tasks without facilitator correction;
- repeat the core path without correction;
- distinguish a completed report from a typed diagnosis;
- leave no blocking issue unresolved; and
- record the three requested task timings (without imposing a performance
  threshold).

The separate repeat is task 960 and is not a seventh task Boolean; its result
is recorded in `repeat_core_path_without_facilitator_correction`.

Each of the six Boolean task outcomes must agree with the aggregate completed
count. Every issue needs a pseudonymous code, severity (`blocks`, `confuses`,
or `cosmetic`), status (`open` or `resolved`), and short non-identifying
summary; the number of open blocking issues must match the aggregate count.

This is a formative usability rehearsal record, not a formal user study or
evidence of general analytical effectiveness.
