from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.exports import export_analysis
from ethoscopy_mcp.registry import sha256_file
from ethoscopy_mcp.schemas import AnalysisRunResult, ArtifactReference


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "experiment.pkl"
        self.source.write_bytes(b"source remains immutable")
        run = self.root / "canonical"
        run.mkdir()
        artifact = run / "provenance.json"
        artifact.write_text('{"synthetic": true}\n')
        self.result = AnalysisRunResult(
            analysis_id="synthetic-0123456789ab", recipe_id="synthetic",
            experiment_id="synthetic", recipe_hash="a" * 64,
            created_at=datetime.now(timezone.utc), run_directory=run,
            reused_existing=False, group_outcomes=(), provenance_path=artifact,
            source_hashes_verified=True,
            artifacts=(ArtifactReference(
                artifact_id="sha256-synthetic", artifact_type="provenance",
                format="json", name="provenance.json", path=artifact,
                size_bytes=artifact.stat().st_size, sha256=sha256_file(artifact),
            ),),
        )
        self.destination = self.root / f"{self.result.analysis_id}_exports"

    def test_exports_are_verified_and_reused_without_modifying_source(self):
        before = sha256_file(self.source)
        destination = export_analysis(self.source, self.result)
        self.assertEqual(destination, self.destination)
        target = destination / "provenance.json"
        modified = target.stat().st_mtime_ns
        self.assertEqual(export_analysis(self.source, self.result), destination)
        self.assertEqual(target.stat().st_mtime_ns, modified)
        self.assertEqual(sha256_file(target), self.result.artifacts[0].sha256)
        self.assertEqual(sha256_file(self.source), before)

    def test_changed_or_missing_export_is_not_overwritten(self):
        export_analysis(self.source, self.result)
        target = self.destination / "provenance.json"
        target.write_text("user edit")
        with self.assertRaisesRegex(InvalidExperimentError, "no files overwritten"):
            export_analysis(self.source, self.result)
        self.assertEqual(target.read_text(), "user edit")
        target.unlink()
        with self.assertRaises(InvalidExperimentError):
            export_analysis(self.source, self.result)
        self.assertFalse(target.exists())

    def test_symlink_directory_and_file_are_rejected(self):
        self.destination.symlink_to(self.result.run_directory, target_is_directory=True)
        with self.assertRaisesRegex(InvalidExperimentError, "symlink"):
            export_analysis(self.source, self.result)
        self.destination.unlink()
        self.destination.mkdir()
        (self.destination / "provenance.json").symlink_to(self.result.provenance_path)
        with self.assertRaises(InvalidExperimentError):
            export_analysis(self.source, self.result)

    def test_failed_copy_leaves_no_partial_export_and_can_retry(self):
        with patch("ethoscopy_mcp.exports.shutil.copy2", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                export_analysis(self.source, self.result)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".ethoscopy-export-*")), [])
        self.assertTrue(self.result.provenance_path.is_file())
        self.assertEqual(export_analysis(self.source, self.result), self.destination)
