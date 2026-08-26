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
- 2026-08-26 | candidate: RemoveTripletCandidateVerboseLog | outcome: keep | lesson: Removing the disabled hot-path candidate-count log preserved all stages, lowered timed total to 2512.69 ms/event, and slightly improved ambiguity track efficiency to 0.575438.
- 2026-08-26 | candidate: RemoveTripletEmptyPathLogs | outcome: discard | lesson: Removing the two empty-path diagnostic logs passed all stages but produced a slower 2654.12 ms/event timed result than the active base; keep the active implementation unchanged.
- 2026-08-26 | candidate: RemoveRepeatedTripletReserve | outcome: discard | lesson: Removing reserve() calls passed all stages and raised ambiguity track efficiency to 0.575841, but timed total worsened to 2612.74 ms/event; vector growth cost outweighed the call savings.
- 2026-08-26 | candidate: RemoveSeedCountVerboseLog | outcome: discard | lesson: Removing the final per-middle seed-count log passed all stages but slowed timed total to 2581.54 ms/event; keep only the earlier hot-path log removal.
- 2026-08-26 | candidate: RemoveSeedCreationVerboseLog | outcome: discard | lesson: Removing per-seed verbose logging passed all stages but slowed timed total to 2575.68 ms/event; the earlier candidate-count log removal remains the only beneficial logging change.
- 2026-08-26 | candidate: CacheTopRadiusMode | outcome: discard | lesson: Caching the top-radius mode preserved all stages and improved ambiguity track efficiency to 0.575778, but timed total worsened to 2580.20 ms/event; keep the simpler configuration access.
