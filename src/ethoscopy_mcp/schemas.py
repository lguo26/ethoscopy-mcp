"""Versioned structured contracts shared by service and future MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

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


class BaselineAlignment(StrictModel):
    metadata_column: str = "baseline"
    day_length_hours: float = Field(default=24, gt=0, allow_inf_nan=False)
    apply_once: Literal[True] = True


class DeathDetectionSettings(StrictModel):
    movement_column: str = "moving"
    second_movement_column: str | None = "walk"
    time_window_hours: float = Field(default=24, gt=0)
    proportion_immobile: float = Field(default=0.01, ge=0, le=1)
    zero_run_hours: float | None = Field(default=12, gt=0)
    cumulative: bool = True


class OutputRequest(StrictModel):
    artifact_type: Literal["table", "plot"]
    format: Literal["csv", "png", "svg", "pdf", "json"]
    name: str = Field(min_length=1)
    dataset: Literal["primary", "timecourse", "individuals", "comparison", "heatmap", "statistics", "exclusions"] = "primary"
    group_label: str | None = None


class SurvivalRecipe(StrictModel):
    schema_version: str = SCHEMA_VERSION
    recipe_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    experiment_id: str = Field(min_length=1)
    analysis_type: Literal["survival"] = "survival"
    cohort_filters: dict[str, ScalarValue]
    group: GroupDefinition
    identity_overlay: IdentityOverlay
    baseline_alignment: BaselineAlignment
    time_alignment: TimeAlignment
    death_detection: DeathDetectionSettings = Field(
        default_factory=DeathDetectionSettings
    )
    output_requests: tuple[OutputRequest, ...] = ()
    assumptions: tuple[str, ...] = ()
    context_warnings: tuple[str, ...] = ()


    @model_validator(mode="after")
    def validate_survival_outputs(self) -> "SurvivalRecipe":
        for request in self.output_requests:
            if request.dataset != "primary" or request.group_label is not None:
                raise ValueError("Survival outputs use dataset=primary without group_label")
            if (request.artifact_type, request.format) not in {("table", "csv"), ("plot", "png"), ("plot", "svg")}:
                raise ValueError("Survival supports CSV tables and PNG/SVG plots")
        return self


class SleepSettings(StrictModel):
    asleep_column: str = "asleep"
    sample_period_seconds: float = Field(default=10, gt=0, allow_inf_nan=False)
    bin_minutes: float = Field(default=30, gt=0, allow_inf_nan=False)
    start_hours: float = Field(default=0, ge=0, allow_inf_nan=False)
    end_hours: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_window(self) -> "SleepSettings":
        if self.end_hours is not None and self.end_hours <= self.start_hours:
            raise ValueError("end_hours must exceed start_hours")
        return self


class SleepRecipe(StrictModel):
    schema_version: str = SCHEMA_VERSION
    recipe_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    experiment_id: str = Field(min_length=1)
    analysis_type: Literal["sleep"] = "sleep"
    cohort_filters: dict[str, ScalarValue]
    group: GroupDefinition
    identity_overlay: IdentityOverlay
    baseline_alignment: BaselineAlignment
    time_alignment: TimeAlignment
    # Deliberately explicit: no automatic death inference or implicit inclusion
    # of terminal immobility in sleep. The CSV records reviewed event/censor times.
    endpoints_path: Path
    strata_columns: tuple[str, ...] = ("temperature", "OD600")
    sleep: SleepSettings = Field(default_factory=SleepSettings)
    output_requests: tuple[OutputRequest, ...] = ()
    assumptions: tuple[str, ...] = ()
    context_warnings: tuple[str, ...] = ()


class AnalysisWindow(StrictModel):
    start_hours: float = Field(default=0, ge=0, allow_inf_nan=False)
    end_hours: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_window(self) -> "AnalysisWindow":
        if self.end_hours is not None and self.end_hours <= self.start_hours:
            raise ValueError("end_hours must exceed start_hours")
        return self


class MannWhitneySettings(StrictModel):
    group_labels: tuple[str, str]
    method: Literal["auto", "exact", "asymptotic"] = "auto"
    alternative: Literal["two-sided", "less", "greater"] = "two-sided"

    @model_validator(mode="after")
    def distinct_groups(self) -> "MannWhitneySettings":
        if self.group_labels[0] == self.group_labels[1]:
            raise ValueError("Statistical comparison needs two different groups")
        return self


class DeprivationMetadata(StrictModel):
    path: Path | None = None
    join_columns: tuple[str, ...] = Field(default=("machine_name", "date"), min_length=1)
    range_columns: tuple[str, ...] = ("stimulus_range",)
    start_hours_column: str = "deprivation_start_hours"
    end_hours_column: str = "deprivation_end_hours"
    zt0_column: str = "zt0"
    date_column: str = "date"
    time_column: str = "time"
    reference_hour: float | None = Field(default=None, ge=0, lt=24, allow_inf_nan=False)
    timezone: str | None = None


class ResolvedDeprivationWindow(StrictModel):
    start_hours: float
    end_hours: float
    source: str
    animals: int = Field(ge=1)


class SleepDeprivationQC(StrictModel):
    target_group_label: str
    window: AnalysisWindow | None = None
    metadata: DeprivationMetadata = Field(default_factory=DeprivationMetadata)
    maximum_sleep_fraction: float = Field(default=0.05, ge=0, lt=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def finite_window(self) -> "SleepDeprivationQC":
        if self.window is not None and self.window.end_hours is None:
            raise ValueError("An explicit fallback window requires a finite end time")
        return self


class MetadataExclusion(StrictModel):
    column: str
    values: tuple[ScalarValue, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    stage: Literal["before_qc", "after_curate"] = "before_qc"


class CurationSettings(StrictModel):
    movement_column: str = "moving"
    time_window_hours: int = Field(default=24, gt=0)
    proportion_immobile: float = Field(default=0.01, ge=0, le=1, allow_inf_nan=False)
    resolution: int = Field(default=24, gt=0)

    @model_validator(mode="after")
    def valid_resolution(self) -> "CurationSettings":
        if self.resolution > self.time_window_hours:
            raise ValueError("Curation resolution must not exceed time_window_hours")
        return self


class NotebookSleepRecipe(SleepRecipe):
    """Direct public Ethoscopy calls, as used in the supplied sleep notebook."""
    analysis_type: Literal["sleep_notebook"] = "sleep_notebook"
    endpoints_path: Path | None = None
    endpoint_policy: Literal["untrimmed", "reviewed", "curate"]
    strata_columns: tuple[str, ...] = ()
    profile_window: AnalysisWindow = Field(default_factory=AnalysisWindow)
    quantification_window: AnalysisWindow = Field(default_factory=AnalysisWindow)
    avg_window_minutes: int = Field(default=30, gt=0)
    day_length_hours: float = Field(default=24, gt=0, allow_inf_nan=False)
    lights_off_hours: float = Field(default=12, gt=0, allow_inf_nan=False)
    title: str = "Sleep analysis"
    deprivation_qc: SleepDeprivationQC | None = None
    exclusions: tuple[MetadataExclusion, ...] = ()
    curation: CurationSettings = Field(default_factory=CurationSettings)
    comparison: MannWhitneySettings | None = None

    @model_validator(mode="after")
    def validate_notebook_settings(self) -> "NotebookSleepRecipe":
        if (self.endpoints_path is not None) != (self.endpoint_policy == "reviewed"):
            raise ValueError("Supply endpoints_path exactly when endpoint_policy is reviewed")
        if self.lights_off_hours >= self.day_length_hours:
            raise ValueError("lights_off_hours must be below day_length_hours")
        if self.strata_columns and self.comparison is not None:
            raise ValueError("Use fixed cohort filters or explicit composite groups for a statistical comparison; implicit pooling across strata is forbidden")
        # The direct library mode uses its own windows and annotation means;
        # interval-based summary settings must not silently affect this mode.
        if self.sleep != SleepSettings():
            raise ValueError("sleep_notebook uses profile_window/quantification_window and avg_window_minutes, not interval sleep settings")
        return self


AnalysisRecipe = Annotated[SurvivalRecipe | SleepRecipe | NotebookSleepRecipe, Field(discriminator="analysis_type")]


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
    baseline_alignment: BaselineAlignment
    time_alignment: TimeAlignment
    death_detection: DeathDetectionSettings | None = None
    sleep: SleepSettings | None = None
    auxiliary_sources: tuple[SourceFile, ...] = ()
    deprivation_windows: tuple[ResolvedDeprivationWindow, ...] = ()
    transformations: tuple[TransformationPreview, ...]
    expected_artifacts: tuple[ArtifactPreview, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[ValidationWarning, ...]


class ArtifactReference(StrictModel):
    artifact_id: str
    artifact_type: str
    format: str
    name: str
    path: Path
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GroupOutcome(StrictModel):
    label: str
    animals: int = Field(ge=0)
    detected_deaths: int = Field(ge=0)
    censored: int = Field(ge=0)


class AnalysisRunResult(StrictModel):
    schema_version: str = SCHEMA_VERSION
    analysis_id: str
    recipe_id: str
    experiment_id: str
    recipe_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    run_directory: Path
    reused_existing: bool
    artifacts: tuple[ArtifactReference, ...]
    group_outcomes: tuple[GroupOutcome, ...]
    provenance_path: Path
    source_hashes_verified: bool
