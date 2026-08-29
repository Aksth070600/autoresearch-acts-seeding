import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT = PROJECT_ROOT / "orchestration-files" / "report.py"
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from protocol import current_protocol  # noqa: E402
from proposal import bind_proposal  # noqa: E402
from report import (  # noqa: E402
    REPOSITORY_URL,
    build_report,
    classify_speed_claim,
    commit_url,
    load_records,
    metric_label,
)
from visualizations.pareto import render  # noqa: E402


class ReportPreviewTests(unittest.TestCase):
    def run_report(
        self,
        records: Path,
        output: Path,
        dataset: str = "development",
        x_metric: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(REPORT),
            "--records",
            str(records),
            "--output",
            str(output),
            "--dataset",
            dataset,
        ]
        if x_metric is not None:
            command.extend(["--x-metric", x_metric])
        return subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_empty_reset_writes_placeholder_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = root / "records"
            records.mkdir()
            output = root / "site"

            result = self.run_report(records, output)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / ".nojekyll").is_file())
            self.assertTrue((output / "campaign" / "index.html").is_file())
            campaign = (output / "campaign" / "index.html").read_text(encoding="utf-8")
            self.assertIn("ACTS Seeding Live Campaign", campaign)
            self.assertNotIn("Open results report", campaign)
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("No complete active v3 summaries", index)
            self.assertIn('href="campaign/"', index)
            self.assertIn('"rows":[]', index)
            self.assertIn('"x_metric": "timed_seeding_time_per_event_ms"', index)
            self.assertIn('"y_metric": "timed_seeding_particle_efficiency"', index)

    @staticmethod
    def summary(
        candidate: str,
        category: str,
        time: float,
        efficiency: float,
        peak_rss_kb: float | None = 1024.0,
    ) -> dict:
        run_metrics = {
            "timing": {"seeding": {"time_per_event_ms": time / 3}},
            "performance": {"seeding": {"efficiency_particles": efficiency}},
        }
        repetitions = [
            {
                "repetition": number,
                "events": 10,
                "stage": "seeding",
                "metrics_mode": "none",
                "status": "passed",
                "run_metrics": run_metrics,
            }
            for number in (1, 2, 3)
        ]
        return {
            "candidate_name": candidate,
            "category": category,
            "status": "passed",
            "baseline": candidate == "Genesis",
            "protocol_id": "acts-seeding-v3",
            "protocol": current_protocol(),
            "started_at": "2026-08-26T12:00:00+00:00",
            "stages": [
                {
                    "comparison": "smoke",
                    "metrics_mode": "none",
                    "events": 1,
                    "stage": "seeding",
                    "status": "passed",
                },
                *[
                    {
                        "comparison": "timed",
                        "repetition": number,
                        "metrics_mode": "none",
                        "events": 10,
                        "stage": "seeding",
                        "status": "passed",
                        "run_metrics": run_metrics,
                    }
                    for number in (1, 2, 3)
                ],
                {
                    "comparison": "rss",
                    "metrics_mode": "time",
                    "events": 10,
                    "stage": "seeding",
                    "status": "passed",
                },
            ],
            "timed_comparison": {
                "aggregation": "median",
                "repetition_count": 3,
                "required_repetitions": 3,
                "events": 10,
                "complete": True,
                "repetitions": repetitions,
                "median_run_metrics": run_metrics,
            },
            "rss_evidence": {
                "complete": peak_rss_kb is not None,
                "events": 10,
                "stage": "seeding",
                "metrics_mode": "time",
                "status": "passed",
                "resource_metrics": (
                    {"peak_rss_kb": peak_rss_kb} if peak_rss_kb is not None else {}
                ),
            },
        }

    @staticmethod
    def v2_summary(
        candidate: str = "Genesis",
        category: str = "Development",
        time: float = 12.0,
        seeding_efficiency: float = 0.9,
        ambiguity_efficiency: float = 0.5,
        peak_rss_kb: float = 1024.0,
    ) -> dict:
        events = 10 if category == "Development" else 50
        run_metrics = {
            "timing": {"seeding": {"time_per_event_ms": time}},
            "performance": {
                "seeding": {"efficiency_particles": seeding_efficiency},
                "ambiguity_resolution": {
                    "efficiency_particles": ambiguity_efficiency
                },
            },
        }
        repetitions = [
            {
                "repetition": number,
                "events": events,
                "status": "passed",
                "run_metrics": run_metrics,
            }
            for number in (1, 2, 3)
        ]
        return {
            "candidate_name": candidate,
            "category": category,
            "status": "passed",
            "baseline": candidate == "Genesis",
            "protocol_id": "acts-seeding-v2",
            "protocol": {
                "id": "acts-seeding-v2",
                "acts_version": "v46.5.0",
                "dataset": "ttbar_pu200",
                "execution_target": "HEPP02",
                "threads": 1,
                "seed": 42,
                "pileup": 200,
                "development_events": 10,
                "evaluation_events": 50,
                "timed_repetitions": 3,
                "timed_aggregation": "median",
                "expected_unmasked_fpe_handling": "accept only after every requested event completed",
            },
            "started_at": "2026-08-26T12:00:00+00:00",
            "stages": [
                {
                    "name": "ten_event_full_clean",
                    "comparison": "clean",
                    "metrics_mode": "none",
                    "events": events,
                    "status": "passed",
                    "run_metrics": run_metrics,
                },
                *[
                    {
                        "name": f"timed_full_repetition_{number}",
                        "comparison": "timed",
                        "repetition": number,
                        "metrics_mode": "time",
                        "events": events,
                        "status": "passed",
                        "run_metrics": run_metrics,
                    }
                    for number in (1, 2, 3)
                ],
            ],
            "timed_comparison": {
                "aggregation": "median",
                "repetition_count": 3,
                "required_repetitions": 3,
                "events": events,
                "complete": True,
                "repetitions": repetitions,
                "median_run_metrics": run_metrics,
                "median_resource_metrics": {"peak_rss_kb": peak_rss_kb},
            },
        }

    def test_report_reads_hypothesis_from_measured_summary_copy(self) -> None:
        commit = "a" * 40
        proposal = {
            "schema_version": "1.0.0",
            "candidate": "Candidate",
            "implementation_commit": commit,
            "hypothesis": "The measured summary hypothesis is authoritative.",
            "falsifier": "Seeding time does not decrease.",
            "predicted_directions": {
                "timed_seeding_time_per_event_ms": "decrease",
                "timed_seeding_particle_efficiency": "unchanged",
            },
            "expected_hot_path": "The triplet traversal hot path.",
            "changed_symbols": ["Acts::TripletSeeder::run"],
            "intended_files": [
                "optimization-files/Core/src/Seeding2/TripletSeeder.cpp"
            ],
            "novelty_reason": "This traversal bound has not been tested.",
            "source_references": [
                {
                    "source_type": "Genesis",
                    "reference": "records/Development/Genesis/summary.json",
                    "relevance": "Baseline timing evidence.",
                    "directly_inspected": True,
                }
            ],
            "combination_provenance": None,
        }
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records" / "Development" / "Candidate"
            records.mkdir(parents=True)
            summary = self.summary("Candidate", "Development", 12.0, 0.9)
            summary["implementation_commit"] = commit
            summary["proposal_binding"] = bind_proposal(
                proposal, "Candidate", commit
            )
            summary["combination_provenance"] = None
            (records / "summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )

            row = load_records(records.parents[1], "development")[0]

        self.assertEqual(row["proposal"]["hypothesis"], proposal["hypothesis"])

    def test_current_report_keeps_raw_v3_rss_and_timing_dispersion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records" / "Development" / "Candidate"
            records.mkdir(parents=True)
            summary = self.summary("Candidate", "Development", 36.0, 0.91, 4096.0)
            timings = (10.0, 12.0, 30.0)
            for repetition, timing in zip(summary["timed_comparison"]["repetitions"], timings):
                repetition["run_metrics"] = json.loads(
                    json.dumps(repetition["run_metrics"])
                )
                repetition["run_metrics"]["timing"]["seeding"]["time_per_event_ms"] = timing
            summary["timed_comparison"]["median_run_metrics"]["timing"]["seeding"]["time_per_event_ms"] = 12.0
            (records / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

            row = load_records(records.parents[1], "development")[0]
            report = build_report([row], "Genesis", "development")

        self.assertEqual(row["metrics"]["rss_peak_rss_kb"], 4096.0)
        self.assertEqual(row["metrics"]["timed_seeding_time_per_event_ms"], 12.0)
        self.assertEqual(row["metrics"]["timed_seeding_particle_efficiency"], 0.91)
        self.assertEqual(row["timing_evidence"]["median_ms"], 12.0)
        self.assertEqual(row["timing_evidence"]["range_ms"], 20.0)
        self.assertEqual(row["timing_evidence"]["median_absolute_deviation_ms"], 2.0)
        self.assertEqual(report["rss_metric_key"], "rss_peak_rss_kb")
        self.assertNotIn("rss_normalization", report)

    def test_peak_rss_is_loaded_only_from_separate_rss_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records" / "Development" / "Candidate"
            records.mkdir(parents=True)
            summary = self.summary("Candidate", "Development", 12.0, 0.9, 2_097_152.0)
            (records / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

            row = load_records(records.parents[1], "development")[0]

            self.assertEqual(row["metrics"]["rss_peak_rss_kb"], 2_097_152.0)
            self.assertNotIn("timed_peak_rss_kb", row["metrics"])

    def test_genesis_report_averages_only_genesis_and_keeps_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            for name, category, time, efficiency in (
                ("20260826T120000000000Z-Genesis", "Development", 100.0, 0.90),
                ("20260826T130000000000Z-Genesis", "Development", 120.0, 0.94),
                ("20260826T140000000000Z-Candidate", "Development", 80.0, 0.80),
            ):
                folder = records / category / name
                folder.mkdir(parents=True)
                (folder / "summary.json").write_text(
                    json.dumps(self.summary(name.split("-")[-1], category, time, efficiency)),
                    encoding="utf-8",
                )

            rows = load_records(records, "development")
            report = build_report(rows, "Genesis", "development")
            genesis = [row for row in report["rows"] if row["candidate"] == "Genesis"]
            candidates = [row for row in report["rows"] if row["candidate"] == "Candidate"]

            self.assertEqual(len(genesis), 1)
            self.assertEqual(genesis[0]["sample_count"], 2)
            self.assertAlmostEqual(
                genesis[0]["metrics"]["timed_seeding_time_per_event_ms"], 110.0 / 3
            )
            self.assertAlmostEqual(
                genesis[0]["metrics"]["timed_seeding_particle_efficiency"], 0.92
            )
            self.assertEqual(
                [item["record"] for item in genesis[0]["provenance"]],
                [
                    "Development/20260826T120000000000Z-Genesis/summary.json",
                    "Development/20260826T130000000000Z-Genesis/summary.json",
                ],
            )
            self.assertEqual(len(candidates), 1)
            self.assertAlmostEqual(candidates[0]["metrics"]["timed_seeding_time_per_event_ms"], 80.0 / 3)
            self.assertEqual(report["genesis_aggregation"]["sample_count"], 2)
            self.assertEqual(
                report["primary_objectives"]["minimize"], "timed_seeding_time_per_event_ms"
            )
            self.assertEqual(
                report["metric_labels"]["timed_seeding_time_per_event_ms"],
                "PRIMARY: seeding time/event (ms)",
            )
            self.assertNotIn("timed_total_time_per_event_ms", report["metric_labels"])
            self.assertEqual(
                metric_label("timed_total_time_per_event_ms"),
                "Timed Total Time Per Event Ms",
            )

    def test_dataset_views_do_not_mix_categories(self) -> None:
        rows = [
            {
                "candidate": "Genesis",
                "category": "Development",
                "protocol_id": "acts-seeding-v3",
                "record": "Development/Genesis-a/summary.json",
                "commit": "a",
                "metrics": {"timed_total_time_per_event_ms": 100.0},
            },
            {
                "candidate": "Genesis",
                "category": "Evaluation",
                "protocol_id": "acts-seeding-v3",
                "record": "Evaluation/Genesis-b/summary.json",
                "commit": "b",
                "metrics": {"timed_total_time_per_event_ms": 120.0},
            },
        ]

        development = build_report(rows, "Genesis", "development")
        evaluation = build_report(rows, "Genesis", "evaluation")

        self.assertEqual({row["category"] for row in development["rows"]}, {"Development"})
        self.assertEqual(development["genesis_aggregation"]["sample_count"], 1)
        self.assertEqual(
            development["rows"][0]["metrics"]["timed_total_time_per_event_ms"], 100.0
        )
        self.assertEqual({row["category"] for row in evaluation["rows"]}, {"Evaluation"})
        self.assertEqual(evaluation["genesis_aggregation"]["sample_count"], 1)
        self.assertEqual(
            evaluation["rows"][0]["metrics"]["timed_total_time_per_event_ms"], 120.0
        )

    @staticmethod
    def run_pareto_javascript(report: dict, body: str) -> dict:
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is required for report JavaScript tests")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "index.html"
            render(
                report,
                output,
                defaults={
                    "x_metric": "timed_seeding_time_per_event_ms",
                    "y_metric": "timed_seeding_particle_efficiency",
                    "baseline": "Genesis",
                },
            )
            html = output.read_text(encoding="utf-8")
        script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        browser_stub = r"""
class FakeElement {
  constructor(tagName = 'DIV') {
    this.tagName = tagName.toUpperCase();
    this.options = [];
    this.children = [];
    this._value = '';
    this.hidden = false;
    this.textContent = '';
    this.style = {};
  }
  get value() { return this._value; }
  set value(value) { this._value = String(value); }
  appendChild(child) {
    this.children.push(child);
    if (child.tagName === 'OPTION') {
      this.options.push(child);
      if (this.options.length === 1) this._value = child.value;
    }
    return child;
  }
  replaceChildren(...children) {
    this.children = [];
    this.options = [];
    this._value = '';
    children.forEach((child) => this.appendChild(child));
  }
  addEventListener() {}
  on() {}
  removeListener() {}
  set innerHTML(value) { this._innerHTML = value; }
  get innerHTML() { return this._innerHTML || ''; }
}
const elements = new Map();
const document = {
  createElement: (tagName) => new FakeElement(tagName),
  getElementById: (id) => {
    if (!elements.has(id)) elements.set(id, new FakeElement());
    return elements.get(id);
  },
  querySelectorAll: () => []
};
const window = { open: () => {} };
const Plotly = {
  purge: () => {},
  react: () => ({ then: (callback) => callback() })
};
"""
        result = subprocess.run(
            ["node", "-e", browser_stub + script + "\n" + body],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)

    def test_rss_axis_behavior_and_unavailable_rows(self) -> None:
        metric = "timed_seeding_particle_efficiency"
        time = "timed_seeding_time_per_event_ms"
        rss = "rss_peak_rss_kb"
        rows = [
            {
                "candidate": "Genesis",
                "category": "Development",
                "commit_url": REPOSITORY_URL,
                "metrics": {
                    time: 10.0,
                    metric: 0.90,
                    rss: 2_097_152.0,
                    "rss_peak_rss_kb": 3_145_728.0,
                },
            },
            {
                "candidate": "Lean",
                "category": "Development",
                "commit_url": "",
                "metrics": {
                    time: 9.0,
                    metric: 0.91,
                    rss: 1_048_576.0,
                    "timed_peak_rss_kb": 10_485_760.0,
                },
            },
            {
                "candidate": "NoResourceData",
                "category": "Development",
                "commit_url": "",
                "metrics": {
                    time: 8.0,
                    metric: 0.92,
                    "timed_peak_rss_kb": 524_288.0,
                },
            },
        ]
        result = self.run_pareto_javascript(
            {"rows": rows, "dataset": "development", "rss_metric_key": rss},
            r"""
const x = axisElements('x');
const y = axisElements('y');
x.kind.value = 'metric';
updateAxisOptions('x');
x.stage.value = 'seeding';
x.metric.value = 'particle_fake_ratio';
x.kind.value = 'rss';
updateAxisOptions('x');
const rssState = {
  key: axisKey('x'),
  label: axisLabel('x'),
  stageHidden: x.stageLabel.hidden,
  metricHidden: x.metricLabel.hidden,
  formatted: formatAxisValue('x', 2097152),
  unavailable: formatAxisValue('x', undefined),
  lowerBetter: axisDirection('x').lowerBetter,
  tickSuffix: axisTickFormat('x').ticksuffix
};
y.kind.value = 'time';
updateAxisOptions('y');
y.stage.value = 'seeding';
const rssTimeCount = validRows(axisKey('x'), axisKey('y')).length;
y.kind.value = 'metric';
updateAxisOptions('y');
y.stage.value = 'seeding';
y.metric.value = 'particle_efficiency';
const rssMetricCount = validRows(axisKey('x'), axisKey('y')).length;
const baseline = rows.find((row) => row.candidate === 'Genesis');
const lean = rows.find((row) => row.candidate === 'Lean');
const leanColor = candidateColor(lean, baseline, axisKey('x'), axisKey('y'));
const missingTooltip = candidateTooltip(rows.find((row) => row.candidate === 'NoResourceData'));
x.kind.value = 'metric';
updateAxisOptions('x');
const restored = { stage: x.stage.value, metric: x.metric.value, stageHidden: x.stageLabel.hidden, metricHidden: x.metricLabel.hidden };
y.kind.value = 'rss';
updateAxisOptions('y');
console.log(JSON.stringify({
  kinds: [...x.kind.options].map((item) => [item.value, item.textContent]),
  rssState,
  rssTimeCount,
  rssMetricCount,
  leanColor,
  missingTooltip,
  restored,
  yRss: { key: axisKey('y'), lowerBetter: axisDirection('y').lowerBetter, stageHidden: y.stageLabel.hidden, metricHidden: y.metricLabel.hidden }
}));
""",
        )

        self.assertEqual(
            result["kinds"],
            [["time", "Time"], ["metric", "Metric"], ["rss", "RSS"]],
        )
        self.assertEqual(result["rssState"]["key"], rss)
        self.assertEqual(
            result["rssState"]["label"],
            "SEEDING-ONLY PEAK RSS",
        )
        self.assertTrue(result["rssState"]["stageHidden"])
        self.assertTrue(result["rssState"]["metricHidden"])
        self.assertEqual(result["rssState"]["formatted"], "2.00 GiB")
        self.assertEqual(result["rssState"]["unavailable"], "Unavailable")
        self.assertTrue(result["rssState"]["lowerBetter"])
        self.assertEqual(result["rssState"]["tickSuffix"], " MiB")
        self.assertEqual(result["rssTimeCount"], 2)
        self.assertEqual(result["rssMetricCount"], 2)
        self.assertEqual(result["leanColor"], "#22c55e")
        self.assertIn(
            "Seeding Peak RSS&nbsp;&nbsp;n/a", result["missingTooltip"]
        )
        self.assertEqual(result["restored"]["stage"], "seeding")
        self.assertEqual(result["restored"]["metric"], "particle_fake_ratio")
        self.assertFalse(result["restored"]["stageHidden"])
        self.assertFalse(result["restored"]["metricHidden"])
        self.assertEqual(result["yRss"]["key"], rss)
        self.assertTrue(result["yRss"]["lowerBetter"])
        self.assertTrue(result["yRss"]["stageHidden"])
        self.assertTrue(result["yRss"]["metricHidden"])

    def test_evaluation_speed_claim_uncertainty_classifications(self) -> None:
        genesis = {
            "median_ms": 100.0,
            "range_ms": 4.0,
            "median_absolute_deviation_ms": 2.0,
        }
        confirmed = classify_speed_claim(
            {
                "median_ms": 90.0,
                "range_ms": 2.0,
                "median_absolute_deviation_ms": 1.0,
            },
            genesis,
        )
        directional = classify_speed_claim(
            {
                "median_ms": 98.0,
                "range_ms": 3.0,
                "median_absolute_deviation_ms": 1.0,
            },
            genesis,
        )
        inconclusive = classify_speed_claim(
            {
                "median_ms": 101.0,
                "range_ms": 2.0,
                "median_absolute_deviation_ms": 1.0,
            },
            genesis,
        )
        self.assertEqual(confirmed["classification"], "confirmed")
        self.assertEqual(directional["classification"], "directional")
        self.assertEqual(inconclusive["classification"], "inconclusive")
        self.assertEqual(confirmed["practical_timing_margin_ms"], 4.0)

    def test_interactive_selector_and_candidate_tooltip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "index.html"
            render(
                {"rows": [], "dataset": "development"},
                output,
                defaults={"x_metric": "x", "y_metric": "y", "baseline": "Genesis"},
            )
            html = output.read_text(encoding="utf-8")

        self.assertIn("option(datasetSelect, 'Development', 'Development');", html)
        self.assertIn("option(datasetSelect, 'Evaluation', 'Evaluation');", html)
        self.assertNotIn("option(datasetSelect, 'all'", html)
        self.assertNotIn("All datasets", html)
        self.assertIn("const TOOLTIP_STAGES = ['seeding'];", html)
        self.assertNotIn("full_chain:", html)
        self.assertNotIn("ckf:", html)
        self.assertNotIn("ambiguity:", html)
        self.assertNotIn("Genesis samples", html)
        self.assertIn("function baselineLabel(name, row)", html)

        tooltip_rows = html[html.index("const TOOLTIP_ROWS"): html.index("const TOOLTIP_STAGES")]
        for label in ("label: 'T'", "label: 'E'", "label: 'F'", "label: 'D'"):
            self.assertIn(label, tooltip_rows)
        tooltip = html[html.index("function candidateTooltip"): html.index("function axisDirection")]
        stages = html[html.index("const STAGES"): html.index("const QUALITY_METRICS")]
        self.assertIn("Seeding", stages)
        self.assertNotIn("CKF", stages)
        self.assertNotIn("Ambiguity", stages)
        self.assertNotIn("Full chain", tooltip)
        self.assertIn("→", tooltip)
        self.assertIn("return 'n/a'", html)
        self.assertIn("escapeHtml(row.candidate)", tooltip)
        self.assertIn("timingEvidenceTooltip(row)", tooltip)
        self.assertIn("Median/range/MAD", html)
        self.assertIn("row.proposal.hypothesis", tooltip)
        self.assertNotIn("protocol_id", tooltip)
        self.assertNotIn("source_protocol", tooltip)

        hover = html[html.index("hovertemplate"): html.index("hovertemplate") + 100]
        for field in ("X:", "Y:", "Category:", "Record:", "Commit:"):
            self.assertNotIn(field, hover)

        self.assertIn("customdata: points.map((row) => row.commit_url || '')", html)
        self.assertIn("${name} (${row.sample_count})", html)
        self.assertIn("chart.on('plotly_click'", html)
        self.assertIn("window.open(url, '_blank', 'noopener,noreferrer')", html)
        self.assertIn("cursor = validCommitUrl", html)

    def test_commit_url_requires_a_full_sha(self) -> None:
        sha = "a" * 40
        self.assertEqual(commit_url(sha), f"{REPOSITORY_URL}/commit/{sha}")
        self.assertEqual(commit_url("a" * 39), "")
        self.assertEqual(commit_url("not-a-sha"), "")

        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records" / "Development" / "Candidate"
            records.mkdir(parents=True)
            summary = self.summary("Candidate", "Development", 12.0, 0.9)
            summary["implementation_commit"] = sha
            (records / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            row = load_records(records.parents[1], "development")[0]
            self.assertEqual(row["commit_url"], f"{REPOSITORY_URL}/commit/{sha}")

    def test_aggregated_genesis_links_to_repository_root(self) -> None:
        sha = "b" * 40
        row = {
            "candidate": "Genesis",
            "category": "Development",
            "protocol_id": "acts-seeding-v3",
            "record": "Development/Genesis/summary.json",
            "commit": sha,
            "metrics": {"timed_total_time_per_event_ms": 100.0},
        }
        report = build_report([row], "Genesis", "development")
        self.assertEqual(report["rows"][0]["commit_url"], REPOSITORY_URL)

        second = {**row, "record": "Development/Genesis-2/summary.json", "commit": "c" * 40}
        report = build_report([row, second], "Genesis", "development")
        self.assertEqual(report["rows"][0]["commit_url"], REPOSITORY_URL)

    def test_v2_only_archive_shows_empty_active_v3_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = root / "records" / "Development" / "Genesis"
            records.mkdir(parents=True)
            (records / "summary.json").write_text(
                json.dumps(self.v2_summary()), encoding="utf-8"
            )
            output = root / "site"

            self.assertEqual(load_records(records.parents[1], "development"), [])
            result = self.run_report(records.parents[1], output)

            self.assertEqual(result.returncode, 0, result.stderr)
            index = (output / "index.html").read_text(encoding="utf-8")
            payload = json.loads(index.split("const REPORT = ", 1)[1].split(";", 1)[0])
            self.assertEqual(payload["protocol_id"], "acts-seeding-v3")
            self.assertEqual(payload["rows"], [])
            self.assertNotIn("rss_normalization", payload)
            self.assertNotIn("adjusted", index.lower())
            self.assertIn("No complete active v3 summaries", index)

    def test_mixed_archive_reports_only_v3_by_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = root / "records"
            summaries = (
                ("Development/V2Genesis", self.v2_summary()),
                ("Development/V3Genesis", self.summary("Genesis", "Development", 30.0, 0.8, 4096.0)),
                ("Development/Historical", self.v2_summary("Historical", time=1.0, seeding_efficiency=1.0)),
                ("Development/Current", self.summary("Current", "Development", 27.0, 0.91, 8192.0)),
                ("Evaluation/V2Only", self.v2_summary("V2Only", "Evaluation", 1.0, 1.0)),
            )
            for relative, summary in summaries:
                folder = records / relative
                folder.mkdir(parents=True)
                (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

            development_output = root / "development-site"
            result = self.run_report(records, development_output)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = (development_output / "index.html").read_text(encoding="utf-8")
            payload = json.loads(index.split("const REPORT = ", 1)[1].split(";", 1)[0])
            self.assertEqual([row["candidate"] for row in payload["rows"]], ["Genesis", "Current"])
            self.assertEqual(payload["rows"][0]["sample_count"], 1)
            self.assertEqual(payload["rows"][0]["source_protocol_ids"], ["acts-seeding-v3"])
            self.assertEqual(payload["rows"][0]["metrics"]["rss_peak_rss_kb"], 4096.0)

            evaluation_output = root / "evaluation-site"
            result = self.run_report(records, evaluation_output, "evaluation")
            self.assertEqual(result.returncode, 0, result.stderr)
            evaluation_index = (evaluation_output / "index.html").read_text(encoding="utf-8")
            evaluation = json.loads(evaluation_index.split("const REPORT = ", 1)[1].split(";", 1)[0])
            self.assertEqual(evaluation["rows"], [])
            self.assertIn("No complete active v3 summaries", evaluation_index)

    def test_malformed_v3_summary_keeps_strict_metric_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = root / "records" / "Development" / "Genesis"
            records.mkdir(parents=True)
            summary = self.summary("Genesis", "Development", 12.0, 0.9)
            summary["stages"] = []
            (records / "summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )

            result = self.run_report(records.parents[1], root / "site")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("x metric not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
