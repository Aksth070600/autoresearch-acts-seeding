import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HEPP_FILES = PROJECT_ROOT / "orchestration-files" / "HEPP-files"
STATIC_MODULE = PROJECT_ROOT / "orchestration-files" / "acts-v4-static"
CANDIDATE_HELPER = HEPP_FILES / "acts-v4-static-pilot-candidate.sh"


class StaticV4CandidateHelperTests(unittest.TestCase):
    def test_invalidation_receives_ninja_from_pinned_environment(self):
        temporary_parent = PROJECT_ROOT / "build"
        temporary_parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="v4 candidate pinned path ", dir=temporary_parent
        ) as temporary:
            root = Path(temporary)
            template = root / "template"
            slot = root / "slot"
            workspace = root / "candidate evidence"
            genesis = root / "genesis optimization"
            candidate = root / "candidate optimization"
            fake_bin = root / "pinned bin"
            marker = root / "ninja path.txt"
            source_relative = Path("Core/x.cpp")

            for directory in (
                template / "source" / source_relative.parent,
                template / "build" / "obj",
                template / "deps",
                genesis / source_relative.parent,
                candidate / source_relative.parent,
                fake_bin,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            (template / "source" / source_relative).write_text(
                "Genesis\n", encoding="utf-8"
            )
            (genesis / source_relative).write_text("Genesis\n", encoding="utf-8")
            (candidate / source_relative).write_text("candidate\n", encoding="utf-8")
            (template / "build" / "CMakeCache.txt").write_text(
                f"CMAKE_HOME_DIRECTORY:INTERNAL={slot / 'source'}\n",
                encoding="utf-8",
            )
            (template / "build" / "build.ninja").write_text(
                "# fake Ninja graph\n", encoding="utf-8"
            )
            (template / "build" / "obj" / "x.o").write_bytes(b"Genesis object\n")
            for path in template.rglob("*"):
                if path.is_file():
                    path.chmod(0o444)
            stale = slot / "read-only deps" / "stale.txt"
            stale.parent.mkdir(parents=True)
            stale.write_text("stale\n", encoding="utf-8")
            stale.chmod(0o444)
            stale.parent.chmod(0o555)
            slot.chmod(0o555)

            proposal = root / "proposal.json"
            proposal.write_text(
                json.dumps(
                    {"intended_files": [f"optimization-files/{source_relative}"]},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            setup = root / "pinned setup.sh"
            setup.write_text('export PATH="$PINNED_BIN:$PATH"\n', encoding="utf-8")

            ninja = fake_bin / "ninja"
            ninja.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$(command -v ninja)" >"$NINJA_MARKER"
if [[ "$*" == *"-t deps"* ]]; then
  printf 'obj/x.o: #deps 1, deps mtime 0 (VALID)\n'
  printf '    %s\n' "$FAKE_DEPENDENCY"
  exit 0
fi
echo 'unexpected fake Ninja invocation' >&2
exit 64
""",
                encoding="utf-8",
            )
            ninja.chmod(0o755)
            cp = fake_bin / "cp"
            cp.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
args=()
for argument in "$@"; do
  if [[ "$argument" != "--reflink=always" ]]; then
    args+=("$argument")
  fi
done
exec /usr/bin/cp "${args[@]}"
""",
                encoding="utf-8",
            )
            cp.chmod(0o755)
            cmake = fake_bin / "cmake"
            cmake.write_text(
                "#!/usr/bin/env bash\nexit 73\n",
                encoding="utf-8",
            )
            cmake.chmod(0o755)

            environment = {
                **os.environ,
                "PATH": "/usr/bin:/bin",
                "ACTS_LCG_SETUP": str(setup),
                "PINNED_BIN": str(fake_bin),
                "NINJA_MARKER": str(marker),
                "FAKE_DEPENDENCY": str(slot / "source" / source_relative),
                "ACTS_BUILD_JOBS": "8",
            }
            process = subprocess.run(
                [
                    "bash",
                    str(CANDIDATE_HELPER),
                    str(STATIC_MODULE),
                    str(root / "unused dataset"),
                    str(workspace),
                    str(root / "unused geometry"),
                    str(root / "unused production identity"),
                    str(template),
                    str(slot),
                    str(genesis),
                    str(candidate),
                    str(proposal),
                    "a" * 40,
                    str(root / "unused calibration.json"),
                    str(root / "unused corrections.json"),
                ],
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

            self.assertEqual(process.returncode, 73, process.stdout)
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), str(ninja))
            invalidation = json.loads(
                (workspace / "ninja-invalidation.json").read_text(encoding="utf-8")
            )
            self.assertTrue(invalidation["all_affected_outputs_absent"])
            self.assertFalse((slot / "build" / "obj" / "x.o").exists())
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
