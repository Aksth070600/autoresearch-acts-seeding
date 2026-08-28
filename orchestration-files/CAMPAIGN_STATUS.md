# Live campaign status format

`orchestration-files/campaign-status.json` is the generated public snapshot consumed by the GitHub Pages campaign dashboard. Version 1.0.0 is defined by [`campaign-status.schema.json`](campaign-status.schema.json).

The snapshot contains only protocol-compatible Development evidence. Its scientific fields come from the median timed comparison in generated `summary.json` records:

- Timed seeding time per event, minimized.
- Timed particle ambiguity-resolution efficiency, maximized.

Full-chain time is not an objective. The generator derives record durations, progress, failures, the latest campaign Genesis baseline, objective leaders, and the current Pareto front. Do not hand-edit generated fields.

## Standard composition

`orchestration-files/protocol.py` is the single owner of the standard campaign composition:

- Exactly 20 completed candidates.
- Exactly 10 major candidates.
- Exactly 5 minor candidates.
- Exactly 5 combination candidates.

The three disjoint category targets must sum to the completed-candidate target. Category progress counts only unique candidates that passed every controlled Development stage. Failed runs do not count toward completion. The generator rejects completed counts above any category target and rejects a queued candidate in a category that is already complete.

## Campaign input

Campaign workers maintain the small non-scientific `orchestration-files/campaign-status-input.json` file. Start a campaign with this shape:

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

Before a non-Genesis run, append metadata with no `evidence` block yet:

```json
{
  "candidate": "CandidateName",
  "mechanism_key": "stable-mechanism-key",
  "mechanism_family": "bounded-family-name",
  "classification": "major"
}
```

`classification` is `major`, `minor`, or `combination`. Current Genesis alone uses `baseline`. No more than three consecutive metadata entries may use one `mechanism_family`. `current_attempt.state` is `queued`, `running`, `recording`, or `blocked`. Set `current_attempt` to `null` when no candidate is active. The pull request URL is either this repository's PR URL or `null`.

After `make record`, add the candidate evidence before regenerating status:

```json
"evidence": {
  "implementation_commit": "0123456789abcdef0123456789abcdef01234567",
  "changed_symbols": ["Acts::Example::run"],
  "files_changed": ["optimization-files/Core/src/Example.cpp#L20-L38"],
  "hot_path_rationale": "Remove one allocation from each accepted traversal.",
  "novelty_rationale": "Earlier candidates did not change this ownership boundary.",
  "outcome": "keep",
  "lesson": "The bounded arena reduced timed seeding without changing efficiency."
}
```

Evidence is required for every candidate record included in a new-format snapshot. The implementation commit must match the candidate record. Exact file ranges use `path#L<start>-L<end>`. Outcomes are `keep`, `discard`, or `crash`.

### Combination provenance

A combination must include `combination_provenance` before its run. Each source must name an earlier metadata entry with completed evidence. The source mechanism key and full implementation commit must match that entry. At least two distinct sources are required.

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

The generator rejects unknown input fields. This prevents scientific metrics from entering the hand-maintained file.

## Generate and publish

Run from the campaign branch:

```text
make campaign-status
/usr/bin/python3 -m unittest discover -s orchestration-files/tests -p 'test_campaign_status.py' -v
```

The generator scans `records/`, rejects malformed campaign evidence, validates the result, and atomically replaces `orchestration-files/campaign-status.json`. It derives the active commit from the checked-out branch. Commit and push the input and generated snapshot with the normal campaign milestone commit.

The ETA uses the median duration of complete, passed candidates. It stays unavailable until three durations exist. It subtracts elapsed time for a current candidate and becomes unavailable while a blocker is active. It reaches zero only when every category target is complete.

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

## Version 1 compatibility

The 10/5/5 composition is a backward-compatible campaign-status v1 extension. New snapshots use candidate target and progress fields and the `major`, `minor`, and `combination` classifications. The schema and dashboard also accept immutable historical v1 snapshots that contain the former `completed_attempts`, `structural_attempts`, and `micro_optimization_cap` targets, matching progress fields, and `structural` or `micro` classifications. Historical snapshots render their original labels. Do not rewrite archived snapshots or records.

Version 1 also accepts both canonical and legacy `repository.snapshot_path` values. Any future incompatible change requires a new `schema_version`.
