#!/usr/bin/env python3
"""Create, observe, and consume authenticated continuous-campaign stop requests."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from campaign_scheduler import (
    CATEGORY_COUNT_FIELDS,
    SchedulerError,
    finalization_deficits,
    minimal_final_targets,
)
from campaign_status import (
    CAMPAIGN_ID,
    CONTROL_ID,
    DEFAULT_INPUT,
    DEFAULT_RECORDS,
    FULL_COMMIT_SHA,
    GITHUB_LOGIN,
    REPOSITORY_URL,
    StatusError,
    atomic_write_json,
    is_complete_stage_matrix,
    isoformat,
    load_attempts,
    parse_instant,
    validate_live_state,
    validate_ref,
    validate_status,
)
from protocol import PROTOCOL_ID


REPOSITORY = "Aksth070600/autoresearch-acts-seeding"
CONTROL_LABEL = "campaign-control"
CONTROL_TITLE_PREFIX = "Finish continuous campaign: "
CONTROL_MARKER = "acts-seeding-campaign-control:v1"
CONTROL_PAYLOAD_FIELDS = {
    "schema_version",
    "campaign_id",
    "campaign_branch",
    "control_id",
    "requested_at",
    "requested_by",
    "workflow_run_id",
    "workflow_run_attempt",
    "workflow_run_url",
}


class ControlError(RuntimeError):
    """Raised when a stop request is invalid, stale, or unsafe."""


class ForgeError(ControlError):
    """Raised when GitHub cannot provide or persist control state."""


class GitHubForge:
    """Small GitHub REST adapter. Tests use an in-memory fake instead."""

    def __init__(self, token: str, repository: str = REPOSITORY) -> None:
        if not token:
            raise ForgeError("GITHUB_TOKEN is required")
        self.token = token
        self.repository = repository
        self.api_root = "https://api.github.com"

    def _api(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        data = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "acts-seeding-campaign-control",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.api_root}{path}", data=data, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=30) as response:  # nosec B310 - fixed GitHub API root
                status = response.status
                body = response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise ForgeError(
                f"GitHub API returned HTTP {error.code}: {detail}"
            ) from error
        except (OSError, URLError) as error:
            raise ForgeError(f"GitHub API request failed: {error}") from error
        if status not in expected:
            raise ForgeError(f"GitHub API returned unexpected HTTP {status}")
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as error:
            raise ForgeError("GitHub API returned malformed JSON") from error

    def get_campaign_snapshot(self, branch: str) -> dict[str, Any]:
        encoded_branch = urlencode({"ref": branch})
        value = self._api(
            "GET",
            f"/repos/{self.repository}/contents/orchestration-files/campaign-status.json?{encoded_branch}",
        )
        try:
            encoded = "".join(value["content"].split())
            content = base64.b64decode(encoded, validate=True)
            snapshot = json.loads(content.decode("utf-8"))
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise ForgeError("campaign snapshot response is malformed") from error
        if not isinstance(snapshot, dict):
            raise ForgeError("campaign snapshot must be a JSON object")
        return snapshot

    def open_campaign_pulls(self, branch: str) -> list[dict[str, Any]]:
        owner = self.repository.split("/", 1)[0]
        query = urlencode(
            {"state": "open", "head": f"{owner}:{branch}", "per_page": 100}
        )
        value = self._api("GET", f"/repos/{self.repository}/pulls?{query}")
        if not isinstance(value, list):
            raise ForgeError("GitHub pull request response is malformed")
        return value

    def control_issues(self) -> list[dict[str, Any]]:
        query = urlencode(
            {
                "state": "all",
                "labels": CONTROL_LABEL,
                "per_page": 100,
                "sort": "created",
            }
        )
        value = self._api("GET", f"/repos/{self.repository}/issues?{query}")
        if not isinstance(value, list):
            raise ForgeError("GitHub issue response is malformed")
        return [
            item
            for item in value
            if isinstance(item, dict) and "pull_request" not in item
        ]

    def ensure_control_label(self) -> None:
        encoded = quote(CONTROL_LABEL, safe="")
        try:
            self._api("GET", f"/repos/{self.repository}/labels/{encoded}")
        except ForgeError as error:
            if "HTTP 404" not in str(error):
                raise
            self._api(
                "POST",
                f"/repos/{self.repository}/labels",
                {
                    "name": CONTROL_LABEL,
                    "color": "b60205",
                    "description": "Authenticated campaign finish requests",
                },
                expected=(201,),
            )

    def create_control_issue(self, title: str, body: str) -> dict[str, Any]:
        value = self._api(
            "POST",
            f"/repos/{self.repository}/issues",
            {"title": title, "body": body, "labels": [CONTROL_LABEL]},
            expected=(201,),
        )
        if not isinstance(value, dict):
            raise ForgeError("GitHub issue creation response is malformed")
        return value


def _workflow_context(context: dict[str, Any]) -> dict[str, Any]:
    actor = context.get("actor")
    run_id = context.get("run_id")
    run_attempt = context.get("run_attempt")
    if not isinstance(actor, str) or not GITHUB_LOGIN.fullmatch(actor):
        raise ControlError("workflow actor is invalid")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ControlError("workflow run id is invalid")
    if (
        not isinstance(run_attempt, int)
        or isinstance(run_attempt, bool)
        or run_attempt < 1
    ):
        raise ControlError("workflow run attempt is invalid")
    return {"actor": actor, "run_id": run_id, "run_attempt": run_attempt}


def control_payload(
    campaign: dict[str, Any], context: dict[str, Any], requested_at: datetime
) -> dict[str, Any]:
    context = _workflow_context(context)
    return {
        "schema_version": "1.0.0",
        "campaign_id": campaign["campaign_id"],
        "campaign_branch": campaign["branch"],
        "control_id": campaign["control_id"],
        "requested_at": isoformat(requested_at),
        "requested_by": context["actor"],
        "workflow_run_id": context["run_id"],
        "workflow_run_attempt": context["run_attempt"],
        "workflow_run_url": f"{REPOSITORY_URL}/actions/runs/{context['run_id']}",
    }


def issue_body(payload: dict[str, Any]) -> str:
    return (
        "This issue is the durable authenticated finish request for one continuous campaign.\n\n"
        "Do not edit or reuse it for another campaign. The campaign worker consumes it only at a safe candidate boundary.\n\n"
        f"<!-- {CONTROL_MARKER}\n"
        + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        + "\n-->\n"
    )


def parse_issue_payload(issue: dict[str, Any]) -> dict[str, Any]:
    body = issue.get("body")
    if not isinstance(body, str):
        raise ControlError("campaign-control issue has no machine-readable body")
    pattern = re.compile(
        rf"<!-- {re.escape(CONTROL_MARKER)}\n([^\n]+)\n-->", re.MULTILINE
    )
    matches = pattern.findall(body)
    if len(matches) != 1:
        raise ControlError("campaign-control issue marker is missing or ambiguous")
    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as error:
        raise ControlError("campaign-control issue payload is malformed") from error
    if not isinstance(payload, dict) or set(payload) != CONTROL_PAYLOAD_FIELDS:
        raise ControlError("campaign-control issue payload fields are invalid")
    if payload.get("schema_version") != "1.0.0":
        raise ControlError("campaign-control issue schema is unsupported")
    campaign_id = payload.get("campaign_id")
    branch = payload.get("campaign_branch")
    control_id = payload.get("control_id")
    if not isinstance(campaign_id, str) or not CAMPAIGN_ID.fullmatch(campaign_id):
        raise ControlError("campaign-control issue campaign id is invalid")
    try:
        validate_ref(branch)
    except StatusError as error:
        raise ControlError(str(error)) from error
    if not isinstance(control_id, str) or not CONTROL_ID.fullmatch(control_id):
        raise ControlError("campaign-control issue control id is invalid")
    parse_instant(payload.get("requested_at"), "requested_at")
    _workflow_context(
        {
            "actor": payload.get("requested_by"),
            "run_id": payload.get("workflow_run_id"),
            "run_attempt": payload.get("workflow_run_attempt"),
        }
    )
    if payload.get("workflow_run_url") != (
        f"{REPOSITORY_URL}/actions/runs/{payload['workflow_run_id']}"
    ):
        raise ControlError("campaign-control issue workflow URL is invalid")
    return payload


def request_from_issue(
    issue: dict[str, Any], payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = payload or parse_issue_payload(issue)
    number = issue.get("number")
    url = issue.get("html_url")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ControlError("campaign-control issue number is invalid")
    if url != f"{REPOSITORY_URL}/issues/{number}":
        raise ControlError("campaign-control issue URL is invalid")
    return {
        key: payload[key] for key in CONTROL_PAYLOAD_FIELDS if key != "schema_version"
    } | {"issue_number": number, "issue_url": url}


def _matching_issue(
    issues: list[dict[str, Any]], campaign: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    exact: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for issue in issues:
        title = issue.get("title")
        if not isinstance(title, str) or not title.startswith(CONTROL_TITLE_PREFIX):
            continue
        label_names = {
            label.get("name")
            for label in issue.get("labels", [])
            if isinstance(label, dict)
        }
        authored_by_actions = (
            issue.get("user", {}).get("login") == "github-actions[bot]"
        )
        if CONTROL_LABEL not in label_names or not authored_by_actions:
            if title == CONTROL_TITLE_PREFIX + campaign["campaign_id"]:
                raise ControlError(
                    "campaign-control issue was not created by the trusted workflow"
                )
            continue
        try:
            payload = parse_issue_payload(issue)
        except ControlError:
            if title == CONTROL_TITLE_PREFIX + campaign["campaign_id"]:
                raise
            continue
        if payload["campaign_id"] != campaign["campaign_id"]:
            continue
        if (
            payload["campaign_branch"] != campaign["branch"]
            or payload["control_id"] != campaign["control_id"]
        ):
            raise ControlError(
                "stale or replayed stop request uses this campaign id with different identity"
            )
        exact.append((issue, payload))
    if len(exact) > 1:
        raise ControlError(
            "multiple stop requests exist for the same campaign identity"
        )
    return exact[0] if exact else None


def _validate_request_identity(campaign_id: str, branch: str, control_id: str) -> None:
    if not CAMPAIGN_ID.fullmatch(campaign_id):
        raise ControlError("campaign_id is invalid")
    try:
        validate_ref(branch)
    except StatusError as error:
        raise ControlError(str(error)) from error
    if not CONTROL_ID.fullmatch(control_id):
        raise ControlError("control_id is invalid")


def request_stop(
    forge: Any,
    *,
    campaign_id: str,
    branch: str,
    control_id: str,
    context: dict[str, Any],
    requested_at: datetime,
) -> dict[str, Any]:
    """Validate a dispatch and create one durable idempotent control issue."""

    _validate_request_identity(campaign_id, branch, control_id)
    try:
        snapshot = forge.get_campaign_snapshot(branch)
        validate_status(snapshot)
    except (StatusError, ForgeError) as error:
        raise ControlError(f"unknown or malformed campaign: {error}") from error
    campaign = snapshot["campaign"]
    if campaign.get("mode") != "continuous":
        raise ControlError("selected campaign is not continuous")
    if campaign.get("branch") != branch:
        raise ControlError("campaign branch does not match the selected branch")
    if campaign.get("campaign_id") != campaign_id:
        raise ControlError("campaign id does not match the selected campaign")
    if campaign.get("control_id") != control_id:
        raise ControlError(
            "control id is stale or does not match the selected campaign"
        )
    if snapshot["control"]["state"] == "completed":
        raise ControlError(
            "completed campaigns are immutable and cannot be stopped again"
        )

    pull_url = snapshot.get("links", {}).get("pull_request")
    pulls = forge.open_campaign_pulls(branch)
    matching_pulls = [
        pull
        for pull in pulls
        if pull.get("html_url") == pull_url
        and pull.get("head", {}).get("ref") == branch
        and pull.get("head", {}).get("repo", {}).get("full_name") == REPOSITORY
    ]
    if len(matching_pulls) != 1:
        raise ControlError("campaign must have one matching open pull request")

    issues = forge.control_issues()
    existing = _matching_issue(issues, campaign)
    if existing is not None:
        return request_from_issue(*existing)
    if snapshot["control"]["state"] != "open":
        raise ControlError("campaign stop request has already been consumed")

    payload = control_payload(campaign, context, requested_at)
    forge.ensure_control_label()
    issue = forge.create_control_issue(
        CONTROL_TITLE_PREFIX + campaign_id, issue_body(payload)
    )
    return request_from_issue(issue, payload)


def observe_stop_request(
    live_state: dict[str, Any], issues: list[dict[str, Any]], observed_at: datetime
) -> tuple[dict[str, Any], bool]:
    """Persist an authenticated issue without changing an active transaction."""

    state = validate_live_state(live_state)
    if state["campaign"].get("mode") != "continuous":
        raise ControlError("selected campaign is not continuous")
    # Once branch state contains the request, it is the restart authority. A
    # later issue edit or network failure cannot erase or replace it.
    if state["control"]["request"] is not None:
        return state, False
    existing = _matching_issue(issues, state["campaign"])
    if existing is None:
        return state, False
    request = request_from_issue(*existing)
    updated = copy.deepcopy(state)
    updated["control"].update(
        {
            "state": "requested",
            "request": request,
            "observed_at": isoformat(observed_at),
        }
    )
    return validate_live_state(updated), True


def consume_stop_request(
    live_state: dict[str, Any], counts: dict[str, int], consumed_at: datetime
) -> tuple[dict[str, Any], bool]:
    """Fix the smallest final ratio only after the active transaction is recorded."""

    state = validate_live_state(live_state)
    control_state = state.get("control", {}).get("state")
    if control_state == "consumed":
        return state, False
    if control_state != "requested":
        raise ControlError("no observed stop request is ready to consume")
    if state["current_attempt"] is not None:
        raise ControlError(
            "active candidate must finish and be recorded before stop consumption"
        )
    updated = copy.deepcopy(state)
    updated["control"].update(
        {"state": "consumed", "consumed_at": isoformat(consumed_at)}
    )
    updated["scheduler"].update(
        {
            "state": "finishing",
            "final_targets": minimal_final_targets(counts),
            "blocker": None,
        }
    )
    return validate_live_state(updated), True


def _git(repository_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _scientific_run_blockers(records_root: Path, started_at: datetime) -> list[str]:
    blockers: list[str] = []
    for path in sorted(records_root.glob("**/summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            blockers.append(f"cannot validate scientific record {path}: {error}")
            continue
        timestamp = summary.get("started_at") if isinstance(summary, dict) else None
        try:
            started = parse_instant(timestamp, f"{path}: started_at")
        except StatusError:
            continue
        if started < started_at:
            continue
        if (
            str(summary.get("mode", "development")).lower() != "development"
            or str(summary.get("category", "")).lower() == "evaluation"
        ):
            blockers.append(f"unauthorized non-Development run exists: {path}")
        if summary.get("protocol_id") != PROTOCOL_ID:
            blockers.append(f"unauthorized protocol run exists: {path}")
        stages = summary.get("stages")
        if isinstance(stages, list):
            for stage in stages:
                if isinstance(stage, dict) and stage.get("events") == 50:
                    blockers.append(f"unauthorized 50-event stage exists: {path}")
                    break
        if (
            summary.get("status") == "passed"
            and summary.get("protocol_id") == PROTOCOL_ID
        ):
            if not is_complete_stage_matrix(stages):
                blockers.append(f"passed run has an unauthorized stage matrix: {path}")
    return blockers


def finalization_blockers(
    live_state: dict[str, Any],
    attempts: list[dict[str, Any]],
    records_root: Path,
    repository_root: Path,
) -> list[str]:
    """Return concrete blockers for graceful continuous-campaign completion."""

    state = validate_live_state(live_state)
    blockers: list[str] = []
    if state["campaign"].get("mode") != "continuous":
        return ["campaign is not continuous"]
    if state["control"]["state"] != "consumed":
        blockers.append("a valid stop request has not been consumed")
    if state["current_attempt"] is not None:
        blockers.append("a candidate transaction is still active")
    if state["scheduler"]["state"] not in {"finishing", "blocked"}:
        blockers.append("scheduler is not in finalization")
    if state["scheduler"]["blocker"] is not None:
        blockers.append(state["scheduler"]["blocker"])

    completed = {
        attempt["candidate"]: attempt
        for attempt in attempts
        if attempt["state"] == "completed" and attempt["classification"] != "baseline"
    }
    counts = {
        category: sum(
            attempt["classification"] == category for attempt in completed.values()
        )
        for category in CATEGORY_COUNT_FIELDS
    }
    final_targets = state["scheduler"]["final_targets"]
    if final_targets is None:
        blockers.append("exact final targets have not been persisted")
    else:
        try:
            deficits = finalization_deficits(counts, final_targets)
            if any(deficits.values()):
                blockers.append(f"final category deficits remain: {deficits}")
        except SchedulerError as error:
            blockers.append(str(error))

    genesis = [
        attempt
        for attempt in attempts
        if attempt["state"] == "completed" and attempt["classification"] == "baseline"
    ]
    if not genesis:
        blockers.append("no complete protocol-compatible Development Genesis exists")
    metadata = {item["candidate"]: item for item in state["attempt_metadata"]}
    for candidate, attempt in completed.items():
        item = metadata.get(candidate)
        if not isinstance(item, dict) or not isinstance(item.get("evidence"), dict):
            blockers.append(f"retained candidate lacks evidence: {candidate}")
        commit = attempt.get("implementation_commit")
        if not isinstance(commit, str) or not FULL_COMMIT_SHA.fullmatch(commit):
            blockers.append(
                f"retained candidate lacks a full implementation commit: {candidate}"
            )
            continue
        reachable = _git(repository_root, "merge-base", "--is-ancestor", commit, "HEAD")
        if reachable.returncode != 0:
            blockers.append(
                f"candidate implementation commit is not reachable: {candidate}"
            )

    genesis_commit = state["campaign"]["genesis_commit"]
    if (
        _git(
            repository_root, "merge-base", "--is-ancestor", genesis_commit, "HEAD"
        ).returncode
        != 0
    ):
        blockers.append("Genesis commit is not reachable from the archive branch")
    restored = _git(
        repository_root,
        "diff",
        "--quiet",
        genesis_commit,
        "--",
        "optimization-files",
    )
    if restored.returncode != 0:
        blockers.append("optimization-files/ is not restored exactly to Genesis")
    blockers.extend(
        _scientific_run_blockers(
            records_root,
            parse_instant(state["campaign"]["started_at"], "campaign.started_at"),
        )
    )
    return blockers


def mark_completed(
    live_state: dict[str, Any], completed_at: datetime
) -> dict[str, Any]:
    """Mark an already validated graceful campaign terminal and immutable."""

    state = validate_live_state(live_state)
    if state["control"]["state"] == "completed":
        return state
    if state["control"]["state"] != "consumed" or state["current_attempt"] is not None:
        raise ControlError("campaign is not ready for terminal completion")
    if state["scheduler"]["state"] != "finishing":
        raise ControlError("scheduler is not ready for terminal completion")
    updated = copy.deepcopy(state)
    updated["control"].update(
        {"state": "completed", "completed_at": isoformat(completed_at)}
    )
    updated["scheduler"]["state"] = "completed"
    return validate_live_state(updated)


def completed_counts(attempts: list[dict[str, Any]]) -> dict[str, int]:
    return {
        category: len(
            {
                attempt["candidate"]
                for attempt in attempts
                if attempt["state"] == "completed"
                and attempt["classification"] == category
            }
        )
        for category in CATEGORY_COUNT_FIELDS
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    request_parser = subparsers.add_parser("request-stop")
    request_parser.add_argument("--campaign-id", required=True)
    request_parser.add_argument("--branch", required=True)
    request_parser.add_argument("--control-id", required=True)

    check_parser = subparsers.add_parser("check-stop")
    check_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    consume_parser = subparsers.add_parser("consume-stop")
    consume_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    consume_parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    finalize_parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    finalize_parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    return parser.parse_args()


def _load_input(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ControlError(f"cannot read campaign input: {error}") from error
    try:
        return validate_live_state(value)
    except StatusError as error:
        raise ControlError(str(error)) from error


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    if args.command == "request-stop":
        context = {
            "actor": os.environ.get("GITHUB_ACTOR"),
            "run_id": int(os.environ.get("GITHUB_RUN_ID", "0")),
            "run_attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
        }
        request = request_stop(
            GitHubForge(os.environ.get("GITHUB_TOKEN", "")),
            campaign_id=args.campaign_id,
            branch=args.branch,
            control_id=args.control_id,
            context=context,
            requested_at=now,
        )
        print(f"durable stop request: {request['issue_url']}")
        return 0

    state = _load_input(args.input)
    forge = (
        GitHubForge(os.environ.get("GITHUB_TOKEN", ""))
        if args.command == "check-stop"
        else None
    )
    if args.command == "check-stop":
        updated, changed = observe_stop_request(state, forge.control_issues(), now)
        if changed:
            atomic_write_json(args.input, updated)
            print(
                f"observed stop request: {updated['control']['request']['issue_url']}"
            )
        else:
            print("no new stop request")
        return 0

    attempts = load_attempts(
        args.records.resolve(),
        state,
        args.repository_root.resolve() if args.command == "finalize" else None,
    )
    if args.command == "consume-stop":
        updated, changed = consume_stop_request(state, completed_counts(attempts), now)
        if changed:
            atomic_write_json(args.input, updated)
            print("consumed stop request and persisted exact final targets")
        else:
            print("stop request already consumed")
        return 0

    blockers = finalization_blockers(
        state, attempts, args.records.resolve(), args.repository_root.resolve()
    )
    if blockers:
        for blocker in blockers:
            print(f"blocker: {blocker}", file=sys.stderr)
        return 1
    atomic_write_json(args.input, mark_completed(state, now))
    print("campaign finalization checks passed; campaign marked completed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ControlError, StatusError, SchedulerError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
