from pathlib import Path
import unittest

from mcp import Client

from ethoscopy_mcp.schemas import ArtifactReference
from ethoscopy_mcp.server import create_server


class FakeService:
    def get_artifact(
        self, analysis_id: str, artifact_id: str
    ) -> ArtifactReference:
        return ArtifactReference(
            artifact_id=artifact_id,
            artifact_type="plot",
            format="png",
            name=f"{analysis_id}-survival",
            path=Path("/local/artifacts/survival.png"),
            size_bytes=123,
            sha256="a" * 64,
        )


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_exposes_typed_local_tool_surface(self):
        async with Client(
            create_server(service=FakeService()),
            raise_exceptions=True,
            read_timeout_seconds=10,
        ) as client:
            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}

            self.assertEqual(
                set(tools),
                {
                    "inspect_experiment",
                    "preview_analysis",
                    "run_analysis",
                    "run_kaplan_meier",
                    "get_analysis",
                    "get_artifact",
                },
            )
            self.assertTrue(tools["inspect_experiment"].annotations.read_only_hint)
            self.assertFalse(tools["run_analysis"].annotations.read_only_hint)
            self.assertFalse(tools["run_kaplan_meier"].annotations.read_only_hint)
            self.assertIn("$defs", tools["preview_analysis"].input_schema)
            self.assertIsNotNone(tools["get_analysis"].output_schema)

            result = await client.call_tool(
                "get_artifact",
                {"analysis_id": "run-001", "artifact_id": "sha256-example"},
            )

            self.assertFalse(result.is_error)
            self.assertEqual(
                result.structured_content["artifact_id"], "sha256-example"
            )
            self.assertEqual(result.structured_content["format"], "png")


if __name__ == "__main__":
    unittest.main()

class SleepMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_sleep_preview_run_and_retrieve_through_mcp(self):
        import tempfile
        from test_sleep import fixture
        with tempfile.TemporaryDirectory() as directory:
            service, manifest, recipe = fixture(Path(directory))
            async with Client(create_server(service=service), raise_exceptions=True,
                              read_timeout_seconds=30) as client:
                args = {"manifest": manifest.model_dump(mode="json"), "recipe": recipe.model_dump(mode="json")}
                preview = await client.call_tool("preview_analysis", args)
                self.assertFalse(preview.is_error)
                self.assertEqual(preview.structured_content["analysis_type"], "sleep")
                run = await client.call_tool("run_analysis", {**args,
                    "approved_recipe_hash": preview.structured_content["recipe_hash"]})
                self.assertFalse(run.is_error)
                result = await client.call_tool("get_analysis", {"analysis_id": run.structured_content["analysis_id"]})
                self.assertFalse(result.is_error)
                self.assertEqual(len(result.structured_content["artifacts"]), 7)

class NotebookSleepMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_notebook_recipe_through_mcp(self):
        import tempfile
        from test_notebook_sleep import fixture
        with tempfile.TemporaryDirectory() as directory:
            service, manifest, recipe = fixture(Path(directory))
            # Quantification, statistics, and QC audit are sufficient to exercise
            # the distinct union arm through the actual MCP contract.
            recipe = recipe.model_copy(update={"output_requests": tuple(
                r for r in recipe.output_requests if r.dataset in {"individuals", "statistics", "exclusions"})})
            async with Client(create_server(service=service), raise_exceptions=True,
                              read_timeout_seconds=30) as client:
                args = {"manifest": manifest.model_dump(mode="json"), "recipe": recipe.model_dump(mode="json")}
                preview = await client.call_tool("preview_analysis", args)
                self.assertFalse(preview.is_error)
                self.assertEqual(preview.structured_content["analysis_type"], "sleep_notebook")
                result = await client.call_tool("run_analysis", {**args,
                    "approved_recipe_hash": preview.structured_content["recipe_hash"]})
                self.assertFalse(result.is_error)
                self.assertEqual(len(result.structured_content["artifacts"]), 4)
