from pathlib import Path
import tempfile
import unittest

from ethoscopy_mcp.config import Settings
from ethoscopy_mcp.errors import SourceChangedError
from ethoscopy_mcp.registry import SourceRegistry, sha256_file


class SourceRegistryTests(unittest.TestCase):
    def test_registers_content_hash_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "experiment.pkl"
            source_path.write_bytes(b"original")
            registry = SourceRegistry(Settings.create([directory]))

            source = registry.register(source_path)

            self.assertEqual(source.sha256, sha256_file(source_path))
            registry.assert_unchanged(source)

            source_path.write_bytes(b"changed")
            with self.assertRaises(SourceChangedError):
                registry.assert_unchanged(source)


if __name__ == "__main__":
    unittest.main()
