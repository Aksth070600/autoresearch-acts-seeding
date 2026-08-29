import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_HELPER = (
    PROJECT_ROOT
    / "orchestration-files"
    / "HEPP-files"
    / "acts-v4-static-pilot-candidate.sh"
)


class StaticV4CandidateHelperTests(unittest.TestCase):
    def test_pinned_ninja_path_is_loaded_before_invalidation_and_retained(self):
        script = CANDIDATE_HELPER.read_text(encoding="utf-8")
        setup = 'source "$ACTS_LCG_SETUP"'
        invalidation = 'python3 "$MODULE_DIR/invalidate_candidate.py"'
        build = 'cmake --build "$ACTS_BUILD_DIR"'
        dry_run = 'dry_run="$(ninja -C "$ACTS_BUILD_DIR"'

        self.assertEqual(script.count(setup), 1)
        setup_index = script.index(setup)
        invalidation_index = script.index(invalidation)
        build_index = script.index(build)
        dry_run_index = script.index(dry_run)
        self.assertLess(setup_index, invalidation_index)
        self.assertLess(invalidation_index, build_index)
        self.assertLess(build_index, dry_run_index)

        pinned_environment = script[setup_index:dry_run_index]
        self.assertNotIn("unset PATH", pinned_environment)
        self.assertNotIn("export PATH=", pinned_environment)

    def test_generated_python_setup_runs_without_nounset(self):
        script = CANDIDATE_HELPER.read_text(encoding="utf-8")
        setup = 'source "$ACTS_BUILD_DIR/python/setup.sh"'
        setup_index = script.index(setup)

        self.assertEqual(script.count(setup), 1)
        self.assertEqual(script[:setup_index].rstrip().splitlines()[-2:], [
            "set +u",
            "# shellcheck disable=SC1090,SC1091",
        ])
        self.assertEqual(
            script[setup_index:].splitlines()[1],
            "set -u",
        )


if __name__ == "__main__":
    unittest.main()
