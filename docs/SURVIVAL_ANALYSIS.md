# Survival analysis

Use `analysis_type: "survival"` with the same `preview_analysis` and
`run_analysis` tools as sleep. Python callers use `SurvivalRecipe` and
`EthoscopyService`. Both interfaces call Ethoscopy 2.4.0's public
`km_death_table` and `km_survival_plot` functions through the shared service.

## Inputs and identity

Supply a manifest containing trusted Ethoscopy pickle paths, plus an identity
overlay CSV. Pickles must include `t` in seconds, the selected movement columns,
and metadata for grouping, cohort filters, baseline, machine and ROI.

The overlay maps each recording segment's `original_id` to its `analysis_id`
and canonical machine/ROI identity. Defaults use `canonical_machine` and `roi`
as the physical-fly key, with `date` identifying recording dates. It must cover
all source metadata IDs, including animals outside the selected cohort. Group
and filter columns must also be present. Include important experimental factors
in `consistency_columns` so they are checked against the source metadata.

For transfers of the same flies, use a reviewed mapping to the same canonical
machine/ROI. Independent flies must have distinct canonical machine/ROI keys:
the survival engine merges on `machine_name` and `region_id`. Changing only
the overlay's key columns does not change this engine grouping. Overlapping
recordings for a merged subject are rejected by Ethoscopy.

Source pickles and metadata remain unchanged; alignment, filtering and identity
mapping operate on working copies.

## Recipe settings

The default death detector is:

```json
{
  "analysis_type": "survival",
  "death_detection": {
    "movement_column": "moving",
    "second_movement_column": "walk",
    "time_window_hours": 24,
    "proportion_immobile": 0.01,
    "zero_run_hours": 12,
    "cumulative": false
  }
}
```

These fields extend the manifest, identity, group, cohort and alignment settings.
See the [complete synthetic recipe](../examples/synthetic_survival/run_example.py)
for an executable example using these detection defaults.

The recipe's `proportion_immobile` maps to Ethoscopy's `prop_immobile`: a mean
movement value at or below this threshold qualifies as death. A contiguous
zero-movement run of the configured duration can also trigger detection. Either
movement column can trigger death. Set `second_movement_column` to `null` to
use only the primary column, or `zero_run_hours` to `null` to disable that rule.

No `min_coverage` override is applied. Incomplete final windows are evaluated
using the library defaults, matching the Ethoscopy 2.4 notebook behavior.
The adapter retains the library's resolution of 24 window starts per window;
`time_window_hours` below 24 is rejected during preview.
Missing tracking values and short or interrupted recordings should therefore
be reviewed when interpreting inferred deaths.

## Time and censoring

Baseline days are applied once; `subtract_hours` is then subtracted from source
timestamps. Negative aligned observations are discarded by default. The engine
reports elapsed time from each subject's **first retained sample**:

- Death-table `T` values are in hours.
- Kaplan–Meier plot time is in days.
- `cumulative` must be `false`; `true` is rejected.

These durations are not automatically time since injection or absolute ZT.
An injection-time subtraction does not change the engine's elapsed-time origin.

Death events are movement-based estimates. Animals without detected death are
right-censored at their final usable observation. The Kaplan–Meier plot includes
censored subjects, confidence intervals and censor marks.

## Groups and interpretation

Use `group.column` and labelled `group.levels` for the treatment factor and
`cohort_filters` for exact metadata selections, such as a single temperature.
There is no survival `strata_columns` option; run separate filtered recipes to
report temperature-specific curves. Check group counts in the preview.

A dose filter also applies to controls: selecting OD600=0.1 excludes PBS animals
recorded at OD600=0. Pooling temperatures or doses can confound group comparisons.
Controls are not synthesized for conditions with no recorded control animals.
Record known design limitations in `context_warnings` for preview and provenance.

The current workflow reports descriptive survival curves and event counts. It
does not run log-rank tests, Cox models, multiple-comparison corrections, or
manual endpoint overrides. Reviewed endpoints can instead be supplied to the
separate [sleep summary workflow](SLEEP_ANALYSIS.md).

## Outputs and reporting

Survival output requests use `dataset: "primary"` (the default), without
`group_label`:

| Output | Format | Contents |
| --- | --- | --- |
| Death table | CSV | Detected deaths only: `id`, `treatment`, `T` in hours, and applied cohort filters. Censored animals have no row in this table. |
| Survival plot | PNG or SVG | Kaplan–Meier curves by treatment, confidence intervals and censor marks; time in days. |
| Run summary | MCP/Python response | `group_outcomes`: animals with data, detected deaths and censored counts for each group. |
| Provenance | JSON, automatic | Exact recipe, source and overlay hashes, engine version, warnings, group outcomes and artifact hashes. |

For example, include the following in a complete recipe:

```json
{
  "output_requests": [
    {"artifact_type": "table", "format": "csv", "name": "death_table"},
    {"artifact_type": "plot", "format": "png", "name": "survival"},
    {"artifact_type": "plot", "format": "svg", "name": "survival"}
  ]
}
```

An analysis report should state the cohort, death settings, elapsed-time basis,
per-group animal/death/censor counts, relevant design limitations, and links to
the plots, death table and provenance. The service returns these structured
results; it does not generate a narrative HTML or PDF report.

Canonical results are stored under `ETHOSCOPY_ARTIFACT_ROOT/<analysis_id>/`.
`run_analysis` also copies all requested artifacts and provenance to
`<first_pickle_folder>/<analysis_id>_exports/`, returning `export_directory`.
Repeated runs verify and reuse the same export folder. Changed existing exports
are never overwritten. The first source folder must be writable; for multi-file
analyses spanning directories, exports go beside the first source only.

## Reproducible example

From the repository root:

```sh
MPLBACKEND=Agg PYTHONPATH=src python examples/synthetic_survival/run_example.py
MPLBACKEND=Agg PYTHONPATH=src python examples/synthetic_survival/run_example.py --approve
```

The first command previews the synthetic transfer recipe. The second executes
the freshly previewed hash and saves the outputs. No private data are required.

Example request to an assistant:

> Run survival analysis on my experiment pickle, using its reviewed identity
> mapping. Compare treatments at 29 degrees C, use the 24-hour window and
> 12-hour zero-movement rule, and export the death table and PNG/SVG curves.
> Report deaths and censored counts for every group and explain the time basis.

The workflow is inspect → preview → exact current hash → run → retrieve.
Source, mapping, recipe and survival-engine changes invalidate approval hashes.
Restart the MCP server after upgrading so it loads the updated implementation.
