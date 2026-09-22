"""Reusable scientific application service, independent of MCP transport."""

from __future__ import annotations

from collections import defaultdict
from importlib import metadata as importlib_metadata
import math
from typing import Any, Iterable

import pandas as pd

from ethoscopy_mcp.config import Settings
from ethoscopy_mcp.execution import execute_survival, load_analysis_result
from ethoscopy_mcp.exports import export_analysis
from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.loaders import load_behaviour_pickle
from ethoscopy_mcp.preview import preview_survival
from ethoscopy_mcp.registry import SourceRegistry
from ethoscopy_mcp.schemas import (
    ColumnSummary,
    ExperimentManifest,
    ExperimentSummary,
    GroupSummary,
    TimeRange,
    ValidationWarning,
    WarningSeverity,
    AnalysisPreview,
    AnalysisRunResult,
    ArtifactReference,
    AnalysisRecipe,
    SleepRecipe,
    NotebookSleepRecipe,
)


class EthoscopyService:
    """Inspect trusted Ethoscopy sources without changing them."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.registry = SourceRegistry(settings)

    def inspect_experiment(self, manifest: ExperimentManifest) -> ExperimentSummary:
        sources = tuple(self.registry.register(path) for path in manifest.source_paths)
        frames: list[pd.DataFrame] = []
        metadata_frames: list[pd.DataFrame] = []
        object_types: list[str] = []
        warnings: list[ValidationWarning] = []

        for source in sources:
            frame = load_behaviour_pickle(source)
            frames.append(frame)
            metadata_frames.append(frame.meta)
            object_types.append(type(frame).__name__)
            warnings.extend(_validate_frame(frame, source.source_id))
            self.registry.assert_unchanged(source)

        data_ids = _collect_ids(frames)
        metadata_ids = _collect_ids(metadata_frames)
        missing_metadata = data_ids - metadata_ids
        unused_metadata = metadata_ids - data_ids

        if missing_metadata:
            warnings.append(
                ValidationWarning(
                    code="animals_missing_metadata",
                    message=f"{len(missing_metadata)} data IDs have no metadata row",
                    severity=WarningSeverity.ERROR,
                )
            )
        if unused_metadata:
            warnings.append(
                ValidationWarning(
                    code="metadata_without_data",
                    message=f"{len(unused_metadata)} metadata IDs have no data rows",
                )
            )

        combined_meta = pd.concat(metadata_frames, axis=0, copy=False)
        return ExperimentSummary(
            experiment_id=manifest.experiment_id,
            display_name=manifest.display_name,
            ethoscopy_version=_package_version("ethoscopy"),
            sources=sources,
            data_object_types=tuple(object_types),
            data_rows=sum(len(frame) for frame in frames),
            metadata_rows=sum(len(frame) for frame in metadata_frames),
            animals_in_data=len(data_ids),
            animals_in_metadata=len(metadata_ids),
            data_columns=_column_summaries(frames),
            metadata_columns=_column_summaries(metadata_frames),
            groups=_group_summaries(combined_meta),
            time_range=_time_range(frames),
            warnings=tuple(warnings),
            source_hashes_verified=True,
        )

    def preview_analysis(
        self,
        manifest: ExperimentManifest,
        recipe: AnalysisRecipe,
    ) -> AnalysisPreview:
        """Validate and summarize an analysis recipe without executing it."""

        inspection = self.inspect_experiment(manifest)
        if isinstance(recipe, NotebookSleepRecipe):
            from ethoscopy_mcp.notebook_sleep import preview_notebook_sleep
            return preview_notebook_sleep(self.registry, inspection, recipe)
        if isinstance(recipe, SleepRecipe):
            from ethoscopy_mcp.sleep import preview_sleep
            return preview_sleep(self.registry, inspection, recipe)
        return preview_survival(self.registry, inspection, recipe)

    def run_analysis(
        self,
        manifest: ExperimentManifest,
        recipe: AnalysisRecipe,
        approved_recipe_hash: str,
    ) -> AnalysisRunResult:
        """Execute only the recipe whose freshly validated hash was approved."""

        preview = self.preview_analysis(manifest, recipe)
        result = execute_survival(
            self.registry, preview, recipe, approved_recipe_hash
        )
        # Validate canonical artifacts before copying, including cached runs.
        verified = self.get_analysis(result.analysis_id)
        source = self.settings.resolve_source(preview.sources[0].path)
        destination = export_analysis(source, verified)
        return result.model_copy(update={"export_directory": destination})

    def get_analysis(self, analysis_id: str) -> AnalysisRunResult:
        """Return a completed run after validating all referenced artifacts."""

        return load_analysis_result(self.registry, analysis_id)

    def get_artifact(
        self, analysis_id: str, artifact_id: str
    ) -> ArtifactReference:
        """Return verified artifact metadata without embedding file contents."""

        result = self.get_analysis(analysis_id)
        matches = tuple(
            artifact for artifact in result.artifacts
            if artifact.artifact_id == artifact_id
        )
        if len(matches) != 1:
            raise InvalidExperimentError(
                f"Artifact does not exist in analysis {analysis_id}: {artifact_id}"
            )
        return matches[0]


def _validate_frame(frame: pd.DataFrame, source_id: str) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if "t" not in frame.columns:
        warnings.append(
            ValidationWarning(
                code="missing_time_column",
                message="Data has no 't' column",
                severity=WarningSeverity.ERROR,
                source_id=source_id,
            )
        )
    if not _has_ids(frame):
        warnings.append(
            ValidationWarning(
                code="missing_data_ids",
                message="Data has no 'id' column or named index",
                severity=WarningSeverity.ERROR,
                source_id=source_id,
            )
        )
    if not _has_ids(frame.meta):
        warnings.append(
            ValidationWarning(
                code="missing_metadata_ids",
                message="Metadata has no 'id' column or named index",
                severity=WarningSeverity.ERROR,
                source_id=source_id,
            )
        )
    if _id_values(frame.meta).duplicated().any():
        warnings.append(
            ValidationWarning(
                code="duplicate_metadata_ids",
                message="Metadata contains duplicate animal IDs",
                severity=WarningSeverity.ERROR,
                source_id=source_id,
            )
        )
    return warnings


def _has_ids(frame: pd.DataFrame) -> bool:
    return "id" in frame.columns or frame.index.name == "id"


def _id_values(frame: pd.DataFrame) -> pd.Series:
    if "id" in frame.columns:
        return frame["id"].astype(str)
    if frame.index.name == "id":
        return pd.Series(frame.index.astype(str), dtype="string")
    return pd.Series(dtype="string")


def _collect_ids(frames: Iterable[pd.DataFrame]) -> set[str]:
    collected: set[str] = set()
    for frame in frames:
        collected.update(_id_values(frame).dropna().tolist())
    return collected


def _column_summaries(frames: Iterable[pd.DataFrame]) -> tuple[ColumnSummary, ...]:
    dtypes: dict[str, set[str]] = defaultdict(set)
    missing: dict[str, int] = defaultdict(int)
    for frame in frames:
        for column in frame.columns:
            name = str(column)
            dtypes[name].add(str(frame[column].dtype))
            missing[name] += int(frame[column].isna().sum())
    return tuple(
        ColumnSummary(
            name=name,
            dtypes=tuple(sorted(dtypes[name])),
            missing_values=missing[name],
        )
        for name in sorted(dtypes)
    )


def _group_summaries(metadata: pd.DataFrame) -> tuple[GroupSummary, ...]:
    groups: list[GroupSummary] = []
    for column in metadata.columns:
        series = metadata[column]
        if not bool(series.map(_is_scalar_group_value).fillna(False).all()):
            continue
        unique_count = int(series.nunique(dropna=True))
        if unique_count == 0 or unique_count > 50:
            continue
        counts: dict[str, int] = {}
        for value, count in series.value_counts(dropna=False).items():
            counts[_display_value(value)] = int(count)
        groups.append(GroupSummary(column=str(column), counts=counts))
    return tuple(groups)


def _is_scalar_group_value(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool, pd.Timestamp))


def _display_value(value: Any) -> str:
    if pd.isna(value):
        return "<missing>"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def _time_range(frames: Iterable[pd.DataFrame]) -> TimeRange | None:
    minima: list[float] = []
    maxima: list[float] = []
    for frame in frames:
        if "t" not in frame.columns:
            continue
        numeric = pd.to_numeric(frame["t"], errors="coerce").dropna()
        if numeric.empty:
            continue
        minimum = float(numeric.min())
        maximum = float(numeric.max())
        if math.isfinite(minimum) and math.isfinite(maximum):
            minima.append(minimum)
            maxima.append(maximum)
    if not minima:
        return None
    return TimeRange(minimum_seconds=min(minima), maximum_seconds=max(maxima))


def _package_version(package: str) -> str | None:
    try:
        return importlib_metadata.version(package)
    except importlib_metadata.PackageNotFoundError:
        return None
