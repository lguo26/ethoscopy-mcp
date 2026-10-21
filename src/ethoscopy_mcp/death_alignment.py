"""Immutable pre-death alignment of observations to MCP survival endpoints."""

import numpy as np
import pandas as pd


def align_to_death(data, events, window_hours=(-48, 0), time_column="t"):
    """Return a DataFrame of observed deaths in a half-open pre-death window.

    Data needs an ``id`` column/index and time in seconds. Events need unique
    ``id`` and ``E`` (1=estimated death, 0=censored), plus either explicit
    ``anchor_seconds`` or the MCP columns ``T``, ``first_sample_aligned_hours``,
    ``time_unit=hours`` and ``time_basis=elapsed_from_first_retained_sample``.
    Data timestamps MUST use the same baseline/offset-aligned coordinate as
    the anchors; source IDs must already match the MCP identity mapping.

    Sleep labels and original timestamps are preserved. No death detection,
    sleep scoring, coverage filtering, binning, or PBS matching is performed.
    Censored animals are omitted rather than aligned to their recording end.
    """
    bounds = np.asarray(window_hours, dtype=float)
    if bounds.shape != (2,) or not np.isfinite(bounds).all() or not bounds[0] < bounds[1] <= 0:
        raise ValueError("Require finite window start < end <= 0")
    endpoints = pd.DataFrame(events).copy(deep=True)
    if not {"id", "E"}.issubset(endpoints):
        raise ValueError("Events require id and E columns")
    if endpoints.id.isna().any() or endpoints.id.duplicated().any():
        raise ValueError("Event IDs must be non-null and unique")
    if not endpoints.E.isin([0, 1]).all():
        raise ValueError("E must contain only 0 or 1")
    if "anchor_seconds" not in endpoints:
        required = {"T", "first_sample_aligned_hours", "time_unit", "time_basis"}
        if not required.issubset(endpoints):
            raise ValueError("Supply anchor_seconds or MCP hourly elapsed endpoints")
        if not endpoints.time_unit.eq("hours").all() or not endpoints.time_basis.eq("elapsed_from_first_retained_sample").all():
            raise ValueError("MCP endpoints must be hours elapsed from the first retained sample")
        endpoints["anchor_seconds"] = 3600 * (
            pd.to_numeric(endpoints["T"], errors="raise")
            + pd.to_numeric(endpoints.first_sample_aligned_hours, errors="raise")
        )
    deaths = endpoints.loc[endpoints.E.eq(1), ["id", "anchor_seconds"]].copy()
    deaths["anchor_seconds"] = pd.to_numeric(deaths.anchor_seconds, errors="raise")
    if not np.isfinite(deaths.anchor_seconds).all():
        raise ValueError("Death anchors must be finite")
    frame = pd.DataFrame(data).copy(deep=True)
    if "id" not in frame and frame.index.name == "id":
        frame = frame.reset_index()
    if not {"id", time_column}.issubset(frame):
        raise ValueError("Data require id and the requested time column")
    if {"anchor_seconds", "time_to_death_hours"}.intersection(frame.columns):
        raise ValueError("Data already contain alignment columns")
    if frame.id.isna().any() or not frame.id.isin(endpoints.id).all():
        raise ValueError("Missing endpoint information for data IDs; check the identity mapping")
    times = pd.to_numeric(frame[time_column], errors="raise")
    if not np.isfinite(times).all():
        raise ValueError("Observation times must be finite seconds")
    frame = frame.merge(deaths, on="id", how="inner", validate="many_to_one", sort=False)
    frame["time_to_death_hours"] = (pd.to_numeric(frame[time_column]) - frame.anchor_seconds) / 3600
    return frame.loc[
        frame.time_to_death_hours.ge(bounds[0]) & frame.time_to_death_hours.lt(bounds[1])
    ].copy()
