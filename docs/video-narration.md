# Final narration handoff

Status: author-recording script for the checked 70.00-second fallback video.
This file is not evidence that a final narrated submission video exists.

This 70-second script describes the separate registry repair/data-gap fallback.
For the current question-only agentic UI, use the **144-second** walkthrough and
matching narration handoff in [agentic-video.md](agentic-video.md). Do not mix the
two audio timelines or describe registry footage as a real-model agentic run.

## Read-aloud script

> Ask, Don't Upload starts with an analytical question, not an uploaded table.
> The deployment already knows its authorized data environment, so the user
> supplies no filename, schema, join path, preparation plan, or report outline.
>
> The system compiles the question into an Analytical Sufficiency Contract, then
> discovers and verifies the most relevant source. For the SHSAT question, the
> first table contains 2016 Grade-8 participation counts, but downstream analysis
> reveals that all three requested demographic measures are missing.
>
> That typed violation reopens Discovery. The system adds School Explorer, cleans
> its percentages, joins on the school identifier, and replays analysis over 21
> matched rows with complete join coverage.
>
> Only then does it release the three correlations. Selecting the Black/Hispanic
> claim reveals its executed artifact, materialized table state, and both
> checksummed source profiles.
>
> Finally, an attendance question requires columns from a referenced source that
> is absent from the authorized environment. The system stops with an explicit
> data-gap diagnosis instead of inventing a report.
>
> This deterministic rehearsal demonstrates the closed-loop mechanism, not
> unseen-question generalization.

The script has 169 words. At roughly 144 words per minute it fits the current
walkthrough without racing. Preserve the paper's claim boundary: say neither
“ask anything” nor that the current deterministic registry establishes unseen
question generalization.

Use these scene-aligned targets while recording; they are pacing anchors, not
instructions to splice the narration into separate files:

| Time | Script block | Visible scene |
|---:|---|---|
| 0:00--0:13 | Opening boundary | Title card, then question-only workspace |
| 0:13--0:32 | Contract and first-source insufficiency | Execute and Discover captions |
| 0:32--0:44 | Typed backward repair | Repair-impact comparison |
| 0:44--0:53 | Report evidence | Selected Black/Hispanic claim lineage |
| 0:53--1:06 | Honest stopping | Attendance question and data-gap diagnosis |
| 1:06--1:10 | Claim boundary | Closing card |

## Recording specification

- Record one continuous narration track in a quiet room, without music or
  third-party audio.
- Export WAV, FLAC, or M4A at 48 kHz when possible; mono or stereo is accepted.
- Keep the complete exported track close to 70.00 seconds. The automated mux
  rejects a track shorter than 60% of the video or more than 0.5 seconds longer,
  because either case would hide missing narration or truncate speech.
- Leave modest headroom. The technical gate requires a measured mean of at least
  -50 dB and a peak of at least -30 dB; these thresholds reject digital silence,
  but they do not replace a human intelligibility review.
- Do not speak an artifact URL until the final public, credential-free HTTPS URL
  is fixed and also visible on the closing card.

## Build and review

```bash
make demo-video-narrated NARRATION_FILE=/absolute/path/to/narration.wav
```

The command creates `artifacts/demo/submission-walkthrough.mp4` atomically and
accepts it only after the submission media gate verifies H.264/yuv420p video,
one AAC narration stream, 44.1 kHz or higher audio, timeline coverage, non-silent
levels, duration, and size. To recheck an existing candidate explicitly:

```bash
make video-check \
  VIDEO_CHECK_MODE=submission \
  VIDEO_PATH=artifacts/demo/submission-walkthrough.mp4
```

Finally, two authors should independently watch the entire exported file with
sound enabled and confirm pronunciation, synchronization, claim accuracy,
caption legibility, the data-gap ending, and the final artifact URL. Automated
checks cannot establish those semantic or perceptual properties. Only after
both reviews, copy `docs/video-review.example.json` to
`artifacts/demo/submission-walkthrough.review.json`, replace the video SHA-256,
timestamp and two author codes, and set each check to true. The readiness audit
binds this ignored sidecar to the exact video bytes and rejects a stale review.
