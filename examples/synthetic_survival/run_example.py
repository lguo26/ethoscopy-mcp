"""Preview, and optionally execute, the synthetic survival recipe."""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("MPLBACKEND", "Agg")

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings
from ethoscopy_mcp.schemas import (
    BaselineAlignment,
    DeathDetectionSettings,
    GroupDefinition,
    GroupLevel,
    IdentityOverlay,
    OutputRequest,
    SurvivalRecipe,
    TimeAlignment,
)

from make_data import GENERATED, main as make_data


def main(approve: bool = False) -> None:
    first, second, mapping = make_data()
    artifact_root = GENERATED / "analysis_runs"
    artifact_root.mkdir(exist_ok=True)
    manifest = ExperimentManifest(
        experiment_id="synthetic-transfer",
        display_name="Synthetic transfer survival",
        source_paths=(first, second),
    )
    recipe = SurvivalRecipe(
        recipe_id="synthetic-male-survival",
        experiment_id=manifest.experiment_id,
        cohort_filters={"sex": "male"},
        group=GroupDefinition(
            column="infection",
            levels=(
                GroupLevel(value=False, label="PBS"),
                GroupLevel(value=True, label="S. aureus"),
            ),
        ),
        identity_overlay=IdentityOverlay(
            mapping_path=mapping,
            expected_dates=("2026-01-01", "2026-01-02"),
        ),
        baseline_alignment=BaselineAlignment(),
        time_alignment=TimeAlignment(
            source_basis="baseline-aligned ZT",
            output_basis="time since injection",
            subtract_hours=2,
            zt0_description="synthetic ZT0",
            injection_description="synthetic ZT2",
        ),
        death_detection=DeathDetectionSettings(
            time_window_hours=12,
            zero_run_hours=6,
            cumulative=False,
        ),
        output_requests=(
            OutputRequest(
                artifact_type="table", format="csv", name="synthetic_death_table"
            ),
            OutputRequest(
                artifact_type="plot", format="png", name="synthetic_survival"
            ),
            OutputRequest(
                artifact_type="plot", format="svg", name="synthetic_survival"
            ),
        ),
        assumptions=("Synthetic flies retain their ROI after transfer.",),
        context_warnings=("Synthetic data are for software demonstration only.",),
    )
    service = EthoscopyService(
        Settings.create([GENERATED], artifact_root=artifact_root)
    )
    preview = service.preview_analysis(manifest, recipe)
    print(preview.model_dump_json(indent=2))
    if not approve:
        print("\nPreview only. Rerun with --approve to execute this exact recipe.")
        return

    result = service.run_analysis(
        manifest, recipe, approved_recipe_hash=preview.recipe_hash
    )
    print("\nApproved result:")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approve", action="store_true", help="execute the freshly previewed recipe"
    )
    arguments = parser.parse_args()
    main(approve=arguments.approve)
