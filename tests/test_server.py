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
                    "get_analysis",
                    "get_artifact",
                },
            )
            self.assertTrue(tools["inspect_experiment"].annotations.read_only_hint)
            self.assertFalse(tools["run_analysis"].annotations.read_only_hint)
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
