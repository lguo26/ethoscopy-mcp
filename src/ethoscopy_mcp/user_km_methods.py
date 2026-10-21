"""KM methods authored by lguo26, vendored from lguo26/ethoscopy.

Source commit: 76e23fdd6c904eefc856ab5c7103a1a9bda0ba43 (GPL-3.0).
Bodies/decorators preserved by AST extraction; formatting normalized by ast.unparse.
Do not change detector semantics in this pinned implementation.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

class UserKMMethods:

    @staticmethod
    def kaplan_meier_estimate(times, events):
        """
        Compute Kaplan-Meier survival estimate with Greenwood confidence intervals.

        Parameters
        ----------
        times : array-like
            Time to event or censoring (hours).
        events : array-like
            1 = event (death), 0 = censored.

        Returns
        -------
        pd.DataFrame with columns: time, n_at_risk, n_events, n_censored,
        survival, ci_lower, ci_upper
        """
        import numpy as np
        times = np.asarray(times, dtype=float)
        events = np.asarray(events, dtype=int)
        order = np.argsort(times)
        times_sorted = times[order]
        events_sorted = events[order]
        unique_times = np.unique(times_sorted[events_sorted == 1])
        if len(unique_times) == 0:
            unique_times = np.unique(times_sorted)
        records = []
        survival = 1.0
        greenwood_var = 0.0
        for t in unique_times:
            at_risk = np.sum(times_sorted >= t)
            if at_risk == 0:
                continue
            n_events = np.sum((times_sorted == t) & (events_sorted == 1))
            n_censored = np.sum((times_sorted == t) & (events_sorted == 0))
            if n_events > 0:
                survival *= 1 - n_events / at_risk
                if at_risk > n_events:
                    greenwood_var += n_events / (at_risk * (at_risk - n_events))
                else:
                    greenwood_var += n_events / (at_risk * max(1, at_risk - n_events))
            se_log = np.sqrt(max(greenwood_var, 0))
            z = 1.96
            ci_lower = np.exp(np.log(max(survival, 1e-10)) - z * se_log)
            ci_upper = np.exp(np.log(max(survival, 1e-10)) + z * se_log)
            ci_lower = np.clip(ci_lower, 0, 1)
            ci_upper = np.clip(ci_upper, 0, 1)
            records.append({'time': t, 'n_at_risk': at_risk, 'n_events': n_events, 'n_censored': n_censored, 'survival': survival, 'ci_lower': ci_lower, 'ci_upper': ci_upper})
        if len(records) == 0:
            return pd.DataFrame([{'time': 0, 'n_at_risk': len(times), 'n_events': 0, 'n_censored': 0, 'survival': 1.0, 'ci_lower': 1.0, 'ci_upper': 1.0}])
        result = pd.DataFrame(records)
        max_time = times.max()
        last_event_time = result['time'].iloc[-1]
        if max_time > last_event_time:
            last_row = result.iloc[-1].to_dict()
            last_row['time'] = max_time
            last_row['n_events'] = 0
            last_row['n_censored'] = 0
            result = pd.concat([result, pd.DataFrame([last_row])], ignore_index=True)
        return result

    def _build_km_survival_table(self, t_column='t', mov_column='moving', time_window=24, prop_immobile=0.01, resolution=24, cumulative=False, zero_run_hours=None, second_mov_column=None):
        """
        Build a per-fly survival table with ROI-based deduplication.

        Flies are identified by (machine_name, ROI) rather than by ID,
        so the same fly re-detected after a machine restart is tracked
        as one individual.  Death is detected via three methods (earliest wins):
          1. Sliding-window mean immobility (existing method)
          2. Longest contiguous zero-run (optional, if zero_run_hours is set)
          3. Second movement column check (optional, if second_mov_column is set)

        Parameters
        ----------
        cumulative : bool
            If True, T is computed as continuous hours from the earliest
            data point across all flies.  Adds a 'T_cumulative' column.
        zero_run_hours : float or None
            If set, also detect death when the longest contiguous run of
            zero movement exceeds this many hours (e.g. 12).
        second_mov_column : str or None
            Optional second movement column. Death is declared if EITHER
            column indicates death.

        Returns
        -------
        pd.DataFrame with columns:
            id, T, E, species, machine_name, roi, start_time, end_time,
            n_segments (and T_cumulative if cumulative=True)
        """
        import numpy as np
        species_map = {}
        meta = self.meta
        if 'species' in meta.columns:
            species_map = meta['species'].to_dict()
        id_vals = self.index.values.astype(str)
        t_vals = self[t_column].values.astype(np.float64)
        mov_vals = self[mov_column].values.astype(np.float64)
        if second_mov_column and second_mov_column in self.columns:
            mov2_vals = self[second_mov_column].values.astype(np.float64)
        else:
            mov2_vals = None
        n_rows = len(t_vals)
        mach_nums = np.array([s.split('_')[-1].split('|')[0] for s in id_vals])
        machine_names = np.char.add('ETHOSCOPE_', mach_nums)
        rois = np.array([s.split('|')[-1] for s in id_vals])
        fly_keys = np.char.add(machine_names, '_ROI')
        fly_keys = np.char.add(fly_keys, rois)
        sort_idx = np.lexsort((t_vals, fly_keys))
        fly_keys_sorted = fly_keys[sort_idx]
        t_sorted = t_vals[sort_idx]
        id_sorted = id_vals[sort_idx]
        mov_sorted = mov_vals[sort_idx]
        mov2_sorted = mov2_vals[sort_idx] if mov2_vals is not None else None
        machine_sorted = machine_names[sort_idx]
        roi_sorted = rois[sort_idx]
        fly_changes = np.where(fly_keys_sorted[:-1] != fly_keys_sorted[1:])[0] + 1
        fly_starts = np.concatenate([[0], fly_changes])
        fly_ends = np.concatenate([fly_changes, [len(fly_keys_sorted)]])
        results = []
        time_window_s = 60 * 60 * time_window
        resolution = max(1, min(resolution, time_window))
        step = max(1, int(time_window_s / resolution))
        min_pts = time_window_s / 10.0 * 0.75

        def _detect_in_segment(seg_t, seg_mov):
            """Returns earliest death_time in segment, or None."""
            best = None
            t_min, t_max = (seg_t[0], seg_t[-1])
            target_t = np.arange(int(t_min), int(t_max), step)
            if len(target_t) == 0:
                return None
            local_means = np.full(len(target_t), np.nan)
            for idx, i in enumerate(target_t):
                mask = (seg_t >= i) & (seg_t < i + time_window_s)
                n_pts = mask.sum()
                if n_pts >= min_pts:
                    local_means[idx] = seg_mov[mask].mean()
            death_points = np.where(local_means <= prop_immobile)[0]
            if len(death_points) > 0:
                best = target_t[death_points[0]]
            if zero_run_hours is not None and zero_run_hours > 0:
                zero_run_s = zero_run_hours * 3600.0
                seg_mov_clean = np.nan_to_num(seg_mov, nan=1.0)
                is_zero = seg_mov_clean == 0
                shifted = np.roll(is_zero, 1)
                shifted[0] = False
                run_starts = np.where(is_zero & ~shifted)[0]
                shifted_end = np.roll(is_zero, -1)
                shifted_end[-1] = False
                run_ends = np.where(is_zero & ~shifted_end)[0] + 1
                for rs, re in zip(run_starts, run_ends):
                    if rs < re and re <= len(seg_t):
                        dur = seg_t[re - 1] - seg_t[rs]
                        if dur >= zero_run_s:
                            zr_death = seg_t[rs]
                            if best is None or zr_death < best:
                                best = zr_death
            return best
        for start, end in zip(fly_starts, fly_ends):
            f_t = t_sorted[start:end]
            f_mov = mov_sorted[start:end]
            f_mov2 = mov2_sorted[start:end] if mov2_sorted is not None else None
            fly_id = id_sorted[start]
            machine = machine_sorted[start]
            roi = roi_sorted[start]
            species = str(species_map.get(fly_id, 'unknown'))
            if len(f_t) == 0:
                continue
            gaps = np.diff(f_t)
            seg_breaks = np.where(gaps > 3600)[0]
            if len(seg_breaks) == 0:
                seg_indices = [(0, len(f_t))]
            else:
                seg_indices = []
                prev = 0
                for brk in seg_breaks:
                    seg_indices.append((prev, brk + 1))
                    prev = brk + 1
                seg_indices.append((prev, len(f_t)))
            first_s, first_e = seg_indices[0]
            last_s, last_e = seg_indices[-1]
            t_first = f_t[first_s]
            t_last = f_t[last_e - 1]
            death_time = None
            for seg_idx in range(len(seg_indices)):
                seg_s, seg_e = seg_indices[seg_idx]
                seg_t = f_t[seg_s:seg_e]
                seg_mov = f_mov[seg_s:seg_e]
                dt = _detect_in_segment(seg_t, seg_mov)
                if dt is not None and (death_time is None or dt < death_time):
                    death_time = dt
                if f_mov2 is not None:
                    seg_mov2 = f_mov2[seg_s:seg_e]
                    dt2 = _detect_in_segment(seg_t, seg_mov2)
                    if dt2 is not None and (death_time is None or dt2 < death_time):
                        death_time = dt2
            if death_time is not None:
                T_hours = (death_time - t_first) / 3600.0
                E = 1
                end_time_val = death_time
            else:
                T_hours = (t_last - t_first) / 3600.0
                E = 0
                end_time_val = t_last
            results.append({'id': fly_id, 'T': T_hours, 'E': E, 'species': species, 'machine_name': machine, 'roi': roi, 'start_time': t_first, 'end_time': end_time_val, 'n_segments': len(seg_indices)})
        surv_df = pd.DataFrame(results)
        if cumulative:
            surv_df['T_cumulative'] = surv_df['end_time'] / 3600.0
        return surv_df

    def km_death_table(self, t_column='t', mov_column='moving', time_window=24, prop_immobile=0.01, resolution=24, cumulative=False, time_unit='hours', zero_run_hours=None, second_mov_column=None):
        """
        Return a DataFrame of dead flies with genotype, machine, ROI, and
        time of death.

        Parameters
        ----------
        time_unit : str
            'hours' or 'days'.
        zero_run_hours : float or None
            If set, also detect death via longest zero-movement run >= this
            many hours.
        second_mov_column : str or None
            Optional second movement column for combined detection.

        Returns
        -------
        pd.DataFrame with columns: genotype, machine, ROI, T
        """
        surv = self._build_km_survival_table(t_column=t_column, mov_column=mov_column, time_window=time_window, prop_immobile=prop_immobile, resolution=resolution, cumulative=cumulative, zero_run_hours=zero_run_hours, second_mov_column=second_mov_column)
        time_col = 'T_cumulative' if cumulative and 'T_cumulative' in surv.columns else 'T'
        div = 24.0 if time_unit == 'days' else 1.0
        dead = surv[surv['E'] == 1].sort_values(time_col).copy()
        dead['T'] = dead[time_col] / div
        return dead[['species', 'machine_name', 'roi', 'T']].rename(columns={'species': 'genotype', 'machine_name': 'machine'}).reset_index(drop=True)

    def count_unique_flies(self, timepoints=None, t_column='t'):
        """
        Count unique flies (by machine_name, ROI) active at specific
        timepoints.  Returns the *maximum* count — the "definition 2"
        cross-validation of the true n per genotype.

        Parameters
        ----------
        timepoints : list of float, optional
            Hours at which to count. Default: [0, 10, 50, 100, 150].
        t_column : str

        Returns
        -------
        dict : {timepoint: n_flies_per_species_dict}
        max_n : dict, {species: max count across all timepoints}
        """
        if timepoints is None:
            timepoints = [0, 10, 50, 100, 150]
        id_vals = self.index.values.astype(str)
        t_vals = self[t_column].values.astype(np.float64)
        species_map = {}
        if 'species' in self.meta.columns:
            species_map = self.meta['species'].to_dict()
        mach_nums = np.array([s.split('_')[-1].split('|')[0] for s in id_vals])
        machine_names = np.char.add('ETHOSCOPE_', mach_nums)
        rois = np.array([s.split('|')[-1] for s in id_vals])
        fly_keys = np.char.add(np.char.add(machine_names, '_ROI'), rois)
        species_vals = np.array([str(species_map.get(i, 'unknown')) for i in id_vals])
        t_min = t_vals.min()
        species_list = sorted(set(species_vals))
        result = {}
        max_per_species = {sp: 0 for sp in species_list}
        for tp in timepoints:
            tp_sec = t_min + tp * 3600
            mask = (t_vals >= tp_sec) & (t_vals < tp_sec + 3600)
            pairs = set(zip(fly_keys[mask], species_vals[mask]))
            counts = {}
            for sp in species_list:
                n = sum((1 for _, s in pairs if s == sp))
                counts[sp] = n
                max_per_species[sp] = max(max_per_species[sp], n)
            result[f't={tp}h'] = counts
        return (result, max_per_species)

    def km_survival_plot(self, facet_col: None | str=None, facet_arg: None | str=None, facet_labels: None | str=None, title: str='Kaplan-Meier Survival', t_column: str='t', mov_column: str='moving', time_window: int=24, prop_immobile: float=0.01, resolution: int=24, figsize: tuple=(8, 5), show_ci: bool=False, grid: bool=True, censoring_marks: bool=False, cumulative: bool=False, time_unit: str='hours', zero_run_hours: None | float=None, second_mov_column: None | str=None):
        """
        Kaplan-Meier survival plot with ROI-based deduplication.

        Unlike ``survival_plot`` (which counts tracking end as death), this
        method uses immobility-based death detection and properly censors
        flies that are alive when tracking ends (e.g. due to machine
        restarts or experiment end).  Flies are identified by (machine, ROI)
        so that the same fly re-detected after a restart is tracked as ONE
        individual.

        Parameters
        ----------
        facet_col : str, optional
            Metadata column for faceting (e.g. 'species').
        facet_arg : list, optional
            Values of facet_col to include.
        facet_labels : list, optional
            Display labels for each facet_arg.
        title : str
        t_column, mov_column : str
        time_window : int
            Hours of immobility required to declare death.
        prop_immobile : float
            Mean movement fraction below which fly is considered dead.
        resolution : int
            Segments per time window.
        figsize : tuple
        show_ci : bool
            Show 95 % Greenwood confidence band.
        grid : bool
        censoring_marks : bool
            Show tick marks for censored observations.
        zero_run_hours : float or None
            If set, also detect death via longest zero-movement run ≥ this
            many hours (e.g. 12).
        second_mov_column : str or None
            Optional second movement column for combined detection.
            Death is declared if EITHER column indicates death.

        Returns
        -------
        fig : matplotlib.figure.Figure
        """
        import numpy as np
        surv_df = self._build_km_survival_table(t_column=t_column, mov_column=mov_column, time_window=time_window, prop_immobile=prop_immobile, resolution=resolution, cumulative=cumulative, zero_run_hours=zero_run_hours, second_mov_column=second_mov_column)
        time_col = 'T_cumulative' if cumulative and 'T_cumulative' in surv_df.columns else 'T'
        if facet_col and facet_col in surv_df.columns:
            if facet_arg is None:
                facet_arg = sorted(surv_df[facet_col].dropna().unique())
            if facet_labels is None:
                facet_labels = list(facet_arg)
        else:
            facet_arg = ['all']
            facet_labels = ['all']
            surv_df['_facet'] = 'all'
            facet_col = '_facet'
        plot_df = surv_df[surv_df[facet_col].isin(facet_arg)]
        _, def2_max = self.count_unique_flies()
        if facet_col and facet_col in surv_df.columns:
            def1_counts = {arg: len(plot_df[plot_df[facet_col] == arg]) for arg in facet_arg}
        else:
            def1_counts = {'all': len(plot_df)}
        validated_n = {}
        for arg, label in zip(facet_arg, facet_labels):
            d1 = def1_counts.get(arg, 0)
            d2 = def2_max.get(arg, d1)
            validated_n[label] = max(d1, d2)
            if d1 != d2 and d2 > 0:
                import warnings
                warnings.warn(f'{label}: def1 (unique ROI)={d1}, def2 (max at timepoints)={d2}. Using n={max(d1, d2)}.')
        km_results = {}
        for arg, label in zip(facet_arg, facet_labels):
            group_data = plot_df[plot_df[facet_col] == arg]
            if len(group_data) == 0:
                continue
            km_df = self.kaplan_meier_estimate(group_data[time_col].values, group_data['E'].values)
            km_results[label] = (km_df, validated_n[label])
        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
        palette = {label: colors[i % len(colors)] for i, label in enumerate(facet_labels)}
        fig, ax = plt.subplots(figsize=figsize)
        time_div = 24.0 if time_unit == 'days' else 1.0
        for label, (km_df, n_flies) in km_results.items():
            color = palette.get(label, 'black')
            plot_t = np.concatenate([[0.0], km_df['time'].values]) / time_div
            plot_s = np.concatenate([[1.0], km_df['survival'].values])
            plot_ci_l = np.concatenate([[1.0], km_df['ci_lower'].values])
            plot_ci_u = np.concatenate([[1.0], km_df['ci_upper'].values])
            ax.step(plot_t, plot_s, where='post', color=color, label=f'{label} (n={n_flies})', linewidth=2)
            if show_ci:
                ax.fill_between(plot_t, plot_ci_l, plot_ci_u, step='post', color=color, alpha=0.12)
            if censoring_marks:
                cens = plot_df[(plot_df[facet_col] == facet_arg[facet_labels.index(label)]) & (plot_df['E'] == 0)]
                for _, fly in cens.iterrows():
                    tf = fly[time_col] / time_div
                    sv = 1.0
                    for j in range(len(plot_t)):
                        if j == len(plot_t) - 1 or tf < plot_t[j + 1]:
                            sv = plot_s[j]
                            break
                    ax.plot(tf, sv, '|', color=color, markersize=5, alpha=0.6, markeredgewidth=1)
        time_label = 'Time (days)' if time_unit == 'days' else 'Time (hours)'
        ax.set_xlabel(time_label)
        ax.set_ylabel('Survival probability')
        ax.set_title(title)
        ax.set_xlim(0, plot_df[time_col].max() / time_div * 1.02)
        ax.set_ylim(-0.02, 1.05)
        ax.legend(loc='lower left', frameon=True)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.0%}'))
        if grid:
            ax.grid(True, alpha=0.2, linestyle='--')
            ax.set_axisbelow(True)
        n_dead = surv_df['E'].sum()
        n_total = len(surv_df)
        anno_parts = [f'{n_dead}/{n_total} deaths', f'tw={time_window}h pi={prop_immobile}']
        if zero_run_hours:
            anno_parts.append(f'zr={zero_run_hours}h')
        if second_mov_column:
            anno_parts.append(f'+{second_mov_column}')
        ax.text(0.99, 0.02, ' | '.join(anno_parts), transform=ax.transAxes, fontsize=7, ha='right', va='bottom', color='gray', style='italic')
        plt.tight_layout()
        return fig
