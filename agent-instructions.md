# ACTS Seeding Autoresearch Agent Instructions

This repository is an ACTS Seeding2 autoresearch platform.
The goal is to find faster or more efficient ACTS Seeding2 implementations while preserving physics correctness and the fixed validation protocol.

## Setup

1. Agree on a run tag based on the current date, such as `aug25`.
2. Confirm that `autoresearch-acts-seeding/<tag>` does not already exist.
3. Create the campaign branch from current `main`:

   ```text
   git switch main
   git pull --ff-only
   git switch -c autoresearch-acts-seeding/<tag>
   ```

4. Keep the first Genesis baseline run in every campaign:

   ```text
   make evaluate CANDIDATE=Genesis
   ```

The Genesis run is required even when an older Genesis record exists.
It anchors the campaign against current infrastructure drift.
Do not start mutation experiments until the baseline completes or its failure is understood.

## Experiment surface

An experiment may change only:

- Files under `optimization-files/` that satisfy the evaluator's ACTS-relative allowlist.
- Concise entries in `agent-learnings.md`.

Do not modify the evaluator, HEPP helpers, report tooling, workload constants, event counts, seeds, pileup, thread settings, timing collection, metric parsing, or acceptance logic.
Do not change variables outside the ACTS processing implementation to improve a result.
Do not modify the static ITk dataset, the ACTS source tree, or `~/Projects/ACTS-Seeding/Thesis-Documents/Makefile`.
Do not install new experiment dependencies.

The evaluator owns ACTS backup, optimization-file application, remote execution, restoration, rebuild, and cleanup.
Do not reproduce those lifecycle operations manually.

## Run commands

Development evaluates one candidate through one-event seeding, one-event full chain, and fifty-event clean and timed full-chain runs:

```text
make evaluate CANDIDATE=<candidate-name>
```

After the run, retrieve the result for the agent without browsing the archive:

```text
make record CANDIDATE=<candidate-name>
```

`make record` returns the latest summary and, for a failed run, the relevant failure-log tails.
It is read-only.

Use the historical population selector for an inspiration implementation:

```text
make evolve
```

It returns a candidate implementation commit selected from successful results.
Inspect that implementation and form a new hypothesis from it, a prior result, an implementation detail, or a documented algorithm idea.

## Candidate objective

A candidate is promising when it passes all requested stages and improves at least one of these against the selected Genesis baseline:

- Lower total full-chain time per event.
- Lower seeding time per event.
- Higher seeding efficiency.
- Higher CKF efficiency.
- Higher ambiguity-resolution efficiency.

Lower CKF or ambiguity time alone is not an eligibility criterion.
CKF and ambiguity improvements count through their efficiencies.
Prefer a meaningful improvement without unnecessary complexity.
If performance is equal, prefer the simpler implementation.

## Experiment loop

Once setup is confirmed, continue until the captain stops the campaign or a real blocker needs a decision.
Do not pause after every candidate to ask whether to continue.

For each attempt:

1. Inspect the current branch and commit.
2. Confirm there are no uncommitted changes outside `records/` and `agent-learnings.md`.
3. Read `agent-learnings.md` for promising approaches and failed ideas.
4. Run `make evolve` to get an inspiration implementation.
5. Choose one hypothesis based on that implementation, a prior result, an implementation detail, or a documented algorithm idea.
6. Modify only the permitted experiment files.
7. Inspect the diff and commit the candidate before running it.
8. Run `make evaluate CANDIDATE=<candidate-name>`.
9. Run `make record CANDIDATE=<candidate-name>` and judge success, failure, and improvement from its output.
10. Add a concise lesson to `agent-learnings.md` when the attempt teaches something reusable.
11. Keep a passing improvement; otherwise restore the previous candidate with a safe, non-force operation on the campaign branch.
12. Use the simplification skill to curate `agent-learnings.md` when it reaches 250 lines.
13. Never allow `agent-learnings.md` to exceed 500 lines.

Each candidate name must be unique.
Do not overwrite generated results.

## Failure handling

If `make evaluate` fails, run `make record CANDIDATE=<candidate-name>` and classify the result.

- For a dumb implementation error, such as a syntax error, missing import, typo, or obvious local bug, fix it and retry the same candidate once.
- For a project setup, HEPP02, ACTS environment, dataset, transport, or otherwise uncertain failure, stop and ask the captain to inspect or repair it.
- For a fundamentally broken idea or repeated failed fixes, record the lesson and return to the last accepted candidate.

Expected unmasked floating-point exceptions are nonfatal only when every requested event completed.
Do not hide other errors or reduce event counts.

## Records and reports

Do not inspect or edit generated summaries and logs directly during the ordinary loop.
Use `make record` for run output and `make evolve` for historical selection.
Use `make report` for interactive comparison when the captain requests a broader visual review.

Successful candidates are retained by the evaluator.
Do not commit failure logs, temporary output, or runtime state.

## Agent learnings

`agent-learnings.md` is a concise memory of reusable experiment lessons.
Record the candidate, outcome, and one actionable lesson, not raw logs or full metric dumps.
Record both useful improvements and failed ideas that should not be repeated.
Keep the file below 500 lines.
At 250 lines, invoke the simplification skill to merge duplicate lessons, remove stale details, and keep the file below the hard limit.

Do not claim a scientific improvement from a run that did not complete all required stages.
