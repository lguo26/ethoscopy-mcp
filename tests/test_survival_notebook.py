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
    def test_survival_projects_columns_before_concat_without_changing_deaths(self):
        import ethoscopy as etho
        import pandas as pd
        import matplotlib.pyplot as plt
        from ethoscopy_mcp.registry import sha256_file

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, _, mapping = _write_transfer_fixture(root)
            meta = pd.read_pickle(first).meta.copy()
            rows = [
                {"id": animal_id, "t": t, "moving": not (row.infection and t >= 12 * 3600),
                 "walk": not (row.infection and t >= 12 * 3600), "x": 0.5, "asleep": False}
                for animal_id, row in meta.iterrows()
                for t in range(0, 48 * 3600, 600)
            ]
            data = etho.behavpy(pd.DataFrame(rows).set_index("id"), meta, check=True)
            data.to_pickle(first)
            before = sha256_file(first)
            overlay = pd.read_csv(mapping)
            overlay.loc[overlay.date == "2026-08-21"].to_csv(mapping, index=False)
            recipe = _survival_recipe(mapping)
            recipe = recipe.model_copy(update={"identity_overlay": recipe.identity_overlay.model_copy(
                update={"expected_dates": ("2026-08-21",)}
            )})
            manifest = ExperimentManifest(experiment_id=recipe.experiment_id, source_paths=(first,))
            preview = EthoscopyService(Settings.create([root])).preview_analysis(manifest, recipe)

            reference = data.baseline(column="baseline")
            reference["t"] -= 2 * 3600
            reference = reference.loc[reference.t >= 0].copy()
            reference.meta["species"] = reference.meta.infection.map({False: "PBS", True: "S. aureus"})
            expected = reference.km_death_table(
                mov_column="moving", second_mov_column="walk", time_window=24,
                prop_immobile=0.01, zero_run_hours=12,
                subject_cols=["machine_name", "region_id"], meta_cols=["species"], time_unit="hours",
            ).rename(columns={"species": "treatment"})
            expected["sex"] = "male"
            concat = etho.concat
            seen = []

            def checked_concat(*frames):
                seen.extend([list(frame.columns) for frame in frames])
                return concat(*frames)

            with patch("ethoscopy_mcp.execution.etho.concat", side_effect=checked_concat):
                actual, figure = _run_recipe(preview, recipe)
            try:
                self.assertEqual(seen, [["t", "moving", "walk"]])
                self.assertEqual(len(expected), 2)
                pd.testing.assert_frame_equal(actual, expected)
                self.assertEqual(sha256_file(first), before)
            finally:
                plt.close(figure)

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
