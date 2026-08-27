# CompositePositiveV1 Development campaign

## Contract

This is a one-candidate, Development-only composite campaign under protocol `acts-seeding-v2`. It uses ACTS v46.5.0, ITk `ttbar_pu200`, HEPP02, seed 42, pileup 200, one ACTS thread, 10 events, and three timed repetitions aggregated by median. Evaluation and every 50-event workload are excluded.

The historical comparison is the latest compatible existing Development Genesis at `records/Development/20260827T110406490471Z-Genesis/summary.json`. It measured 296.03 ms/event timed seeding and 0.972769 timed ambiguity particle efficiency. It was run at 2026-08-27T11:04:06Z and was not rerun for this campaign.

The strongest prior compatible candidate is `TripletReserveElision` at `records/Development/20260827T155328Z-TripletReserveElision/summary.json`. It measured 277.38 ms/event timed seeding and 0.972769 timed ambiguity particle efficiency.

## Inclusion rule

A mechanism is positive here only if its archived candidate was marked `keep`, completed the compatible Development protocol, improved a current primary objective against that campaign's historical Genesis or accepted active base, and did not reduce timed ambiguity particle efficiency. An improvement in diagnostic full-chain timing alone is not enough.

The implementation commits below were inspected directly. Source line ranges are the ranges recorded for those commits in `agent-learnings.md`.

## Accepted evidence inventory and inclusion matrix

| Source campaign | Source candidate and implementation commit | Exact source symbols and files | Timed seeding / efficiency | Included | Reason |
| --- | --- | --- | --- | --- | --- |
| v3 | `MapEmplaceSingleLookup` [`0155cb01`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/0155cb01d2f69992290d8870acc7ab23c7af6866) | `setBestSeedQuality`; `optimization-files/Core/src/Seeding2/BroadTripletSeedFilter.cpp#L38-L43` | 297.81 / 0.972769 | No | The v3 Genesis was 296.87 ms/event. The archived keep decision used full-chain timing, which is diagnostic under the current objectives. |
| v3 | `TripletRareDivisionHint` [`6d1645b1`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/6d1645b11a37b0ed04209c28bc2ac28c6eb9f8a8) | `Impl::createPixelTripletTopCandidates`; `optimization-files/Core/src/Seeding2/TripletSeedFinder.cpp#L222-L226` | 297.46 / 0.972769 | No | Did not improve timed seeding against v3 Genesis. |
| v3 | `SeederTopLoopPrune` [`93bdfae2`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/93bdfae25876feaf6298a819bb05ee8d23490fdb) | `createAndFilterTriplets`; `optimization-files/Core/src/Seeding2/TripletSeeder.cpp#L29-L37` | 301.20 / 0.972769 | No | Did not improve timed seeding. Later shared-storage work also changes this seeder flow. |
| v3 | `DoubletZRangeHint` [`85e49f98`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/85e49f983b8e1f7e365158f9d388b19306b1d04e) | `Impl::createDoubletsImpl`; `optimization-files/Core/src/Seeding2/DoubletSeedFinder.cpp#L138-L141` | 302.46 / 0.972769 | No | Did not improve timed seeding. |
| v3 | `CandidateHeapCapacityHint` [`faa85600`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/faa856008b5be5d2400b89fb8a1c01f554ebdadb) | `CandidatesForMiddleSp2::push`; `optimization-files/Core/src/Seeding2/detail/CandidatesForMiddleSp2.cpp#L52-L58` | 300.78 / 0.972769 | No | Did not improve timed seeding. `CandidateLinearSmallSet` supersedes heap maintenance at the same seam with primary-objective evidence. |
| v3 | `FilterSelfCandidateHint` [`bd325dc6`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/bd325dc678ea2a305363489dc8115341302c8f59) | `BroadTripletSeedFilter::filterTripletTopCandidates`; `optimization-files/Core/src/Seeding2/BroadTripletSeedFilter.cpp#L179-L183` | 299.11 / 0.972769 | No | Did not improve timed seeding. |
| v4 | `DoubletBinaryRadiusWindow` [`a493107c`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/a493107c52919489162a15b72e7e7bdab5299406) | `Impl::createDoubletsImpl`; `optimization-files/Core/src/Seeding2/DoubletSeedFinder.cpp#L14-L15,L74-L84` | 298.85 / 0.972769 | No | The v4 Genesis was 298.06 ms/event. The archived keep decision used diagnostic full-chain timing. |
| v4 | `DoubletErrorColumnLayout` [`c1bfddd0`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/c1bfddd037d5ea4b5b677277778fb26834d17bd3) | `DoubletsForMiddleSp::clear/emplace_back`, `Proxy::er/iDeltaR`, storage; `optimization-files/Core/include/Acts/Seeding2/DoubletSeedFinder.hpp#L44-L50,L62-L68,L132-L136,L258-L261` | 302.47 / 0.972769 | No | Did not improve timed seeding. The included identity-pair layout has primary-objective evidence at the same storage seam and preserves the Genesis error pair. |
| v4 | `FilterCurvatureLowerBound` [`7241f1f9`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/7241f1f9cb73de55b768a4147524a24b96d4f62e) | `BroadTripletSeedFilter::filterTripletTopCandidates`; `optimization-files/Core/src/Seeding2/BroadTripletSeedFilter.cpp#L174-L205` | 302.58 / 0.972769 | No | Did not improve timed seeding. |
| v4 | `TripletCandidateAoS` [`aec446a2`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/aec446a2a5beb07be7bf2d7d1714be518b87542c) | `TripletTopCandidates`, `BroadTripletSeedFilter::filterTripletTopCandidates`; `optimization-files/Core/include/Acts/Seeding2/TripletSeedFinder.hpp#L29-L58,L104-L108`, `optimization-files/Core/src/Seeding2/BroadTripletSeedFilter.cpp#L146-L207` | 300.84 / 0.972769 | No | Did not improve timed seeding. |
| v4 | `SeederEmptyGroupPrune` [`57b3a257`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/57b3a2571813146fd1898c74e2662df759d54cb0) | `createSeedsFromGroupsImpl`; `optimization-files/Core/src/Seeding2/TripletSeeder.cpp#L55-L83` | 298.48 / 0.972769 | No | Did not improve timed seeding. The included unified-storage implementation has stronger primary-objective evidence at this flow seam. |
| v5 | `DoubletIdentityPairLayout` [`ccb89a13`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/ccb89a13b0a0033bb73fd92865e78e0a21e374d4) | `DoubletsForMiddleSp::clear/emplace_back/sortByCotTheta`, `Proxy::spacePointIndex/cotTheta`, storage; `optimization-files/Core/include/Acts/Seeding2/DoubletSeedFinder.hpp#L35-L126,L251-L254` | 296.07 / 0.972769 | Yes | Improved v5 Genesis 297.05 ms/event with unchanged efficiency. Identity records feed the included insertion traversal without changing ordering semantics. |
| v5 | `CandidateLinearSmallSet` [`ad70a71e`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/ad70a71eea648389e5bbec6aa1171cb881b3bce9) | `CandidatesForMiddleSp2::push/toSortedCandidates`; `optimization-files/Core/src/Seeding2/detail/CandidatesForMiddleSp2.cpp#L52-L81` | 294.14 / 0.972769 | Yes | Improved the accepted v5 base with unchanged efficiency and supersedes heap hints at the same seam. |
| v6 | `DoubletInsertionSort` [`776df4d2`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/776df4d2d1f54c3e05ead9c8cc3f4b56559a1e50) | `DoubletsForMiddleSp::sortByCotTheta`; `optimization-files/Core/include/Acts/Seeding2/DoubletSeedFinder.hpp#L101-L110` | 284.50 / 0.972769 | Yes | Improved v6 Genesis 296.03 ms/event with unchanged efficiency. |
| v6 | `CoreBatchSpacePointMaterialization` [`59e7fb57`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/59e7fb575596a7adc2936cd40bf1b06a6303b79a) | `SpacePointContainer2::createSpacePoints`, `GridTripletSeedingAlgorithm::execute`; `optimization-files/Core/include/Acts/EventData/SpacePointContainer2.hpp#L113-L117`, `optimization-files/Core/src/EventData/SpacePointContainer2.cpp#L174-L183`, `optimization-files/Examples/Algorithms/TrackFinding/src/GridTripletSeedingAlgorithm.cpp#L162-L180` | 282.07 / 0.972769 | Yes | Improved the accepted v6 base with unchanged efficiency. |
| v6 | `SeederUnifiedDoubletStorage` [`5d231ed0`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/5d231ed0dfeb23bc8954290146ea3fdd38ddda88) | `TripletSeeder::Cache::doublets`, `createSeedsFromGroupsImpl`; `optimization-files/Core/include/Acts/Seeding2/TripletSeeder.hpp#L28-L30`, `optimization-files/Core/src/Seeding2/TripletSeeder.cpp#L55-L101` | 281.42 / 0.972769 | Yes | Improved the accepted v6 base with unchanged efficiency. |
| v6 | `GridCoreRangeViewCache` [`a44b3b89`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/a44b3b89ea2373bc03549d272c43bf4505daa530) | `GridTripletSeedingAlgorithm::execute`; `optimization-files/Examples/Algorithms/TrackFinding/src/GridTripletSeedingAlgorithm.cpp#L183-L188,L279-L284` | 281.05 / 0.972769 | Yes | Improved the accepted v6 base with unchanged efficiency. |
| v6 | `GridBinInsertionSort` [`291adb85`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/291adb8541df26a3c49d6e198f63d31533bf952a) | `GridTripletSeedingAlgorithm::execute`; `optimization-files/Examples/Algorithms/TrackFinding/src/GridTripletSeedingAlgorithm.cpp#L151-L164` | 280.79 / 0.972769 | Yes | Improved the accepted v6 base with unchanged efficiency. |
| v6 | `DoubletMiddleDataflowRecord` [`08c31790`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/08c3179067db9812607368c22355f8be3e46ec80) | `MiddleSpInfo`, `computeMiddleSpInfo`, `createDoubletsImpl`; `optimization-files/Core/include/Acts/Seeding2/DoubletSeedFinder.hpp#L281-L287`, `optimization-files/Core/src/Seeding2/DoubletSeedFinder.cpp#L49-L54,L356-L357` | 279.99 / 0.972769 | Yes | Improved the accepted v6 base with unchanged efficiency. |
| v6 | `TripletReserveElision` [`27b8954c`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/27b8954c18329c01da4e2b75f671916cf7713d92) | `Impl::createPixelTripletTopCandidates`; `optimization-files/Core/src/Seeding2/TripletSeedFinder.cpp#L161-L166` | 277.38 / 0.972769 | Yes | Improved the accepted v6 base with unchanged efficiency and is the strongest prior candidate. |

No two of the nine included mechanisms are mutually exclusive in source. `DoubletIdentityPairLayout` and `DoubletInsertionSort` overlap `sortByCotTheta`; the composite preserves the identity record and applies insertion traversal to the derived index/cotangent sequence. This is an implementation compatibility judgment only. The composite run is the first scientific evidence for their combined result.

## Composite proposal

- Candidate: `CompositePositiveV1`
- Stable mechanism key: `composite-positive-v1`
- Implementation commit: [`ec49bd1`](https://github.com/Aksth070600/autoresearch-acts-seeding/commit/ec49bd1)
- Changed symbols: `DoubletsForMiddleSp` storage and `sortByCotTheta`; `MiddleSpInfo`; `DoubletSeedFinder::computeMiddleSpInfo` and `Impl::createDoubletsImpl`; `TripletSeeder::Cache` and `createSeedsFromGroupsImpl`; `CandidatesForMiddleSp2::push/toSortedCandidates`; `SpacePointContainer2::createSpacePoints`; `GridTripletSeedingAlgorithm::execute`; `Impl::createPixelTripletTopCandidates`.
- Expected hot path: combine accepted layout, short-list traversal, batch allocation, range-view reuse, shared storage, middle-data reuse, bounded linear selection, and reserve-policy mechanisms across seeding.
- Novelty: this is the first controlled composite of all source-compatible mechanisms with accepted evidence on the current primary objective. No source campaign measured the combination.

## Development result

Exactly one controlled Development run completed. All requested stages passed. Each timed repetition processed all 10 events; the existing expected-unmasked-FPE rule accepted one unmasked FPE only after all events completed.

Timed seeding repetitions were 280.31, 278.96, and 280.71 ms/event. Their median was 280.31 ms/event. Timed ambiguity particle efficiency was 0.972769 in every repetition.

| Comparison | Timed seeding | Difference | Timed ambiguity particle efficiency | Difference |
| --- | ---: | ---: | ---: | ---: |
| Historical latest compatible Genesis, 296.03 ms/event | 280.31 ms/event | -15.72 ms (-5.31%) | 0.972769 | 0 |
| Strongest prior `TripletReserveElision`, 277.38 ms/event | 280.31 ms/event | +2.93 ms (+1.06%) | 0.972769 | 0 |

The composite improves the historical Genesis primary timing objective without reducing the efficiency objective. It does not beat the strongest prior candidate. The positive effects were not additive under combination.

Diagnostic-only median timing was 2134.99 ms/event for CKF and 2447.54 ms/event for the selected full-chain sum. Historical Genesis measured 2200.93 and 2531.34 ms/event, while `TripletReserveElision` measured 2084.53 and 2392.56 ms/event. These diagnostics do not change the primary-objective assessment.

- Record: `records/Development/20260827T173333Z-CompositePositiveV1/summary.json`
- Outcome: keep as a Genesis improvement, then restore by campaign contract for archive publication.
- Lesson: source-compatible improvements can interact non-additively. Preserve `TripletReserveElision` as the stronger prior seeding result rather than assuming that adding the v5 layout and selection mechanisms improves its timing.
- Genesis comparison is historical. It was not rerun concurrently.
