# Autoresearch ACTS Seeding

Autoresearch ACTS Seeding is an experiment platform for improving the performance of ACTS Seeding2 track reconstruction.

The project explores candidate algorithm and configuration changes through controlled, reproducible experiments.
Each change must preserve reconstruction correctness, physics validity, and clear evidence about the environment and data used.

The initial focus is ITk seeding with ACTS on HEPP02.

## Interactive reports

Open the latest interactive comparison report on [GitHub Pages](https://aksth070600.github.io/autoresearch-acts-seeding/).

To regenerate it, open the repository's **Actions** tab, select **Publish ACTS reports**, and choose **Run workflow**.
The workflow supports development, evaluation, or all records, plus configurable X-axis, Y-axis, and baseline selections.
Pushes to `main` also publish the report automatically.

## Candidate evolution

Run `make evolve` to maintain a historical NSGA-II population from successful records.
The baseline is always retained.
A non-baseline candidate enters the eligible pool when it improves total time per event, seeding time per event, or one of the selected seeding, CKF, or ambiguity efficiencies.
The selected population is saved in `records/evolution/population.json`.
The command returns a candidate implementation commit for the next optimization attempt.

Install the pinned local dependency with:

```text
/usr/bin/python3 -m pip install --user -r orchestration-files/requirements.txt
```

## Principles

- Measure performance with reproducible workloads.
- Keep candidate changes isolated and reviewable.
- Preserve correctness before optimizing speed or efficiency.
- Record the software, data, configuration, and results for each experiment.
- Distinguish development experiments from final scientific claims.

This project is in its initial setup phase.
