import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HEPP_FILES = PROJECT_ROOT / "orchestration-files" / "HEPP-files"
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

import evaluate  # noqa: E402
from evaluate import CandidateFailure, CommandResult  # noqa: E402


class EvaluatorRestorationTests(unittest.TestCase):
    def run_script(self, name, *arguments, environment):
        return subprocess.run(
            ["bash", str(HEPP_FILES / name), *map(str, arguments)],
            cwd=PROJECT_ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_restoration_clean_first_rebuilds_genesis_artifact(self):
        with tempfile.TemporaryDirectory(prefix="acts restore path with spaces ") as temporary:
            root = Path(temporary)
            source_root = root / "ACTS source"
            build_root = source_root / "build directory"
            optimization_root = root / "candidate optimization files"
            backup_root = root / "reusable backup"
            run_root = root / "evaluation run"
            fake_bin = root / "fake commands"
            relative_source = Path("Core/src/Seeding2/example source.cpp")
            source_file = source_root / relative_source
            candidate_file = optimization_root / relative_source
            artifact = build_root / "libActsCandidate.so"
            unrelated = source_root / "unrelated state.txt"
            build_log = root / "build invocations.log"

            source_file.parent.mkdir(parents=True)
            build_root.mkdir(parents=True)
            candidate_file.parent.mkdir(parents=True)
            fake_bin.mkdir()
            source_file.write_text("Genesis content\n", encoding="utf-8")
            candidate_file.write_text("candidate content\n", encoding="utf-8")
            unrelated.write_text("must not change\n", encoding="utf-8")
            (source_root / ".gitignore").write_text("build directory/\n", encoding="utf-8")
            (build_root / "CMakeCache.txt").touch()
            os.utime(source_file, (1_000_000_000, 1_000_000_000))
            os.utime(candidate_file, (1_500_000_000, 1_500_000_000))

            subprocess.run(["git", "init", "-q", source_root], check=True)
            subprocess.run(
                ["git", "-C", source_root, "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", source_root, "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(["git", "-C", source_root, "add", "."], check=True)
            subprocess.run(
                ["git", "-C", source_root, "commit", "-qm", "Genesis"], check=True
            )

            fake_cmake = fake_bin / "cmake"
            fake_cmake.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
clean_first=0
jobs=''
while (( $# )); do
  case "$1" in
    --clean-first) clean_first=1 ;;
    --parallel) shift; jobs="${1:?parallel jobs missing}" ;;
  esac
  shift
done
printf 'clean_first=%s jobs=%s\\n' "$clean_first" "$jobs" >>"$FAKE_BUILD_LOG"
if (( clean_first )); then
  rm -f -- "$FAKE_ARTIFACT"
  if [[ "${FAKE_CLEAN_BUILD_FAIL:-0}" == 1 ]]; then
    echo 'forced clean rebuild failure' >&2
    exit 19
  fi
fi
if [[ ! -e "$FAKE_ARTIFACT" || "$FAKE_SOURCE_FILE" -nt "$FAKE_ARTIFACT" ]]; then
  cp -- "$FAKE_SOURCE_FILE" "$FAKE_ARTIFACT"
  touch -d '@2000000000' "$FAKE_ARTIFACT"
  echo 'fake build: rebuilt artifact'
else
  echo 'ninja: no work to do'
fi
""",
                encoding="utf-8",
            )
            fake_cmake.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "ACTS_SOURCE": str(source_root),
                "ACTS_BUILD_DIR": str(build_root),
                "ACTS_BUILD_JOBS": "8",
                "ACTS_LCG_SETUP": str(root / "missing lcg setup.sh"),
                "FAKE_SOURCE_FILE": str(source_file),
                "FAKE_ARTIFACT": str(artifact),
                "FAKE_BUILD_LOG": str(build_log),
            }

            backup = self.run_script(
                "backup-acts-files.sh",
                optimization_root,
                backup_root,
                run_root,
                environment=environment,
            )
            self.assertEqual(backup.returncode, 0, backup.stdout)
            apply = self.run_script(
                "apply-optimization-files.sh", optimization_root, environment=environment
            )
            self.assertEqual(apply.returncode, 0, apply.stdout)
            candidate_build = self.run_script("build.sh", environment=environment)
            self.assertEqual(candidate_build.returncode, 0, candidate_build.stdout)
            self.assertEqual(artifact.read_text(encoding="utf-8"), "candidate content\n")

            restore = self.run_script(
                "restore-acts-files.sh", backup_root, run_root, environment=environment
            )
            self.assertEqual(restore.returncode, 0, restore.stdout)
            self.assertEqual(source_file.read_text(encoding="utf-8"), "Genesis content\n")
            self.assertEqual(source_file.stat().st_mtime_ns, 1_000_000_000_000_000_000)

            incremental = self.run_script("build.sh", environment=environment)
            self.assertEqual(incremental.returncode, 0, incremental.stdout)
            self.assertIn("ninja: no work to do", incremental.stdout)
            self.assertEqual(
                artifact.read_text(encoding="utf-8"),
                "candidate content\n",
                "ordinary restoration build must reproduce the stale candidate artifact",
            )

            artifact.unlink()
            pristine = self.run_script("build.sh", environment=environment)
            self.assertEqual(pristine.returncode, 0, pristine.stdout)
            self.assertEqual(artifact.read_text(encoding="utf-8"), "Genesis content\n")

            artifact.unlink()
            apply = self.run_script(
                "apply-optimization-files.sh", optimization_root, environment=environment
            )
            self.assertEqual(apply.returncode, 0, apply.stdout)
            candidate_build = self.run_script("build.sh", environment=environment)
            self.assertEqual(candidate_build.returncode, 0, candidate_build.stdout)
            restore = self.run_script(
                "restore-acts-files.sh", backup_root, run_root, environment=environment
            )
            self.assertEqual(restore.returncode, 0, restore.stdout)
            unrelated_before = (unrelated.read_bytes(), unrelated.stat().st_mtime_ns)

            restored_build = self.run_script(
                "build.sh", "--clean-first", environment=environment
            )
            self.assertEqual(restored_build.returncode, 0, restored_build.stdout)
            self.assertEqual(artifact.read_text(encoding="utf-8"), "Genesis content\n")
            self.assertIn("ACTS build parallel jobs: 8", restored_build.stdout)
            build_invocations = build_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(build_invocations[-1], "clean_first=1 jobs=8")
            self.assertTrue(
                all(line == "clean_first=0 jobs=8" for line in build_invocations[:-1])
            )
            self.assertEqual(
                (unrelated.read_bytes(), unrelated.stat().st_mtime_ns), unrelated_before
            )

            default_environment = environment.copy()
            default_environment.pop("ACTS_BUILD_JOBS")
            default_build = self.run_script("build.sh", environment=default_environment)
            self.assertEqual(default_build.returncode, 0, default_build.stdout)
            self.assertIn("ACTS build parallel jobs: 8", default_build.stdout)
            self.assertEqual(
                build_log.read_text(encoding="utf-8").splitlines()[-1],
                "clean_first=0 jobs=8",
            )

            cleanup = self.run_script(
                "cleanup-evaluation-files.sh",
                optimization_root,
                run_root,
                environment=environment,
            )
            self.assertEqual(cleanup.returncode, 0, cleanup.stdout)
            self.assertFalse(optimization_root.exists())
            self.assertFalse(run_root.exists())
            self.assertTrue(backup_root.exists())
            self.assertEqual(
                (unrelated.read_bytes(), unrelated.stat().st_mtime_ns), unrelated_before
            )

    def run_evaluator_transaction(self, *, stage_fails=False, restore_build_fails=False):
        helper_calls = []
        written = {}

        def fake_helper(helper, run_id, *arguments):
            helper_calls.append((helper, run_id, arguments))
            if helper == "build.sh":
                if run_id.endswith("-restore-build") and restore_build_fails:
                    return CommandResult(19, "forced restore build failure\n")
                return CommandResult(0, "ACTS build parallel jobs: 8\n")
            return CommandResult(0, f"{helper} completed\n")

        def fake_stage(*args, **kwargs):
            if stage_fails:
                raise CandidateFailure("candidate failed stage: one_event_seeding_smoke")

        def capture_summary(folder, summary):
            written["summary"] = summary

        proposal_binding = {"proposal": {"combination_provenance": None}}
        candidate_identity = {
            "mechanism_key": "candidate-mechanism",
            "mechanism_family": "candidate-family",
            "classification": "major",
            "derives_from": None,
        }
        args = SimpleNamespace(
            candidate_name="Candidate", evaluation=False, campaign_input=Path("campaign.json")
        )
        with (
            patch.dict(os.environ, {"ACTS_BUILD_JOBS": "8"}),
            patch.object(evaluate, "enforce_continuous_development_run"),
            patch.object(evaluate, "validate_optimization_files", return_value=["Core/x.cpp"]),
            patch.object(evaluate, "require_clean_repository", return_value="a" * 40),
            patch.object(evaluate, "candidate_implementation_commit", return_value="b" * 40),
            patch.object(
                evaluate,
                "candidate_implementation_files",
                return_value=["optimization-files/Core/x.cpp"],
            ),
            patch.object(
                evaluate,
                "load_candidate_proposal",
                return_value=(proposal_binding, candidate_identity),
            ),
            patch.object(evaluate, "run_command", return_value=CommandResult(0, "exported\n")),
            patch.object(evaluate, "run_hepp_helper", side_effect=fake_helper),
            patch.object(
                evaluate,
                "controlled_stage_plan",
                return_value=[
                    {
                        "name": "one_event_seeding_smoke",
                        "events": 1,
                        "stage": "seeding",
                        "metrics": "none",
                        "comparison": "smoke",
                    }
                ],
            ),
            patch.object(evaluate, "run_stage", side_effect=fake_stage),
            patch.object(evaluate, "build_timed_comparison", return_value={"complete": True}),
            patch.object(evaluate, "build_rss_evidence", return_value={"complete": True}),
            patch.object(evaluate, "write_summary", side_effect=capture_summary),
            patch.object(evaluate, "write_failure_logs") as failure_logs,
            patch("builtins.print"),
        ):
            return_code = evaluate.run_evaluation(args)
        return return_code, helper_calls, written["summary"], failure_logs.call_args_list

    def assert_pristine_restore_sequence(self, helper_calls):
        names = [call[0] for call in helper_calls]
        restore_index = names.index("restore-acts-files.sh")
        self.assertEqual(names[restore_index : restore_index + 3], [
            "restore-acts-files.sh",
            "build.sh",
            "cleanup-evaluation-files.sh",
        ])
        self.assertEqual(helper_calls[restore_index + 1][2], ("--clean-first",))

    def test_successful_candidate_uses_pristine_restore_then_cleanup(self):
        return_code, calls, summary, failure_logs = self.run_evaluator_transaction()
        self.assertEqual(return_code, 0)
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(failure_logs, [])
        self.assert_pristine_restore_sequence(calls)

    def test_failed_candidate_keeps_evidence_and_uses_pristine_restore(self):
        return_code, calls, summary, failure_logs = self.run_evaluator_transaction(
            stage_fails=True
        )
        self.assertEqual(return_code, 1)
        self.assertEqual(summary["category"], "Failed")
        self.assertTrue(summary["raw_logs_retained"])
        self.assertTrue(failure_logs)
        self.assert_pristine_restore_sequence(calls)

    def test_restore_build_failure_propagates_and_cleanup_still_runs(self):
        return_code, calls, summary, failure_logs = self.run_evaluator_transaction(
            restore_build_fails=True
        )
        self.assertEqual(return_code, 1)
        self.assertEqual(summary["category"], "Errors")
        self.assertEqual(summary["error"], "pristine ACTS rebuild failed after restoration")
        self.assertTrue(failure_logs)
        self.assert_pristine_restore_sequence(calls)


if __name__ == "__main__":
    unittest.main()
