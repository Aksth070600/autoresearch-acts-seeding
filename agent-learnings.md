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
