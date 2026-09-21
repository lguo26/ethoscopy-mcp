"""MCP integration for reproducible Ethoscopy analysis."""

from ethoscopy_mcp.config import Settings
from ethoscopy_mcp.schemas import ExperimentManifest, ExperimentSummary
from ethoscopy_mcp.service import EthoscopyService

__version__ = "0.0.0"

__all__ = [
    "EthoscopyService",
    "ExperimentManifest",
    "ExperimentSummary",
    "Settings",
    "__version__",
]
