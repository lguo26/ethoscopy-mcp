# Death alignment with MCP endpoints

The Python helper `ethoscopy_mcp.align_to_death` aligns observations to estimated
deaths from an MCP survival run. It is part of this integration package, not an
upstream Ethoscopy method or a standalone MCP tool.

For “run death alignment analysis”, follow [analysis requests](ANALYSIS_REQUESTS.md).
First request a survival `primary` CSV named `km_death_table`, alongside the
`individuals` CSV. Verify the MCP run's artifact hashes before loading them.

```python
import ethoscopy as etho
import pandas as pd
import numpy as np
from ethoscopy_mcp import align_to_death

etho.set_sleep_rule("k")
data = pd.read_pickle("Sa_1007_1.pkl")
events = pd.read_csv("survival_individuals.csv")  # MCP export
deaths = pd.read_csv("km_death_table.csv")        # MCP primary CSV
assert deaths.id.is_unique
assert set(deaths.id) == set(events.loc[events.E.eq(1), "id"])
times = deaths.set_index("id")["T"]
mask = events.E.eq(1)
np.testing.assert_allclose(
    events.loc[mask, "T"], events.loc[mask, "id"].map(times),
    rtol=0, atol=1e-9,
)
events.loc[mask, "T"] = events.loc[mask, "id"].map(times)
# For these ten-second recordings, remove CSV floating-point noise at boundaries.
events["anchor_seconds"] = (
    3600 * (events.first_sample_aligned_hours + events["T"])
).round(6)
aligned = align_to_death(data, events, window_hours=(-48, 0))
```

This example assumes zero baseline, no time subtraction, and unchanged animal
IDs, as verified for the October 7 and 16 cohorts. For other experiments, first
apply the same baseline/time transformation and identity mapping as the MCP
survival recipe. The helper cannot infer these transformations from endpoints.

For MCP exports, the anchor in seconds is
`3600 * (first_sample_aligned_hours + T)`. `T` alone is elapsed survival, not a
source timestamp. Alternatively, provide explicit `id`, `E`, and
`anchor_seconds` columns using the same time coordinate as the observations.

The returned ordinary pandas DataFrame preserves input columns and adds
`anchor_seconds` and `time_to_death_hours`. The window is half-open: `[-48, 0)`
excludes the death timestamp and later observations. Only `E == 1` subjects are
aligned. Censored subjects are never assigned a death. Inputs are not modified.
An estimated death at the first retained observation has no pre-death rows;
the function does not invent observations or change that endpoint.
Missing endpoint IDs, duplicate event IDs, nonfinite times/anchors, ambiguous
MCP time units, and invalid windows raise errors.

The helper does not score sleep, estimate death, remove tracking gaps, bin
observations, or match PBS controls. It preserves stored k annotations; calling
`set_sleep_rule("k")` does not convert a classic-scored pickle. For PBS comparisons,
use each case's anchor to select observed/alive controls from the same experiment,
then apply the tracking-coverage checks used by the cohort analysis scripts.

The endpoint engine is recipe-selected: `user_km_76e23fd` uses the user
`_build_km_survival_table()`; `ethoscopy_3` uses installed `survival_table()`. Scripts can consume MCP outputs without calling it
directly. The explicit death-only table supplies death times; full endpoints
supply recording bounds and censoring. Reviewed endpoint overrides must be
consistent across both exports; do not mix artifacts from different runs.

Tests cover MCP time-offset conversion, window boundaries, censoring, stored
sleep-label preservation, source immutability, and invalid inputs. The real-cohort
validation script also aligns both October datasets to freshly generated MCP
3.0 endpoints and writes per-fly row counts.
