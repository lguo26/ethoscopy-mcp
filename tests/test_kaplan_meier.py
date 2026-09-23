from pathlib import Path
import tempfile
import unittest

import pandas as pd
from mcp import Client

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings
from ethoscopy_mcp.schemas import OutputRequest, LogRankComparison
from ethoscopy_mcp.server import create_server
from test_preview import _write_transfer_fixture, _survival_recipe


class KaplanMeierMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_run_endpoints_curves_and_hash_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, mapping = _write_transfer_fixture(root)
            recipe = _survival_recipe(mapping).model_copy(update={
                "logrank_comparisons": (LogRankComparison(name="infection", group_labels=("PBS", "S. aureus")),),
                "output_requests": (
                OutputRequest(artifact_type="table", format="csv", name="endpoints", dataset="individuals"),
                OutputRequest(artifact_type="table", format="csv", name="km", dataset="kaplan_meier"),
                OutputRequest(artifact_type="plot", format="png", name="survival"),
                OutputRequest(artifact_type="table", format="csv", name="statistics", dataset="statistics"),
            )})
            (root / "runs").mkdir()
            service = EthoscopyService(Settings.create([root], artifact_root=root / "runs"))
            manifest = ExperimentManifest(experiment_id=recipe.experiment_id, source_paths=(first, second))
            async with Client(create_server(service=service), raise_exceptions=True,
                              read_timeout_seconds=30) as client:
                args = {"manifest": manifest.model_dump(mode="json"), "recipe": recipe.model_dump(mode="json")}
                preview = await client.call_tool("preview_analysis", args)
                bad = await client.call_tool("run_kaplan_meier", {**args, "approved_recipe_hash": "0" * 64})
                self.assertTrue(bad.is_error)
                result = await client.call_tool("run_kaplan_meier", {**args,
                    "approved_recipe_hash": preview.structured_content["recipe_hash"]})
                self.assertFalse(result.is_error)
                artifacts = {a["name"]: a for a in result.structured_content["artifacts"]}
                endpoints = pd.read_csv(artifacts["endpoints"]["path"])
                curves = pd.read_csv(artifacts["km"]["path"])
                self.assertEqual(len(endpoints), 4)
                self.assertTrue(endpoints.id.is_unique)
                self.assertEqual(int(curves.n_events.sum()), int(endpoints.E.sum()))
                self.assertEqual(int(curves.n_censored.sum()), int((endpoints.E == 0).sum()))
                statistics = pd.read_csv(artifacts["statistics"]["path"])
                self.assertEqual(len(statistics), 1)
                self.assertEqual(statistics.iloc[0].correction, "Holm")
                self.assertEqual(statistics.iloc[0].n_a + statistics.iloc[0].n_b, 4)
                retrieved = await client.call_tool("get_analysis", {"analysis_id": result.structured_content["analysis_id"]})
                self.assertFalse(retrieved.is_error)
