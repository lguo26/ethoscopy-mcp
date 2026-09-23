"""Local stdio MCP adapter for the transport-independent Ethoscopy service."""

from __future__ import annotations

from mcp import types
from mcp.server import MCPServer

from ethoscopy_mcp.config import Settings
from ethoscopy_mcp.schemas import (
    AnalysisPreview,
    AnalysisRunResult,
    ArtifactReference,
    ExperimentManifest,
    ExperimentSummary,
    AnalysisRecipe,
    SurvivalRecipe,
)
from ethoscopy_mcp.service import EthoscopyService


READ_ONLY = types.ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
LOCAL_WRITE = types.ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def create_server(
    settings: Settings | None = None,
    service: EthoscopyService | None = None,
) -> MCPServer:
    """Build an MCP server; dependency injection keeps transport tests local."""

    if settings is not None and service is not None:
        raise ValueError("Pass settings or service, not both")
    active_service = service

    def get_service() -> EthoscopyService:
        nonlocal active_service
        if active_service is None:
            active_service = EthoscopyService(settings or Settings.from_env())
        return active_service

    server = MCPServer(
        "ethoscopy-mcp",
        description="Local-first, immutable Ethoscopy analysis tools",
        instructions=(
            "Inspect trusted Ethoscopy files, preview survival or sleep recipes, and execute "
            "only an exactly approved recipe hash. Source files are immutable. Tools "
            "return summaries and artifact references, never raw behavioural rows."
        ),
    )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def inspect_experiment(manifest: ExperimentManifest) -> ExperimentSummary:
        """Inspect trusted pickle sources and return compact metadata summaries."""

        return get_service().inspect_experiment(manifest)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def preview_analysis(
        manifest: ExperimentManifest, recipe: AnalysisRecipe
    ) -> AnalysisPreview:
        """Validate a survival or sleep recipe and return its exact approval hash."""

        return get_service().preview_analysis(manifest, recipe)

    @server.tool(annotations=LOCAL_WRITE, structured_output=True)
    def run_analysis(
        manifest: ExperimentManifest,
        recipe: AnalysisRecipe,
        approved_recipe_hash: str,
    ) -> AnalysisRunResult:
        """Run a freshly revalidated recipe only when its hash exactly matches."""

        return get_service().run_analysis(manifest, recipe, approved_recipe_hash)

    @server.tool(annotations=LOCAL_WRITE, structured_output=True)
    def run_kaplan_meier(
        manifest: ExperimentManifest,
        recipe: SurvivalRecipe,
        approved_recipe_hash: str,
    ) -> AnalysisRunResult:
        """Run Kaplan–Meier survival analysis using an exactly previewed survival recipe.

        Preview with preview_analysis first. Request CSV datasets individuals for
        all event/censor endpoints and kaplan_meier for curves, confidence
        intervals and risk counts; request primary PNG/SVG for survival plots.
        Configure logrank_comparisons and a statistics CSV for two-sided
        log-rank tests with optional strata and Holm correction.
        Times in CSV outputs are hours from each subject's first retained sample.
        """
        return get_service().run_analysis(manifest, recipe, approved_recipe_hash)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_analysis(analysis_id: str) -> AnalysisRunResult:
        """Return a completed run after verifying every artifact hash."""

        return get_service().get_analysis(analysis_id)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_artifact(analysis_id: str, artifact_id: str) -> ArtifactReference:
        """Return verified local artifact metadata, not the artifact contents."""

        return get_service().get_artifact(analysis_id, artifact_id)

    return server


mcp = create_server()


def main() -> None:
    """Run the local MCP server over standard input/output."""

    mcp.run()


if __name__ == "__main__":
    main()
