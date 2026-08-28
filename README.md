# ACTS Seeding Autoresearch

ACTS Seeding Autoresearch runs controlled experiments on HEPP02 to improve ACTS seeding speed while preserving reconstruction quality on a fixed ITk workload.

- [View the interactive results report](https://aksth070600.github.io/autoresearch-acts-seeding/)
- [View the live campaign dashboard](https://aksth070600.github.io/autoresearch-acts-seeding/campaign/)

## Start a campaign

From the repository root, start a coding agent with this prompt:

```text
Read agent-instructions.md, complete the setup, and start a new experiment campaign.
```

[`agent-instructions.md`](agent-instructions.md) defines the experiment workflow and agent boundaries.

## Finish a campaign

For a continuous campaign, open the [live campaign dashboard](https://aksth070600.github.io/autoresearch-acts-seeding/campaign/) and select **Finish campaign**. Sign in to GitHub, copy the branch, campaign ID, and control ID from the dashboard into the linked workflow form, then confirm the run.

The request takes effect at a safe experiment boundary. The agent completes the required campaign balance, restores the Genesis implementation, and finalizes the campaign. See the [campaign status guide](orchestration-files/CAMPAIGN_STATUS.md) for the full control contract.

## Essential commands

Run these from the repository root:

```text
make evaluate CANDIDATE=<candidate-name>  # Run a controlled Development experiment
make record CANDIDATE=<candidate-name>    # Show its latest result and failure details
make report                               # Build the results report and dashboard in build/site/
make campaign-status                      # Refresh the campaign status snapshot
make test                                 # Run the non-scientific repository test suite
```

Follow `agent-instructions.md` when running an experiment.

## Safety and scientific controls

- Experiment agents run Development only. The captain controls Evaluation.
- Development and Evaluation use the fixed evaluator protocol. Agents must not override it.
- Each campaign starts from a fresh Genesis baseline. A completed continuous campaign restores the Genesis implementation.
- Pareto comparison uses measured median seeding time per event, which is minimized, and measured median seeding-stage particle efficiency, which is maximized. Peak RSS is diagnostic, not a Pareto objective.

## More detail

- [`agent-instructions.md`](agent-instructions.md) covers experiment setup, candidate work, evidence, and campaign completion.
- [`orchestration-files/CAMPAIGN_STATUS.md`](orchestration-files/CAMPAIGN_STATUS.md) covers live status and authenticated finish control.
