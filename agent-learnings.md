# Agent Learnings

Keep this file concise and actionable.
Record reusable lessons from successful, worse, and failed implementation attempts.
Do not copy raw logs or full metric dumps.

## Entry format

```text
- YYYY-MM-DD | candidate: <name> | outcome: <keep/discard/crash> | lesson: <one actionable lesson>
```

## Maintenance limit

Keep this file below 500 lines.
When it reaches 250 lines, invoke the simplification skill to merge duplicate lessons, remove stale details, and keep it below the hard limit.

- 2026-08-25 | candidate: SkipEmptyTripletFilter | outcome: keep | lesson: Skipping the filter call for empty triplet candidate sets preserved all stages and reduced measured seeding time, but one 50-event run did not improve total full-chain time.
- 2026-08-26 | candidate: RemoveRedundantTopEmptyCheck | outcome: keep | lesson: The helper's repeated top-doublet emptiness branch was redundant after its caller's non-empty guard; removing it passed all stages and improved the timed full-chain result.
- 2026-08-26 | candidate: RemoveBranchAndSkipEmptyFilter | outcome: keep | lesson: Combining both cheap skips passed all stages and reduced timed total to 2543.24 ms/event, but ambiguity track efficiency fell to 0.575228; TripletTopCandidates exposes size(), not empty(), so the compile fix required one retry.
- 2026-08-26 | candidate: ConditionalTripletCandidateClear | outcome: discard | lesson: Guarding clear() on the reusable candidate cache passed all stages and improved ambiguity track efficiency to 0.575471, but timed total was 2600.55 ms/event and did not beat the simpler active base.
