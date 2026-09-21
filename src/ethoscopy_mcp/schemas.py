"""Versioned structured contracts shared by service and future MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WarningSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationWarning(StrictModel):
    code: str
    message: str
    severity: WarningSeverity = WarningSeverity.WARNING
    source_id: str | None = None


class ExperimentManifest(StrictModel):
    schema_version: str = SCHEMA_VERSION
    experiment_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source_paths: tuple[Path, ...] = Field(min_length=1)
    display_name: str | None = None


class SourceFile(StrictModel):
    schema_version: str = SCHEMA_VERSION
    source_id: str
    path: Path
    media_type: str
    size_bytes: int = Field(ge=0)
    modified_ns: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ColumnSummary(StrictModel):
    name: str
    dtypes: tuple[str, ...]
    missing_values: int = Field(ge=0)


class GroupSummary(StrictModel):
    column: str
    counts: dict[str, int]


class TimeRange(StrictModel):
    minimum_seconds: float
    maximum_seconds: float


class ExperimentSummary(StrictModel):
    schema_version: str = SCHEMA_VERSION
    experiment_id: str
    display_name: str | None = None
    inspected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    ethoscopy_version: str | None = None
    sources: tuple[SourceFile, ...]
    data_object_types: tuple[str, ...]
    data_rows: int = Field(ge=0)
    metadata_rows: int = Field(ge=0)
    animals_in_data: int = Field(ge=0)
    animals_in_metadata: int = Field(ge=0)
    data_columns: tuple[ColumnSummary, ...]
    metadata_columns: tuple[ColumnSummary, ...]
    groups: tuple[GroupSummary, ...]
    time_range: TimeRange | None = None
    warnings: tuple[ValidationWarning, ...] = ()
    source_hashes_verified: bool
