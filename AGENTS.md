# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

- The controlled campaign identity, run constants, and standard candidate composition are authoritative in `orchestration-files/protocol.py`; evaluator, report, status, and record consumers must use that protocol.
- For candidate proposal binding, live status, continuous scheduling, authenticated finish control, or archive finalization, follow `orchestration-files/CAMPAIGN_STATUS.md`; proposal normalization and hashing are authoritative in `orchestration-files/proposal.py`.
- For future continuous archive closure and task-scoped firstmate merge gates, follow `agent-instructions.md`; the campaign worker never merges its own PR.
- When changing the evaluator transaction or HEPP build helpers, run `orchestration-files/tests/test_evaluator_restoration.py`; it protects restored source and binary agreement.
