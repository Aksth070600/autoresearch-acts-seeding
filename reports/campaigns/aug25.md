# Campaign review: `aug25`

This is a retrospective campaign review prepared from the autonomous trial report so the campaign can be inspected through GitHub.

## Campaign

- Campaign branch: `autoresearch-acts-seeding/aug25`
- Baseline: fresh Genesis development run
- Experiments: one mutation candidate
- Candidate: `SkipEmptyTripletFilter`
- Original implementation commit: `660d764`
- Original lesson commit: `9e87070`

The original trial ran in a disposable worktree. Its generated JSON summaries were not committed before cleanup, so this retrospective report is evidence copied from the surviving audit report, not a replacement machine-generated record.

## Hypothesis

`filter.filterTripletTopCandidates(...)` has no useful work when triplet construction produces zero candidates. Skipping that call should save setup and dispatch work without changing physics results.

## Implementation

The candidate added a size check around the triplet candidate filter call in:

`optimization-files/Core/src/Seeding2/TripletSeeder.cpp`

The change was committed before evaluation. The experiment lesson was recorded separately in `agent-learnings.md`.

## Development result

All four development stages passed. The two 50-event stages completed all events with the expected two unmasked floating-point exceptions.

| Stage | Metric | Genesis | Candidate | Difference |
| --- | --- | ---: | ---: | ---: |
| Clean | Total time/event | 2635.97 ms | 2688.65 ms | +52.68 ms (+2.00%) |
| Clean | Seeding time/event | 303.39 ms | 299.19 ms | -4.20 ms (-1.38%) |
| Clean | Seeding efficiency | 0.983625 | 0.983618 | -0.000007 |
| Clean | CKF efficiency | 0.974246 | 0.974695 | +0.000449 |
| Clean | Ambiguity efficiency | 0.973668 | 0.974116 | +0.000448 |
| Timed | Total time/event | 2730.23 ms | 2736.20 ms | +5.97 ms (+0.22%) |
| Timed | Seeding time/event | 303.17 ms | 296.96 ms | -6.21 ms (-2.05%) |
| Timed | Seeding efficiency | 0.983644 | 0.983646 | +0.000002 |
| Timed | CKF efficiency | 0.974624 | 0.974471 | -0.000153 |
| Timed | Ambiguity efficiency | 0.973995 | 0.973806 | -0.000189 |

## Assessment

The candidate reduced seeding time but increased total full-chain time. It is not a demonstrated overall improvement. The candidate is a useful follow-up hypothesis, but it should be measured again before promotion.

## Process observations

- The agent completed setup and exactly one mutation experiment.
- `make evolve` returned Genesis because no distinct eligible historical candidate existed.
- The agent correctly formed a hypothesis from the current implementation.
- Expected FPE handling worked as documented.
- The original process did not publish the branch, commits, or generated summaries to GitHub. This review PR demonstrates the intended presentation format after the fact.
