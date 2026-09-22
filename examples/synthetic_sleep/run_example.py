"""Run a self-contained sleep comparison: python run_example.py /tmp/sleep-demo."""
from pathlib import Path
import sys
import ethoscopy as etho
import pandas as pd
from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings, SleepRecipe


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "runs").mkdir(exist_ok=True)
    meta = pd.DataFrame({"id": ["fly-a", "fly-b", "fly-c", "fly-d"],
        "sex": ["male"] * 4, "infection": [False, False, True, True],
        "temperature": [25] * 4, "OD600": [0, 0, .1, .1], "baseline": [0] * 4}).set_index("id")
    rows = [{"id": fly, "t": t, "asleep": (t // 600 + i) % 2 == 0}
            for i, fly in enumerate(meta.index) for t in range(0, 7201, 60)]
    etho.behavpy(pd.DataFrame(rows).set_index("id"), meta, canvas=None, check=True).to_pickle(root / "sleep.pkl")
    mapping = meta.reset_index().rename(columns={"id": "original_id"})
    mapping["analysis_id"] = mapping["original_id"]
    mapping["canonical_machine"] = "synthetic"
    mapping["roi"] = range(1, 5)
    mapping["date"] = "2026-09-09"
    mapping.to_csv(root / "mapping.csv", index=False)
    pd.DataFrame({"analysis_id": list(meta.index), "end_hours": [2, 2, 1, 2],
        "event": [0, 0, 1, 0], "reason": ["synthetic recording end", "synthetic recording end",
        "synthetic reviewed manual death", "synthetic recording end"]}).to_csv(root / "endpoints.csv", index=False)
    recipe = SleepRecipe.model_validate({
        "recipe_id": "synthetic-sleep", "experiment_id": "synthetic-sleep", "analysis_type": "sleep",
        "cohort_filters": {}, "group": {"column": "infection", "levels": [
            {"value": False, "label": "PBS"}, {"value": True, "label": "S. aureus"}]},
        "identity_overlay": {"mapping_path": str(root / "mapping.csv")},
        "baseline_alignment": {},
        "time_alignment": {"source_basis": "synthetic recording", "output_basis": "Time since start", "subtract_hours": 0},
        "endpoints_path": str(root / "endpoints.csv"), "sleep": {"sample_period_seconds": 60, "bin_minutes": 30},
        "output_requests": [
            *[{"artifact_type": "table", "format": "csv", "name": x, "dataset": x}
              for x in ["primary", "individuals", "timecourse", "comparison"]],
            {"artifact_type": "plot", "format": "png", "name": "profile", "dataset": "timecourse"},
            {"artifact_type": "plot", "format": "svg", "name": "comparison", "dataset": "comparison"}]})
    manifest = ExperimentManifest(experiment_id="synthetic-sleep", source_paths=(root / "sleep.pkl",))
    service = EthoscopyService(Settings.create([root], artifact_root=root / "runs"))
    preview = service.preview_analysis(manifest, recipe)
    # This local example deliberately executes its own reviewed synthetic recipe.
    result = service.run_analysis(manifest, recipe, preview.recipe_hash)
    (root / "manifest.json").write_text(manifest.model_dump_json(indent=2))
    (root / "recipe.json").write_text(recipe.model_dump_json(indent=2))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
