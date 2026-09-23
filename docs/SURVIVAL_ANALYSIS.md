# Survival analysis

Use `analysis_type: "survival"` with the same `preview_analysis` and
`run_analysis` tools as sleep, or the dedicated `run_kaplan_meier` tool.
Python callers use `SurvivalRecipe` and
`EthoscopyService`. Default runs call Ethoscopy 2.4.0's public `km_death_table` and
`km_survival_plot` functions through the shared service. Reviewed runs use the
same default estimates, then plot explicitly reviewed endpoints using Ethoscopy's
Kaplan–Meier helper.

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
Run separate filtered recipes to report temperature-specific curves. Log-rank
comparisons can use `strata_columns` within each comparison to adjust for
temperature or other metadata. Check group counts in the preview.

A dose filter also applies to controls: selecting OD600=0.1 excludes PBS animals
recorded at OD600=0. Pooling temperatures or doses can confound group comparisons.
Controls are not synthesized for conditions with no recorded control animals.
Record known design limitations in `context_warnings` for preview and provenance.

The workflow supports log-rank comparisons with Holm correction, documented
below, as well as descriptive survival curves and event counts. Cox models are
not included. Optional endpoint review is described below.

## Outputs and reporting

All survival output requests omit `group_label`. The legacy `primary` dataset
(the default) provides death-only CSVs and plots; complete endpoints, numerical
curves, and statistical tests use the additional datasets documented below:

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

## Kaplan–Meier survival analysis

Use `preview_analysis` with an `analysis_type: "survival"` recipe, then pass
that unchanged recipe and its preview hash to `run_kaplan_meier`. This uses the
same validated execution path as `run_analysis`, including source immutability,
identity mapping, baseline alignment, censoring, and artifact verification.

To export complete endpoints, numerical curves, and a plot, include:

```json
"output_requests": [
  {"artifact_type": "table", "format": "csv", "name": "survival_individuals", "dataset": "individuals"},
  {"artifact_type": "table", "format": "csv", "name": "kaplan_meier", "dataset": "kaplan_meier"},
  {"artifact_type": "plot", "format": "png", "name": "survival"}
]
```

The `individuals` CSV includes every analyzed animal: `id`, `treatment`, `T`
(elapsed hours), and `E` (1 = detected death, 0 = censored), plus available cohort
metadata. The `kaplan_meier` CSV contains each group's observed times,
`n_at_risk`, `n_events`, `n_censored`, `survival`, `ci_lower`, and `ci_upper`.
Confidence intervals use Ethoscopy's 95% log-transformed Greenwood method.
CSV times are hours from each subject's first retained sample; plots use days.
Explicit reviewed endpoints, when supplied, also drive these CSVs.
Existing `primary` CSV requests remain death-only for compatibility.
No 75% coverage variant is added.

## Log-rank comparisons with Holm correction

Survival recipes can request named, two-sided log-rank comparisons. Use display
labels from `group.levels`, optional exact-match metadata filters, and optional
stratum columns. All comparisons in one recipe form a single Holm family at
alpha 0.05. Add both `logrank_comparisons` and a CSV request with
`dataset: "statistics"` before previewing the recipe:

```json
"logrank_comparisons": [
  {
    "name": "Treatment effect adjusted for temperature",
    "group_labels": ["Control", "Treatment"],
    "filters": {"sex": "male"},
    "strata_columns": ["temperature"]
  }
]
```

The statistics CSV includes sample sizes, event/censor counts, chi-square,
raw and Holm-adjusted p-values, and significance at 0.05. Stratified tests sum
observed-minus-expected deaths and their tied-event hypergeometric variances
across strata before computing the chi-square statistic (1 df). Every stratum
must contain both groups. Zero-variance comparisons are marked unestimable;
they remain in the planned correction family but have missing reported p-values.
Reviewed endpoints also drive these tests when provided.

These are animal-level asymptotic tests, assuming independent observations and
non-informative censoring. Sparse events, crossing curves, and machine/treatment
confounding limit interpretation. Non-significance does not establish equivalence.

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

## Upgrading to Ethoscopy 2.4

Restart the MCP server after upgrading so it loads the updated implementation.
The running process must use Ethoscopy 2.4.0. Update older recipes that set
`cumulative: true` to `false`, then generate and review a fresh preview.

Survival approval hashes include the loaded engine version and adapter revision,
so older cached results cannot substitute for a new 2.4 analysis. Previously
saved results remain available for retrieval. The detection defaults and
elapsed-time interpretation are documented above under Recipe settings and
Time and censoring.

## Per-fly review and reference comparison

Set `review_diagnostics: true` to export `survival_review.csv` and
`survival_candidates.csv`. These report original event/censor endpoints,
post-restart movement counts, triggering column and method, candidate times,
window sample count/span and recording segment. Candidate evidence contains the
first window and zero-run candidate for each movement column in each segment,
not every possible window. Movement after restart is a review flag, not proof
of survival: tracking noise and the difference between walking and moving matter.
No automatic latest-candidate selection or 75% coverage override is applied.

To apply reviewed decisions, add `reviewed_endpoints_path` to the recipe.
To compare against a saved script table without changing results, add
`reference_endpoints_path`. Either field also enables diagnostic exports.
Both files use CSV columns:

```csv
canonical_machine,roi,time_hours,event,time_basis,reason
ETHOSCOPE_example,1,48,0,elapsed,Escaped at the reviewed observation time
```

`event` is 1 for death or 0 for censoring. `time_basis` must be `elapsed`
(hours from the subject's first retained sample) or `aligned` (hours in source
`t` after baseline and recipe subtraction). Explicitly convert script columns
to this format; the service does not infer units or identity from filenames.
A nonempty `reason` is required for each reviewed decision; reference rows do
not require it. Keys must match selected canonical machine/ROI identities and
be unique. Partial review/reference tables are supported; unlisted flies keep
the original estimates. Reviewed times outside retained observations fail.

Both the death export and plot use the selected endpoints, including censoring.
The review export preserves `original_T`, `original_E`, selected `T`, `E`, reason,
and reference differences where provided. Differences must be interpreted with
the event indicators: a censored time is not a detected death time. Existing
`detected_deaths` summary counts describe selected death events in reviewed runs.
The auxiliary files are trusted-root validated, hashed into the approval and
recorded in provenance. Changing any review reason or reference invalidates
approval. Restart/reconnect the MCP process after updating to load these fields.
