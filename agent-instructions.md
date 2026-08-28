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
Successful Genesis runs are preserved as timestamped records. `make evolve`
selects the latest complete protocol-compatible Development Genesis record.
Failed or incomplete Genesis runs are never baselines. Do not start mutation
experiments until the baseline completes or its failure is understood.

## Controlled campaign protocol

The machine-readable evaluator contract is `orchestration-files/protocol.py`.
The experiment agent must use protocol `acts-seeding-v2` without overrides:

- ACTS v46.5.0 on the fixed `ttbar_pu200` ITk dataset through HEPP02.
- One ACTS thread, seed 42, and pileup 200.
- Experiment candidates use the 10-event development workload only. Evaluation workloads are captain-controlled and must not be run by experiment agents.
- Clean full-chain stages may run once. Timed full-chain stages run three repetitions;
  compare their median and retain each repetition for auditability.
- Accept expected unmasked FPEs only when every requested event completed.

The only primary objectives are median timed seeding time per event (minimize)
and median timed particle ambiguity-resolution efficiency (maximize). Keep them
as a Pareto tradeoff. Full-chain and CKF timing are diagnostics unless the
candidate actually changes those implementation areas. All other metrics are
diagnostics only and must not determine eligibility, Pareto objectives, or
recommendation ranking.

## Experiment surface

An experiment may change only:

- Files under `optimization-files/` that satisfy the evaluator's ACTS-relative allowlist.
- Concise entries in `orchestration-files/agent-learnings.md`.

Do not modify the evaluator, HEPP helpers, report tooling, workload constants, event counts, seeds, pileup, thread settings, timing collection, metric parsing, or acceptance logic during ordinary candidate experiments.
Do not change variables outside the ACTS processing implementation to improve a result.
Do not modify the static ITk dataset, the ACTS source tree, or `~/Projects/ACTS-Seeding/Thesis-Documents/Makefile`.
Do not install new experiment dependencies.

The evaluator owns ACTS backup, optimization-file application, remote execution, restoration, rebuild, and cleanup.
Do not reproduce those lifecycle operations manually.

## Run commands

The development evaluator runs one candidate through 10-event seeding and
clean full-chain stages plus three 10-event timed full-chain repetitions:

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

A candidate is eligible to remain the active experiment base only when it passes all requested stages and improves at least one of the two primary metrics against the fresh Genesis baseline:

- Lower median timed seeding time per event.
- Higher median timed particle ambiguity-resolution efficiency.

Full-chain and CKF timing are diagnostics unless the candidate actually changes
those implementation areas. Use Pareto dominance and the non-dominated front for candidate comparison. Do not
collapse the two objectives into a weighted score. A candidate that improves one
primary metric while worsening the other may remain a Pareto tradeoff for a
follow-up experiment, but report it as a mixed result and do not call it an
overall improvement. Diagnostics never make a candidate eligible or preferred.
Prefer a meaningful improvement without unnecessary complexity.
If primary performance is equal, prefer the simpler implementation.

## Experiment loop

Once setup is confirmed, continue until the captain stops the campaign or a real blocker needs a decision.
Do not pause after every candidate to ask whether to continue. A campaign must
have at least 20 completed candidate attempts, counting only attempts whose
development run completes all requested stages, and at least 10 structurally
distinct attempts. It may contain no more than 5 micro-optimization attempts in
total, and no more than 3 consecutive attempts may come from one mechanism
family. Do not stop after one attempt or a routine progress update. Change
mechanism families before exceeding any of those limits.

Structural work changes algorithm or data flow, traversal or control flow, data
layout or allocation behavior, pruning or search bounds, or an equivalent
non-trivial implementation mechanism. A renamed or mechanically equivalent
cache, logging change, STL spelling, `reserve`, or branch variant is not
structurally distinct. A micro-optimization is a change limited to that kind of
local spelling, hint, reserve, cache, logging, or similarly small rewrite.

Before each candidate run, state all four fields below in the candidate
proposal and evidence:

- `mechanism_key`: a stable key for the mechanism family and idea.
- `changed_symbols`: the functions, classes, data members, or other symbols changed.
- `expected_hot_path`: the hot path expected to change and the direction of change.
- `novelty_reason`: why the mechanism is not a semantic duplicate of earlier work.

Use the mechanism key to count families and structural attempts. Do not claim a
candidate is structurally distinct when only names, logging, STL spelling,
`reserve`, cache placement, or branch hints changed.

For each attempt:

1. Inspect the current branch and commit.
2. Confirm there are no uncommitted changes outside `records/` and `orchestration-files/agent-learnings.md`.
3. Read `orchestration-files/agent-learnings.md` for promising approaches and failed ideas.
4. Run `make evolve` to get an inspiration implementation.
5. Choose one hypothesis based on that implementation, a prior result, an implementation detail, or a documented algorithm idea.
6. Modify only the permitted experiment files.
7. Inspect the diff and commit the candidate before running it.
8. Update the current attempt and its non-scientific classification in `orchestration-files/campaign-status-input.json`, run `make campaign-status`, commit the validated state, and push it before starting the run.
9. Run `make evaluate CANDIDATE=<candidate-name>`.
10. Run `make record CANDIDATE=<candidate-name>` and judge success, failure, and improvement from its output.
11. Add a concise lesson to `orchestration-files/agent-learnings.md` when the attempt teaches something reusable. Update the phase or current controlled stage, run `make campaign-status` again, and include both status files in the normal evidence commit and push.
12. Keep a candidate that meets the active-base criteria. Otherwise restore the previous candidate with a safe, non-force operation on the campaign branch.
    Classify each attempt by a stable mechanism key, not only by its candidate name.
    Keep a mixed ambiguity-improvement candidate when a follow-up experiment is explicitly targeting recovery of its seeding time, but do not present it as an overall improvement.
13. Use the simplification skill to curate `orchestration-files/agent-learnings.md` when it reaches 250 lines.
14. Never allow `orchestration-files/agent-learnings.md` to exceed 500 lines.

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

A successful Genesis development run writes a unique timestamped record under
`records/Development/` and retains any older records. The legacy canonical
`records/Development/Genesis/summary.json` location remains readable for
compatibility. Each summary records protocol identity, the timed repetition
metadata, every timed repetition, and the median timed metrics. A failed or
incomplete Genesis run must not be used as a baseline. Successful non-Genesis
candidates are retained by the evaluator. Consumers must reject summaries whose
protocol identity does not match `acts-seeding-v2`.
Do not commit failure logs, temporary output, or runtime state.

### Live campaign status

The public dashboard contract and the exact non-scientific input format are in `orchestration-files/CAMPAIGN_STATUS.md`. `orchestration-files/campaign-status.json` is generated. Never hand-edit it or copy scientific values into `orchestration-files/campaign-status-input.json`.

Publish a validated snapshot at these milestones only:

- Before the fresh Genesis run and before every candidate attempt starts.
- After `make record` has produced the attempt evidence.
- When a blocker starts or clears.
- At campaign closure, with `current_attempt` set to `null`.

Run `make campaign-status`, commit the input and snapshot with the corresponding normal campaign milestone, and push them together. Keep updates sparse. Do not create cosmetic refresh commits for elapsed time or stage wording. The generator reads protocol-compatible Development summaries only. It does not run a workload and does not authorize Evaluation. Experiment agents must preserve the captain-only Evaluation boundary.

## GitHub campaign review

Make each campaign reviewable on GitHub through one draft pull request.
After creating the campaign branch, push it and open one draft PR before the first mutation experiment.
After every candidate attempt, push the branch so the draft PR shows the new implementation and its evidence.
Keep every candidate implementation commit reachable on the campaign branch, including candidates that are later rejected; restore a rejected candidate with a safe revert commit instead of resetting away its history.

After `make record`, commit the candidate's `summary.json`, the refreshed campaign status, and any concise `orchestration-files/agent-learnings.md` lesson in a separate evidence commit.
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

`orchestration-files/agent-learnings.md` is a concise memory of reusable experiment lessons.
Record both useful improvements and failed ideas that should not be repeated.
Do not claim a scientific improvement from a run that did not complete all required stages.

### Candidate provenance policy

Every new candidate lesson must record the candidate name, its full implementation
commit, the exact files changed, and line ranges as they existed in that candidate
commit. It must also include a stable `mechanism_key` so renamed duplicates can
be detected. Use this format:

```text
- YYYY-MM-DD | candidate: <name> | implementation_commit: <full-sha> | mechanism_key: <stable-family-key> | files_changed: <path>#L<start>-L<end>[, <path>#L<start>-L<end>] | outcome: <keep/discard/crash> | lesson: <one actionable lesson>
```

Get the file list from the candidate commit with `git diff-tree --no-commit-id
--name-only -r <commit>`, then inspect line numbers in that commit with
`git show <commit>:<file>` and `nl -ba`. Before editing a file and line range that overlaps an earlier lesson,
the future agent must run `git show <commit> -- <file>` and read the relevant
commit before editing. Do not infer provenance from the current tree after later
commits moved the lines. Existing entries without this metadata are historical
and must not be silently reinterpreted.

Keep the file below 500 lines. At 250 lines, invoke the simplification skill to
merge duplicate lessons, remove stale details, and keep it below the hard limit.
