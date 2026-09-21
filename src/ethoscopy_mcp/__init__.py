"""MCP integration for reproducible Ethoscopy analysis."""

from ethoscopy_mcp.config import Settings
from ethoscopy_mcp.schemas import (
    AnalysisPreview,
    AnalysisRunResult,
    ExperimentManifest,
    ExperimentSummary,
    SurvivalRecipe,
)
from ethoscopy_mcp.service import EthoscopyService

__version__ = "0.0.0"

__all__ = [
    "EthoscopyService",
    "AnalysisPreview",
    "AnalysisRunResult",
    "ExperimentManifest",
    "ExperimentSummary",
    "Settings",
    "SurvivalRecipe",
    "__version__",
]
