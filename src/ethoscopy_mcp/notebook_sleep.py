"""Direct Ethoscopy sleep workflow mirroring the reference notebook's public API."""
from __future__ import annotations

import hashlib
import json
from importlib.metadata import version

import ethoscopy as etho
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from ethoscopy_mcp.schemas import (
    AnalysisPreview, ArtifactPreview, CohortPreview, IdentityOverlayPreview,
    NotebookSleepRecipe, TransformationPreview, ValidationWarning, WarningSeverity,
    ResolvedDeprivationWindow,
)
from ethoscopy_mcp.sleep import _require, prepare_sleep


def prepare_notebook_sleep(sources, mapping_source, endpoints_source, recipe, schedule_source=None):
    observations, subjects, mapping = prepare_sleep(sources, mapping_source, endpoints_source, recipe)
    if recipe.endpoint_policy == "reviewed":
        observations = observations.loc[
            observations.t < observations.subject_id.map(subjects.end_hours) * 3600
        ].copy()
    metadata = subjects.copy()
    fields = ["group", *recipe.strata_columns]
    metadata["comparison_group"] = metadata.apply(
        lambda r: str(r["group"]) + "".join(f" | {k}={r[k]}" for k in recipe.strata_columns), axis=1)
    _require(metadata[fields].drop_duplicates().shape[0] == metadata.comparison_group.nunique(),
             "Comparison labels collide; change group labels")
    extra = mapping.drop_duplicates("subject_id").set_index("subject_id")
    for column in extra.columns:
        if column not in metadata:
            metadata[column] = extra[column]
    metadata.index.name = "id"
    working = etho.behavpy(observations.rename(columns={"subject_id": "id"}).set_index("id"),
                          metadata, check=True)
    working, audit = apply_notebook_qc(working, recipe, mapping, schedule_source)
    subjects = subjects.loc[subjects.index.isin(working.index)].copy()
    if recipe.endpoint_policy == "curate":
        subjects["end_hours"] = working.groupby(level=0).t.max() / 3600
        subjects["reason"] = "Ethoscopy curate_dead_animals; algorithmic truncation, not a reviewed death"
    labels = []
    for level in recipe.group.levels:
        labels.extend(working.meta.loc[working.meta.group.eq(level.label), "comparison_group"].drop_duplicates().tolist())
    return working, subjects, mapping, labels, audit


def _window(working, window):
    # Public API uses >= start and < end, exactly as in the notebook.
    return working.t_filter(start_time=window.start_hours,
                            end_time=window.end_hours if window.end_hours is not None else np.inf)


def _quantification_means(working, recipe):
    selected = _window(working, recipe.quantification_window)
    means = pd.DataFrame(selected).groupby(level=0).asleep.mean().rename("asleep_mean").to_frame()
    return means.join(working.meta[["comparison_group"]])


def statistical_comparison(quantified, recipe):
    settings = recipe.comparison
    if settings is None:
        return pd.DataFrame()
    left, right = settings.group_labels
    samples = [quantified.loc[quantified.comparison_group.eq(label), "asleep_mean"].dropna().to_numpy()
               for label in (left, right)]
    _require(all(len(x) for x in samples), "Statistical groups need observed per-fly sleep means")
    pooled = np.concatenate(samples)
    ties = len(np.unique(pooled)) < len(pooled)
    result = mannwhitneyu(*samples, alternative=settings.alternative, method=settings.method, nan_policy="omit")
    effective = settings.method
    if effective == "auto":
        effective = "exact" if min(map(len, samples)) <= 8 and not ties else "asymptotic"
    return pd.DataFrame([{
        "group_a": left, "group_b": right, "n_a": len(samples[0]), "n_b": len(samples[1]),
        "statistic_U": float(result.statistic), "p_value": float(result.pvalue),
        "test": "mannwhitneyu", "alternative": settings.alternative,
        "requested_method": settings.method, "effective_method": effective, "ties_present": ties,
        "start_hours": recipe.quantification_window.start_hours,
        "end_hours": recipe.quantification_window.end_hours,
        "pvalue_adjustment": "none; one requested comparison",
        "note": "Exact method does not correct for ties" if ties and effective == "exact" else "",
    }])


def preview_notebook_sleep(registry, inspection, recipe: NotebookSleepRecipe):
    _require(recipe.experiment_id == inspection.experiment_id, "Recipe and manifest experiment IDs differ")
    mapping_source = registry.register_auxiliary(recipe.identity_overlay.mapping_path)
    endpoints_source = registry.register_auxiliary(recipe.endpoints_path) if recipe.endpoints_path else None
    schedule_path = recipe.deprivation_qc.metadata.path if recipe.deprivation_qc else None
    schedule_source = registry.register_auxiliary(schedule_path) if schedule_path else None
    working, subjects, mapping, labels, audit = prepare_notebook_sleep(inspection.sources, mapping_source, endpoints_source, recipe, schedule_source)
    warnings = list(inspection.warnings)
    if recipe.deprivation_qc or recipe.exclusions or recipe.endpoint_policy == "curate" or audit.excluded.any():
        warnings.append(ValidationWarning(code="sleep_qc_applied", severity=WarningSeverity.INFO,
            message=f"Exclusion audit: {len(audit)} selected flies, {int(audit.excluded.sum())} excluded, {int((~audit.excluded).sum())} retained. QC targets only the configured deprivation group; controls are not screened by the deprivation threshold."))
    warnings.extend(ValidationWarning(code="scientific_context", message=x) for x in recipe.context_warnings)
    if recipe.endpoint_policy == "untrimmed":
        warnings.append(ValidationWarning(code="untrimmed_notebook_sleep",
            message="Explicit notebook workflow: no death trimming or censor/death assessment. Terminal inactivity may remain in stored sleep annotations."))
    quantified = _quantification_means(working, recipe)
    _require(quantified.asleep_mean.notna().any(), "No sleep observations in quantification window")
    expected = set(labels)
    _require(set(quantified.loc[quantified.asleep_mean.notna(), "comparison_group"]) == expected,
             "Every comparison group needs observations in the quantification window")
    requested_labels = {level.label for level in recipe.group.levels}
    _require(set(subjects.group) == requested_labels, "A requested group has no individuals")
    if recipe.comparison:
        _require(set(recipe.comparison.group_labels).issubset(expected), "Unknown statistical group labels")
        stats = statistical_comparison(quantified, recipe)
        if bool(stats.iloc[0].ties_present) and recipe.comparison.method == "exact":
            warnings.append(ValidationWarning(code="exact_test_with_ties", message="The requested exact Mann–Whitney method matches the notebook but does not correct for ties. Use auto/asymptotic for a tie-corrected test."))
    for column in ("temperature", "OD600"):
        if column in mapping and column not in recipe.strata_columns and column != recipe.group.column:
            if mapping.loc[mapping.subject_id.isin(subjects.index), column].nunique() > 1:
                severity = WarningSeverity.ERROR if recipe.comparison else WarningSeverity.WARNING
                warnings.append(ValidationWarning(code="pooled_strata", severity=severity,
                    message=f"Multiple {column} values would be pooled; use filters, strata or explicit composite groups."))
    # Ethoscopy's light bars are drawn from time zero. Avoid silently displaying
    # ZT light bars on an injection-relative axis with a shifted origin.
    _require(recipe.time_alignment.subtract_hours % recipe.day_length_hours == 0,
             "Direct Ethoscopy sleep plots require a ZT-aligned origin for light bars; use interval sleep mode for shifted injection times")
    names = set()
    from ethoscopy_mcp.execution import _output_filename
    for request in recipe.output_requests:
        _require(request.format in ({"csv"} if request.artifact_type == "table" else {"png", "svg", "pdf"}), "Unsupported notebook sleep format")
        _require(not (request.dataset == "statistics" and (recipe.comparison is None or request.artifact_type != "table")),
                 "Statistics output requires a requested test and CSV table")
        _require(request.dataset != "exclusions" or request.artifact_type == "table", "Exclusions output must be a CSV table")
        _require(request.dataset != "heatmap" or (request.artifact_type == "plot" and request.group_label in labels),
                 "Heatmap output requires a plot and an explicit valid group_label")
        _require(request.dataset == "heatmap" or request.group_label is None, "group_label is only used for heatmaps")
        if request.dataset in {"timecourse", "heatmap"}:
            selected = _window(working, recipe.profile_window)
            present = set(selected.index)
            needed = {request.group_label} if request.dataset == "heatmap" else expected
            _require(set(working.meta.loc[working.meta.index.isin(present), "comparison_group"]).issuperset(needed),
                     "Requested profile groups have no observations in profile window")
        name = _output_filename(request.name, request.format)
        _require(name not in names, "Duplicate output filename")
        _require(name != "exclusion-audit.csv", "exclusion-audit.csv is reserved for the automatic QC audit")
        if request.dataset == "heatmap":
            _require(recipe.day_length_hours == 24, "Ethoscopy heatmap supports a 24-hour light cycle")
        names.add(name)
    payload = {"implementation": "notebook-sleep-v2-metadata-windows", "recipe": recipe.model_dump(mode="json"),
               "ethoscopy": version("ethoscopy"), "scipy": version("scipy"),
               "sources": [s.sha256 for s in inspection.sources], "mapping": mapping_source.sha256,
               "endpoints": endpoints_source.sha256 if endpoints_source else None,
               "schedule": schedule_source.sha256 if schedule_source else None}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    for source in inspection.sources:
        registry.assert_unchanged(source)
    for source in [mapping_source, *([endpoints_source] if endpoints_source else []), *([schedule_source] if schedule_source else [])]:
        registry.assert_auxiliary_unchanged(source)
    overlay = recipe.identity_overlay
    cohorts = tuple(CohortPreview(label=level.label,
        metadata_individuals=int(subjects.group.eq(level.label).sum()),
        individuals_with_data=int(subjects.group.eq(level.label).sum()),
        data_segments=int(mapping.subject_id.isin(subjects.index[subjects.group.eq(level.label)]).sum()))
        for level in recipe.group.levels)
    return AnalysisPreview(recipe_id=recipe.recipe_id, experiment_id=recipe.experiment_id,
        analysis_type=recipe.analysis_type, recipe_hash=digest,
        ready_to_approve=not any(w.severity == WarningSeverity.ERROR for w in warnings), sources=inspection.sources,
        identity_overlay=IdentityOverlayPreview(source=mapping_source, mapping_rows=len(mapping),
            mapped_individuals=mapping.subject_id.nunique(),
            changed_segment_ids=int((mapping[overlay.source_id_column] != mapping[overlay.analysis_id_column]).sum()),
            recording_dates=tuple(sorted(mapping[overlay.date_column].astype(str).unique())),
            individual_key_columns=overlay.individual_key_columns, consistency_columns=overlay.consistency_columns),
        auxiliary_sources=tuple(s for s in (endpoints_source, schedule_source) if s is not None),
        deprivation_windows=tuple(ResolvedDeprivationWindow(start_hours=float(start), end_hours=float(end), source=source, animals=len(rows))
            for (start,end,source), rows in audit.dropna(subset=["qc_start_hours", "qc_end_hours"]).groupby(["qc_start_hours", "qc_end_hours", "qc_window_source"])),
        cohort_filters=recipe.cohort_filters, cohorts=cohorts,
        baseline_alignment=recipe.baseline_alignment, time_alignment=recipe.time_alignment,
        transformations=(TransformationPreview(operation="ethoscopy_notebook", description=(
            f"Baseline once; endpoint policy={recipe.endpoint_policy}; "
            f"profile window={recipe.profile_window.model_dump()}; quantify window={recipe.quantification_window.model_dump()}; "
            f"call heatmap/plot_overtime(avg_window={recipe.avg_window_minutes})/plot_quantify; "
            f"statistics={recipe.comparison.model_dump() if recipe.comparison else 'none'}; "
            f"deprivation_qc={recipe.deprivation_qc.model_dump() if recipe.deprivation_qc else 'none'}; "
            f"exclusions={[r.model_dump() for r in recipe.exclusions]}; curation={recipe.curation.model_dump() if recipe.endpoint_policy == 'curate' else 'none'}.")),),
        expected_artifacts=tuple(ArtifactPreview(artifact_type=r.artifact_type, format=r.format, name=r.name) for r in recipe.output_requests),
        assumptions=recipe.assumptions, warnings=tuple(warnings))


def write_notebook_artifacts(preview, recipe, temporary, run_directory):
    import matplotlib.pyplot as plt
    from ethoscopy_mcp.execution import _artifact_reference, _output_filename
    def auxiliary(path):
        return next((source for source in preview.auxiliary_sources if path and source.path == path.resolve()), None)
    working, subjects, _, labels, audit = prepare_notebook_sleep(preview.sources, preview.identity_overlay.source,
        auxiliary(recipe.endpoints_path), recipe,
        auxiliary(recipe.deprivation_qc.metadata.path) if recipe.deprivation_qc else None)
    common = dict(variable="asleep", facet_col="comparison_group", facet_arg=labels,
                  facet_labels=labels, title=recipe.title, grids=True, figsize=(12.8, 7.2))
    figures = {}
    tables = {"exclusions": audit}
    references = []
    try:
        # Public method returns the per-fly data used for the optional test.
        quantified_figure, quantified = _window(working, recipe.quantification_window).plot_quantify(**common)
        figures["comparison"] = quantified_figure
        quantified.index.name = "subject_id"
        quantified = quantified.join(subjects.drop(columns="group"), how="left")
        tables["primary"] = tables["individuals"] = quantified.reset_index()
        tables["comparison"] = quantified.groupby("comparison_group", observed=True).asleep_mean.agg(["count", "mean", "sem"]).reset_index()
        if recipe.comparison:
            tables["statistics"] = statistical_comparison(quantified, recipe)
        for request in recipe.output_requests:
            dataset = request.dataset
            if dataset == "timecourse" and dataset not in figures:
                figures[dataset] = _window(working, recipe.profile_window).plot_overtime(**common,
                    avg_window=recipe.avg_window_minutes, day_length=recipe.day_length_hours, lights_off=recipe.lights_off_hours)
                rows = []
                for line in figures[dataset].axes[0].lines:
                    if line.get_label() in labels:
                        x, y = line.get_data()
                        rows.append(pd.DataFrame({"comparison_group": line.get_label(), "time_hours": x, "mean_sleep": y}))
                _require(bool(rows), "Ethoscopy returned no profile lines")
                tables[dataset] = pd.concat(rows, ignore_index=True)
            name = _output_filename(request.name, request.format)
            path = temporary / name
            if request.artifact_type == "table":
                tables[dataset].to_csv(path, index=False)
            else:
                if dataset == "heatmap":
                    figure = _window(working, recipe.profile_window).xmv("comparison_group", request.group_label).heatmap(
                        variable="asleep", title=f"{recipe.title}: {request.group_label}", lights_off=recipe.lights_off_hours,
                        figsize=(12.8, 7.2))
                    try:
                        figure.savefig(path, dpi=300, bbox_inches="tight")
                    finally:
                        plt.close(figure)
                else:
                    figure = figures["comparison" if dataset in {"primary", "individuals", "comparison"} else dataset]
                    figure.savefig(path, dpi=300, bbox_inches="tight")
            references.append(_artifact_reference(path, run_directory / name,
                artifact_type=request.artifact_type, format_name=request.format, name=request.name))
        if (recipe.deprivation_qc or recipe.exclusions or recipe.endpoint_policy == "curate" or audit.excluded.any()) and not any(r.dataset == "exclusions" for r in recipe.output_requests):
            audit_path = temporary / "exclusion-audit.csv"
            audit.to_csv(audit_path, index=False)
            references.append(_artifact_reference(audit_path, run_directory / audit_path.name,
                artifact_type="table", format_name="csv", name="exclusion-audit"))
    finally:
        for figure in figures.values():
            plt.close(figure)
    return tuple(references)


def apply_notebook_qc(working, recipe, mapping=None, schedule_source=None):
    """Apply the notebook's explicit sequence and preserve an audit of every fly."""
    audit = working.meta[["group", "comparison_group"]].copy()
    audit["initial_rows"] = working.groupby(level=0).size().reindex(audit.index).fillna(0).astype(int)
    audit["excluded"] = False
    audit["exclusion_reason"] = ""
    audit["qc_sleep_fraction"] = np.nan
    audit["qc_window_seconds_observed_span"] = np.nan
    audit["qc_start_hours"] = np.nan
    audit["qc_end_hours"] = np.nan
    audit["qc_window_source"] = ""

    def exclude(frame, ids, reason):
        ids = list(ids)
        if not ids:
            return frame
        audit.loc[ids, "excluded"] = True
        audit.loc[ids, "exclusion_reason"] = reason
        remaining = frame.loc[~frame.index.isin(ids)].copy()
        _require(not remaining.empty, "Exclusion rules remove the entire cohort")
        return etho.behavpy(pd.DataFrame(remaining), frame.meta.loc[frame.meta.index.isin(remaining.index)].copy(), check=True)

    def manual(frame, stage):
        for rule in recipe.exclusions:
            if rule.stage != stage:
                continue
            _require(rule.column in frame.meta, f"Exclusion metadata lacks {rule.column!r}")
            ids = frame.meta.index[frame.meta[rule.column].isin(rule.values)]
            frame = exclude(frame, ids, f"{stage}: {rule.column} in {list(rule.values)}; {rule.reason}")
        return frame

    working = exclude(working, audit.index[audit.initial_rows.eq(0)], "Metadata present but recording observations missing")
    working = manual(working, "before_qc")
    qc = recipe.deprivation_qc
    if qc:
        _require(qc.target_group_label in set(working.meta.group), "QC target group is absent")
        from ethoscopy_mcp.deprivation import resolve_windows
        target_ids = working.meta.index[working.meta.group.eq(qc.target_group_label)]
        if mapping is None:
            mapping = working.meta.copy()
            mapping["subject_id"] = mapping.index
        resolved = resolve_windows(mapping, target_ids, recipe, schedule_source)
        audit.loc[resolved.index, ["qc_start_hours", "qc_end_hours", "qc_window_source"]] = resolved
        for (start, end), schedule_rows in resolved.groupby(["qc_start_hours", "qc_end_hours"]):
            target = working.xmv("id", schedule_rows.index.tolist())
            window = target.t_filter(start_time=start, end_time=end)
            valid = window.groupby(level=0).asleep.count()
            span = window.groupby(level=0).t.agg(lambda x: x.max() - x.min())
            insufficient = target.meta.index.difference(valid.index[(valid >= 2) & (span > 0)])
            working = exclude(working, insufficient, "No usable deprivation-window evidence (fewer than two annotated timestamps)")
            usable_ids = target.meta.index.difference(insufficient)
            if len(usable_ids):
                target = working.xmv("id", usable_ids.tolist())
                result = target.remove_sleep_deprived(start_time=start, end_time=end,
                    remove=False, sleep_column="asleep", t_column="t")
                audit.loc[result.index, "qc_sleep_fraction"] = result["Percent Asleep"]
                audit.loc[result.index, "qc_window_seconds_observed_span"] = result["time(s)"]
                _require(np.isfinite(result["Percent Asleep"]).all(), "Ethoscopy returned non-finite deprivation QC fractions")
                remove = result.index[result["Percent Asleep"] > qc.maximum_sleep_fraction]
                working = exclude(working, remove, f"Deprivation QC: Percent Asleep > {qc.maximum_sleep_fraction:g} in [{start:g}, {end:g}) hours")
    if recipe.endpoint_policy == "curate":
        settings = recipe.curation
        before_ids = set(working.index)
        working = working.curate_dead_animals(mov_column=settings.movement_column,
            time_window=settings.time_window_hours, prop_immobile=settings.proportion_immobile,
            resolution=settings.resolution)
        lost = before_ids - set(working.index)
        if lost:
            audit.loc[list(lost), "excluded"] = True
            audit.loc[list(lost), "exclusion_reason"] = "No observations remain after curate_dead_animals"
        _require(not working.empty, "No data remain after dead-animal curation")
    working = manual(working, "after_curate")
    working = etho.behavpy(pd.DataFrame(working), working.meta.loc[working.meta.index.isin(working.index)].copy(), check=True)
    audit["retained_rows"] = working.groupby(level=0).size().reindex(audit.index).fillna(0).astype(int)
    audit["retained_end_hours"] = working.groupby(level=0).t.max().reindex(audit.index) / 3600
    audit.index.name = "subject_id"
    return working, audit.reset_index()
