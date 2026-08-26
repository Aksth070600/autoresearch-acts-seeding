# Campaign review: `aug25`

This campaign is now reproduced on the campaign branch with committed machine-generated summaries so the implementation and evidence can be reviewed together on GitHub.

## Campaign

- Campaign branch: `autoresearch-acts-seeding/aug25`
- Baseline: Genesis
- Experiments: one mutation candidate
- Candidate: `SkipEmptyTripletFilter`
- Candidate implementation: `optimization-files/Core/src/Seeding2/TripletSeeder.cpp`
- Candidate history: `1d923ab` and `56fdc8e`
- Genesis summary: `records/Development/Genesis/summary.json`
- Candidate summary: `records/Development/20260825T235218Z-SkipEmptyTripletFilter/summary.json`

The original autonomous trial ran in a disposable worktree. The campaign was rerun to preserve the machine-generated summaries and include the fake and duplicate ratios in this review.

## Hypothesis

`filter.filterTripletTopCandidates(...)` has no useful work when triplet construction produces zero candidates. Skipping that call should save setup and dispatch work without changing physics results.

## Development result

All four development stages passed for both implementations. The two 50-event stages completed all events with the expected two unmasked floating-point exceptions.

| Stage | Metric | Genesis | Candidate | Difference |
| --- | --- | ---: | ---: | ---: |
| Clean | Total time/event | 2625.47 ms | 2691.28 ms | +65.81 ms (+2.51%) |
| Clean | Seeding time/event | 303.25 ms | 296.16 ms | -7.09 ms (-2.34%) |
| Timed | Total time/event | 2728.79 ms | 2711.36 ms | -17.43 ms (-0.64%) |
| Timed | Seeding time/event | 312.68 ms | 297.33 ms | -15.35 ms (-4.91%) |

## Fake and duplicate ratios

Values are percentages. Differences are candidate minus Genesis in percentage points. Lower fake and duplicate ratios are better.

### Clean 50-event stage

| Algorithm | Metric | Genesis | Candidate | Difference |
| --- | --- | ---: | ---: | ---: |
| Seeding | Particle fake ratio | 20.262% | 20.328% | +0.066 pp |
| Seeding | Track fake ratio | 2.502% | 2.509% | +0.007 pp |
| Seeding | Particle duplicate ratio | 97.325% | 97.312% | -0.013 pp |
| Seeding | Track duplicate ratio | 54.876% | 54.802% | -0.075 pp |
| CKF | Particle fake ratio | 3.840% | 3.849% | +0.009 pp |
| CKF | Track fake ratio | 2.184% | 2.174% | -0.010 pp |
| CKF | Particle duplicate ratio | 30.058% | 30.048% | -0.011 pp |
| CKF | Track duplicate ratio | 21.174% | 21.150% | -0.024 pp |
| Ambiguity | Particle fake ratio | 0.475% | 0.470% | -0.005 pp |
| Ambiguity | Track fake ratio | 1.702% | 1.684% | -0.018 pp |
| Ambiguity | Particle duplicate ratio | 0.109% | 0.106% | -0.003 pp |
| Ambiguity | Track duplicate ratio | 0.137% | 0.138% | +0.001 pp |

### Timed 50-event stage

| Algorithm | Metric | Genesis | Candidate | Difference |
| --- | --- | ---: | ---: | ---: |
| Seeding | Particle fake ratio | 20.346% | 20.342% | -0.004 pp |
| Seeding | Track fake ratio | 2.517% | 2.519% | +0.001 pp |
| Seeding | Particle duplicate ratio | 97.304% | 97.305% | +0.001 pp |
| Seeding | Track duplicate ratio | 54.839% | 54.764% | -0.075 pp |
| CKF | Particle fake ratio | 3.864% | 3.864% | +0.000 pp |
| CKF | Track fake ratio | 2.210% | 2.191% | -0.019 pp |
| CKF | Particle duplicate ratio | 30.071% | 30.102% | +0.031 pp |
| CKF | Track duplicate ratio | 21.199% | 21.165% | -0.034 pp |
| Ambiguity | Particle fake ratio | 0.475% | 0.479% | +0.005 pp |
| Ambiguity | Track fake ratio | 1.690% | 1.689% | -0.001 pp |
| Ambiguity | Particle duplicate ratio | 0.107% | 0.103% | -0.005 pp |
| Ambiguity | Track duplicate ratio | 0.141% | 0.134% | -0.006 pp |

## Assessment

The candidate reduced seeding time in both modes. It was slower in the clean run but faster in the timed run. Fake and duplicate ratios moved only slightly and inconsistently, so they do not explain the clean total-time regression by themselves. The timed run shows that the candidate can reduce measured chain time, but this is one 50-event measurement per implementation and needs repetition before promotion.

The candidate remains a useful exploratory parent under the campaign policy because it improves timed total time. It is not yet a demonstrated overall improvement.

## Reproduction note

An initial rerun accidentally measured Genesis with the candidate optimization still applied. That generated summary was discarded. The Genesis and candidate summaries listed above were produced after restoring the baseline implementation before the Genesis run, then reapplying the candidate before the candidate run.
