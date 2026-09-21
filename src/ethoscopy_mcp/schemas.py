"""Versioned structured contracts shared by service and future MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


ScalarValue = str | int | float | bool


class GroupLevel(StrictModel):
    value: ScalarValue
    label: str = Field(min_length=1)


class GroupDefinition(StrictModel):
    column: str = Field(min_length=1)
    levels: tuple[GroupLevel, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_levels(self) -> "GroupDefinition":
        values = [(type(level.value).__name__, repr(level.value)) for level in self.levels]
        labels = [level.label for level in self.levels]
        if len(values) != len(set(values)):
            raise ValueError("Group level values must be unique")
        if len(labels) != len(set(labels)):
            raise ValueError("Group level labels must be unique")
        return self


class IdentityOverlay(StrictModel):
    mapping_path: Path
    source_id_column: str = "original_id"
    analysis_id_column: str = "analysis_id"
    individual_key_columns: tuple[str, ...] = Field(
        default=("canonical_machine", "roi"), min_length=1
    )
    date_column: str = "date"
    expected_dates: tuple[str, ...] = ()
    consistency_columns: tuple[str, ...] = ("sex", "infection")


class TimeAlignment(StrictModel):
    source_basis: str = Field(min_length=1)
    output_basis: str = Field(min_length=1)
    subtract_hours: float = Field(allow_inf_nan=False)
    discard_negative_time: bool = True
    zt0_description: str | None = None
    injection_description: str | None = None


class DeathDetectionSettings(StrictModel):
    movement_column: str = "moving"
    second_movement_column: str | None = "walk"
    time_window_hours: float = Field(default=24, gt=0)
    proportion_immobile: float = Field(default=0.01, ge=0, le=1)
    zero_run_hours: float | None = Field(default=12, gt=0)
    cumulative: bool = True


class OutputRequest(StrictModel):
    artifact_type: Literal["table", "plot"]
    format: Literal["csv", "png", "svg", "json"]
    name: str = Field(min_length=1)


class SurvivalRecipe(StrictModel):
    schema_version: str = SCHEMA_VERSION
    recipe_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    experiment_id: str = Field(min_length=1)
    analysis_type: Literal["survival"] = "survival"
    cohort_filters: dict[str, ScalarValue]
    group: GroupDefinition
    identity_overlay: IdentityOverlay
    time_alignment: TimeAlignment
    death_detection: DeathDetectionSettings = Field(
        default_factory=DeathDetectionSettings
    )
    output_requests: tuple[OutputRequest, ...] = ()
    assumptions: tuple[str, ...] = ()
    context_warnings: tuple[str, ...] = ()


class CohortPreview(StrictModel):
    label: str
    metadata_individuals: int = Field(ge=0)
    individuals_with_data: int = Field(ge=0)
    data_segments: int = Field(ge=0)


class IdentityOverlayPreview(StrictModel):
    source: SourceFile
    mapping_rows: int = Field(ge=0)
    mapped_individuals: int = Field(ge=0)
    changed_segment_ids: int = Field(ge=0)
    recording_dates: tuple[str, ...]
    individual_key_columns: tuple[str, ...]
    consistency_columns: tuple[str, ...]


class TransformationPreview(StrictModel):
    operation: str
    description: str
    mutates_source: Literal[False] = False


class ArtifactPreview(StrictModel):
    artifact_type: str
    format: str
    name: str


class AnalysisPreview(StrictModel):
    schema_version: str = SCHEMA_VERSION
    previewed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    recipe_id: str
    experiment_id: str
    analysis_type: str
    recipe_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_required: Literal[True] = True
    ready_to_approve: bool
    sources: tuple[SourceFile, ...]
    identity_overlay: IdentityOverlayPreview
    cohort_filters: dict[str, ScalarValue]
    cohorts: tuple[CohortPreview, ...]
    time_alignment: TimeAlignment
    death_detection: DeathDetectionSettings
    transformations: tuple[TransformationPreview, ...]
    expected_artifacts: tuple[ArtifactPreview, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[ValidationWarning, ...]
