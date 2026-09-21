from pathlib import Path
import tempfile
import unittest

import ethoscopy as etho
import pandas as pd

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings
from ethoscopy_mcp.registry import sha256_file
from ethoscopy_mcp.schemas import (
    DeathDetectionSettings,
    GroupDefinition,
    GroupLevel,
    IdentityOverlay,
    OutputRequest,
    SurvivalRecipe,
    TimeAlignment,
)


class SurvivalPreviewTests(unittest.TestCase):
    def test_previews_transfer_mapped_survival_without_mutating_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, mapping_path = _write_transfer_fixture(root)
            hashes_before = {
                path: sha256_file(path) for path in (first, second, mapping_path)
            }
            manifest = ExperimentManifest(
                experiment_id="synthetic-transfer",
                source_paths=(first, second),
            )
            recipe = _survival_recipe(mapping_path)

            preview = EthoscopyService(Settings.create([root])).preview_analysis(
                manifest, recipe
            )

            self.assertTrue(preview.approval_required)
            self.assertTrue(preview.ready_to_approve)
            self.assertEqual(preview.identity_overlay.mapping_rows, 8)
            self.assertEqual(preview.identity_overlay.mapped_individuals, 4)
            self.assertEqual(preview.identity_overlay.changed_segment_ids, 4)
            self.assertEqual(
                preview.identity_overlay.recording_dates,
                ("2026-08-21", "2026-08-24"),
            )
            cohorts = {cohort.label: cohort for cohort in preview.cohorts}
            self.assertEqual(cohorts["PBS"].metadata_individuals, 2)
            self.assertEqual(cohorts["PBS"].individuals_with_data, 2)
            self.assertEqual(cohorts["PBS"].data_segments, 4)
            self.assertEqual(cohorts["S. aureus"].metadata_individuals, 2)
            self.assertEqual(cohorts["S. aureus"].individuals_with_data, 2)
            self.assertEqual(cohorts["S. aureus"].data_segments, 4)
            self.assertEqual(len(preview.recipe_hash), 64)
            self.assertEqual(len(preview.expected_artifacts), 3)
            for path, digest in hashes_before.items():
                self.assertEqual(sha256_file(path), digest)

    def test_rejects_mapping_that_does_not_cover_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, mapping_path = _write_transfer_fixture(root)
            mapping = pd.read_csv(mapping_path, dtype={"roi": "string"})
            mapping.iloc[:-1].to_csv(mapping_path, index=False)

            from ethoscopy_mcp.errors import InvalidExperimentError

            with self.assertRaises(InvalidExperimentError):
                EthoscopyService(Settings.create([root])).preview_analysis(
                    ExperimentManifest(
                        experiment_id="synthetic-transfer",
                        source_paths=(first, second),
                    ),
                    _survival_recipe(mapping_path),
                )


def _survival_recipe(mapping_path: Path) -> SurvivalRecipe:
    return SurvivalRecipe(
        recipe_id="synthetic-male-survival",
        experiment_id="synthetic-transfer",
        cohort_filters={"sex": "male"},
        group=GroupDefinition(
            column="infection",
            levels=(
                GroupLevel(value=False, label="PBS"),
                GroupLevel(value=True, label="S. aureus"),
            ),
        ),
        identity_overlay=IdentityOverlay(
            mapping_path=mapping_path,
            expected_dates=("2026-08-21", "2026-08-24"),
        ),
        time_alignment=TimeAlignment(
            source_basis="baseline-aligned ZT",
            output_basis="time since injection",
            subtract_hours=2,
            zt0_description="10:00 BST",
            injection_description="2026-08-21 12:00 BST",
        ),
        death_detection=DeathDetectionSettings(),
        output_requests=(
            OutputRequest(
                artifact_type="table", format="csv", name="death_table_male"
            ),
            OutputRequest(
                artifact_type="plot", format="png", name="survival_male"
            ),
            OutputRequest(
                artifact_type="plot", format="svg", name="survival_male"
            ),
        ),
        assumptions=("The same flies retained their ROI numbers after transfer.",),
        context_warnings=("Machine and treatment are not independent.",),
    )


def _write_transfer_fixture(root: Path) -> tuple[Path, Path, Path]:
    rows = []
    first_specs = [
        ("2026-08-21_12-00-00_074250|01", "ETHOSCOPE_074", "01", True),
        ("2026-08-21_12-00-00_074250|02", "ETHOSCOPE_074", "02", True),
        ("2026-08-21_12-00-00_316250|01", "ETHOSCOPE_316", "01", False),
        ("2026-08-21_12-00-00_316250|02", "ETHOSCOPE_316", "02", False),
    ]
    second_specs = [
        ("2026-08-24_12-00-00_316250|01", "ETHOSCOPE_316", "01", True),
        ("2026-08-24_12-00-00_316250|02", "ETHOSCOPE_316", "02", True),
        ("2026-08-24_12-00-00_074250|01", "ETHOSCOPE_074", "01", False),
        ("2026-08-24_12-00-00_074250|02", "ETHOSCOPE_074", "02", False),
    ]
    transfers = {
        "ETHOSCOPE_316": "ETHOSCOPE_074",
        "ETHOSCOPE_074": "ETHOSCOPE_316",
    }
    tokens = {"ETHOSCOPE_074": "074250", "ETHOSCOPE_316": "316250"}

    for date, specs in (("2026-08-21", first_specs), ("2026-08-24", second_specs)):
        for original_id, machine, roi, infection in specs:
            canonical = transfers[machine] if date == "2026-08-24" else machine
            prefix = original_id.rsplit("_", 1)[0]
            analysis_id = f"{prefix}_{tokens[canonical]}|{roi}"
            rows.append(
                {
                    "original_id": original_id,
                    "analysis_id": analysis_id,
                    "date": date,
                    "original_machine": machine,
                    "canonical_machine": canonical,
                    "roi": roi,
                    "sex": "male",
                    "infection": infection,
                }
            )

    first = root / "first.pkl"
    second = root / "second.pkl"
    _write_behavpy(first, first_specs, "2026-08-21")
    _write_behavpy(second, second_specs, "2026-08-24")
    mapping_path = root / "mapping.csv"
    pd.DataFrame(rows).to_csv(mapping_path, index=False)
    return first, second, mapping_path


def _write_behavpy(path: Path, specs: list[tuple], date: str) -> None:
    data_rows = []
    metadata_rows = []
    for animal_id, machine, roi, infection in specs:
        data_rows.extend(
            {
                "id": animal_id,
                "t": time,
                "moving": moving,
                "walk": moving,
            }
            for time, moving in ((0, True), (10, False))
        )
        metadata_rows.append(
            {
                "id": animal_id,
                "date": date,
                "machine_name": machine,
                "region_id": int(roi),
                "sex": "male",
                "infection": infection,
            }
        )
    data = pd.DataFrame(data_rows).set_index("id")
    metadata = pd.DataFrame(metadata_rows).set_index("id")
    etho.behavpy(data, metadata, canvas=None, check=True).to_pickle(path)


if __name__ == "__main__":
    unittest.main()
