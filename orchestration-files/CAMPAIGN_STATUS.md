# Live campaign status format

`campaign-status.json` is the public, generated snapshot consumed by the GitHub Pages campaign dashboard. Version 1.0.0 is defined by [`campaign-status.schema.json`](campaign-status.schema.json).

The snapshot contains only protocol-compatible Development evidence. Its scientific fields come from the median timed comparison in generated `summary.json` records:

- Timed seeding time per event, minimized.
- Timed particle ambiguity-resolution efficiency, maximized.

Full-chain time is not read or published as an objective. The generator also derives record durations, progress, failures, the latest campaign Genesis baseline, objective leaders, and the current Pareto front. Do not hand-edit these fields.

## Campaign input

Campaign workers maintain the small non-scientific `campaign-status-input.json` file at the repository root. Start a campaign with this shape:

```json
{
  "schema_version": "1.0.0",
  "campaign": {
    "name": "ACTS Seeding aug25",
    "branch": "autoresearch-acts-seeding/aug25",
    "phase": "fresh Genesis baseline",
    "started_at": "2026-08-27T09:00:00Z"
  },
  "current_attempt": {
    "candidate": "Genesis",
    "mechanism_family": "fresh Genesis baseline",
    "classification": "baseline",
    "controlled_stage": "queued Development run",
    "state": "queued",
    "started_at": "2026-08-27T09:05:00Z"
  },
  "attempt_metadata": [],
  "blockers": [],
  "pull_request_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/pull/123"
}
```

For every non-Genesis candidate, append one item to `attempt_metadata` before its run:

```json
{
  "candidate": "CandidateName",
  "mechanism_family": "stable-mechanism-key",
  "classification": "structural"
}
```

`classification` is `structural` or `micro`. Current Genesis uses `baseline`. `current_attempt.state` is `queued`, `running`, `recording`, or `blocked`. Set `current_attempt` to `null` when no attempt is active. Blockers are short operator-facing strings. The pull request URL is either this repository's PR URL or `null`.

Campaigns use the protocol policy targets of 20 completed attempts, 10 structural attempts, and a micro-optimization cap of 5 by default. A captain-authorized special campaign may override them by adding `targets` to `campaign`:

```json
"targets": {
  "completed_attempts": 1,
  "structural_attempts": 1,
  "micro_optimization_cap": 0
}
```

`completed_attempts` must be a positive integer. The other targets must be non-negative integers and cannot exceed `completed_attempts`. Omitting `targets` preserves the ordinary defaults.

The generator rejects unknown input fields. This prevents scientific metrics from entering the hand-maintained file.

## Generate and publish

Run from the campaign branch:

```text
make campaign-status
/usr/bin/python3 -m unittest tests.test_campaign_status -v
```

The generator scans `records/`, rejects malformed campaign evidence, validates the result, and atomically replaces root `campaign-status.json`. It derives the active commit from the checked-out branch. Commit and push the input and generated snapshot with the normal campaign milestone commit.

The ETA uses the median duration of complete, passed candidate attempts. It stays unavailable until three durations exist. It subtracts elapsed time for a current attempt and becomes unavailable while a blocker is active. Failed runs do not become ETA samples.

## Dashboard fetch contract

At page load, the dashboard makes one unauthenticated request for public pull requests:

```text
https://api.github.com/repos/Aksth070600/autoresearch-acts-seeding/pulls?state=all&per_page=100&sort=created&direction=desc
```

Campaign PRs use the `autoresearch-acts-seeding/` branch prefix. The dropdown sorts them newest to oldest by PR creation time and selects the newest by default. A safe `?ref=<branch>` deep link takes precedence and remains available if discovery fails.

A selected open PR reads the live branch snapshot. A selected closed PR reads the immutable final head SHA returned by the PR list:

```text
https://raw.githubusercontent.com/Aksth070600/autoresearch-acts-seeding/refs/heads/<branch>/campaign-status.json
https://raw.githubusercontent.com/Aksth070600/autoresearch-acts-seeding/<final-head-sha>/campaign-status.json
```

Only a selected open campaign refreshes, at most once per minute with cache busting. The pull-request list is not polled. A refresh error is visible and does not replace that campaign's last good snapshot. Older campaigns without snapshots show an explicit unavailable state. An open snapshot becomes stale after 15 minutes unless a future schema version changes `stale_after_seconds`; a closed snapshot is labeled final.

Schema changes must be backward compatible within version 1 or use a new `schema_version`. Keep the old schema available so published campaign branches remain readable. Numeric per-campaign targets are a backward-compatible v1 extension: all existing snapshots with 20/10/5 remain valid, and consumers already read the generated numeric target values.
