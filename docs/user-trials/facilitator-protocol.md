# Ask, Don't Upload — non-author rehearsal protocol

Protocol ID: `askdu-non-author-rehearsal-v1`

This is a formative usability rehearsal of the conference demonstration, not
a controlled user study and not evidence of open-ended analytical accuracy.
Use the participant task card verbatim. Do not add hints that make a failed
interface appear successful.

## Eligibility and preflight

Use one consenting non-author who has not previously seen the project. Record
only a pseudonymous participant code. Do not store a name, email address,
private analytical question, recording, or identifying quotation in the
repository.

Immediately before the session:

1. run `make rehearsal-surface` and `make rehearsal-protocol`;
2. record both digests, version `0.4.0`, deployment, browser version, CSS-pixel
   viewport, and zoom in the session sheet;
3. confirm `/readyz`, prewarm task 959 outside the participant session, then
   open a fresh browser context at the landing page with no result visible;
4. give the participant `participant-task-card.md`; and
5. start timing only at the anchors below.

If the service, browser, or input device fails, record a blocking issue and
reschedule. A screenshot, persisted JSON, or fallback video is valid for booth
recovery but cannot replace participant interaction in this rehearsal.

## What counts as facilitator correction

The facilitator may repeat the printed prompt verbatim or resolve a physical
accessibility problem identified before the affected task starts. Any of the
following is a correction, and the affected Boolean task result must be
`false`:

- pointing to, scrolling to, naming, or activating the relevant control/panel;
- choosing a pilot, entering text, or operating the participant's browser;
- paraphrasing the intended answer, defining a UI label, or explaining the
  workflow before the participant answers; or
- telling the participant that their current interpretation is right or wrong
  before they finish the task.

Record accidental clicks and dead ends as observations even when the
participant recovers without a correction.

## Timing anchors

- `time_to_first_run`: from reading task 2 until the participant activates
  **Run hands-off analysis** for task 959.
- `time_to_locate_repair_edge`: from the task-959 terminal result becoming
  visible until the participant satisfies task 4.
- `time_to_locate_claim_evidence`: from reading task 5 until the participant
  identifies both the executed artifact and supporting source evidence.

Record observed seconds without rounding them into a performance claim. A
missing timing makes the rehearsal ineligible for the acceptance gate, but no
speed threshold is imposed.

## Pass criteria for the six task Booleans

1. `identify_question_only_input`: says that the task input is an analytical
   question and that no dataset/file, table, schema, or join path is required.
2. `launch_verified_question`: selects task 959 and starts it without a
   correction; the run reaches a terminal state.
3. `explain_insufficient_initial_source`: explains that the initial SHSAT
   source lacks the requested demographic variables/dimensions. Saying only
   “there was an error” is insufficient.
4. `locate_backward_repair_edge`: points to the visible
   `Analysis -> Discovery` revisit and identifies the missing-variable trigger.
5. `trace_report_claim_to_evidence`: selects a numeric report claim and locates
   its executed artifact/materialized result plus the supporting source
   profiles. Recalling the coefficient without navigating the evidence fails.
6. `explain_honest_data_gap`: identifies task 179's terminal output as a typed
   diagnosis with no released report and explains that required evidence is
   absent from the authorized environment, rather than calling it a crash.

Set `repeat_core_path_without_facilitator_correction=true` only if the
participant completes the separate task-960 repeat without correction,
recognizes its category-coverage repair, and traces one claim to evidence.
Set `correctly_distinguished_report_and_diagnosis=true` only if their answers
to tasks 5 and 6 clearly distinguish those outcomes.

## Issue triage and closeout

- `blocks`: prevents a task or causes an incorrect report/diagnosis
  interpretation;
- `confuses`: participant finishes without correction but misreads or must
  repeatedly search for a label/control; and
- `cosmetic`: visual or copy defect that does not impede the path.

Resolve every blocking issue, update the demo, and rerun the affected rehearsal
against the new demo-surface digest. Never edit an old record's digest to make
it appear current. After the session, create the pseudonymous JSON record and
run `make rehearsal-check REHEARSAL_RECORD=/absolute/path/to/record.json`.
