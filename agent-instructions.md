# ACTS Seeding Autoresearch Agent Instructions

This repository is an ACTS Seeding2 autoresearch platform.
The goal is to find faster or more efficient ACTS Seeding2 implementations while preserving physics correctness, reproducibility, and the fixed evaluation protocol.

## Operating contract

- Work only on a dedicated branch named `autoresearch/<tag>`.
- Never experiment directly on `main`.
- Do not modify the static ITk dataset at `/storage/thomaaks/acts-itk`.
- Do not modify the ACTS source tree directly at `/storage/thomaaks/acts-v46.5.0`.
- Do not modify `~/Projects/ACTS-Seeding/Thesis-Documents/Makefile`.
- Do not modify the evaluator, HEPP helpers, or report tooling as part of an optimization attempt.
- Do not install new experiment dependencies during an optimization attempt.
- Preserve unrelated human changes and stop if the repository contains uncommitted changes outside the records archive.
- Never force-reset, force-push, or discard uncommitted work.

The evaluator owns ACTS backup, optimization-file application, remote execution, restoration, rebuild, and cleanup.
Do not reproduce those lifecycle operations manually.

## Setup

Before starting a new campaign:

1. Agree on a run tag based on the current date, such as `aug25`.
2. Confirm that `autoresearch/<tag>` does not already exist.
3. Start from the current `main` branch and create the campaign branch:

   ```text
   git switch main
   git pull --ff-only
   git switch -c autoresearch/<tag>
   ```

4. Read these files completely:
   - `README.md` for project context and report links.
   - `Makefile` for supported commands and fixed workload defaults.
   - `orchestration-files/evaluate.py` for the validation contract and allowlist.
   - `orchestration-files/report.py` for searchable metric names.
   - `orchestration-files/evolution.py` for the active candidate population.
   - The current `records/evolution/population.json` when it exists.
5. Verify that the local project can reach HEPP02 and that the persistent `acts-hepp02` tmux session is available.
6. Verify that the ACTS source and ITk dataset paths are available through the configured HEPP02 environment.
7. Verify the required optimization files exist under `optimization-files/`.
8. Confirm that the repository is clean outside `records/`.

The existing `fake-*` records are synthetic fixtures for testing reports and evolution.
Do not treat their metrics or placeholder commits as scientific evidence or as real implementation starting points.

The first run must use the unchanged baseline optimization files:

```text
make evaluate CANDIDATE=baseline
```

Do not start a mutation campaign until the baseline completes or its failure is understood.

## What an experiment may change

An optimization attempt may change only files under `optimization-files/` that satisfy the evaluator's ACTS-relative allowlist.
The files mirror paths in ACTS v46.5.0.

A candidate may change ACTS Seeding2 implementation details, data structures, algorithms, and related permitted headers or sources.
Keep the change focused enough that its performance and correctness effect can be explained.

Do not add files outside the permitted ACTS-relative paths.
Do not change workload constants, event counts, seeds, pileup, thread settings, timing collection, metric parsing, or acceptance logic to improve a result.

## Development and evaluation runs

A development run executes these stages:

1. One-event seeding.
2. One-event full chain.
3. Fifty-event clean full chain with `ITK_METRICS=none`.
4. Fifty-event timed full chain with GNU time metrics.

Run a development candidate with:

```text
make evaluate CANDIDATE=<candidate-name>
```

An evaluation run executes only:

1. Two-hundred-event clean full chain.
2. Two-hundred-event timed full chain.

Evaluation is captain-controlled and is not part of the ordinary experiment loop.
The captain selects a top-N set of candidates from the development results or active evolution population, then runs evaluation for each selected candidate:

```text
make evaluate CANDIDATE=<candidate-name> EVALUATION=1
```

Compare the resulting evaluation summaries against each other and the baseline before making a final claim.
Do not automatically run evaluation after every kept development candidate.

Clean runs must not invoke `/usr/bin/time`.
Timed runs may report peak RSS, user CPU, system CPU, and elapsed time.

ACTS may report unmasked floating-point exceptions.
Treat them as nonfatal only when every requested event completed and the evaluator records the expected completion.
Do not hide other errors or reduce event counts.

## Candidate objective

The primary development comparison uses the timed fifty-event full-chain metrics.
Use the clean run to confirm behavior and the timed run to compare cost.

A candidate is promising when it improves at least one of these against the selected baseline without breaking the required stages:

- Lower total full-chain time per event.
- Lower seeding time per event.
- Higher seeding efficiency.
- Higher CKF efficiency.
- Higher ambiguity-resolution efficiency.

A lower CKF or ambiguity time by itself is not an eligibility criterion.
The time criteria are total time per event and seeding time per event.
CKF and ambiguity improvements are considered through their efficiencies.

Do not select a candidate based on one noisy metric without checking the other metrics, reconstruction completion, and resource use.
Prefer a meaningful improvement that does not add unnecessary complexity.
If performance is equal, prefer the simpler implementation.

## Evolution population

Run the historical population selector when choosing an implementation for inspiration:

```text
make evolve
```

The selector uses NSGA-II from the pinned `pymoo` dependency.
It reads successful summaries from `records/`, always retains the baseline, and saves the active population in `records/evolution/population.json`.
It returns a recommended candidate's `implementation_commit`.

Use the returned commit as an implementation reference only.
Inspect its optimization files and result summary before changing code.
Never assume a commit is valid because it was selected by the population selector.

## Experiment loop

Once setup is confirmed, continue experiments autonomously until the captain stops the campaign or a real blocker requires a decision.
Do not pause after every candidate to ask whether to continue.

For each attempt:

1. Inspect the current branch and commit.
2. Confirm there are no uncommitted changes outside `records/`.
3. Choose one hypothesis grounded in a prior result, an implementation detail, or a documented algorithm idea.
4. Modify only the permitted files under `optimization-files/`.
5. Inspect the diff and verify that the change stays within the allowlist.
6. Commit the candidate before running it.
7. Run the development evaluator:

   ```text
   make evaluate CANDIDATE=<candidate-name>
   ```

8. Read the generated `records/Development/<timestamp>-<candidate-name>/summary.json`.
9. Keep the candidate commit when it passes and improves the objective.
10. For an equal or worse candidate, restore the previous candidate using a safe, non-force operation on the campaign branch.
11. For a crash, inspect the retained raw logs under `records/Failed/` or `records/Errors/` and classify the failure.
12. If it is a dumb implementation error, such as a syntax error, missing import, typo, or obvious local bug, fix it and retry the same candidate once.
13. If it is a project setup, HEPP02, ACTS environment, dataset, transport, or otherwise uncertain failure, stop and ask the captain to inspect or repair it.
14. If the idea is fundamentally broken or repeated fixes fail, record the failure and return to the last accepted candidate.

Each attempt must have a unique candidate name.
Do not overwrite an existing summary.

A candidate is not ready for captain-selected evaluation merely because it builds or improves one development metric.
Use `make evolve` and the interactive report to help rank candidates, then evaluate only the top-N set the captain selects.

## Records and reporting

The evaluator writes successful summaries under `records/Development/` or `records/Evaluation/`.
It retains raw logs for failed and infrastructure-error runs under `records/Failed/` or `records/Errors/`.
Do not hand-edit generated summaries or raw logs.
Do not commit error logs, temporary output, or runtime state.

Use the interactive report to compare candidates:

```text
make report
```

The Pareto report defaults to timed total time per event versus ambiguity particle efficiency.
Use it to inspect baseline-relative tradeoffs, not as a replacement for the evaluator.

## Completion report

When the campaign stops, report:

- The campaign branch.
- The best candidate commit and candidate name.
- The baseline commit used for comparison.
- Development and evaluation summary paths.
- Total time per event and seeding time per event.
- Seeding, CKF, and ambiguity efficiencies.
- Peak RSS and CPU metrics for timed runs.
- Any expected FPEs and completed event counts.
- Remaining risks, failed attempts, or decisions needed.

Never claim a scientific improvement from synthetic records or from a development run that did not complete all required stages.
