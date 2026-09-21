from pathlib import Path
import tempfile
import unittest

from ethoscopy_mcp.config import Settings
from ethoscopy_mcp.errors import UnsafePathError, UnsupportedSourceError


class SettingsTests(unittest.TestCase):
    def test_allows_supported_file_inside_trusted_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "experiment.pkl"
            source.write_bytes(b"fixture")
            settings = Settings.create([root])

            self.assertEqual(settings.resolve_source(source), source.resolve())

    def test_rejects_file_outside_trusted_root(self):
        with tempfile.TemporaryDirectory() as trusted, tempfile.TemporaryDirectory() as other:
            source = Path(other) / "experiment.pkl"
            source.write_bytes(b"fixture")
            settings = Settings.create([trusted])

            with self.assertRaises(UnsafePathError):
                settings.resolve_source(source)

    def test_rejects_symlink_that_escapes_trusted_root(self):
        with tempfile.TemporaryDirectory() as trusted, tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "experiment.pkl"
            outside.write_bytes(b"fixture")
            link = Path(trusted) / "linked.pkl"
            link.symlink_to(outside)
            settings = Settings.create([trusted])

            with self.assertRaises(UnsafePathError):
                settings.resolve_source(link)

    def test_rejects_unsupported_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "experiment.csv"
            source.write_text("id,t\nfly-1,0\n", encoding="utf-8")
            settings = Settings.create([directory])

            with self.assertRaises(UnsupportedSourceError):
                settings.resolve_source(source)


if __name__ == "__main__":
    unittest.main()
