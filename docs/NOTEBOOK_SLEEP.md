# Direct Ethoscopy notebook sleep workflow

Use `analysis_type: "sleep_notebook"` and `NotebookSleepRecipe` to call the
same public functions used in the reference notebooks:

- `heatmap(variable="asleep")`
- `t_filter(...).plot_overtime(variable="asleep", avg_window=30, ...)`
- `t_filter(...).plot_quantify(variable="asleep", ...)`
- Optional `remove_sleep_deprived(..., remove=False)` quality control
- Optional `curate_dead_animals(...)`
- Optional `scipy.stats.mannwhitneyu` on the **per-fly** `asleep_mean` values
  returned by `plot_quantify`.

Unlike the separate `sleep` interval-summary recipe, this workflow preserves
Ethoscopy's sample means, rolling profiles, QC denominator and plotting rules.
It reuses saved sleep annotations. It does not execute arbitrary notebook cells,
reload raw databases, or overwrite the source notebook, metadata or pickle.

## Reference notebook settings

One reference notebook uses:

- Baseline alignment once, ZT origin 09:00, no injection-time subtraction.
- Groups `sleep_deprived=False` (control) and `True` (sleep deprived).
- Profile window `[24, 96)` hours with 30-minute rolling smoothing.
- Rebound quantification window `[72, 75)` hours.
- Two-sided Mann–Whitney U with `method="exact"`, missing means omitted.
- No dead-animal curation or deprivation exclusions in that notebook.

A second reference workflow combines independent experiments, applies a reviewed
machine exclusion, screens failed deprivation, curates dead animals, and applies
a further reviewed exclusion. Machine exclusions must be explicit for the
relevant experiment, never global defaults. Comments describing suspected faults
are not executable exclusion rules.

## Sleep-deprivation QC: use the machine's stimulus_range

The >5% criterion applies to the **actual sleep-deprivation interval**, not a
fixed 48–72-hour interval. The default schedule field is `stimulus_range`, read
from ethoscope acquisition metadata by `etho.load_ethoscope_metadata`.

For example, a synthetic schedule from day 3 at 09:00 to day 4 at 09:00
converts to 48–72 hours when day 1 at 09:00 is the ZT origin. Other
experiments and machines may have completely different windows.

```python
# linked_metadata is the metadata returned by etho.link_meta_index.
# This reads the machine database METADATA/interactor settings.
mdf = etho.load_ethoscope_metadata(linked_metadata, progress=False)
mdf.to_csv("ethoscope_metadata.csv", index=True)
```

Supply that immutable CSV to the recipe, or retain `stimulus_range` in the
pickle's metadata. Pickles saved without acquisition metadata may not retain it. The MCP
reads the saved metadata; it does not connect over the network to live machines.

```json
{
  "deprivation_qc": {
    "target_group_label": "sleep deprived",
    "maximum_sleep_fraction": 0.05,
    "metadata": {
      "path": "/trusted/experiment/ethoscope_metadata.csv",
      "reference_hour": 9
    }
  }
}
```

Omit `metadata.path` if the schedule is already in the pickle or identity overlay.
The default CSV join is `machine_name` plus `date`; `date` can be derived from
`load_ethoscope_metadata`'s acquisition `date_time`. Ambiguous repeated acquisitions
are rejected; configure explicit `join_columns` for those experiments. Sources
cannot silently override conflicting schedule fields in other inputs.

Clock ranges are converted using the recording date/time and explicitly supplied
`reference_hour` (the value used to load the data). Alternatively supply a `zt0`
metadata timestamp for each recording. Recordings before lights-on use the
previous ZT day, matching Ethoscopy's modulo-24 convention. Baseline offsets and
time subtraction are applied once. Naive timestamps use their recorded clock;
set `timezone` explicitly when conversion is needed. Mixed timezone-aware and
naive values without a configured timezone are rejected. The two numeric columns
`deprivation_start_hours` and `deprivation_end_hours`, if supplied instead, must
already be in the final analysis time basis.

`stimulus_range` is the modern field. For a **verified old interactor export**,
explicitly set `metadata.range_columns` to `["date_range"]`. Ordinary acquisition
`date_range` must not be mistaken for the deprivation schedule.

Different flies/machines can have different windows. Multiple or conflicting
intervals for one physical fly require review rather than being flattened into
one large interval. Missing or malformed schedules block the analysis unless an
explicit fallback `window` is supplied; there is **no default 48–72 window**.
Fallback applies only when schedule metadata are absent, never to override
valid or malformed machine schedules:

```json
{"window": {"start_hours": 48, "end_hours": 72}}
```

For each resolved interval, the MCP calls
`remove_sleep_deprived(start_time=start, end_time=end, remove=False,
sleep_column="asleep", t_column="t")` on the **deprived group only**. It removes
flies with `Percent Asleep > 0.05`; exactly 0.05 remains. This is a fraction (5%),
despite the library column's name. Controls are not screened by this criterion.

The library computes sleep seconds divided by the span between first and last
timestamps in the window, preserving the notebook's metric. Gaps or incomplete
windows can affect it; inspect the exported span. Flies with fewer than two
annotated timestamps or no usable QC span are excluded with a missing-evidence
reason, never counted as successful deprivation. Missing schedules are a
configuration error, distinct from a recording with a known schedule but no data.

Preview lists resolved windows, their sources and animal counts. The per-fly
audit records `qc_start_hours`, `qc_end_hours`, `qc_window_source`, sleep fraction,
observed span, exclusion reason and retained data counts. It also distinguishes
metadata-only animals without observations. If no `exclusions` table is explicitly
requested, QC automatically saves the reserved `exclusion-audit.csv` artifact.
Acquisition CSV hashes are included in preview/provenance and checked again after
execution; edits require a fresh preview. Source files are never rewritten.

## Death handling and explicit exclusions

Choose `endpoint_policy` explicitly:

- `untrimmed`: reproduce a notebook without death trimming. No survival status
  is inferred. Preview warns that terminal immobility may remain as sleep.
- `curate`: run Ethoscopy `curate_dead_animals` after deprivation QC. The typed
  `curation` settings default to `moving`, 24-hour window, 0.01 immobility
  proportion, resolution 24. This is algorithmic curation, not reviewed deaths.
- `reviewed`: provide `endpoints_path` as documented in
  [Sleep analysis](SLEEP_ANALYSIS.md). Confirmed/manual endpoints are applied
  before notebook calculations. This does not run automatic curation.

Example experiment-specific exclusions (synthetic machine names):

```json
{
  "endpoint_policy": "curate",
  "exclusions": [
    {
      "column": "machine_name", "values": ["MACHINE_BAD_A"],
      "reason": "Reviewed equipment problem in this experiment",
      "stage": "before_qc"
    },
    {
      "column": "machine_name", "values": ["MACHINE_BAD_B"],
      "reason": "Reviewed experiment-specific machine exclusion",
      "stage": "after_curate"
    }
  ]
}
```

## Identity, grouping and time

Use the same manifest/identity-overlay/alignment fields as other recipes. For
**independent** experiments, include the experiment/date in
`individual_key_columns`, e.g. `["date", "canonical_machine", "roi"]`, so the
same machine/ROI reused on another date does not become the same fly. For a
transfer of the **same flies**, use an explicitly reviewed canonical identity
mapping instead. Set `consistency_columns` to the actual experiment fields,
e.g. `["sex", "sleep_deprived"]` rather than the survival default `infection`.

Group labels must match the labels referenced by QC and statistical settings.
Use `strata_columns` to preserve additional factors in descriptive plots. A
statistical comparison requires fixed filters or explicit composite groups;
implicit pooling across multiple temperatures/doses blocks approval. Controls
are never invented. Strata default to empty for this generic notebook recipe.

Set `profile_window`, `quantification_window`, `avg_window_minutes`, `title`,
`day_length_hours` and `lights_off_hours`. The direct library mode uses a ZT
origin for its light bars; shifted injection-relative plots use the separate
interval workflow. Heatmaps currently require a 24-hour cycle. Do not supply
interval-mode `sleep` settings to `sleep_notebook`.

## Statistics

```json
{
  "comparison": {
    "group_labels": ["control", "sleep deprived"],
    "method": "exact",
    "alternative": "two-sided"
  }
}
```

Omit `comparison` for descriptive analysis. Default method is `auto` when a
comparison is requested. Explicit `exact` reproduces the reference notebook;
preview warns if there are tied per-fly values because SciPy's exact method
has no tie correction. `asymptotic` and `auto` are also supported. The CSV records
sample sizes, U statistic, p-value, requested/effective method, ties and window.
This is one unadjusted, independent two-group comparison. It does not account
for machine/date clustering, repeated measures or multiple-testing selection.

## Outputs

Use CSV tables or PNG/SVG/PDF plots:

| Dataset | Table | Plot |
| --- | --- | --- |
| `primary` / `individuals` | Per-fly `plot_quantify` results and endpoint notes | `plot_quantify` |
| `comparison` | Count, mean, SEM of per-fly means | `plot_quantify` |
| `timecourse` | Mean line coordinates returned by `plot_overtime` | `plot_overtime` |
| `heatmap` | Not supported | `heatmap`, with explicit `group_label` |
| `statistics` | One requested Mann–Whitney result | Not supported |
| `exclusions` | Complete fly-level QC/exclusion audit | Not supported |

Profile CSVs contain the plotted mean, not the shaded confidence limits. Library
bootstrap confidence intervals and point jitter can vary on a fresh execution;
individual means and statistical results are regression checked. Cached artifacts
remain byte-verified by the existing store.

All recipes use preview → exact current hash → run → retrieve. Changing the QC
window, threshold, exclusions, source files or reviewed endpoints requires a new
preview. Both Python scripts and MCP use these same functions.

## Long experiments and rebound coverage

Use the actual machine schedule even for multi-day SD. Profile, deprivation QC
and quantification windows are separate. A rebound comparison is meaningful only
when observations exist after SD ends; sleep during SD is not rebound. Current
preview rejects an empty requested quantification window instead of inventing
zero rebound. Automatic optional-rebound handling remains future work.

Legacy inputs with duplicate metadata IDs or overlapping timestamps need a
reviewed correction before running. The service does not silently merge them.
