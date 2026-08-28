# Live campaign status format

`orchestration-files/campaign-status.json` is the generated public snapshot consumed by the GitHub Pages campaign dashboard. [`campaign-status.schema.json`](campaign-status.schema.json) defines fixed and historical version 1.0.0 snapshots plus continuous version 1.1.0 snapshots. Existing 1.0.0 snapshots and fixed-20 evidence stay immutable.

The snapshot contains only protocol-compatible Development evidence. Its scientific fields come from the median timed comparison in generated `summary.json` records:

- Timed seeding time per event, minimized.
- Timed seeding-stage particle efficiency, maximized.

Peak RSS is a separate diagnostic. Ambiguity-resolution, CKF, and full-chain values are not v3 objectives. Development and captain-authorized Evaluation both use one uninstrumented 1-event seeding smoke run, three uninstrumented 10-event seeding timing repetitions, and one separate instrumented 10-event seeding Peak RSS run. The generator derives record durations, progress, failures, the latest campaign Genesis baseline, objective leaders, and the current Pareto front. Do not hand-edit generated fields.

## Campaign modes and composition

`orchestration-files/protocol.py` is the single owner of both composition contracts. Archived fixed campaigns use:

- Exactly 20 completed candidates.
- Exactly 10 major candidates.
- Exactly 5 minor candidates.
- Exactly 5 combination candidates.

The three disjoint category targets must sum to the completed-candidate target. Category progress counts only unique candidates that passed every controlled Development stage. Failed runs do not count toward completion. The generator rejects completed counts above any category target and rejects a queued candidate in a category that is already complete.

Continuous campaigns have no fixed total while their control state is `open`. They use the authoritative 50% major, 25% minor, and 25% combination ratio. `campaign_scheduler.py` owns deterministic deficit selection and the category-order tie-break. A combination slot is skipped unless `scheduler.combination_readiness` contains at least two earlier candidates with completed measured evidence and fully validated provenance. Quota pressure never overrides this check.

At each snapshot, continuous progress reports retained counts, actual percentages, target percentages, and signed candidate deficits. After a stop is consumed, the scheduler persists the smallest positive exact 2:1:1 target that contains all completed candidates. Final totals are therefore positive multiples of four.

## Campaign input

Campaign workers maintain the small operator input `orchestration-files/campaign-status-input.json`. It contains campaign state, pre-run proposals, and post-run assessments, but no measured metrics. Start a campaign with this shape:

```json
{
  "schema_version": "1.0.0",
  "campaign": {
    "name": "ACTS Seeding sep01",
    "branch": "autoresearch-acts-seeding/sep01",
    "phase": "fresh Genesis baseline",
    "started_at": "2026-09-01T09:00:00Z"
  },
  "current_attempt": {
    "candidate": "Genesis",
    "mechanism_key": "fresh-genesis-baseline",
    "mechanism_family": "fresh Genesis baseline",
    "classification": "baseline",
    "controlled_stage": "queued Development run",
    "state": "queued",
    "started_at": "2026-09-01T09:05:00Z"
  },
  "attempt_metadata": [],
  "blockers": [],
  "pull_request_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/pull/123"
}
```

Omitting `campaign.targets` uses the standard composition. A captain-authorized special campaign may provide different category counts only when they are non-negative integers and sum exactly to `completed_candidates`:

```json
"targets": {
  "completed_candidates": 4,
  "major_candidates": 2,
  "minor_candidates": 1,
  "combination_candidates": 1
}
```

### Continuous campaign input

A new continuous campaign uses schema version 1.1.0. Give it a globally unique campaign ID, a random 64-hex-character control ID, and the full Genesis commit whose `optimization-files/` tree must be restored. The control ID is a public replay-resistant identifier, not a credential. Generate it locally with `python3 -c 'import secrets; print(secrets.token_hex(32))'` and publish this initial state:

```json
{
  "schema_version": "1.1.0",
  "campaign": {
    "name": "ACTS Seeding continuous sep01",
    "branch": "autoresearch-acts-seeding/sep01",
    "phase": "continuous Development",
    "started_at": "2026-09-01T09:00:00Z",
    "mode": "continuous",
    "campaign_id": "acts-seeding-sep01-20260901",
    "control_id": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "genesis_commit": "0123456789abcdef0123456789abcdef01234567",
    "targets": {
      "major_percentage": 50,
      "minor_percentage": 25,
      "combination_percentage": 25
    }
  },
  "current_attempt": null,
  "attempt_metadata": [],
  "blockers": [],
  "pull_request_url": null,
  "control": {
    "state": "open",
    "request": null,
    "observed_at": null,
    "consumed_at": null,
    "completed_at": null
  },
  "scheduler": {
    "state": "running",
    "combination_readiness": null,
    "final_targets": null,
    "blocker": null
  }
}
```

A continuous `current_attempt` also has `"scheduling": "ordinary"` or `"scheduling": "finalization"`. Persist one active attempt at a time. Before selecting a combination category, set `combination_readiness` to the same validated shape described under Combination provenance. Every source must already have measured completed evidence. Clear readiness when the proposed combination consumes it.

Before a non-Genesis run, append metadata with no `evidence` block yet. The proposal must already identify the candidate's optimization implementation commit:

```json
{
  "candidate": "CandidateName",
  "mechanism_key": "stable-exact-mechanism-key",
  "mechanism_family": "bounded-family-name",
  "classification": "major",
  "proposal": {
    "schema_version": "1.0.0",
    "candidate": "CandidateName",
    "implementation_commit": "0123456789abcdef0123456789abcdef01234567",
    "hypothesis": "Removing the repeated lookup will reduce seeding time.",
    "falsifier": "The prediction fails if median seeding time does not decrease.",
    "predicted_directions": {
      "timed_seeding_time_per_event_ms": "decrease",
      "timed_seeding_particle_efficiency": "unchanged"
    },
    "expected_hot_path": "Acts::Example::run accepted-item traversal.",
    "changed_symbols": ["Acts::Example::run"],
    "intended_files": ["optimization-files/Core/src/Example.cpp"],
    "novelty_reason": "Earlier candidates did not remove this lookup.",
    "source_references": [
      {
        "source_type": "Genesis",
        "reference": "records/Development/<run>-Genesis/summary.json",
        "relevance": "The baseline identifies the timed hot path.",
        "directly_inspected": true
      }
    ],
    "combination_provenance": null
  }
}
```

The proposal is the only pre-run scientific-claim contract. Source types are exactly `Genesis`, `prior record/commit`, `inspected source code`, or `external primary source`. The last two types also require a permanent HTTPS `reference`, `directly_inspected: true`, `inspected_scope`, and `acts_mapping`. A standard 10/5/5 campaign requires at least three of its first ten major proposals to contain one of those directly inspected primary-source references. Their falsifier, predicted directions, ACTS symbols, and hot-path mapping make the later prediction assessment possible.

At evaluation start, the evaluator normalizes this proposal, verifies its candidate, implementation commit, and exact intended file set, and hashes the normalized proposal with that commit. It copies the binding and combination provenance into `summary.json`. Later status generation rejects proposal changes and reads claims from that measured copy. Genesis is exempt.

`classification` is `major`, `minor`, or `combination`. Current Genesis alone uses `baseline`. Every new-format non-Genesis `mechanism_key` must be globally unique, regardless of name or category. A refinement may add `derives_from` with the earlier candidate, mechanism key, and implementation commit, but the refinement still needs a new exact mechanism key. No more than three consecutive metadata entries may use one `mechanism_family`. `current_attempt.state` is `queued`, `running`, `recording`, or `blocked`. Set `current_attempt` to `null` when no candidate is active. The pull request URL is either this repository's PR URL or `null`.

After `make record`, add the candidate evidence before regenerating status:

```json
"evidence": {
  "files_changed": ["optimization-files/Core/src/Example.cpp#L20-L38"],
  "outcome": "keep",
  "lesson": "The bounded arena reduced timed seeding without changing efficiency.",
  "prediction_assessment": "held",
  "prediction_assessment_rationale": "Both primary objectives moved as predicted."
}
```

Evidence is required for every candidate record included in a new-format snapshot. Exact file ranges use `path#L<start>-L<end>`. Outcomes are `keep`, `discard`, or `crash`. Prediction assessments are `held`, `not held`, `mixed`, or `inconclusive`. The implementation commit, changed symbols, hot-path claim, novelty claim, source references, and combination provenance come only from the immutable measured proposal copy.

### Combination provenance

A combination must include `combination_provenance` before its run. Copy the same normalized object into the proposal's `combination_provenance`; the validator rejects any difference. Each source must name an earlier metadata entry with completed evidence. The source mechanism key and full implementation commit must match that entry. At least two distinct sources are required.

```json
"combination_provenance": {
  "sources": [
    {
      "candidate": "EarlierMajor",
      "mechanism_key": "earlier-major-key",
      "implementation_commit": "1111111111111111111111111111111111111111",
      "directly_inspected": true
    },
    {
      "candidate": "EarlierMinor",
      "mechanism_key": "earlier-minor-key",
      "implementation_commit": "2222222222222222222222222222222222222222",
      "directly_inspected": true
    }
  ],
  "compatibility_rationale": "The changes affect separate storage and traversal seams.",
  "interaction_hypothesis": "Combining them should reduce allocation and improve locality additively."
}
```

Before setting `directly_inspected`, inspect each source with `git show <full-commit> -- <file>`. Candidate and chart links continue to point to the new combined implementation commit.

The generator rejects unknown input fields. This prevents measured metrics and unbound scientific claims from entering the hand-maintained file.

## Generate and publish

Run from the campaign branch:

```text
make campaign-status
/usr/bin/python3 -m unittest discover -s orchestration-files/tests -p 'test_campaign_status.py' -v
```

The generator scans `records/`, rejects malformed campaign evidence, validates the result, and atomically replaces `orchestration-files/campaign-status.json`. It derives the active commit from the checked-out branch. Commit and push the input and generated snapshot with the normal campaign milestone commit.

The ETA uses the median duration of complete, passed candidates. It stays unavailable until three durations exist. It subtracts elapsed time for a current candidate and becomes unavailable while a blocker is active. It reaches zero only when every category target is complete.

## Authenticated finish control

GitHub Pages stays static. It only links the selected open continuous campaign to `.github/workflows/finish-campaign.yml` on `main`. The captain signs in to GitHub, copies the branch, campaign ID, and control ID shown on the page into the `workflow_dispatch` form, and confirms the run. The page sends no credential and makes no privileged request.

The workflow has only `contents: read` and `issues: write`. It validates the exact branch snapshot, continuous identity, matching open PR, lifecycle state, and trusted `main` workflow ref. It then creates one `campaign-control` issue authored by `github-actions[bot]`. The issue contains a strict machine-readable request with the campaign identity, GitHub actor, workflow run, and server-side request time. A matching issue is idempotent. A malformed issue, reused campaign ID with another control ID, unknown branch, closed PR, fixed campaign, or completed campaign is refused.

At every safe candidate boundary, run:

```text
make campaign-check-stop
```

This authenticated GitHub read is the only network-dependent operator check. Tests inject a fake forge and never use the network. If a request arrives during an evaluator transaction, record that transaction and its restoration first. If it arrives before a queued ordinary candidate starts, cancel that queued attempt. Then set `current_attempt` to `null` and run:

```text
make campaign-consume-stop
```

Consumption persists the smallest exact final target once and is restart-safe. From then on, schedule only categories with a positive persisted deficit. If a combination deficit remains without validated readiness, set `scheduler.state` to `blocked`, record the concrete provenance blocker, publish status, and stop safely.

After all deficits reach zero, restore `optimization-files/` exactly to `campaign.genesis_commit`, build the ignored archive report with `make report`, and run `make campaign-finalize`. Finalization rejects a missing consumed request, incomplete ratio, active candidate, missing retained evidence, unauthorized Evaluation or 50-event records, unreachable candidate commits, and a Genesis tree mismatch. Publish the terminal snapshot and archive PR. The input and generated snapshot preserve the request, final targets, and terminal timestamps across process or machine restart.

## Dashboard fetch contract

At page load, the dashboard makes one unauthenticated request for public pull requests:

```text
https://api.github.com/repos/Aksth070600/autoresearch-acts-seeding/pulls?state=all&per_page=100&sort=created&direction=desc
```

Campaign PRs use the `autoresearch-acts-seeding/` branch prefix. The dropdown sorts them newest to oldest by PR creation time and selects the newest by default. A safe `?ref=<branch>` deep link takes precedence and remains available if discovery fails.

A selected open PR reads the live branch snapshot. A selected closed PR reads the immutable final head SHA returned by the PR list:

```text
https://raw.githubusercontent.com/Aksth070600/autoresearch-acts-seeding/refs/heads/<branch>/orchestration-files/campaign-status.json
https://raw.githubusercontent.com/Aksth070600/autoresearch-acts-seeding/<final-head-sha>/orchestration-files/campaign-status.json
```

The dashboard requests the canonical path first. On a 404, it falls back to the legacy root `campaign-status.json` path. This keeps completed immutable campaign heads and old safe `?ref=` deep links available without masking malformed canonical snapshots or other HTTP errors.

Only a selected open campaign refreshes, at most once per minute with cache busting. The pull-request list is not polled. A refresh error is visible and does not replace that campaign's last good snapshot. Older campaigns without snapshots show an explicit unavailable state. An open snapshot becomes stale after 15 minutes; a closed snapshot is final.

The Finish campaign area is enabled only for a discovered open continuous snapshot whose branch and public control identity match the selected PR. It shows explicit unavailable states for fixed, direct-ref, requested, finalizing, malformed, and completed selections. Navigation opens GitHub's authenticated workflow page. Browser code never contains an API credential, authorization header, workflow dispatch POST, or issue mutation.

## Version compatibility

Version 1.1.0 adds continuous ratio progress plus durable scheduler and control state. Version 1.0.0 remains the fixed and historical format. The 10/5/5 composition is a backward-compatible campaign-status v1 extension. New snapshots use candidate target and progress fields and the `major`, `minor`, and `combination` classifications. The schema and dashboard also accept immutable historical v1 snapshots that contain the former `completed_attempts`, `structural_attempts`, and `micro_optimization_cap` targets, matching progress fields, and `structural` or `micro` classifications. Historical snapshots render their original labels. Do not rewrite archived snapshots or records.

Version 1 also accepts both canonical and legacy `repository.snapshot_path` values. Historical v2 snapshots retain ambiguity-efficiency fields. New v3 snapshots use seeding-efficiency fields. The dashboard maps each protocol to its matching field without comparing protocols. Any future incompatible status shape requires a new `schema_version`.
