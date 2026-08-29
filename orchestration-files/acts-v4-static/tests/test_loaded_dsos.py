from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401
from loaded_dsos import loaded_acts_dsos
from schema import ManifestError, sha256_file


class LoadedActsDsoTests(unittest.TestCase):
    def _maps(self, paths: list[Path]) -> str:
        return "".join(
            f"7f000000-7f001000 r-xp 00000000 00:00 0 {path}\n" for path in paths
        )

    def test_hashes_every_private_acts_object_and_ignores_non_acts_libraries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "private-build"
            core = build / "lib64/libActsCore.so"
            binding = build / "python/acts/ActsPythonBindings.cpython-39.so"
            unrelated = root / "external/libUnrelated.so"
            for path, content in (
                (core, b"core"),
                (binding, b"binding"),
                (unrelated, b"unrelated"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            maps = root / "maps"
            maps.write_text(self._maps([core, binding, unrelated]), encoding="utf-8")

            closure = loaded_acts_dsos(build, maps_path=maps)

            self.assertEqual(closure, {
                "lib64/libActsCore.so": sha256_file(core),
                "python/acts/ActsPythonBindings.cpython-39.so": sha256_file(binding),
            })

    def test_rejects_loaded_acts_library_or_binding_outside_private_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "private-build"
            core = build / "lib64/libActsCore.so"
            external_library = root / "other-build/lib64/libActsPluginRoot.so"
            external_binding = (
                root / "other-build/python/acts/ActsExamplesPythonBindings.cpython-39.so"
            )
            for path in (core, external_library, external_binding):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(path.name.encode())
            maps = root / "maps"

            for external in (external_library, external_binding):
                with self.subTest(external=external.name):
                    maps.write_text(self._maps([core, external]), encoding="utf-8")
                    with self.assertRaisesRegex(
                        ManifestError, "outside validated private build"
                    ):
                        loaded_acts_dsos(build, maps_path=maps)

    def test_rejects_deleted_loaded_acts_object(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "private-build"
            core = build / "lib64/libActsCore.so"
            core.parent.mkdir(parents=True)
            core.write_bytes(b"core")
            maps = root / "maps"
            maps.write_text(self._maps([core]).rstrip() + " (deleted)\n", encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "deleted"):
                loaded_acts_dsos(build, maps_path=maps)


if __name__ == "__main__":
    unittest.main()
