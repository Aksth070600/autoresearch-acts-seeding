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
- 2026-08-26 | candidate: TripletRareDivisionHint | implementation_commit: 6d1645b11a37b0ed04209c28bc2ac28c6eb9f8a8 | mechanism_key: triplet-branch-prediction | files_changed: optimization-files/Core/src/Seeding2/TripletSeedFinder.cpp#L222-L226 | outcome: keep | lesson: Marking the pixel dU-zero guard unlikely passed all stages with particle ambiguity efficiency 0.972769 and lowered median timed total to 2424.08 ms/event; retain the branch hint.
- 2026-08-26 | candidate: FilterFloatAbs | implementation_commit: 916bb976347416a12bc22e6f473c939f83af99df | mechanism_key: filter-absolute-value | files_changed: optimization-files/Core/src/Seeding2/BroadTripletSeedFilter.cpp#L202-L212 | outcome: discard | lesson: Replacing float std::abs with std::fabs passed all stages with unchanged particle ambiguity efficiency but raised median timed total to 2444.48 ms/event; retain std::abs.
- 2026-08-26 | candidate: SeederTopLoopPrune | implementation_commit: 93bdfae25876feaf6298a819bb05ee8d23490fdb | mechanism_key: seeder-empty-loop-pruning | files_changed: optimization-files/Core/src/Seeding2/TripletSeeder.cpp#L29-L37 | outcome: keep | lesson: Removing the redundant top-doublet emptiness check passed all stages with particle ambiguity efficiency 0.972769 and lowered median timed total to 2365.56 ms/event; retain the simpler loop.
- 2026-08-26 | candidate: DoubletZRangeHint | implementation_commit: 85e49f983b8e1f7e365158f9d388b19306b1d04e | mechanism_key: doublet-branch-prediction | files_changed: optimization-files/Core/src/Seeding2/DoubletSeedFinder.cpp#L138-L141 | outcome: keep | lesson: Marking the doublet z-range rejection unlikely passed all stages with particle ambiguity efficiency 0.972769 and lowered median timed total to 2357.88 ms/event; retain the hint.
- 2026-08-26 | candidate: CandidateHeapRejectHint | implementation_commit: 9a5b8d33f410d687bda53bc6df2e98a1958d0bca | mechanism_key: candidate-heap-branch-prediction | files_changed: optimization-files/Core/src/Seeding2/detail/CandidatesForMiddleSp2.cpp#L60-L65 | outcome: discard | lesson: Marking rejected full heaps unlikely passed all stages with particle ambiguity efficiency 0.972769 but raised median timed total to 2483.18 ms/event; retain the unhinted comparison.
- 2026-08-26 | candidate: CandidateStorageInPlace | implementation_commit: 62b31ce50737541b2aadf87229ef11a66bc50b85 | mechanism_key: candidate-storage-update | files_changed: optimization-files/Core/src/Seeding2/detail/CandidatesForMiddleSp2.cpp#L67-L77 | outcome: discard | lesson: Updating retained candidate fields individually passed all stages with particle ambiguity efficiency 0.972769 but raised median timed total to 2436.02 ms/event; retain aggregate assignment.
- 2026-08-26 | candidate: GridSingletonSortSkip | implementation_commit: 6b06cb7c9ce848386a496aed163224aedef37590 | mechanism_key: grid-bin-sort | files_changed: optimization-files/Examples/Algorithms/TrackFinding/src/GridTripletSeedingAlgorithm.cpp#L151-L158 | outcome: discard | lesson: Skipping sort for singleton grid bins passed all stages with particle ambiguity efficiency 0.972769 but raised median timed total to 2469.91 ms/event; retain unconditional ranges::sort.
