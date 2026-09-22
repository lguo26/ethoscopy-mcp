"""Shared sleep summaries for Python and MCP, using stored Ethoscopy annotations.

Each valid annotation represents at most one configured sample period. Gaps and
missing values never become sleep. Reviewed endpoints truncate intervals before
aggregation; terminal inactivity is never classified here as a new death event.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.loaders import load_behaviour_pickle
from ethoscopy_mcp.preview import (
    _apply_filters, _frame_ids, _id_set, _validate_mapping_schema,
    _validate_mapping_against_sources, _values_equal,
)
from ethoscopy_mcp.schemas import (
    AnalysisPreview, ArtifactPreview, CohortPreview, IdentityOverlayPreview,
    SleepRecipe, TransformationPreview, ValidationWarning, WarningSeverity,
)


def _require(condition, message):
    if not condition:
        raise InvalidExperimentError(message)


def prepare_sleep(sources, mapping_source, endpoints_source, recipe: SleepRecipe):
    """Validate and align a working copy; return observations and reviewed subjects.

    Endpoint hours use the recipe's OUTPUT time basis. One endpoint is required
    per selected physical individual (any of its analysis segment IDs may be used).
    No source data, annotation, or identity mapping is modified.
    """
    mapping = pd.read_csv(mapping_source.path, dtype={"roi": "string"})
    overlay = recipe.identity_overlay
    mapping[overlay.source_id_column] = mapping[overlay.source_id_column].astype(str)
    mapping[overlay.analysis_id_column] = mapping[overlay.analysis_id_column].astype(str)
    _validate_mapping_schema(mapping, recipe)
    frames = [load_behaviour_pickle(source) for source in sources]
    metadata = pd.concat([frame.meta for frame in frames])
    if "id" in metadata:
        metadata = metadata.set_index("id")
    metadata.index = metadata.index.astype(str)
    _require(not metadata.index.duplicated().any(), "Source metadata IDs overlap")
    _validate_mapping_against_sources(mapping, metadata, _frame_ids(metadata), _id_set(frames), recipe)
    qc = getattr(recipe, "deprivation_qc", None)
    if qc:
        settings = qc.metadata
        schedule_columns = [*settings.range_columns, settings.start_hours_column,
            settings.end_hours_column, settings.zt0_column, settings.date_column,
            settings.time_column, recipe.baseline_alignment.metadata_column]
        aligned_meta = metadata.reindex(mapping[overlay.source_id_column])
        for column in dict.fromkeys(schedule_columns):
            if column in aligned_meta:
                values = aligned_meta[column].reset_index(drop=True)
                if column in mapping:
                    populated = values.notna() & mapping[column].notna()
                    _require((values[populated].astype(str).to_numpy() == mapping.loc[populated, column].astype(str).to_numpy()).all(),
                             f"Identity mapping conflicts with source schedule metadata in {column!r}")
                    mapping[column] = values.combine_first(mapping[column])
                else:
                    mapping[column] = values
    _require(set(recipe.strata_columns).issubset(mapping.columns), "Mapping lacks requested strata columns")
    _require(len(set(recipe.strata_columns)) == len(recipe.strata_columns), "Duplicate strata columns")
    keys = list(overlay.individual_key_columns)
    _require(not mapping[keys].isna().any().any(), "Identity keys must not be missing")
    # JSON encodes the tuple without delimiter collisions; it is the physical fly,
    # not a recording segment, that receives equal weight in group comparisons.
    mapping["subject_id"] = mapping[keys].apply(lambda row: json.dumps([str(x) for x in row]), axis=1)
    fields = list(dict.fromkeys([recipe.group.column, *recipe.strata_columns, *recipe.cohort_filters,
                                 *(r.column for r in getattr(recipe, "exclusions", ())) ]))
    _require(not mapping[fields].isna().any().any(), "Group/filter/strata values must not be missing")
    _require(not (mapping.groupby("subject_id")[fields].nunique() > 1).any().any(),
             "Group, filter or stratum changes within a physical individual")
    for column in fields:
        if column in metadata:
            aligned = metadata.loc[mapping[overlay.source_id_column], column].reset_index(drop=True)
            provided = mapping[column].reset_index(drop=True)
            # CSV can parse booleans/numbers differently, but cannot relabel a
            # known temperature, dose, or treatment from the source metadata.
            if pd.api.types.is_bool_dtype(aligned):
                equal = provided.map(lambda x: str(x).lower()).equals(aligned.map(lambda x: str(x).lower()))
            else:
                equal = provided.equals(aligned) or (provided.astype(str) == aligned.astype(str)).all()
                if not equal:
                    a, b = pd.to_numeric(provided, errors="coerce"), pd.to_numeric(aligned, errors="coerce")
                    equal = a.notna().all() and b.notna().all() and np.array_equal(a, b)
            _require(bool(equal), f"Mapping disagrees with source metadata for {column!r}")
    selected = _apply_filters(mapping, recipe.cohort_filters).copy()
    selected["group"] = None
    for level in recipe.group.levels:
        selected.loc[_values_equal(selected[recipe.group.column], level.value), "group"] = level.label
    selected = selected.loc[selected["group"].notna()].copy()
    _require(not selected.empty, "Filters and group levels select no individuals")
    by_original = selected.set_index(overlay.source_id_column)
    chunks = []
    for frame in frames:
        data = pd.DataFrame(frame)
        if "id" in data:
            data = data.set_index("id")
        data.index = data.index.astype(str)
        _require({"t", recipe.sleep.asleep_column}.issubset(data.columns), "Source lacks time or saved sleep annotations")
        columns = ["t", recipe.sleep.asleep_column]
        if getattr(recipe, "endpoint_policy", None) == "curate":
            _require(recipe.curation.movement_column in data, "Death curation requires its movement column")
            columns.append(recipe.curation.movement_column)
        data = data.loc[data.index.isin(by_original.index), list(dict.fromkeys(columns))].copy()
        if data.empty:
            continue
        baseline = recipe.baseline_alignment.metadata_column
        _require(baseline in metadata, f"Source metadata lacks baseline column {baseline!r}")
        offsets = pd.to_numeric(metadata[baseline], errors="coerce")
        data["t"] = pd.to_numeric(data["t"], errors="coerce") + data.index.map(offsets) * recipe.baseline_alignment.day_length_hours * 3600 - recipe.time_alignment.subtract_hours * 3600
        _require(np.isfinite(data["t"]).all(), "Non-finite timestamps or baseline offsets")
        values = data[recipe.sleep.asleep_column]
        _require(values.dropna().isin([True, False, 0, 1]).all(), "Sleep annotations must be boolean/0/1 or missing")
        data["asleep"] = pd.to_numeric(values, errors="raise")
        data["subject_id"] = data.index.map(by_original["subject_id"])
        retain = ["subject_id", "t", "asleep"]
        if getattr(recipe, "endpoint_policy", None) == "curate":
            retain.append(recipe.curation.movement_column)
        chunks.append(data[list(dict.fromkeys(retain))].reset_index(drop=True))
    _require(bool(chunks), "Selected cohort contains no observations")
    observations = pd.concat(chunks, ignore_index=True).sort_values(["subject_id", "t"])
    _require(not observations.duplicated(["subject_id", "t"]).any(), "Overlapping timestamps within a physical individual")
    if endpoints_source is None:
        # This explicit notebook mode makes no death/censoring assessment.
        # Do not label these inferred observation limits as reviewed survival.
        subjects = selected.drop_duplicates("subject_id").set_index("subject_id")
        extents = observations.groupby("subject_id")["t"].max()
        subjects["end_hours"] = extents / 3600
        subjects["event"] = pd.NA
        subjects["reason"] = "Untrimmed notebook workflow; death status not assessed"
        keep = list(dict.fromkeys(["group", *recipe.strata_columns, "end_hours", "event", "reason"]))
        return observations, subjects[keep], mapping
    endpoints = pd.read_csv(endpoints_source.path, dtype={"analysis_id": str})
    _require({"analysis_id", "end_hours", "event", "reason"}.issubset(endpoints),
             "Endpoint CSV requires analysis_id, end_hours, event (0/1), reason")
    all_ids = set(mapping[overlay.analysis_id_column])
    _require(set(endpoints["analysis_id"]).issubset(all_ids), "Endpoint CSV contains unknown analysis IDs")
    segment_to_subject = mapping.set_index(overlay.analysis_id_column)["subject_id"]
    endpoints["subject_id"] = endpoints["analysis_id"].map(segment_to_subject)
    _require(not endpoints["subject_id"].duplicated().any(), "Endpoint CSV has duplicate physical individuals")
    subjects = selected.drop_duplicates("subject_id").set_index("subject_id")
    endpoints = endpoints.loc[endpoints["subject_id"].isin(subjects.index)].set_index("subject_id")
    _require(set(endpoints.index) == set(subjects.index), "Every selected individual needs a reviewed endpoint")
    for column in ("end_hours", "event"):
        endpoints[column] = pd.to_numeric(endpoints[column], errors="coerce")
    _require(np.isfinite(endpoints["end_hours"]).all(), "Endpoint times must be finite")
    _require(endpoints["event"].isin([0, 1]).all(), "Endpoint event must be 0 (censored) or 1 (dead)")
    _require(endpoints["reason"].fillna("").str.strip().ne("").all(), "Each endpoint needs a review reason")
    subjects = subjects.join(endpoints[["end_hours", "event", "reason"]])
    extents = observations.groupby("subject_id")["t"].agg(["min", "max"])
    _require(set(extents.index) == set(subjects.index), "Selected metadata includes individuals without observations")
    extents = extents.reindex(subjects.index)
    end_seconds = subjects["end_hours"] * 3600
    _require(((end_seconds >= extents["min"]) & (end_seconds <= extents["max"] + 1e-6)).all(),
             "Reviewed endpoint lies outside the recorded time range")
    # A censored endpoint is the recording end. Earlier study cutoffs belong in
    # sleep.end_hours, so accidental censor/death confusion is rejected.
    censored = subjects["event"].eq(0)
    _require(np.isclose(end_seconds[censored], extents["max"][censored], atol=1e-6, rtol=0).all(),
             "Censored endpoints must match the recording end")
    # Standardized output columns avoid exposing CSV implementation names.
    keep = list(dict.fromkeys(["group", *recipe.strata_columns, "end_hours", "event", "reason"]))
    return observations, subjects[keep], mapping


def summarize_sleep(observations, subjects, recipe: SleepRecipe):
    """Compute duration-weighted per-fly bins and equal-fly group summaries."""
    settings = recipe.sleep
    width = settings.bin_minutes * 60
    data = observations.copy()
    next_t = data.groupby("subject_id")["t"].shift(-1)
    interval_end = np.minimum(data["t"] + settings.sample_period_seconds, next_t.fillna(np.inf))
    interval_end = np.minimum(interval_end, data["subject_id"].map(subjects["end_hours"]) * 3600)
    if settings.end_hours is not None:
        interval_end = np.minimum(interval_end, settings.end_hours * 3600)
    start = np.maximum(data["t"].to_numpy(), settings.start_hours * 3600)
    end = interval_end.to_numpy()
    valid = (end > start) & data["asleep"].notna().to_numpy()
    ids = data["subject_id"].to_numpy()[valid]
    asleep = data["asleep"].to_numpy(dtype=float)[valid]
    start, end = start[valid], end[valid]
    _require(len(start) > 0, "No observed pre-endpoint sleep intervals in the selected window")
    # Split intervals crossing bin boundaries, without carrying values through
    # gaps longer than the explicitly configured sampling period.
    pieces = []
    while len(start):
        bins = np.floor(start / width).astype(np.int64)
        stop = np.minimum(end, (bins + 1) * width)
        duration = stop - start
        pieces.append(pd.DataFrame({"subject_id": ids, "bin": bins,
                                    "observed_seconds": duration, "sleep_seconds": duration * asleep}))
        more = end > stop
        start, end, ids, asleep = stop[more], end[more], ids[more], asleep[more]
    per_bin = pd.concat(pieces).groupby(["subject_id", "bin"], as_index=False)[["observed_seconds", "sleep_seconds"]].sum()
    per_bin["sleep_fraction"] = per_bin["sleep_seconds"] / per_bin["observed_seconds"]
    per_bin["time_hours"] = per_bin["bin"] * width / 3600
    per_bin["coverage_fraction"] = per_bin["observed_seconds"] / width
    group_columns = list(dict.fromkeys(["group", *recipe.strata_columns]))
    per_bin = per_bin.merge(subjects[group_columns], left_on="subject_id", right_index=True, validate="many_to_one")
    individuals = per_bin.groupby("subject_id")[["observed_seconds", "sleep_seconds"]].sum().reindex(subjects.index).fillna(0).join(subjects)
    individuals["sleep_fraction"] = individuals["sleep_seconds"].div(individuals["observed_seconds"].replace(0, np.nan))
    individuals["observed_minutes"] = individuals.pop("observed_seconds") / 60
    individuals["sleep_minutes"] = individuals.pop("sleep_seconds") / 60
    individuals = individuals.reset_index()
    timecourse = per_bin.groupby([*group_columns, "time_hours"], dropna=False).agg(
        mean_sleep_fraction=("sleep_fraction", "mean"), sem_sleep_fraction=("sleep_fraction", "sem"),
        animals=("subject_id", "nunique"), observed_seconds=("observed_seconds", "sum"),
        mean_coverage_fraction=("coverage_fraction", "mean")).reset_index()
    comparison = individuals.groupby(group_columns, dropna=False).agg(
        animals=("subject_id", "nunique"), animals_with_observations=("sleep_fraction", "count"),
        mean_sleep_fraction=("sleep_fraction", "mean"), sem_sleep_fraction=("sleep_fraction", "sem"),
        mean_observed_minutes=("observed_minutes", "mean"), mean_sleep_minutes=("sleep_minutes", "mean")).reset_index()
    return {"primary": per_bin, "timecourse": timecourse, "individuals": individuals, "comparison": comparison}


def plot_sleep(tables, recipe: SleepRecipe, dataset: str):
    """Plot the same exported numbers; labels retain every requested stratum."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    fields = list(dict.fromkeys(["group", *recipe.strata_columns]))
    def label(values):
        if not isinstance(values, tuple):
            values = (values,)
        return ", ".join(str(v) if k == "group" else f"{k}={v}" for k, v in zip(fields, values))
    if dataset in {"primary", "timecourse"}:
        for values, rows in tables["timecourse"].groupby(fields, sort=False, dropna=False):
            ax.plot(rows["time_hours"], rows["mean_sleep_fraction"], label=label(values))
        ax.set_xlabel(f"{recipe.time_alignment.output_basis} (hours)")
        ax.legend(frameon=False, fontsize=9)
        ax.set_title("Sleep time course (mean across observed individuals)")
    else:
        rows = tables["individuals"]
        for index, (values, subset) in enumerate(rows.groupby(fields, sort=False, dropna=False)):
            y = subset["sleep_fraction"].dropna().to_numpy()
            ax.scatter(np.full(len(y), index), y, alpha=.5)
            if len(y):
                ax.plot([index - .2, index + .2], [np.mean(y)] * 2, color="black")
        labels = [label(values) for values, _ in rows.groupby(fields, sort=False, dropna=False)]
        ax.set_xticks(range(len(labels)), labels, rotation=25, ha="right")
        ax.set_title("Sleep comparison (each point is one individual)")
    ax.set_ylabel("Fraction of observed time asleep")
    ax.set_ylim(0, 1)
    fig.tight_layout()
    return fig


def preview_sleep(registry, inspection, recipe: SleepRecipe):
    _require(recipe.experiment_id == inspection.experiment_id, "Recipe experiment_id does not match manifest")
    mapping_source = registry.register_auxiliary(recipe.identity_overlay.mapping_path)
    endpoints_source = registry.register_auxiliary(recipe.endpoints_path)
    observations, subjects, mapping = prepare_sleep(inspection.sources, mapping_source, endpoints_source, recipe)
    tables = summarize_sleep(observations, subjects, recipe)
    names = set()
    from ethoscopy_mcp.execution import _output_filename
    for request in recipe.output_requests:
        _require(request.dataset in {"primary", "timecourse", "individuals", "comparison"} and request.group_label is None, "Unsupported interval sleep dataset/group_label")
        _require((request.artifact_type == "table" and request.format == "csv") or
                 (request.artifact_type == "plot" and request.format in {"png", "svg"}), "Unsupported sleep output format")
        filename = _output_filename(request.name, request.format)
        _require(filename not in names, "Duplicate output filename")
        names.add(filename)
    warnings = list(inspection.warnings)
    warnings.extend(ValidationWarning(code="scientific_context", message=x) for x in recipe.context_warnings)
    warnings.append(ValidationWarning(code="reviewed_sleep_endpoints", severity=WarningSeverity.INFO,
        message="Uses stored sleep annotations and reviewed endpoints; no new death inference. Missing samples and post-endpoint data are excluded. Group means weight physical individuals equally; these are descriptive comparisons, not significance tests."))
    if tables["individuals"]["sleep_fraction"].isna().any():
        warnings.append(ValidationWarning(code="no_sleep_observations", message="Some selected individuals have no usable pre-endpoint sleep observations; their summaries remain missing."))
    # Warn about possible pooling when users explicitly remove default strata.
    for column in ("temperature", "OD600"):
        if column in mapping and column not in recipe.strata_columns and column != recipe.group.column:
            selected_ids = set(subjects.index)
            selected = mapping.loc[mapping["subject_id"].isin(selected_ids)]
            if selected[column].nunique() > 1:
                warnings.append(ValidationWarning(code="pooled_strata", message=f"Multiple {column} values are pooled; include it in strata_columns to keep them separate."))
    cohorts = tuple(CohortPreview(label=level.label,
        metadata_individuals=int(subjects["group"].eq(level.label).sum()),
        individuals_with_data=int(subjects["group"].eq(level.label).sum()),
        data_segments=int(mapping.loc[mapping["subject_id"].isin(subjects.index[subjects["group"].eq(level.label)])].shape[0]))
        for level in recipe.group.levels)
    if any(x.individuals_with_data == 0 for x in cohorts):
        warnings.append(ValidationWarning(code="empty_analysis_group", message="A requested group is empty", severity=WarningSeverity.ERROR))
    payload = {"implementation": "sleep-v1", "recipe": recipe.model_dump(mode="json"),
               "sources": [s.sha256 for s in inspection.sources], "mapping": mapping_source.sha256, "endpoints": endpoints_source.sha256}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    for source in inspection.sources:
        registry.assert_unchanged(source)
    for source in (mapping_source, endpoints_source):
        registry.assert_auxiliary_unchanged(source)
    overlay = recipe.identity_overlay
    return AnalysisPreview(recipe_id=recipe.recipe_id, experiment_id=recipe.experiment_id,
        analysis_type="sleep", recipe_hash=digest,
        ready_to_approve=not any(w.severity == WarningSeverity.ERROR for w in warnings), sources=inspection.sources,
        identity_overlay=IdentityOverlayPreview(source=mapping_source, mapping_rows=len(mapping),
            mapped_individuals=mapping["subject_id"].nunique(),
            changed_segment_ids=int((mapping[overlay.source_id_column] != mapping[overlay.analysis_id_column]).sum()),
            recording_dates=tuple(sorted(mapping[overlay.date_column].astype(str).unique())),
            individual_key_columns=overlay.individual_key_columns, consistency_columns=overlay.consistency_columns),
        auxiliary_sources=(endpoints_source,), cohort_filters=recipe.cohort_filters, cohorts=cohorts,
        baseline_alignment=recipe.baseline_alignment, time_alignment=recipe.time_alignment, sleep=recipe.sleep,
        transformations=(TransformationPreview(operation="sleep_summary", description="Apply baseline once, align time, preserve physical identity and strata, truncate at reviewed endpoints, and summarize only observed sleep intervals."),),
        expected_artifacts=tuple(ArtifactPreview(artifact_type=r.artifact_type, format=r.format, name=r.name) for r in recipe.output_requests),
        assumptions=recipe.assumptions, warnings=tuple(warnings))
