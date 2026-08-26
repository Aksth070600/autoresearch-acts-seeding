# Agent Learnings

Keep this file concise and actionable. The campaign starts with no carried-over
candidate lessons after the generated evidence reset.

## Candidate provenance policy

Every new candidate lesson must record:

- the candidate name;
- the full implementation commit;
- every exact implementation file touched by that commit; and
- the line ranges as they existed in that candidate commit.

Include a stable `mechanism_key` so renamed duplicates are detectable. Use this
format:

```text
- YYYY-MM-DD | candidate: <name> | implementation_commit: <full-sha> | mechanism_key: <stable-family-key> | files_changed: <path>#L<start>-L<end>[, <path>#L<start>-L<end>] | outcome: <keep/discard/crash> | lesson: <one actionable lesson>
```

Derive the exact file list from the candidate commit with:

```text
git diff-tree --no-commit-id --name-only -r <commit>
```

Inspect each changed file at that commit with `git show <commit>:<file>` and
`nl -ba`; do not reuse line numbers from the current tree. Before editing a
file and line range that overlaps an earlier candidate lesson, a future agent
must run `git show <commit> -- <file>` and read the relevant commit before
editing. This prior-commit review applies even when a candidate was rejected.

Do not record raw logs or scientific metrics that were not produced by a
completed controlled run. Keep this file below 500 lines. At 250 lines, invoke
the simplification skill to merge duplicate lessons, remove stale details, and
keep it below the hard limit.

- 2026-08-26 | candidate: MapEmplaceSingleLookup | implementation_commit: 0155cb01d2f69992290d8870acc7ab23c7af6866 | mechanism_key: best-quality-map-insertion | files_changed: optimization-files/Core/src/Seeding2/BroadTripletSeedFilter.cpp#L38-L43 | outcome: keep | lesson: Replacing find-then-emplace with one emplace passed all stages, kept particle ambiguity efficiency at 0.972769, and lowered median timed total to 2564.52 ms/event from the Genesis 2575.60 ms/event.
