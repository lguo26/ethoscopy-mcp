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
    ExclusionDecisionRequest,
)
from ethoscopy_mcp.service import EthoscopyService
from ethoscopy_mcp.experiment_records import (
    ExperimentRecord, RegisteredExperiment, ExperimentRecords, DashboardResult,
)


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

    @server.tool(annotations=LOCAL_WRITE, structured_output=True)
    def register_experiment(record: ExperimentRecord, expected_revision: int = 0) -> RegisteredExperiment:
        """Save a local work record; 0 creates, current revision updates.

        Supply explicit conditions and recording status. Unknown fields stay unknown.
        Registration opts matching experiment ID/source paths into automatic result
        linking and dashboard rebuilding after successful analysis. Build the
        dashboard explicitly after editing work records. Never infer exclusions.
        """
        return get_service().register_experiment(record, expected_revision)

    @server.tool(annotations=LOCAL_WRITE, structured_output=True)
    def record_exclusion_decision(experiment_id: str, decision: ExclusionDecisionRequest,
                                  expected_revision: int) -> RegisteredExperiment:
        """Append a versioned, researcher-confirmed survival exclusion decision.

        Register source files first. Supply the current experiment revision, actual
        confirmation context and exact source animal IDs. Never infer exclusion
        from time-zero death alone. A new version supersedes but preserves history;
        status retired withdraws the decision. Inspect/preview retrieve decisions
        by source identity even for a new experiment name. Record new versions to
        reconfirm changed source bytes. This tool does not authenticate humans.
        """
        return get_service().record_exclusion_decision(experiment_id, decision, expected_revision)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def list_experiments() -> ExperimentRecords:
        """List local work records, revisions, and linked verified-run references."""
        return get_service().list_experiments()

    @server.tool(annotations=LOCAL_WRITE, structured_output=True)
    def link_experiment_analysis(analysis_id: str) -> RegisteredExperiment:
        """Verify an existing run, link to its registered experiment, rebuild dashboard."""
        return get_service().link_experiment_analysis(analysis_id)

    @server.tool(annotations=LOCAL_WRITE, structured_output=True)
    def build_experiment_dashboard() -> DashboardResult:
        """Build offline HTML with filters, plots and a condition tree.

        Reverify all linked artifacts. Do not aggregate overlapping run counts or
        infer acquisition status. Refresh the browser after rebuilding.
        """
        return get_service().build_experiment_dashboard()

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def inspect_experiment(manifest: ExperimentManifest) -> ExperimentSummary:
        """Inspect trusted pickle sources and return compact metadata summaries."""

        return get_service().inspect_experiment(manifest)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def preview_analysis(
        manifest: ExperimentManifest, recipe: AnalysisRecipe
    ) -> AnalysisPreview:
        """Validate a recipe and return its exact approval hash.

        Survival previews surface applicable reviewed exclusions. Resolve each in
        decision_resolutions using apply or sensitivity_include, its current
        revision, and a reason. Missing resolutions block execution. Apply adds
        recorded exclusions to effective_survival_recipe for review and execution.
        """

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
        Use exclusions with original_id and reason to remove whole mapped animals.
        Optional metadata_csv checks external metadata; unresolved conflicts block
        execution. Explicit metadata_corrections apply only to working copies.
        Exclusions and corrections automatically export audit CSVs. Set plot_title
        for a custom readable title; group labels control the legend.
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
