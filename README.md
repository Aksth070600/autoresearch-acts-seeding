# ACTS Seeding Autoresearch

An experiment platform for making ACTS Seeding2 faster without sacrificing reconstruction quality.
It runs controlled candidates on the fixed ITk workload through ACTS on HEPP02, keeps the results, and helps the next experiment build on what worked.

[Open the interactive report](https://aksth070600.github.io/autoresearch-acts-seeding/)

## How the repository works

```mermaid
flowchart LR
    A[Experiment agent] --> B[make evolve]
    B --> C[Edit optimization-files/]
    C --> D[make evaluate]
    D --> E[make record]
    E --> F[records/]
    F --> B
    F --> G[make report]
    H[agent-learnings.md] --> A
```

- `optimization-files/` contains the ACTS implementation files an experiment may change.
- `make evolve` selects a promising implementation from successful history.
- `make evaluate CANDIDATE=name` runs the controlled development workload.
- `make record CANDIDATE=name` returns the latest summary and failure details without editing the archive.
- `records/` stores reproducible summaries used by evolution and reports.
- `agent-learnings.md` stores short lessons so agents do not repeat failed ideas.
- `Genesis` is the canonical starting point for every campaign.

## Start an experiment agent

From the repository root, start your coding agent and give it this prompt:

```text
You are the ACTS Seeding autoresearch agent.
Read agent-instructions.md and follow it exactly.
Start by running the Genesis baseline with:
make evaluate CANDIDATE=Genesis
Then use make record to inspect the result, make evolve for implementation inspiration, and continue one focused experiment at a time.
Keep the campaign autonomous until I stop it or a real setup or infrastructure problem needs my help.
```

The full operating contract is in [`agent-instructions.md`](agent-instructions.md).

## Useful commands

```text
make evolve
make evaluate CANDIDATE=<candidate-name>
make record CANDIDATE=<candidate-name>
make report
```

The pinned Python dependency is installed with:

```text
/usr/bin/python3 -m pip install --user -r orchestration-files/requirements.txt
```
