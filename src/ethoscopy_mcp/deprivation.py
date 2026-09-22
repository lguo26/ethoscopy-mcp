"""Resolve per-recording deprivation schedules into the analysis time basis."""
from __future__ import annotations

import ast
import re

import numpy as np
import pandas as pd

from ethoscopy_mcp.errors import InvalidExperimentError


def _require(ok, message):
    if not ok:
        raise InvalidExperimentError(message)


def _present(value):
    if isinstance(value, (list, tuple)):
        return bool(value)
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def _stamp(value, timezone):
    try:
        stamp = pd.Timestamp(value)
        _require(not pd.isna(stamp), "Missing schedule timestamp")
        if timezone:
            stamp = stamp.tz_localize(timezone, ambiguous="raise", nonexistent="raise") if stamp.tzinfo is None else stamp.tz_convert(timezone)
        return stamp
    except (ValueError, TypeError) as exc:
        raise InvalidExperimentError(f"Invalid or ambiguous deprivation timestamp: {value!r}") from exc


def _range(value):
    if isinstance(value, str) and value.strip().startswith(("[", "(")):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError) as exc:
            raise InvalidExperimentError("Invalid serialized stimulus range") from exc
    if isinstance(value, (list, tuple)):
        _require(len(value) == 2, "Exactly one start/end deprivation interval is supported per recording")
        return value
    stamp = r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
    match = re.fullmatch(rf"\s*({stamp})\s*(?:\s+|,|;|/|->|to)\s*({stamp})\s*", str(value))
    _require(match is not None, "Deprivation range must contain exactly two full timestamps; open/multiple intervals require review")
    return match.groups()


def _origin(row, settings):
    if _present(row.get(settings.zt0_column)):
        return _stamp(row[settings.zt0_column], settings.timezone)
    _require(settings.reference_hour is not None, "Clock-time deprivation metadata requires an explicit reference_hour or zt0 timestamp")
    _require(_present(row.get(settings.date_column)) and _present(row.get(settings.time_column)),
             "Clock-time conversion requires recording date and time (or an explicit zt0 timestamp)")
    day = _stamp(row[settings.date_column], settings.timezone).normalize()
    time = str(row[settings.time_column]).strip().replace("-", ":")
    try:
        hour, minute, second = map(float, time.split(":"))
        _require(0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60, "Invalid recording time")
    except (ValueError, TypeError) as exc:
        raise InvalidExperimentError("Recording time must be HH:MM:SS or HH-MM-SS") from exc
    # Ethoscopy reference_hour uses modulo 24: recordings before lights-on
    # start in the previous ZT day. Preserve that convention explicitly.
    origin_day = day.date() - pd.Timedelta(days=int(hour + minute/60 + second/3600 < settings.reference_hour))
    naive = pd.Timestamp(origin_day) + pd.Timedelta(hours=settings.reference_hour)
    return _stamp(naive, settings.timezone) if settings.timezone else naive


def _recording_window(row, recipe):
    qc, settings = recipe.deprivation_qc, recipe.deprivation_qc.metadata
    candidates = []
    start, end = row.get(settings.start_hours_column), row.get(settings.end_hours_column)
    if _present(start) or _present(end):
        _require(_present(start) and _present(end), "Both numeric deprivation window columns are required")
        try:
            candidates.append((float(start), float(end), f"metadata:{settings.start_hours_column}/{settings.end_hours_column}"))
        except (ValueError, TypeError) as exc:
            raise InvalidExperimentError("Deprivation hour columns must be numeric in the output time basis") from exc
    for column in settings.range_columns:
        if not _present(row.get(column)):
            continue
        start, end = [_stamp(x, settings.timezone) for x in _range(row[column])]
        origin = _origin(row, settings)
        _require((start.tzinfo is None) == (end.tzinfo is None) == (origin.tzinfo is None),
                 "Schedule and ZT origin mix naive and timezone-aware timestamps; configure timezone explicitly")
        baseline = float(row[recipe.baseline_alignment.metadata_column])
        shift = baseline * recipe.baseline_alignment.day_length_hours - recipe.time_alignment.subtract_hours
        candidates.append(((start-origin).total_seconds()/3600 + shift,
                           (end-origin).total_seconds()/3600 + shift, f"metadata:{column}"))
    if not candidates:
        _require(qc.window is not None, "No deprivation schedule in metadata; supply acquisition metadata or an explicit fallback window")
        candidates.append((qc.window.start_hours, qc.window.end_hours, "explicit_fallback"))
    for start, end, _ in candidates:
        _require(np.isfinite([start, end]).all() and 0 <= start < end, "Invalid deprivation interval in analysis hours")
        _require(np.allclose([start,end], candidates[0][:2], atol=1e-9, rtol=0), "Conflicting deprivation schedule fields; review metadata")
    return candidates[0]


def schedule_metadata(mapping, source, recipe):
    """Merge an optional immutable acquisition-metadata CSV without row expansion."""
    if source is None:
        return mapping
    settings = recipe.deprivation_qc.metadata
    external = pd.read_csv(source.path)
    # load_ethoscope_metadata returns acquisition date_time, rather than the
    # fly metadata's date. Derive the join date without mixing recording dates.
    if settings.date_column not in external and "date_time" in external:
        external[settings.date_column] = external.date_time.map(lambda x: _stamp(x, settings.timezone).strftime("%Y-%m-%d"))
    columns = list(settings.join_columns)
    _require(set(columns).issubset(mapping) and set(columns).issubset(external), "Schedule CSV and fly metadata lack explicit join columns")
    left, right = mapping.copy(), external.copy()
    for column in columns:
        _require(left[column].notna().all() and right[column].notna().all(), "Schedule join keys must not be missing")
        if column == settings.date_column:
            left[column] = left[column].map(lambda x: pd.Timestamp(x).strftime("%Y-%m-%d"))
            right[column] = right[column].map(lambda x: pd.Timestamp(x).strftime("%Y-%m-%d"))
        else:
            left[column] = left[column].astype(str)
            right[column] = right[column].astype(str)
    fields = [*settings.range_columns, settings.start_hours_column, settings.end_hours_column, settings.zt0_column]
    fields = [c for c in dict.fromkeys(fields) if c in right and c not in columns]
    _require(bool(fields), "Schedule CSV contains no deprivation schedule fields")
    right = right[[*columns, *fields]].drop_duplicates()
    _require(not right.duplicated(columns).any(), "Ambiguous schedule rows for the same acquisition keys")
    merged = left.merge(right, on=columns, how="left", validate="many_to_one", suffixes=("", "__schedule"))
    for column in fields:
        extra = column + "__schedule"
        if extra not in merged:
            continue
        both = merged[column].notna() & merged[extra].notna()
        # Reject ambiguous conflicting sources rather than preferring a stale
        # CSV or pickle without surfacing it. Numeric equality handles 1 vs 1.0.
        for a, b in zip(merged.loc[both, column], merged.loc[both, extra]):
            numeric = pd.to_numeric(pd.Series([a,b]), errors="coerce")
            _require(str(a) == str(b) or (numeric.notna().all() and numeric.iloc[0] == numeric.iloc[1]),
                     f"Conflicting source and acquisition schedule metadata: {column}")
        merged[column] = merged[column].combine_first(merged.pop(extra))
    return merged


def resolve_windows(mapping, subject_ids, recipe, source=None):
    """Resolve one consistent interval per fly, allowing different machine schedules."""
    selected = schedule_metadata(mapping, source, recipe)
    selected = selected.loc[selected.subject_id.isin(subject_ids)]
    result = []
    for subject, rows in selected.groupby("subject_id", sort=False):
        windows = [_recording_window(row, recipe) for _,row in rows.iterrows()]
        _require(all(np.allclose(w[:2], windows[0][:2], atol=1e-9, rtol=0) for w in windows),
                 "A physical fly has conflicting/multiple deprivation schedules across recordings")
        start,end,origin = windows[0]
        result.append({"subject_id": subject, "qc_start_hours": start, "qc_end_hours": end,
                       "qc_window_source": origin + ("; acquisition_csv=" + source.source_id if source else "")})
    table = pd.DataFrame(result).set_index("subject_id")
    _require(set(table.index) == set(subject_ids), "Missing deprivation schedule identity")
    return table
