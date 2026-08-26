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
- 2026-08-26 | candidate: CacheSeedConfirmationMode | outcome: discard | lesson: Caching seed-confirmation mode passed all stages but slowed timed total to 2633.15 ms/event; repeated configuration reads were not the bottleneck.
- 2026-08-26 | candidate: CacheCompatibleSeedLimit | outcome: discard | lesson: Caching the compatibility-seed limit passed all stages and measured 2508.55 ms/event, but it regressed ambiguity track efficiency to 0.574723 and was not a meaningful improvement over the simpler active base.
- 2026-08-26 | candidate: CacheDeltaRMin | outcome: discard | lesson: Caching deltaRMin passed all stages but slowed timed total to 2523.59 ms/event and slightly reduced ambiguity track efficiency to 0.575407.
- 2026-08-26 | candidate: CacheExperimentCutsDelegate | outcome: discard | lesson: Caching the experiment-cuts delegate passed all stages but slowed timed total to 2535.01 ms/event; keep the direct configuration access.
- 2026-08-26 | candidate: CacheCurvatureVectorReference | outcome: discard | lesson: Caching the curvature vector reference for sorting passed all stages but slowed timed total to 2532.65 ms/event; the direct accessor was already optimized.
- 2026-08-26 | candidate: RemoveUnusedLoggerParameter | outcome: crash | lesson: The helper's logger parameter is required by ACTS_VERBOSE macros even though ordinary code does not reference it; the compile fix restored the active tree and the retry passed with no implementation change.
- 2026-08-26 | candidate: CacheTripletFilterScalars | outcome: discard | lesson: Caching scalar cuts and weights passed all stages but slowed timed total to 2585.30 ms/event; retain direct configuration access.
- 2026-08-26 | candidate: CacheTripletCandidateVectorViews | outcome: discard | lesson: Caching candidate vector references passed all stages but slowed timed total to 2590.33 ms/event; the container accessors were already inexpensive.
- 2026-08-26 | candidate: CacheTripletFilterZRReferences | outcome: discard | lesson: Caching bottom and middle ZR references passed all stages but slowed timed total to 2531.16 ms/event; proxy column access was not a bottleneck.
- 2026-08-26 | candidate: RemoveInsufficientTopVerboseLog | outcome: discard | lesson: Removing the insufficient-top diagnostic log passed all stages but slowed timed total to 2670.31 ms/event; retain the existing logging on that early-return path.
- 2026-08-26 | candidate: AvoidAbsInRadiusCompatibility | outcome: discard | lesson: Replacing absolute-value radius checks with range comparisons passed all stages but slowed timed total to 2682.47 ms/event; retain the original abs checks.
- 2026-08-26 | candidate: RemoveCompatibleSeedReserve | outcome: discard | lesson: Removing the compatible-seed reserve call passed all stages but slowed timed total to 2587.78 ms/event; reserve capacity before the loop.
- 2026-08-26 | candidate: SkipSingletonTripletSort | outcome: discard | lesson: Skipping sort for singleton candidate sets passed all stages but slowed timed total to 2599.93 ms/event; retain the unconditional sort.
- 2026-08-26 | candidate: AvoidBottomProxyCopy | outcome: discard | lesson: Binding bottom-doublet proxies by forwarding reference passed all stages but slowed timed total to 2601.42 ms/event; retain the value iteration.
- 2026-08-26 | candidate: IndexedTopDoubletLoops | outcome: crash | lesson: Direct indexing works for Range and Subset but not Subset2, whose index type is IndexAndCotTheta; the compile retry restored the zip traversal and the no-op retry measured 2538.30 ms/event.
- 2026-08-26 | candidate: IteratorIndexedTopDoubletLoops | outcome: discard | lesson: Explicit iterator-plus-counter loops compiled and preserved all stages, but timed total worsened to 2648.93 ms/event; retain zip traversal.
- 2026-08-26 | candidate: RemoveNoCompatibleTopsVerboseLog | outcome: discard | lesson: Removing only the no-compatible-tops log passed all stages but slowed timed total to 2760.32 ms/event; retain this diagnostic log.
- 2026-08-26 | candidate: ExplicitBestSeedQualityUpdates | outcome: discard | lesson: Replacing the initializer-list loop with direct map updates passed all stages but slowed timed total to 2530.81 ms/event; the compiler already handles the small loop efficiently.
- 2026-08-26 | candidate: DeferTopSpacePointLookup | outcome: discard | lesson: Applying curvature bounds before the other top-space-point lookup passed all stages but slowed timed total to 2617.45 ms/event; retain the existing lookup order.
- 2026-08-26 | candidate: ClassicTopCandidateSort | outcome: discard | lesson: Replacing ranges::sort with std::sort passed all stages but slowed timed total to 2586.35 ms/event; retain ranges::sort.
- 2026-08-26 | candidate: ClassicCandidateHeapAlgorithms | outcome: discard | lesson: Replacing ranges heap algorithms with classic iterator-based calls passed all stages but slowed timed total to 2675.49 ms/event; retain ranges heap operations.
- 2026-08-26 | candidate: HoistStripCotThetaCut | outcome: discard | lesson: Hoisting the invariant strip cot-theta tolerance calculation passed all stages but slowed timed total to 2601.29 ms/event; retain the local calculation.
- 2026-08-26 | candidate: SkipSingletonDoubletSort | outcome: discard | lesson: Skipping ranges::sort for singleton doublet ranges passed all stages but slowed timed total to 2732.24 ms/event; retain the unconditional sort.
- 2026-08-26 | candidate: ResizeDoubletSortStorage | outcome: discard | lesson: Reusing doublet sort storage with resize and indexed writes passed all stages but slowed timed total to 2775.23 ms/event; retain clear, reserve, and emplace_back.
- 2026-08-26 | candidate: ClassicDoubletCotThetaSort | outcome: discard | lesson: Replacing the doublet cot-theta ranges::sort with std::sort passed all stages but slowed timed total to 2624.83 ms/event; retain ranges::sort.
- 2026-08-26 | candidate: RemoveDoubletSortReserve | outcome: discard | lesson: Removing the doublet sort-index reserve call passed all stages but slowed timed total to 2758.58 ms/event; retain reserve before rebuilding the vector.
- 2026-08-26 | candidate: MemberProjectionDoubletSort | outcome: discard | lesson: Using a member-pointer projection for cot-theta sorting passed all stages but slowed timed total to 2833.08 ms/event; retain the lambda projection.
- 2026-08-26 | candidate: EmplaceDoubletScalarFields | outcome: discard | lesson: Replacing scalar doublet push_back calls with emplace_back passed all stages but slowed timed total to 2583.44 ms/event; retain push_back.
- 2026-08-26 | candidate: CacheDoubletCotThetaLimit | outcome: discard | lesson: Caching the doublet cot-theta limit passed all stages but slowed timed total to 2759.76 ms/event; retain direct configuration access.
- 2026-08-26 | candidate: InPlaceCandidateReplacement | outcome: discard | lesson: Updating retained candidate fields in place passed all stages but slowed timed total to 2604.16 ms/event; retain temporary TripletCandidate2 assignment.
- 2026-08-26 | candidate: CacheTopCandidateCount | outcome: discard | lesson: Caching the top-candidate count passed all stages but slowed timed total to 2557.08 ms/event; retain direct size access.
- 2026-08-26 | candidate: CacheBestSeedQualityMap | outcome: discard | lesson: Caching the best-seed-quality map reference passed all stages but slowed timed total to 2659.73 ms/event; retain direct state access.
- 2026-08-26 | candidate: SingleBestQualityMapLookup | outcome: keep | lesson: Using unordered_map::emplace insertion results removed a duplicate lookup, passed all stages, improved ambiguity track efficiency to 0.575458, and reduced timed total to 2499.84 ms/event.
- 2026-08-26 | candidate: BranchBestQualityUpdate | outcome: discard | lesson: Replacing std::max with an explicit comparison passed all stages but slowed timed total to 2606.03 ms/event; retain std::max after the emplace lookup.
- 2026-08-26 | candidate: TryEmplaceBestQualityMap | outcome: discard | lesson: Replacing emplace with try_emplace passed all stages but slowed timed total to 2651.65 ms/event; retain emplace in the active single-lookup path.
- 2026-08-26 | candidate: CacheFinalCandidateCollector | outcome: discard | lesson: Caching the candidate collector reference in final filtering passed all stages but slowed timed total to 2543.97 ms/event; retain direct state access.
- 2026-08-26 | candidate: TernaryBestQualityLookup | outcome: discard | lesson: Rewriting the best-quality map lookup as a ternary return passed all stages but slowed timed total to 2537.79 ms/event; retain the explicit branch.
- 2026-08-26 | candidate: DirectCandidateStorageSize | outcome: discard | lesson: Replacing the candidate size accessor with direct storage size passed all stages but slowed timed total to 2634.74 ms/event; retain the accessor.
- 2026-08-26 | candidate: PushSortedCandidateOutput | outcome: discard | lesson: Replacing emplace_back with push_back for sorted candidate copies passed all stages but slowed timed total to 2516.98 ms/event; retain emplace_back.
- 2026-08-26 | candidate: SkipEmptyCandidateHeaps | outcome: discard | lesson: Skipping sort_heap calls for empty candidate heaps passed all stages but slowed timed total to 2628.46 ms/event; retain unconditional heap sorting.
- 2026-08-26 | candidate: CompileQualityPushPaths | outcome: discard | lesson: Templating the quality flag in candidate pushes passed all stages but slowed timed total to 2598.46 ms/event; retain the runtime quality argument.
- 2026-08-26 | candidate: CacheCompatibleSeedLimitOnMapParent | outcome: discard | lesson: Caching compatSeedLimit from the improved map parent passed all stages but slowed timed total to 2665.24 ms/event and reduced ambiguity track efficiency to 0.575515; retain direct configuration access.
- 2026-08-26 | candidate: ReuseSortedCandidateOutputCapacity | outcome: discard | lesson: Removing the sorted-output reserve call passed all stages but slowed timed total to 2594.88 ms/event; retain reserve before copying candidates.
