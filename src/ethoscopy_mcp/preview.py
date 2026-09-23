"""Analysis preview builders that never mutate experiment data."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import ethoscopy as etho
import pandas as pd

from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.loaders import load_behaviour_pickle
from ethoscopy_mcp.registry import SourceRegistry
from ethoscopy_mcp.schemas import (
    AnalysisPreview,
    ArtifactPreview,
    CohortPreview,
    ExperimentSummary,
    IdentityOverlayPreview,
    SurvivalRecipe,
    TransformationPreview,
    ValidationWarning,
    WarningSeverity,
)


def preview_survival(
    registry: SourceRegistry,
    inspection: ExperimentSummary,
    recipe: SurvivalRecipe,
) -> AnalysisPreview:
    if recipe.death_detection.time_window_hours < 24:
        raise InvalidExperimentError(
            "Survival time_window_hours must be at least 24 with the current "
            "adapter's fixed Ethoscopy resolution of 24."
        )
    if etho.__version__ != "2.4.0":
        raise InvalidExperimentError(
            "Survival analysis requires loaded Ethoscopy 2.4.0; "
            "restart ethoscopy-mcp after upgrading its environment."
        )
    if recipe.experiment_id != inspection.experiment_id:
        raise InvalidExperimentError(
            "Recipe experiment_id does not match the inspected experiment"
        )

    mapping_source = registry.register_auxiliary(recipe.identity_overlay.mapping_path)
    mapping = pd.read_csv(mapping_source.path, dtype={"roi": "string"})
    _validate_mapping_schema(mapping, recipe)

    frames = [load_behaviour_pickle(source) for source in inspection.sources]
    metadata = pd.concat([frame.meta for frame in frames], axis=0, copy=False)
    data_ids = _id_set(frames)
    metadata_ids = _frame_ids(metadata)
    _validate_mapping_against_sources(mapping, metadata, metadata_ids, data_ids, recipe)
    _validate_survival_columns(frames, recipe)

    cohort_mapping = _apply_filters(mapping, recipe.cohort_filters)
    if cohort_mapping.empty:
        raise InvalidExperimentError("Cohort filters select no metadata rows")

    key_columns = list(recipe.identity_overlay.individual_key_columns)
    group_column = recipe.group.column
    cohort_previews: list[CohortPreview] = []
    for level in recipe.group.levels:
        level_rows = cohort_mapping.loc[_values_equal(cohort_mapping[group_column], level.value)]
        with_data = level_rows[level_rows[recipe.identity_overlay.source_id_column].isin(data_ids)]
        cohort_previews.append(
            CohortPreview(
                label=level.label,
                metadata_individuals=_unique_individual_count(level_rows, key_columns),
                individuals_with_data=_unique_individual_count(with_data, key_columns),
                data_segments=len(with_data),
            )
        )

    warnings = list(inspection.warnings)
    for message in recipe.context_warnings:
        warnings.append(
            ValidationWarning(code="scientific_context", message=message)
        )
    warnings.append(
        ValidationWarning(
            code="algorithmic_death_estimate",
            message=(
                "Death events are movement-based estimates; animals without a "
                "detected event are censored at their final usable observation."
            ),
            severity=WarningSeverity.INFO,
        )
    )
    if any(cohort.individuals_with_data == 0 for cohort in cohort_previews):
        warnings.append(
            ValidationWarning(
                code="empty_analysis_group",
                message="At least one requested group has no individuals with data",
                severity=WarningSeverity.ERROR,
            )
        )

    changed_ids = int(
        (
            mapping[recipe.identity_overlay.source_id_column].astype(str)
            != mapping[recipe.identity_overlay.analysis_id_column].astype(str)
        ).sum()
    )
    recording_dates = tuple(
        sorted(mapping[recipe.identity_overlay.date_column].astype(str).unique())
    )
    mapped_individuals = _unique_individual_count(mapping, key_columns)

    transformations = (
        TransformationPreview(
            operation="baseline_alignment",
            description=(
                f"Apply metadata column {recipe.baseline_alignment.metadata_column!r} "
                f"once using {recipe.baseline_alignment.day_length_hours:g}-hour days."
            ),
        ),
        TransformationPreview(
            operation="identity_overlay",
            description=(
                "Map recording-segment IDs to canonical machine/ROI identities "
                "in a working copy while retaining original IDs in provenance."
            ),
        ),
        TransformationPreview(
            operation="column_selection",
            description=(
                "Create a survival working copy containing time and configured "
                "movement columns."
            ),
        ),
        TransformationPreview(
            operation="time_alignment",
            description=(
                f"Subtract {recipe.time_alignment.subtract_hours:g} hours from "
                f"{recipe.time_alignment.source_basis} to produce "
                f"{recipe.time_alignment.output_basis}. Survival output then uses "
                "elapsed time from each subject's first retained sample."
            ),
        ),
        TransformationPreview(
            operation="cohort_filter",
            description=f"Apply cohort filters: {recipe.cohort_filters!r}.",
        ),
        TransformationPreview(
            operation="group_labels",
            description=(
                f"Map {group_column} values to labels: "
                + ", ".join(f"{level.value!r}={level.label}" for level in recipe.group.levels)
                + "."
            ),
        ),
    )

    from ethoscopy_mcp.survival_review import read_endpoints
    auxiliary = []
    for path, reviewed in ((recipe.reviewed_endpoints_path, True), (recipe.reference_endpoints_path, False)):
        if path is not None:
            source = registry.register_auxiliary(path)
            read_endpoints(source.path, cohort_mapping, reviewed=reviewed)
            auxiliary.append(source)
            registry.assert_auxiliary_unchanged(source)
    if recipe.review_diagnostics or auxiliary:
        warnings.append(ValidationWarning(code="survival_review", message=(
            "Export per-fly estimates, candidate evidence and post-restart movement flags; "
            "flags do not automatically change death estimates. Reviewed endpoints, if supplied, "
            "replace only explicitly listed subjects in both tables and plots."
        )))
    recipe_hash = _recipe_hash(recipe, inspection, mapping_source.sha256,
                               tuple(source.sha256 for source in auxiliary))
    for source in inspection.sources:
        registry.assert_unchanged(source)
    registry.assert_auxiliary_unchanged(mapping_source)

    return AnalysisPreview(
        recipe_id=recipe.recipe_id,
        experiment_id=recipe.experiment_id,
        analysis_type=recipe.analysis_type,
        recipe_hash=recipe_hash,
        ready_to_approve=not any(
            warning.severity == WarningSeverity.ERROR for warning in warnings
        ),
        sources=inspection.sources,
        auxiliary_sources=tuple(auxiliary),
        identity_overlay=IdentityOverlayPreview(
            source=mapping_source,
            mapping_rows=len(mapping),
            mapped_individuals=mapped_individuals,
            changed_segment_ids=changed_ids,
            recording_dates=recording_dates,
            individual_key_columns=recipe.identity_overlay.individual_key_columns,
            consistency_columns=recipe.identity_overlay.consistency_columns,
        ),
        cohort_filters=recipe.cohort_filters,
        cohorts=tuple(cohort_previews),
        baseline_alignment=recipe.baseline_alignment,
        time_alignment=recipe.time_alignment,
        death_detection=recipe.death_detection,
        transformations=transformations,
        expected_artifacts=tuple(
            ArtifactPreview(
                artifact_type=request.artifact_type,
                format=request.format,
                name=request.name,
            )
            for request in recipe.output_requests
        ) + (tuple(ArtifactPreview(artifact_type="table", format="csv", name=name)
                   for name in ("survival_review.csv", "survival_candidates.csv"))
             if recipe.review_diagnostics or auxiliary else ()),
        assumptions=recipe.assumptions,
        warnings=tuple(warnings),
    )


def _validate_mapping_schema(mapping: pd.DataFrame, recipe: SurvivalRecipe) -> None:
    overlay = recipe.identity_overlay
    required = {
        overlay.source_id_column,
        overlay.analysis_id_column,
        overlay.date_column,
        recipe.group.column,
        *overlay.individual_key_columns,
        *overlay.consistency_columns,
        *recipe.cohort_filters.keys(),
    }
    missing = sorted(required - set(mapping.columns))
    if missing:
        raise InvalidExperimentError(
            f"Identity overlay is missing required columns: {', '.join(missing)}"
        )
    if mapping.empty:
        raise InvalidExperimentError("Identity overlay is empty")
    if mapping[overlay.source_id_column].astype(str).duplicated().any():
        raise InvalidExperimentError("Identity overlay contains duplicate source IDs")
    if mapping[overlay.analysis_id_column].astype(str).duplicated().any():
        raise InvalidExperimentError("Identity overlay contains duplicate analysis IDs")

    dates = set(mapping[overlay.date_column].astype(str))
    if overlay.expected_dates and dates != set(overlay.expected_dates):
        raise InvalidExperimentError(
            f"Identity overlay dates {sorted(dates)} do not match expected "
            f"dates {sorted(overlay.expected_dates)}"
        )

    group = mapping.groupby(list(overlay.individual_key_columns), dropna=False)
    inconsistent = group[list(overlay.consistency_columns)].nunique(dropna=False) > 1
    if inconsistent.any().any():
        raise InvalidExperimentError(
            "Identity overlay changes a consistency field within a mapped individual"
        )
    if mapping.duplicated(
        [*overlay.individual_key_columns, overlay.date_column]
    ).any():
        raise InvalidExperimentError(
            "Identity overlay has more than one segment per individual and date"
        )


def _validate_mapping_against_sources(
    mapping: pd.DataFrame,
    metadata: pd.DataFrame,
    metadata_ids: set[str],
    data_ids: set[str],
    recipe: SurvivalRecipe,
) -> None:
    source_column = recipe.identity_overlay.source_id_column
    mapping_ids = set(mapping[source_column].astype(str))
    if mapping_ids != metadata_ids:
        missing = len(metadata_ids - mapping_ids)
        extra = len(mapping_ids - metadata_ids)
        raise InvalidExperimentError(
            f"Identity overlay does not match metadata IDs: {missing} missing, {extra} extra"
        )
    if not data_ids.issubset(mapping_ids):
        raise InvalidExperimentError("Some data IDs are absent from the identity overlay")

    metadata_by_id = metadata.copy()
    if "id" in metadata_by_id.columns:
        metadata_by_id = metadata_by_id.set_index("id", drop=True)
    metadata_by_id.index = metadata_by_id.index.astype(str)
    mapping_by_id = mapping.set_index(source_column, drop=False)
    mapping_by_id.index = mapping_by_id.index.astype(str)
    for column in recipe.identity_overlay.consistency_columns:
        if column not in metadata_by_id.columns:
            raise InvalidExperimentError(f"Metadata is missing consistency column {column!r}")
        left = metadata_by_id.loc[sorted(metadata_ids), column]
        right = mapping_by_id.loc[sorted(metadata_ids), column]
        if not _series_equivalent(left, right):
            raise InvalidExperimentError(
                f"Identity overlay column {column!r} does not match source metadata"
            )


def _validate_survival_columns(frames: list[pd.DataFrame], recipe: SurvivalRecipe) -> None:
    required = {"t", recipe.death_detection.movement_column}
    if recipe.death_detection.second_movement_column:
        required.add(recipe.death_detection.second_movement_column)
    for index, frame in enumerate(frames):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise InvalidExperimentError(
                f"Source {index + 1} is missing survival columns: {', '.join(missing)}"
            )


def _apply_filters(
    mapping: pd.DataFrame, filters: dict[str, Any]
) -> pd.DataFrame:
    selected = pd.Series(True, index=mapping.index)
    for column, value in filters.items():
        selected &= _values_equal(mapping[column], value)
    return mapping.loc[selected]


def _values_equal(series: pd.Series, expected: Any) -> pd.Series:
    if isinstance(expected, bool):
        normalized = series.map(_as_optional_bool)
        return normalized.eq(expected)
    return series.eq(expected)


def _as_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _series_equivalent(left: pd.Series, right: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(left) or pd.api.types.is_bool_dtype(right):
        return left.map(_as_optional_bool).equals(right.map(_as_optional_bool))
    return left.astype(str).equals(right.astype(str))


def _frame_ids(frame: pd.DataFrame) -> set[str]:
    if "id" in frame.columns:
        return set(frame["id"].astype(str))
    if frame.index.name == "id":
        return set(frame.index.astype(str))
    return set()


def _id_set(frames: list[pd.DataFrame]) -> set[str]:
    values: set[str] = set()
    for frame in frames:
        values.update(_frame_ids(frame))
    return values


def _unique_individual_count(frame: pd.DataFrame, columns: list[str]) -> int:
    if frame.empty:
        return 0
    return len(frame.drop_duplicates(columns))


def _recipe_hash(
    recipe: SurvivalRecipe,
    inspection: ExperimentSummary,
    overlay_hash: str,
    auxiliary_hashes: tuple[str, ...] = (),
) -> str:
    payload = {
        "survival_engine": "notebook-2.4-review-v2",
        "auxiliary_hashes": auxiliary_hashes,
        "ethoscopy_version": etho.__version__,
        "recipe": recipe.model_dump(mode="json"),
        "source_hashes": [source.sha256 for source in inspection.sources],
        "overlay_hash": overlay_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
