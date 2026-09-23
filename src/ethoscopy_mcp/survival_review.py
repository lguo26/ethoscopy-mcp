"""Opt-in evidence and explicit endpoint review; never tune the default detector."""
from pathlib import Path

import numpy as np
import pandas as pd

from ethoscopy_mcp.errors import InvalidExperimentError


def roi_key(value):
    try:
        number = float(value)
        if not np.isfinite(number) or number != int(number):
            raise ValueError
        return str(int(number))
    except (TypeError, ValueError, OverflowError):
        raise InvalidExperimentError("ROI must be a finite integer") from None


def read_endpoints(path: Path, mapping: pd.DataFrame, *, reviewed: bool) -> pd.DataFrame:
    data = pd.read_csv(path, dtype={"canonical_machine": "string", "roi": "string"})
    required = {"canonical_machine", "roi", "time_hours", "event", "time_basis"}
    if reviewed:
        required.add("reason")
    if not required.issubset(data.columns) or data.empty:
        raise InvalidExperimentError(f"Endpoint CSV requires nonempty rows with {sorted(required)}")
    if not {"canonical_machine", "roi"}.issubset(mapping.columns):
        raise InvalidExperimentError("Survival review requires canonical_machine and roi in the identity overlay")
    data["roi"] = data.roi.map(roi_key)
    if data.canonical_machine.isna().any() or data.duplicated(["canonical_machine", "roi"]).any():
        raise InvalidExperimentError("Endpoint CSV has missing or duplicate subject keys")
    keys = set(zip(mapping.canonical_machine.astype(str), mapping.roi.map(roi_key)))
    if not set(zip(data.canonical_machine.astype(str), data.roi)).issubset(keys):
        raise InvalidExperimentError("Endpoint CSV contains subjects outside the selected cohort")
    for column in ("time_hours", "event"):
        try:
            data[column] = pd.to_numeric(data[column], errors="raise")
        except (ValueError, TypeError):
            raise InvalidExperimentError(f"Invalid endpoint {column}") from None
        if not np.isfinite(data[column]).all():
            raise InvalidExperimentError(f"Endpoint {column} must be finite")
    if (data.time_hours < 0).any() or not data.event.isin([0, 1]).all():
        raise InvalidExperimentError("Endpoint time must be nonnegative and event must be 0 or 1")
    if not data.time_basis.isin(["elapsed", "aligned"]).all():
        raise InvalidExperimentError("Endpoint time_basis must be elapsed or aligned")
    if reviewed and (data.reason.isna() | data.reason.astype(str).str.strip().eq("")).any():
        raise InvalidExperimentError("Every reviewed endpoint requires a reason")
    return data


def review_survival(working, recipe, settings, death_table, figure):
    from ethoscopy.survival import _segment_bounds, sliding_window_death, zero_run_death

    survival = working.survival_table(**settings, subject_cols=["machine_name", "region_id"])
    metadata = working.meta
    id_keys = {str(i): (str(r.machine_name), roi_key(r.region_id)) for i, r in metadata.iterrows()}
    observations = {}
    for sid, frame in working.groupby(level=0, sort=False):
        observations.setdefault(id_keys[str(sid)], []).append(frame)
    endpoints, candidates = [], []
    death = recipe.death_detection
    columns = [death.movement_column]
    if death.second_movement_column:
        columns.append(death.second_movement_column)
    for _, subject in survival.iterrows():
        sid = str(subject['id']); key = id_keys[sid]
        frame = pd.concat(observations[key]).sort_values('t')
        t = frame.t.to_numpy(dtype=float)
        values = {c: frame[c].to_numpy(dtype=float) for c in columns}
        original_end = float(subject.end_time)
        restart_moving = 0
        for segment, (start, end) in enumerate(_segment_bounds(t, 3600)):
            ts = t[start:end]
            after = values[columns[0]][end:]
            if ts[0] <= original_end <= ts[-1] and subject.E:
                restart_moving = int(np.sum(after > 0))
            for column in columns:
                movement = values[column][start:end]
                window = sliding_window_death(ts, movement, death.time_window_hours * 3600,
                    int(death.time_window_hours * 3600 / 24), death.proportion_immobile)
                zero = zero_run_death(ts, movement, death.zero_run_hours * 3600) if death.zero_run_hours else None
                for method, candidate in (("window", window), ("zero_run", zero)):
                    if candidate is None:
                        continue
                    mask = (ts >= candidate) & (ts <= candidate + death.time_window_hours * 3600)
                    candidates.append(dict(canonical_machine=key[0], roi=key[1], segment=segment,
                        column=column, method=method, elapsed_hours=(candidate-subject.start_time)/3600,
                        aligned_hours=candidate/3600, window_samples=int(mask.sum()),
                        observed_window_span_hours=float(np.ptp(ts[mask])/3600) if mask.any() else 0,
                        segment_end_aligned_hours=float(ts[-1]/3600),
                        later_segment_moving_samples=int(np.sum(after > 0))))
        endpoints.append(dict(id=sid, canonical_machine=key[0], roi=key[1],
            treatment=metadata.loc[sid, 'species'], first_sample_aligned_hours=float(t[0]/3600),
            last_sample_aligned_hours=float(t[-1]/3600), original_T=float(subject['T']), original_E=int(subject.E),
            T=float(subject['T']), E=int(subject.E), reviewed=False, reason="",
            post_restart_moving_samples=restart_moving,
            warning="movement_after_restart_requires_review" if restart_moving else ""))
    report = pd.DataFrame(endpoints)
    keys = pd.DataFrame([dict(canonical_machine=k[0], roi=k[1]) for k in observations])
    for path, reviewed in ((recipe.reviewed_endpoints_path, True), (recipe.reference_endpoints_path, False)):
        if path is None:
            continue
        overrides = read_endpoints(path, keys, reviewed=reviewed)
        for _, change in overrides.iterrows():
            mask = (report.canonical_machine == change.canonical_machine) & (report.roi == change.roi)
            idx = report.index[mask][0]
            time = float(change.time_hours)
            if change.time_basis == 'aligned':
                time -= report.at[idx, 'first_sample_aligned_hours']
            if reviewed:
                maximum = report.at[idx, 'last_sample_aligned_hours'] - report.at[idx, 'first_sample_aligned_hours']
                if time < -1e-8 or time > maximum + 1e-8:
                    raise InvalidExperimentError("Reviewed endpoint lies outside the subject's retained observations")
                report.loc[idx, ['T', 'E', 'reviewed', 'reason']] = [max(0, time), int(change.event), True, change.reason]
            else:
                report.loc[idx, ['reference_T', 'reference_E']] = [time, int(change.event)]
    if 'reference_T' in report:
        report['original_minus_reference_hours'] = report.original_T - report.reference_T
        report['selected_minus_reference_hours'] = report['T'] - report.reference_T
        report['selected_event_matches_reference'] = report.E.eq(report.reference_E).where(report.reference_E.notna())
    reports = {"survival_review.csv": report,
               "survival_candidates.csv": pd.DataFrame(candidates, columns=[
                   'canonical_machine', 'roi', 'segment', 'column', 'method', 'elapsed_hours',
                   'aligned_hours', 'window_samples', 'observed_window_span_hours',
                   'segment_end_aligned_hours', 'later_segment_moving_samples'])}
    if recipe.reviewed_endpoints_path:
        # The same reviewed endpoint table drives both the death export and KM plot.
        death_table = report.loc[report.E == 1, ['id', 'treatment', 'T']].copy()
        for column, value in recipe.cohort_filters.items():
            death_table[column] = value
        figure = plot_reviewed(report, recipe, figure)
    return death_table, figure, reports


def plot_reviewed(report, recipe, original):
    import matplotlib.pyplot as plt
    from ethoscopy.survival import kaplan_meier

    plt.close(original)
    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    for level in recipe.group.levels:
        group = report.loc[report.treatment == level.label]
        if group.empty:
            continue
        km = kaplan_meier(group['T']/24, group.E)
        times = np.r_[0, km.time]; survival = np.r_[1, km.survival]
        line, = ax.step(times, survival, where='post', label=f'{level.label} (n={len(group)})')
        ax.fill_between(times, np.r_[1, km.ci_lower], np.r_[1, km.ci_upper],
                        step='post', color=line.get_color(), alpha=.15)
        for time in group.loc[group.E == 0, 'T']/24:
            ax.plot(time, survival[np.searchsorted(times, time, side='right')-1], '+', color=line.get_color())
    ax.set_title('Survival — reviewed endpoints'); ax.set_ylim(0, 1.05); ax.legend()
    return fig
