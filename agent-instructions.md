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
Successful Genesis runs are preserved as timestamped records. Deterministic
Evaluation selection uses the latest complete protocol-compatible Development
Genesis record. Failed or incomplete Genesis runs are never baselines. Do not start candidate
experiments until the baseline completes or its failure is understood.

## Controlled campaign protocol

The machine-readable evaluator contract is `orchestration-files/protocol.py`.
The experiment agent must use protocol `acts-seeding-v2` without overrides:

- ACTS v46.5.0 on the fixed `ttbar_pu200` ITk dataset through HEPP02.
- One ACTS thread, seed 42, and pileup 200.
- Experiment candidates use the 10-event development workload only. Evaluation workloads are captain-controlled and must not be run by experiment agents.
- Clean full-chain stages may run once. Timed full-chain stages run three repetitions;
  compare their median and retain each repetition, range, and unscaled median absolute deviation for auditability.
- Accept expected unmasked FPEs only when every requested event completed.
- Keep every ACTS build at exactly `ACTS_BUILD_JOBS=8`. Do not raise the build job cap.

The only primary objectives are median timed seeding time per event (minimize)
and median timed particle ambiguity-resolution efficiency (maximize). Keep them
as a Pareto tradeoff. Full-chain and CKF timing are diagnostics unless the
candidate actually changes those implementation areas. All other metrics are
diagnostics only and must not determine eligibility, Pareto objectives, or
recommendation ranking.

Captain-selected Evaluation reports classify seeding-speed evidence as `confirmed`, `directional`, or `inconclusive`. The predeclared practical margin is the maximum Genesis repetition range or unscaled median absolute deviation. A positive speed difference must exceed that margin and comparable candidate/Genesis dispersion to be confirmed. This is reporting and captain selection evidence only. It does not authorize Evaluation, change Development eligibility, or change either primary objective.

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

Use `make record` for a named candidate and read the curated lessons before choosing a hypothesis. When a prior mechanism is relevant, inspect its full implementation commit with `git show <commit> -- <file>`. Form one focused hypothesis from Genesis, a directly inspected prior result, an implementation detail, or a documented algorithm idea.

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
Do not pause after every candidate to ask whether to continue. A standard campaign must complete exactly 20 unique candidate experiments whose Development runs complete every requested stage. The categories are disjoint and exact:

- 10 `major` candidates. Each makes a new substantive algorithm, traversal, allocation, data-layout, pruning, search-bound, or data-flow change.
- 5 `minor` candidates. Each makes a new bounded local optimization, such as a focused hint, reserve, cache-placement, or similarly small rewrite.
- 5 `combination` candidates. Each combines at least two earlier candidate mechanisms and tests a specific additive or interaction hypothesis.

Combination candidates do not count as major or minor. The category targets must sum to the completed-candidate target. No more than 3 consecutive candidates may come from one `mechanism_family`. Do not stop after one candidate or a routine progress update. Change mechanism families before exceeding the streak limit.

A renamed or mechanically equivalent cache, logging change, STL spelling, `reserve`, or branch variant is not a new major mechanism. Every candidate must be novel. Before each candidate run, commit one proposal in the candidate's campaign metadata. Follow the authoritative shape in `orchestration-files/CAMPAIGN_STATUS.md`. It includes the candidate and implementation commit, hypothesis and falsifier, predicted direction for both primary objectives, `expected_hot_path`, `changed_symbols`, exact intended files, `novelty_reason`, typed source references, and nullable combination provenance.

Each `mechanism_key` must be globally unique among non-Genesis candidates, regardless of candidate name or category, and `novelty_reason` must explain why it is not a semantic duplicate. A genuine refinement may declare `derives_from` lineage to an earlier completed candidate, but it still needs a new exact mechanism key. A standard 10/5/5 campaign must ground at least three of its first ten major proposals in a permanent directly inspected primary source or upstream implementation. Those references record inspected scope and an exact ACTS symbol/hot-path mapping. Local hypotheses do not otherwise require citations.

At evaluator start, the proposal candidate, implementation commit, and intended file set must match the implementation commit. The evaluator hashes deterministic normalized proposal JSON with that commit and copies the exact normalized proposal, hash, and combination provenance into the summary. Genesis is exempt. Do not edit a proposal after its run. Reports and generated status use the measured summary copy, not later handwritten claims.

Before implementing a combination, run `git show <full-source-implementation-commit> -- <file>` for every source. Record at least two distinct source candidate names, source mechanism keys, and full source implementation commits. Also record that each source was directly inspected, why the mechanisms are compatible, and one specific additive or interaction hypothesis. The combination candidate's commit and dashboard link must identify the new combined implementation, not a source commit.

For each attempt:

1. Inspect the current branch and commit.
2. Confirm there are no uncommitted changes outside `records/` and `orchestration-files/agent-learnings.md`.
3. Read `orchestration-files/agent-learnings.md` for promising approaches and failed ideas.
4. Choose one hypothesis from Genesis, a directly inspected prior implementation, a prior result, an implementation detail, or a documented algorithm idea.
5. For a combination, inspect every source commit and write the required provenance and interaction hypothesis before editing.
6. Modify only the permitted experiment files.
7. Inspect the diff and commit the candidate before running it.
8. Add its category, globally unique mechanism key, mechanism family, complete proposal, optional refinement lineage, and any matching combination provenance to `orchestration-files/campaign-status-input.json`. Update `current_attempt`, run `make campaign-status`, commit the validated state, and push it before starting the run.
9. Run `make evaluate CANDIDATE=<candidate-name>`.
10. Run `make record CANDIDATE=<candidate-name>` and judge success, failure, and improvement from its output.
11. Record the result in `orchestration-files/agent-learnings.md`. In status input, add exact changed file ranges, outcome, lesson, and a `held`, `not held`, `mixed`, or `inconclusive` prediction assessment with rationale. Do not restate proposal claims. Update the phase or current controlled stage, run `make campaign-status` again, and include both status files in the normal evidence commit and push.
12. Keep a candidate that meets the active-base criteria. Otherwise restore the previous candidate with a safe, non-force operation on the campaign branch. Keep a mixed ambiguity-improvement candidate when a follow-up experiment explicitly targets recovery of its seeding time, but do not present it as an overall improvement.
13. Use the simplification skill to curate `orchestration-files/agent-learnings.md` when it reaches 250 lines.
14. Never allow `orchestration-files/agent-learnings.md` to exceed 500 lines.
15. After all 20 completed candidates and before campaign closure, restore the canonical Genesis implementation with a safe revert commit. Keep every candidate implementation commit reachable.

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
Use `make record` for run output and inspect named historical commits directly when they inform a new candidate.
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

The public dashboard contract and exact operator input format are in `orchestration-files/CAMPAIGN_STATUS.md`. `orchestration-files/campaign-status.json` is generated. Never hand-edit it or copy measured metrics into `orchestration-files/campaign-status-input.json`; only the pre-run proposal and post-run assessment fields are allowed.

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
Merge archive PRs with a regular merge commit, never squash, so each candidate implementation commit remains reachable to future campaigns.
Do not delete a campaign branch until its archive PR has merged and its records are present on `main`.

## Agent learnings

`orchestration-files/agent-learnings.md` is a concise memory of reusable experiment lessons.
Record both useful improvements and failed ideas that should not be repeated.
Do not claim a scientific improvement from a run that did not complete all required stages.

### Candidate provenance policy

Every new candidate lesson must identify the candidate, category, implementation commit, mechanism key, exact changed file ranges, outcome, prediction assessment, and lesson. The immutable measured proposal in `summary.json` owns the hypothesis, falsifier, changed-symbol claim, hot-path claim, novelty claim, source references, and combination provenance. Link to that evidence instead of rewriting it. Use this format:

```text
- YYYY-MM-DD | candidate: <name> | classification: <major/minor/combination> | implementation_commit: <full-sha> | mechanism_key: <stable-key> | files_changed: <path>#L<start>-L<end>[, <path>#L<start>-L<end>] | outcome: <keep/discard/crash> | prediction_assessment: <held/not held/mixed/inconclusive> | lesson: <one actionable lesson>
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
