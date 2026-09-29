"""Metadata reconciliation and whole-animal exclusions on immutable working copies."""
from __future__ import annotations

import math
import numbers

import pandas as pd

from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.schemas import ExclusionPreview, MetadataConflict


SCIENTIFIC_COLUMNS = {
    "temperature", "tempreture", "injection_time", "sex", "infection", "microbe",
    "food", "OD600", "species", "sleep_deprived", "incubator", "baseline", "date",
}


def normalized(value):
    """CSV-safe equality without equating booleans to numeric metadata."""
    if pd.isna(value):
        return ("missing", "")
    if isinstance(value, bool) or str(value).lower() in {"true", "false"}:
        return ("bool", str(value).lower())
    try:
        number = float(value)
        if math.isfinite(number):
            return ("number", number)
    except (ValueError, TypeError):
        pass
    return ("text", str(value))


def prepare_metadata(metadata, mapping, recipe, external=None):
    """Return corrected copies, unresolved conflicts, and a correction audit table.

    External CSVs must identify exactly the source metadata rows; joins use raw
    recording identities, before canonical transfer remapping or corrections.
    """
    metadata = metadata.copy(deep=True)
    if "id" in metadata:
        metadata = metadata.set_index("id", drop=True)
    metadata.index = metadata.index.astype(str)
    mapping = mapping.copy(deep=True)
    id_column = recipe.identity_overlay.source_id_column
    if id_column not in mapping:
        raise InvalidExperimentError(f"Identity overlay is missing source ID column {id_column!r}")
    mapping.index = mapping[id_column].astype(str)
    if not metadata.index.is_unique or not mapping.index.is_unique:
        raise InvalidExperimentError("Metadata and mapping IDs must be unique")
    if set(metadata.index) != set(mapping.index):
        raise InvalidExperimentError("Identity overlay does not match metadata IDs")
    mapping = mapping.loc[metadata.index]
    aligned = None
    if external is not None:
        keys = list(recipe.metadata_csv.key_columns)
        left = metadata.copy()
        if id_column not in left:
            left[id_column] = left.index
        if not set(keys) <= set(left) or not set(keys) <= set(external):
            raise InvalidExperimentError("Metadata CSV join columns must exist in source and CSV")
        def keyed(frame):
            if frame[keys].isna().any().any():
                raise InvalidExperimentError("Metadata CSV join keys cannot be missing")
            result = pd.Series([tuple(normalized(v) for v in row)
                                for row in frame[keys].itertuples(index=False, name=None)])
            if result.duplicated().any():
                raise InvalidExperimentError("Metadata CSV join keys must uniquely identify recording segments")
            return result.tolist()
        source_keys, csv_keys = keyed(left), keyed(external)
        if set(source_keys) != set(csv_keys):
            raise InvalidExperimentError("Metadata CSV must cover exactly the source recording segments")
        positions = {key: i for i, key in enumerate(csv_keys)}
        aligned = external.iloc[[positions[key] for key in source_keys]].copy()
        aligned.index = metadata.index

    forbidden = {"id", "machine_name", "region_id", "date", "canonical_machine", "roi",
                 recipe.identity_overlay.source_id_column, recipe.identity_overlay.analysis_id_column,
                 recipe.identity_overlay.date_column, *recipe.identity_overlay.individual_key_columns}
    if recipe.metadata_csv:
        forbidden.update(recipe.metadata_csv.key_columns)
    audit = []
    for correction in recipe.metadata_corrections:
        subject, column, value = correction.original_id, correction.column, correction.value
        if subject not in metadata.index or column not in metadata or column not in mapping:
            raise InvalidExperimentError("Metadata correction must target a known source ID and shared column")
        if column in forbidden:
            raise InvalidExperimentError("Identity/join columns cannot be changed by metadata corrections")
        if isinstance(value, numbers.Real) and not math.isfinite(value):
            raise InvalidExperimentError("Metadata correction values must be finite")
        row = dict(original_id=subject, column=column, source_value=str(metadata.at[subject, column]),
                   mapping_value=str(mapping.at[subject, column]),
                   csv_value=str(aligned.at[subject, column]) if aligned is not None and column in aligned else "",
                   confirmed_value=value, reason=correction.reason)
        for frame in (metadata, mapping, aligned):
            if frame is not None and column in frame:
                frame[column] = frame[column].astype(object)
                frame.at[subject, column] = value
        audit.append(row)

    required = {recipe.group.column, *recipe.identity_overlay.consistency_columns}
    # Mapping-only filter columns remain supported (legacy include_survival).
    required.update(c for c in recipe.cohort_filters if c in metadata)
    required.update(c for comparison in recipe.logrank_comparisons
                    for c in (*comparison.filters, *comparison.strata_columns))
    if not required <= set(metadata) or not required <= set(mapping):
        raise InvalidExperimentError("Grouping, consistency and statistics columns must exist in source and mapping")
    conflicts = []
    def compare(other, name, columns):
        for column in sorted(columns):
            mask = metadata[column].map(normalized) != other[column].map(normalized)
            if mask.any():
                examples = metadata.index[mask][:5]
                conflicts.append(MetadataConflict(source=name, column=column,
                    mismatched_rows=int(mask.sum()), example_ids=tuple(examples),
                    source_values=tuple(str(metadata.at[i,column]) for i in examples),
                    compared_values=tuple(str(other.at[i,column]) for i in examples)))
    checked = SCIENTIFIC_COLUMNS | {recipe.baseline_alignment.metadata_column}
    compare(mapping, "identity_mapping", required | (checked & set(metadata) & set(mapping)))
    if aligned is not None:
        columns = set(recipe.metadata_csv.columns)
        if columns and (not columns <= set(metadata) or not columns <= set(aligned)):
            raise InvalidExperimentError("Requested metadata CSV comparison columns must exist in both sources")
        if not columns:
            columns = (checked | required) & set(metadata) & set(aligned)
        if not columns:
            raise InvalidExperimentError("Metadata CSV has no comparable scientific columns")
        compare(aligned, "metadata_csv", columns)
    return metadata, mapping.reset_index(drop=True), tuple(conflicts), pd.DataFrame(audit)


def select_cohort(mapping, recipe):
    """Exclude all linked segments, even when the requested ID is a later segment."""
    from ethoscopy_mcp.preview import _apply_filters

    overlay = recipe.identity_overlay
    selected = _apply_filters(mapping, recipe.cohort_filters)
    keys = list(overlay.individual_key_columns)
    source_column = overlay.source_id_column
    seen = set()
    previews, audits = [], []
    for exclusion in recipe.exclusions:
        match = mapping.loc[mapping[source_column].astype(str).eq(exclusion.original_id)]
        if len(match) != 1:
            raise InvalidExperimentError(f"Unknown exclusion source ID: {exclusion.original_id}")
        key = tuple(match.iloc[0][keys])
        if key in seen:
            raise InvalidExperimentError("Multiple exclusion IDs refer to the same mapped animal")
        seen.add(key)
        mask = pd.Series(True, index=mapping.index)
        for column, value in zip(keys, key):
            mask &= mapping[column].eq(value)
        linked = mapping.loc[mask]
        if not selected[source_column].isin(linked[source_column]).any():
            raise InvalidExperimentError("Excluded animal is outside the requested cohort")
        previews.append(ExclusionPreview(requested_id=exclusion.original_id, reason=exclusion.reason,
                                         source_ids=tuple(linked[source_column].astype(str))))
        for _, row in linked.iterrows():
            audits.append(dict(original_id=str(row[source_column]), analysis_id=str(row[overlay.analysis_id_column]),
                               requested_id=exclusion.original_id, reason=exclusion.reason,
                               **{c: row[c] for c in keys}))
        selected = selected.loc[~selected[source_column].isin(linked[source_column])]
    if selected.empty:
        raise InvalidExperimentError("No metadata rows remain after cohort filters and exclusions")
    return selected, tuple(previews), pd.DataFrame(audits)
