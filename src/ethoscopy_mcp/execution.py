"""Approved, immutable survival-analysis execution."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
import inspect
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import ethoscopy as etho
import pandas as pd

from ethoscopy_mcp.errors import ConfigurationError, InvalidExperimentError
from ethoscopy_mcp.loaders import load_behaviour_pickle
from ethoscopy_mcp.registry import SourceRegistry, sha256_file
from ethoscopy_mcp.schemas import (
    AnalysisPreview,
    AnalysisRunResult,
    ArtifactReference,
    GroupOutcome,
    SurvivalRecipe,
    SleepRecipe,
    NotebookSleepRecipe,
    AnalysisRecipe,
)


RESULT_NAME = "run-result.json"
PROVENANCE_NAME = "provenance.json"


def execute_survival(
    registry: SourceRegistry,
    preview: AnalysisPreview,
    recipe: AnalysisRecipe,
    approved_recipe_hash: str,
) -> AnalysisRunResult:
    """Execute exactly one approved recipe into a content-addressed directory."""

    if approved_recipe_hash != preview.recipe_hash:
        raise InvalidExperimentError(
            "Approved recipe hash does not match the current validated preview"
        )
    if not preview.ready_to_approve:
        raise InvalidExperimentError("Analysis preview contains blocking validation errors")
    artifact_root = registry.settings.artifact_root
    if artifact_root is None:
        raise ConfigurationError("An artifact root is required to execute an analysis")

    analysis_id = f"{_safe_component(recipe.recipe_id)}-{preview.recipe_hash[:12]}"
    run_directory = artifact_root / analysis_id
    result_path = run_directory / RESULT_NAME
    if run_directory.exists():
        if not result_path.is_file():
            raise InvalidExperimentError(
                f"Incomplete existing analysis directory must be reviewed: {run_directory}"
            )
        return _load_existing(result_path, preview.recipe_hash)

    temporary = Path(tempfile.mkdtemp(prefix=f".{analysis_id}-", dir=artifact_root))
    try:
        if isinstance(recipe, NotebookSleepRecipe):
            from ethoscopy_mcp.notebook_sleep import write_notebook_artifacts
            requested_artifacts = write_notebook_artifacts(preview, recipe, temporary, run_directory)
            group_outcomes = ()
        elif isinstance(recipe, SleepRecipe):
            from ethoscopy_mcp.sleep import prepare_sleep, summarize_sleep
            observations, subjects, _ = prepare_sleep(
                preview.sources, preview.identity_overlay.source,
                preview.auxiliary_sources[0], recipe,
            )
            tables = summarize_sleep(observations, subjects, recipe)
            requested_artifacts = _write_sleep_artifacts(tables, recipe, temporary, run_directory)
            # Sleep summaries must never masquerade as survival outcome counts.
            group_outcomes = ()
        else:
            table, figure = _run_recipe(preview, recipe)
            requested_artifacts = _write_requested_artifacts(
                table, figure, recipe, temporary, run_directory
            )
            group_outcomes = _group_outcomes(preview, table)
        created_at = datetime.now(timezone.utc)
        provenance_path = run_directory / PROVENANCE_NAME
        provenance = {
            "schema_version": preview.schema_version,
            "analysis_id": analysis_id,
            "created_at": created_at.isoformat(),
            "recipe_hash": preview.recipe_hash,
            "recipe": recipe.model_dump(mode="json"),
            "sources": [source.model_dump(mode="json") for source in preview.sources],
            "identity_overlay": preview.identity_overlay.source.model_dump(mode="json"),
            "auxiliary_sources": [s.model_dump(mode="json") for s in preview.auxiliary_sources],
            "source_hashes_verified": True,
            "ethoscopy_version": _package_version("ethoscopy"),
            "scipy_version": _package_version("scipy"),
            "warnings": [warning.model_dump(mode="json") for warning in preview.warnings],
            "group_outcomes": [outcome.model_dump(mode="json") for outcome in group_outcomes],
            "artifacts": [artifact.model_dump(mode="json") for artifact in requested_artifacts],
        }
        _write_json(temporary / PROVENANCE_NAME, provenance)
        provenance_reference = _artifact_reference(
            temporary / PROVENANCE_NAME,
            run_directory / PROVENANCE_NAME,
            artifact_type="provenance",
            format_name="json",
            name=PROVENANCE_NAME,
        )
        result = AnalysisRunResult(
            analysis_id=analysis_id,
            recipe_id=recipe.recipe_id,
            experiment_id=recipe.experiment_id,
            recipe_hash=preview.recipe_hash,
            created_at=created_at,
            run_directory=run_directory,
            reused_existing=False,
            artifacts=(*requested_artifacts, provenance_reference),
            group_outcomes=group_outcomes,
            provenance_path=provenance_path,
            source_hashes_verified=True,
        )
        _write_json(temporary / RESULT_NAME, result.model_dump(mode="json"))

        _assert_sources_unchanged(registry, preview)
        temporary.rename(run_directory)
        return result
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def load_analysis_result(
    registry: SourceRegistry, analysis_id: str
) -> AnalysisRunResult:
    """Load a completed run after revalidating its filesystem boundary and hashes."""

    artifact_root = registry.settings.artifact_root
    if artifact_root is None:
        raise ConfigurationError("An artifact root is required to retrieve an analysis")
    safe_id = _safe_component(analysis_id)
    run_directory = artifact_root / safe_id
    result_path = run_directory / RESULT_NAME
    if not result_path.is_file():
        raise InvalidExperimentError(f"Analysis does not exist: {safe_id}")

    result = AnalysisRunResult.model_validate_json(result_path.read_text())
    resolved_root = artifact_root.resolve(strict=True)
    resolved_run = run_directory.resolve(strict=True)
    try:
        resolved_run.relative_to(resolved_root)
    except ValueError as exc:
        raise InvalidExperimentError(
            "Analysis directory escapes the configured artifact root"
        ) from exc
    if result.analysis_id != safe_id or result.run_directory.resolve() != resolved_run:
        raise InvalidExperimentError("Stored analysis identity or directory is inconsistent")
    if result.provenance_path.resolve() != (resolved_run / PROVENANCE_NAME):
        raise InvalidExperimentError("Stored provenance path is inconsistent")

    for artifact in result.artifacts:
        try:
            artifact_path = artifact.path.resolve(strict=True)
            artifact_path.relative_to(resolved_run)
        except (FileNotFoundError, ValueError) as exc:
            raise InvalidExperimentError(
                f"Artifact escapes the analysis directory or is missing: {artifact.name}"
            ) from exc
        if (
            not artifact_path.is_file()
            or artifact_path.stat().st_size != artifact.size_bytes
            or sha256_file(artifact_path) != artifact.sha256
        ):
            raise InvalidExperimentError(
                f"Stored artifact is missing or changed: {artifact.name}"
            )
    return result.model_copy(update={"reused_existing": True})


def _run_recipe(
    preview: AnalysisPreview, recipe: SurvivalRecipe
) -> tuple[pd.DataFrame, Any]:
    frames = [load_behaviour_pickle(source) for source in preview.sources]
    combined = etho.concat(*frames)
    combined = combined.baseline(
        column=recipe.baseline_alignment.metadata_column,
        day_length=recipe.baseline_alignment.day_length_hours,
    )

    overlay = recipe.identity_overlay
    mapping = pd.read_csv(preview.identity_overlay.source.path, dtype={"roi": "string"})
    mapping[overlay.source_id_column] = mapping[overlay.source_id_column].astype(str)
    mapping[overlay.analysis_id_column] = mapping[overlay.analysis_id_column].astype(str)
    mapping_by_source = mapping.set_index(overlay.source_id_column, drop=False)
    id_map = mapping_by_source[overlay.analysis_id_column].to_dict()

    columns = ["t", recipe.death_detection.movement_column]
    if recipe.death_detection.second_movement_column:
        columns.append(recipe.death_detection.second_movement_column)
    working = combined[list(dict.fromkeys(columns))].copy()
    working.index = pd.Index(working.index.astype(str).map(id_map), name="id")
    if working.index.isna().any():
        raise InvalidExperimentError("Identity overlay failed to map one or more data IDs")

    metadata = combined.meta.copy(deep=True)
    if "id" in metadata.columns:
        metadata = metadata.set_index("id", drop=True)
    metadata.index = metadata.index.astype(str)
    if "canonical_machine" in mapping.columns:
        metadata["original_machine_name"] = metadata.get("machine_name")
        metadata["machine_name"] = mapping_by_source["canonical_machine"]
    metadata.index = pd.Index(metadata.index.map(id_map), name="id")
    if metadata.index.isna().any():
        raise InvalidExperimentError("Identity overlay failed to map metadata IDs")

    label_map = {level.value: level.label for level in recipe.group.levels}
    metadata["species"] = metadata[recipe.group.column].map(label_map)
    if metadata["species"].isna().any():
        raise InvalidExperimentError("A group value has no configured display label")
    working.meta = metadata

    working["t"] = (
        pd.to_numeric(working["t"], errors="raise")
        - recipe.time_alignment.subtract_hours * 3600
    )
    if recipe.time_alignment.discard_negative_time:
        working = working.loc[working["t"] >= 0].copy()
        working.meta = metadata

    selected_mapping = mapping.copy()
    for column, value in recipe.cohort_filters.items():
        selected_mapping = selected_mapping.loc[
            _values_equal(selected_mapping[column], value)
        ]
    selected_ids = set(selected_mapping[overlay.analysis_id_column].astype(str))
    selected_meta = metadata.loc[metadata.index.isin(selected_ids)].copy()
    working = working.loc[working.index.isin(selected_ids)].copy()
    if working.empty:
        raise InvalidExperimentError("Approved cohort contains no usable observations")
    # Pandas slicing may intentionally return the core subclass. Reconstruct
    # through the public factory so plotting methods and validated metadata are
    # present without altering either loaded source object.
    working = etho.behavpy(pd.DataFrame(working), selected_meta, check=True)

    death = recipe.death_detection
    death_settings: dict[str, Any] = {
        "mov_column": death.movement_column,
        "second_mov_column": death.second_movement_column,
        "time_window": death.time_window_hours,
        "prop_immobile": death.proportion_immobile,
        "zero_run_hours": death.zero_run_hours,
    }
    modern_survival_api = (
        "meta_cols" in inspect.signature(working.km_death_table).parameters
    )
    if modern_survival_api:
        # Ethoscopy >=2.4 names the cross-session identity columns explicitly.
        subject_columns = ["machine_name", "region_id"]
        table = working.km_death_table(
            **death_settings,
            subject_cols=subject_columns,
            meta_cols=["species"],
            time_unit="hours",
        ).rename(columns={"species": "treatment"})
        plot_api_settings = {
            "subject_cols": subject_columns,
            "censor_marks": True,
            "grids": False,
        }
    else:
        # Ethoscopy 2.2/2.3 infer the same identity from machine_name and ROI.
        death_settings["cumulative"] = death.cumulative
        table = working.km_death_table(
            **death_settings, time_unit="hours"
        ).rename(columns={"genotype": "treatment"})
        plot_api_settings = {"censoring_marks": True, "grid": False}
    for column, value in recipe.cohort_filters.items():
        table[column] = value

    labels = [level.label for level in recipe.group.levels]
    figure = working.km_survival_plot(
        **death_settings,
        facet_col="species",
        facet_arg=labels,
        facet_labels=labels,
        title=_plot_title(working, recipe),
        figsize=(12.8, 7.2),
        time_unit="days",
        show_ci=True,
        **plot_api_settings,
    )
    _style_figure(figure)
    return table, figure


def _write_requested_artifacts(
    table: pd.DataFrame,
    figure: Any,
    recipe: SurvivalRecipe,
    temporary: Path,
    run_directory: Path,
) -> tuple[ArtifactReference, ...]:
    import matplotlib.pyplot as plt

    references: list[ArtifactReference] = []
    seen: set[str] = set()
    try:
        for request in recipe.output_requests:
            filename = _output_filename(request.name, request.format)
            if filename in seen:
                raise InvalidExperimentError(f"Duplicate output filename: {filename}")
            seen.add(filename)
            temporary_path = temporary / filename
            if request.artifact_type == "table" and request.format == "csv":
                table.to_csv(temporary_path, index=False)
            elif request.artifact_type == "plot" and request.format in {"png", "svg"}:
                save_kwargs: dict[str, Any] = {"facecolor": "white", "bbox_inches": None}
                if request.format == "png":
                    save_kwargs["dpi"] = 300
                figure.savefig(temporary_path, **save_kwargs)
            else:
                raise InvalidExperimentError(
                    f"Unsupported output request: {request.artifact_type}/{request.format}"
                )
            references.append(
                _artifact_reference(
                    temporary_path,
                    run_directory / filename,
                    artifact_type=request.artifact_type,
                    format_name=request.format,
                    name=request.name,
                )
            )
    finally:
        plt.close(figure)
    return tuple(references)


def _group_outcomes(
    preview: AnalysisPreview, table: pd.DataFrame
) -> tuple[GroupOutcome, ...]:
    death_counts = table.get("treatment", pd.Series(dtype="string")).value_counts()
    return tuple(
        GroupOutcome(
            label=cohort.label,
            animals=cohort.individuals_with_data,
            detected_deaths=int(death_counts.get(cohort.label, 0)),
            censored=cohort.individuals_with_data - int(death_counts.get(cohort.label, 0)),
        )
        for cohort in preview.cohorts
    )


def _style_figure(figure: Any) -> None:
    figure.set_size_inches(12.8, 7.2)
    axis = figure.axes[0]
    axis.set_xlabel("Time since injection (days)", fontsize=20, labelpad=12)
    axis.set_ylabel("Survival probability", fontsize=20, labelpad=12)
    axis.title.set_fontsize(24)
    axis.tick_params(axis="both", labelsize=18)
    legend = axis.get_legend()
    if legend is not None:
        legend.set_frame_on(False)
        for text in legend.get_texts():
            text.set_fontsize(18)
    for annotation in list(axis.texts):
        if "deaths" in annotation.get_text() and "tw=" in annotation.get_text():
            annotation.remove()
    figure.subplots_adjust(left=0.12, right=0.97, bottom=0.16, top=0.88)


def _plot_title(working: pd.DataFrame, recipe: SurvivalRecipe) -> str:
    cohort = ", ".join(f"{key}={value}" for key, value in recipe.cohort_filters.items())
    temperature_column = next(
        (column for column in ("temperature", "tempreture") if column in working.meta),
        None,
    )
    temperature = ""
    if temperature_column:
        values = pd.to_numeric(
            working.meta[temperature_column], errors="coerce"
        ).dropna().unique()
        if len(values):
            temperature = " (" + ", ".join(
                f"{value:g} °C" for value in sorted(values)
            ) + ")"
    return f"Survival — {cohort}{temperature}"


def _load_existing(result_path: Path, recipe_hash: str) -> AnalysisRunResult:
    result = AnalysisRunResult.model_validate_json(result_path.read_text())
    if result.recipe_hash != recipe_hash:
        raise InvalidExperimentError("Existing result has a different recipe hash")
    for artifact in result.artifacts:
        if not artifact.path.is_file() or sha256_file(artifact.path) != artifact.sha256:
            raise InvalidExperimentError(
                f"Existing artifact is missing or changed: {artifact.path}"
            )
    return result.model_copy(update={"reused_existing": True})


def _assert_sources_unchanged(
    registry: SourceRegistry, preview: AnalysisPreview
) -> None:
    for source in preview.sources:
        registry.assert_unchanged(source)
    registry.assert_auxiliary_unchanged(preview.identity_overlay.source)
    for source in preview.auxiliary_sources:
        registry.assert_auxiliary_unchanged(source)


def _artifact_reference(
    temporary_path: Path,
    final_path: Path,
    *,
    artifact_type: str,
    format_name: str,
    name: str,
) -> ArtifactReference:
    digest = sha256_file(temporary_path)
    return ArtifactReference(
        artifact_id=f"sha256-{digest[:16]}",
        artifact_type=artifact_type,
        format=format_name,
        name=name,
        path=final_path,
        size_bytes=temporary_path.stat().st_size,
        sha256=digest,
    )


def _output_filename(name: str, format_name: str) -> str:
    safe = _safe_component(name)
    suffix = f".{format_name}"
    return safe if safe.lower().endswith(suffix) else safe + suffix


def _safe_component(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise InvalidExperimentError(f"Unsafe artifact name: {value!r}")
    return value


def _values_equal(series: pd.Series, expected: Any) -> pd.Series:
    if isinstance(expected, bool):
        return series.map(
            lambda value: str(value).strip().lower() in {"true", "1", "yes"}
        ).eq(expected)
    return series.eq(expected)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _package_version(package: str) -> str | None:
    try:
        return importlib_metadata.version(package)
    except importlib_metadata.PackageNotFoundError:
        return None


def _write_sleep_artifacts(tables, recipe, temporary, run_directory):
    from ethoscopy_mcp.sleep import plot_sleep
    import matplotlib.pyplot as plt
    references = []
    for request in recipe.output_requests:
        filename = _output_filename(request.name, request.format)
        path = temporary / filename
        if request.artifact_type == "table":
            tables[request.dataset].to_csv(path, index=False)
        else:
            figure = plot_sleep(tables, recipe, request.dataset)
            try:
                figure.savefig(path, dpi=300, facecolor="white")
            finally:
                plt.close(figure)
        references.append(_artifact_reference(path, run_directory / filename,
            artifact_type=request.artifact_type, format_name=request.format, name=request.name))
    return tuple(references)
