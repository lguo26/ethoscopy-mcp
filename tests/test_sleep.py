from pathlib import Path
import tempfile
import unittest

import ethoscopy as etho
import pandas as pd

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings, SleepRecipe
from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.registry import sha256_file
from ethoscopy_mcp.schemas import (
    BaselineAlignment, GroupDefinition, GroupLevel, IdentityOverlay,
    OutputRequest, SleepSettings, TimeAlignment,
)
from ethoscopy_mcp.sleep import summarize_sleep


def fixture(root):
    # Fly a dies at 30s. Fly b has a long recording gap. Post-death samples
    # and the gap must not inflate sleep or the observation denominator.
    data = pd.DataFrame([
        {"id": fly, "t": t + 7200, "asleep": asleep}
        for fly, samples in {
            "a": [(0, 1), (10, 0), (20, 1), (30, 1), (40, 1)],
            "b": [(0, 0), (10, 1), (100, 1), (110, 1)],
        }.items() for t, asleep in samples
    ]).set_index("id")
    meta = pd.DataFrame({"id": ["a", "b"], "sex": ["male"] * 2,
        "infection": [True, False], "baseline": [0, 0],
        "temperature": [25, 25], "OD600": [.1, 0]}).set_index("id")
    source = root / "source.pkl"
    etho.behavpy(data, meta, canvas=None, check=True).to_pickle(source)
    mapping = meta.reset_index().rename(columns={"id": "original_id"})
    mapping["analysis_id"] = mapping["original_id"]
    mapping["canonical_machine"] = "machine"
    mapping["roi"] = [1, 2]
    mapping["date"] = "2026-09-09"
    mapping.iloc[::-1].to_csv(root / "mapping.csv", index=False)
    endpoints = pd.DataFrame({"analysis_id": ["a", "b"], "end_hours": [30 / 3600, 110 / 3600],
        "event": [1, 0], "reason": ["manual reviewed death", "recording end; no death detected"]})
    endpoints.to_csv(root / "endpoints.csv", index=False)
    recipe = SleepRecipe(recipe_id="sleep-test", experiment_id="test", cohort_filters={},
        group=GroupDefinition(column="infection", levels=(GroupLevel(value=False, label="PBS"), GroupLevel(value=True, label="S. aureus"))),
        identity_overlay=IdentityOverlay(mapping_path=root / "mapping.csv"),
        baseline_alignment=BaselineAlignment(),
        time_alignment=TimeAlignment(source_basis="ZT", output_basis="since injection", subtract_hours=2),
        endpoints_path=root / "endpoints.csv", sleep=SleepSettings(bin_minutes=1),
        output_requests=tuple(OutputRequest(artifact_type="table", format="csv", name=x, dataset=x)
            for x in ("primary", "timecourse", "individuals", "comparison")) + (
            OutputRequest(artifact_type="plot", format="png", name="profile", dataset="timecourse"),
            OutputRequest(artifact_type="plot", format="svg", name="comparison", dataset="comparison")))
    outputs = root / "runs"
    outputs.mkdir()
    return EthoscopyService(Settings.create([root], artifact_root=outputs)), ExperimentManifest(experiment_id="test", source_paths=(source,)), recipe


class SleepTests(unittest.TestCase):
    def test_end_to_end_manual_death_gaps_comparisons_and_immutability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, manifest, recipe = fixture(root)
            inputs = [*manifest.source_paths, recipe.identity_overlay.mapping_path, recipe.endpoints_path]
            before = {p: sha256_file(p) for p in inputs}
            preview = service.preview_analysis(manifest, recipe)
            self.assertTrue(preview.ready_to_approve)
            result = service.run_analysis(manifest, recipe, preview.recipe_hash)
            individuals = pd.read_csv(result.run_directory / "individuals.csv").set_index("group")
            self.assertAlmostEqual(individuals.loc["S. aureus", "observed_minutes"], .5)
            self.assertAlmostEqual(individuals.loc["S. aureus", "sleep_minutes"], 1/3)
            self.assertAlmostEqual(individuals.loc["PBS", "observed_minutes"], .5)
            self.assertAlmostEqual(individuals.loc["PBS", "sleep_minutes"], 1/3)
            self.assertEqual(individuals.loc["S. aureus", "event"], 1)
            self.assertIn("manual", individuals.loc["S. aureus", "reason"])
            self.assertEqual(len(result.artifacts), 7)
            self.assertEqual(result.group_outcomes, ())
            self.assertTrue(service.get_analysis(result.analysis_id).reused_existing)
            self.assertTrue(service.run_analysis(manifest, recipe, preview.recipe_hash).reused_existing)
            self.assertEqual(before, {p: sha256_file(p) for p in inputs})

    def test_endpoint_edit_invalidates_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, manifest, recipe = fixture(root)
            preview = service.preview_analysis(manifest, recipe)
            endpoints = pd.read_csv(recipe.endpoints_path)
            endpoints.loc[0, "end_hours"] = 20/3600
            endpoints.to_csv(recipe.endpoints_path, index=False)
            with self.assertRaisesRegex(InvalidExperimentError, "hash"):
                service.run_analysis(manifest, recipe, preview.recipe_hash)
            self.assertFalse(any((root / "runs").iterdir()))

    def test_missing_unknown_duplicate_or_invalid_endpoints_rejected(self):
        for kind in ["missing", "unknown", "duplicate", "outside", "censor", "reason"]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                service, manifest, recipe = fixture(Path(directory))
                end = pd.read_csv(recipe.endpoints_path)
                if kind == "missing": end = end.iloc[:1]
                if kind == "unknown": end.loc[0, "analysis_id"] = "unknown"
                if kind == "duplicate": end = pd.concat([end, end.iloc[:1]])
                if kind == "outside": end.loc[0, "end_hours"] = 100
                if kind == "censor": end.loc[1, "end_hours"] = 100/3600
                if kind == "reason": end.loc[0, "reason"] = ""
                end.to_csv(recipe.endpoints_path, index=False)
                with self.assertRaises(InvalidExperimentError): service.preview_analysis(manifest, recipe)

    def test_missing_sleep_annotation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            service, manifest, recipe = fixture(Path(directory))
            frame = pd.read_pickle(manifest.source_paths[0]).drop(columns="asleep")
            frame.to_pickle(manifest.source_paths[0])
            with self.assertRaisesRegex(InvalidExperimentError, "annotations"):
                service.preview_analysis(manifest, recipe)

    def test_metadata_strata_cannot_be_silently_relabelled(self):
        with tempfile.TemporaryDirectory() as directory:
            service, manifest, recipe = fixture(Path(directory))
            mapping = pd.read_csv(recipe.identity_overlay.mapping_path)
            mapping.loc[0, "temperature"] = 29
            mapping.to_csv(recipe.identity_overlay.mapping_path, index=False)
            with self.assertRaisesRegex(InvalidExperimentError, "temperature"):
                service.preview_analysis(manifest, recipe)

    def test_interval_crossing_bin_boundary_and_missing_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, recipe = fixture(Path(directory))
            subjects = pd.DataFrame({"subject_id": ["a"], "group": ["PBS"], "temperature": [25],
                "OD600": [0], "end_hours": [100/3600], "event": [1], "reason": ["reviewed"]}).set_index("subject_id")
            observations = pd.DataFrame({"subject_id": ["a"]*3, "t": [55, 65, 75], "asleep": [1, None, 0]})
            tables = summarize_sleep(observations, subjects, recipe)
            bins = tables["primary"].set_index("bin")
            self.assertEqual(bins.loc[0, "observed_seconds"], 5)
            self.assertEqual(bins.loc[1, "observed_seconds"], 15)
            self.assertEqual(bins["sleep_seconds"].sum(), 10)
            self.assertEqual(tables["individuals"].iloc[0]["sleep_fraction"], .5)

    def test_group_means_weight_flies_not_samples_and_preserve_strata(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, recipe = fixture(Path(directory))
            subjects = pd.DataFrame({"subject_id": ["a", "b", "c"], "group": ["PBS"]*3,
                "temperature": [25, 25, 29], "OD600": [0]*3, "end_hours": [1]*3,
                "event": [0]*3, "reason": ["reviewed"]*3}).set_index("subject_id")
            observations = pd.DataFrame({"subject_id": ["a", "a", "b", "c"], "t": [0, 10, 0, 0], "asleep": [1, 1, 0, 1]})
            comparison = summarize_sleep(observations, subjects, recipe)["comparison"].set_index("temperature")
            self.assertEqual(comparison.loc[25, "mean_sleep_fraction"], .5)
            self.assertEqual(comparison.loc[25, "animals"], 2)
            self.assertEqual(comparison.loc[29, "mean_sleep_fraction"], 1)

    def test_transfer_segments_count_as_one_physical_fly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, manifest, recipe = fixture(root)
            data = pd.read_pickle(manifest.source_paths[0])
            # A second day segment from fly a; baseline aligns it exactly once.
            extra_data = pd.DataFrame({"id": ["a2", "a2"], "t": [7200, 7210], "asleep": [1, 1]}).set_index("id")
            meta = data.meta.loc[["a"]].copy()
            meta.index = pd.Index(["a2"], name="id")
            meta["baseline"] = 1
            etho.behavpy(extra_data, meta, canvas=None, check=True).to_pickle(root / "second.pkl")
            mapping = pd.read_csv(recipe.identity_overlay.mapping_path)
            extra = mapping.loc[mapping.original_id.eq("a")].copy()
            extra["original_id"] = "a2"; extra["analysis_id"] = "a2"; extra["date"] = "2026-09-10"
            pd.concat([mapping, extra]).to_csv(recipe.identity_overlay.mapping_path, index=False)
            endpoints = pd.read_csv(recipe.endpoints_path)
            endpoints.loc[0, "end_hours"] = 24 + 10/3600
            endpoints.to_csv(recipe.endpoints_path, index=False)
            manifest = manifest.model_copy(update={"source_paths": (*manifest.source_paths, root / "second.pkl")})
            preview = service.preview_analysis(manifest, recipe)
            cohort = next(c for c in preview.cohorts if c.label == "S. aureus")
            self.assertEqual(cohort.metadata_individuals, 1)
            self.assertEqual(cohort.data_segments, 2)
            result = service.run_analysis(manifest, recipe, preview.recipe_hash)
            individuals = pd.read_csv(result.run_directory / "individuals.csv")
            self.assertEqual(len(individuals), 2)
            self.assertAlmostEqual(individuals.set_index("group").loc["S. aureus", "observed_minutes"], 1)
