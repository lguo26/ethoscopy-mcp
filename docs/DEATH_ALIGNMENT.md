# Death alignment with MCP endpoints

The Python helper `ethoscopy_mcp.align_to_death` aligns observations to estimated
deaths from an MCP survival run. It is part of this integration package, not an
upstream Ethoscopy method or a standalone MCP tool.

```python
import ethoscopy as etho
import pandas as pd
from ethoscopy_mcp import align_to_death

etho.set_sleep_rule("k")
data = pd.read_pickle("Sa_1007_1.pkl")
events = pd.read_csv("survival_individuals.csv")  # MCP export
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

Tests cover MCP time-offset conversion, window boundaries, censoring, stored
sleep-label preservation, source immutability, and invalid inputs. The real-cohort
validation script also aligns both October datasets to freshly generated MCP
3.0 endpoints and writes per-fly row counts.
