# ACTS Seeding Autoresearch Agent Instructions

This repository is an ACTS Seeding2 autoresearch platform.
The goal is to find faster or more efficient ACTS Seeding2 implementations while preserving physics correctness and the fixed validation protocol.

## Setup

1. Agree on a run tag based on the current UTC date, such as `aug25`.
2. If `autoresearch-acts-seeding/<tag>` already exists, append the next numeric suffix, such as `aug25-2` or `aug25-3`, and confirm that the resulting branch does not exist.
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
The fresh Genesis record is the campaign baseline; use its record path when judging candidates, not an older Genesis result selected by `make evolve`.
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
If it returns Genesis because no distinct candidate is eligible, inspect the current Genesis implementation and form one focused hypothesis from it, a prior result, an implementation detail, or a documented algorithm idea.

## Candidate objective

A candidate is eligible to remain the active experiment base when it passes all requested stages and improves at least one of these against the selected Genesis baseline:

- Lower total full-chain time per event.
- Higher ambiguity-resolution efficiency.

A candidate that improves ambiguity efficiency while worsening total time may remain active for a follow-up recovery experiment, but report it as a mixed result and do not call it an overall improvement.
Seeding time, seeding efficiency, and CKF efficiency remain useful diagnostics and historical inspiration, but do not by themselves keep a candidate as the active base.
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
11. Keep a candidate that meets the active-base criteria. Otherwise restore the previous candidate with a safe, non-force operation on the campaign branch.
    Keep a mixed ambiguity-improvement candidate when a follow-up experiment is explicitly targeting recovery of its total time, but do not present it as an overall improvement.
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

The current successful Genesis summaries live at `records/Development/Genesis/summary.json` and `records/Evaluation/Genesis/summary.json`.
Each successful Genesis run overwrites only its same-category summary and removes older timestamped Genesis directories after the new summary is valid.
A failed Genesis run leaves the previous successful summary intact.
Successful non-Genesis candidates are retained by the evaluator.
Do not commit failure logs, temporary output, or runtime state.

## GitHub campaign review

Make each campaign reviewable on GitHub through one draft pull request.
After creating the campaign branch, push it and open one draft PR before the first mutation experiment.
After every candidate attempt, push the branch so the draft PR shows the new implementation and its evidence.
Keep every candidate implementation commit reachable on the campaign branch, including candidates that are later rejected; restore a rejected candidate with a safe revert commit instead of resetting away its history.

After `make record`, commit the candidate's `summary.json` and any concise `agent-learnings.md` lesson in a separate evidence commit.
Commit successful and failed summaries when they exist, but never commit failure logs, temporary output, or runtime state.
The canonical Genesis summary replacement is evidence and should be included in the campaign branch when it changes.

Create or update the draft PR with `gh-axi` and keep its body current with the campaign tag, candidate name, hypothesis, changed files, development result, and whether the candidate is the active base.
Use PR comments for additional candidate results when rewriting the body would hide history.
Never merge the campaign PR autonomously; leave that decision to the captain.

The `main` branch must always contain the Genesis implementation.
Before a campaign archive PR is merged, revert candidate implementation changes in a final commit while keeping the candidate commits, summaries, lessons, and report in the PR history.
Merge archive PRs with a regular merge commit, never squash, so each candidate implementation commit remains reachable to future `make evolve` runs.
Do not delete a campaign branch until its archive PR has merged and its records are present on `main`.

## Agent learnings

`agent-learnings.md` is a concise memory of reusable experiment lessons.
Record the candidate, outcome, and one actionable lesson, not raw logs or full metric dumps.
Record both useful improvements and failed ideas that should not be repeated.
Keep the file below 500 lines.
At 250 lines, invoke the simplification skill to merge duplicate lessons, remove stale details, and keep the file below the hard limit.

Do not claim a scientific improvement from a run that did not complete all required stages.
