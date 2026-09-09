# Non-author demo rehearsal record

Use one copy per participant. Do not record names, email addresses, or the text
of private analytical questions. Obtain the participant's agreement before
screen/audio recording. This is a formative demo rehearsal, not a human-subject
effectiveness study unless the authors obtain the applicable institutional
approval.

The JSON field `consent_recorded` refers to agreement to participate in this
formative rehearsal. It does not authorize screen/audio capture; obtain and
retain any separate recording permission outside this repository.

## Session metadata

- Date/time and timezone:
- Build/version:
- Trial protocol ID: `askdu-non-author-rehearsal-v1`
- Trial protocol SHA-256 (`make rehearsal-protocol` immediately before the session):
- Demo surface SHA-256 (`make rehearsal-surface` immediately before the session):
- Browser and screen size:
- CSS-pixel viewport and browser zoom:
- Local/container/ECS deployment:
- Facilitator code:
- Participant code:
- Database/data-analysis familiarity (self-rated 1–5):
- Prior exposure to the project: yes / no

## Tasks and unassisted repeat

Give the participant `docs/user-trials/participant-task-card.md` and follow
`docs/user-trials/facilitator-protocol.md`. Do not paraphrase its prompts or
explain panel semantics. Record one Boolean for each of these six task IDs:

1. `identify_question_only_input`
2. `launch_verified_question`
3. `explain_insufficient_initial_source`
4. `locate_backward_repair_edge`
5. `trace_report_claim_to_evidence`
6. `explain_honest_data_gap`

After the six tasks, administer the task-960 unassisted repeat exactly as
printed on the participant card. Record it separately as
`repeat_core_path_without_facilitator_correction`.

## Observations

| Measure | Result |
|---|---|
| Completed tasks without facilitator correction | /6 |
| Time to first run | |
| Time to locate the repair edge | |
| Time to locate claim evidence | |
| Correctly distinguished report vs diagnosis | yes / no |
| Accidental clicks or dead ends | |
| Facilitator interventions and reason | |

## Short interview

Record paraphrases, not identifiable quotations, unless explicit quotation
consent was obtained.

1. What did the system do after you supplied the question?
2. What convinced—or failed to convince—you that the reported value was
   grounded in executed data?
3. Was the backward repair understandable without explanation?
4. Which label or panel was most confusing?
5. What would you try next at a conference booth?

## Issue triage

| Pseudonymous issue code | Non-identifying summary | Severity (blocks/confuses/cosmetic) | Status (open/resolved) | Reproducible steps / proposed change |
|---|---|---|---|---|
| | | | | |

## Acceptance gate

Before calling the demo rehearsed, at least one non-author participant should
finish the six tasks, the team should resolve all blocking issues, and the
participant should repeat the core path without facilitator correction. Report
the number and scope of these rehearsals accurately; do not describe them as a
formal user study without an approved protocol and an appropriate design.

After resolving the session's issues, copy
`docs/user-trials/record.example.json` to a date-matched
`YYYY-MM-DD-<session>.json` record and enter only pseudonymous aggregate
outcomes. Run
`make rehearsal-check REHEARSAL_RECORD=/absolute/path/to/the-record.json`
before relying on it. `make readiness-draft` rejects direct identity fields,
email-like values, inconsistent task/issue counts, and records from either a
stale demo surface or a different prompt/scoring protocol. If covered source
or protocol text changes, repeat the affected rehearsal rather than editing a
recorded digest.
