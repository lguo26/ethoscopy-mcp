"""Compatibility adapter for the pinned user-authored KM methods.

Stored k annotations and Ethoscopy 3.0 stay installed. Only the explicitly
selected survival backend uses these methods. No global monkey-patching.
"""
import inspect
import numpy as np
import pandas as pd
from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.user_km_methods import UserKMMethods

COMMIT = '76e23fdd6c904eefc856ab5c7103a1a9bda0ba43'

class UserKMBackend(UserKMMethods):
    def __init__(self, working):
        self.frame = pd.DataFrame(working).copy()
        self.meta = working.meta.copy()
        self.index = self.frame.index
        self.columns = self.frame.columns
        self._tables = {}
        # Legacy code parses identity from IDs. Reject ambiguous merges rather
        # than silently ignoring the MCP canonical identity mapping.
        keys = []
        canonical = []
        for sid in self.index.unique():
            value = str(sid)
            if '|' not in value or '_' not in value:
                raise InvalidExperimentError('User KM requires original device/ROI formatted IDs')
            keys.append((value.split('_')[-1].split('|')[0], value.split('|')[-1]))
            row = self.meta.loc[sid]
            canonical.append((str(row.machine_name), str(int(row.region_id))))
            times = self.frame.loc[[sid], 't'].to_numpy(dtype=float)
            if len(times) > 1 and not np.allclose(np.diff(times), 10, rtol=0, atol=1e-6):
                raise InvalidExperimentError('Pinned user KM backend currently requires continuous 10-second observations per animal')
        if len(set(keys)) != len(keys) or len(set(canonical)) != len(canonical):
            raise InvalidExperimentError('Pinned user KM backend requires one recording ID per canonical animal; transfers/restarts need separate validation')

    def __getitem__(self, key):
        return self.frame[key]

    def _build_km_survival_table(self, **settings):
        bound = inspect.signature(UserKMMethods._build_km_survival_table).bind(self, **settings)
        bound.apply_defaults()
        key = tuple(sorted((k,v) for k,v in bound.arguments.items() if k != "self"))
        if key not in self._tables:
            self._tables[key] = super()._build_km_survival_table(**settings)
        return self._tables[key].copy(deep=True)

    def full_table(self, **settings):
        table = self._build_km_survival_table(**settings)
        table['machine_name'] = table.id.map(self.meta.machine_name)
        table['roi'] = table.id.map(self.meta.region_id)
        return table

    def death_table(self, **settings):
        raw = self.km_death_table(**settings, time_unit='hours')
        full = self._build_km_survival_table(**settings)
        ids = full[['id', 'machine_name', 'roi']].rename(columns={'machine_name':'machine'})
        raw = raw.merge(ids, on=['machine','roi'], validate='one_to_one')
        return raw[['id','genotype','T']].rename(columns={'genotype':'treatment'})

    @staticmethod
    def window_candidate(t, movement, time_window, resolution, threshold):
        """Exact pinned sliding-window rule for review evidence (not a second backend)."""
        seconds = time_window * 3600
        step = max(1, int(seconds / max(1, min(resolution, time_window))))
        minimum = seconds / 10 * .75
        for start in np.arange(int(t[0]), int(t[-1]), step):
            mask = (t >= start) & (t < start + seconds)
            if mask.sum() >= minimum and movement[mask].mean() <= threshold:
                return float(start)
        return None
