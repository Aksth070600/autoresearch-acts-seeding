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
- `make evaluate-selected` evaluates Genesis, the two strongest ambiguity-efficiency candidates, and two lowest-time candidates, filling overlaps with the next unique candidates.
- `records/` stores reproducible summaries used by evolution and reports.
- `agent-learnings.md` stores short lessons so agents do not repeat failed ideas.
- `Genesis` is the canonical starting point for every campaign.

## Start an experiment agent

From the repository root, start your coding agent and give it this prompt:

```text
Hi, have a look at agent-instructions.md and let's kick off a new experiment.
Let's do the setup first.
```

The full operating contract is in [`agent-instructions.md`](agent-instructions.md).

## Useful commands

```text
make evolve
make evaluate CANDIDATE=<candidate-name>
make record CANDIDATE=<candidate-name>
make select-evaluation
make evaluate-selected
make report
```

The pinned Python dependency is installed with:

```text
/usr/bin/python3 -m pip install --user -r orchestration-files/requirements.txt
```
