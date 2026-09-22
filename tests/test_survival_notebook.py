from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings
from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.execution import _run_recipe
from ethoscopy_mcp.preview import _recipe_hash
from ethoscopy_mcp.schemas import DeathDetectionSettings
from test_preview import _write_transfer_fixture, _survival_recipe


class NotebookSurvivalTests(unittest.TestCase):
    def test_short_window_fails_during_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, mapping = _write_transfer_fixture(root)
            recipe = _survival_recipe(mapping).model_copy(update={
                "death_detection": DeathDetectionSettings(time_window_hours=12)
            })
            manifest = ExperimentManifest(
                experiment_id=recipe.experiment_id, source_paths=(first, second)
            )
            with self.assertRaisesRegex(InvalidExperimentError, "at least 24"):
                EthoscopyService(Settings.create([root])).preview_analysis(manifest, recipe)

    def test_adapter_reports_elapsed_time_for_transfer_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, mapping = _write_transfer_fixture(root)
            recipe = _survival_recipe(mapping)
            service = EthoscopyService(Settings.create([root]))
            manifest = ExperimentManifest(experiment_id=recipe.experiment_id,
                                          source_paths=(first, second))
            preview = service.preview_analysis(manifest, recipe)
            table, fig = _run_recipe(preview, recipe)
            try:
                self.assertEqual(sum(c.individuals_with_data for c in preview.cohorts), 4)
                self.assertEqual(fig.axes[0].get_xlabel(), 'Days from first recorded sample')
                self.assertIn('treatment', table.columns)
                self.assertFalse(recipe.death_detection.cumulative)
            finally:
                import matplotlib.pyplot as plt
                plt.close(fig)

    def test_loaded_old_engine_requires_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, mapping = _write_transfer_fixture(root)
            recipe = _survival_recipe(mapping)
            manifest = ExperimentManifest(experiment_id=recipe.experiment_id,
                                          source_paths=(first, second))
            with patch('ethoscopy_mcp.preview.etho.__version__', '2.2.0'):
                with self.assertRaisesRegex(InvalidExperimentError, 'restart'):
                    EthoscopyService(Settings.create([root])).preview_analysis(manifest, recipe)

    def test_no_silently_ignored_cumulative_request(self):
        with self.assertRaises(ValidationError):
            DeathDetectionSettings(cumulative=True)

    def test_engine_version_changes_cache_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, mapping = _write_transfer_fixture(root)
            recipe = _survival_recipe(mapping)
            manifest = ExperimentManifest(experiment_id=recipe.experiment_id,
                                          source_paths=(first, second))
            inspection = EthoscopyService(Settings.create([root])).inspect_experiment(manifest)
            current = _recipe_hash(recipe, inspection, 'a' * 64)
            with patch('ethoscopy_mcp.preview.etho.__version__', '2.2.0'):
                previous = _recipe_hash(recipe, inspection, 'a' * 64)
            self.assertNotEqual(current, previous)
