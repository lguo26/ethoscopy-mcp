# Sleep analysis and descriptive comparisons

The same `preview_analysis` and `run_analysis` tools now accept
`analysis_type: "sleep"`. Python callers use `SleepRecipe` with
`EthoscopyService`; the shared computation is in `ethoscopy_mcp.sleep`.
The MCP does not discover or execute arbitrary notebooks or scripts.

This workflow reuses a saved Ethoscopy `asleep` column. It does not re-annotate
raw movement, infer new death times, or replace the existing survival detector.
The survival recipe is unchanged: manual corrections are consumed by sleep
through the reviewed endpoint CSV, not yet applied by the survival recipe itself.

## Inputs and identity

Use the existing manifest, identity overlay, baseline and time-alignment fields.
Every physical fly has a canonical identity defined by the overlay's
`individual_key_columns`. Multiple recording segments contribute to that one
fly. Baseline days are added once and `subtract_hours` is subtracted once.
Overlapping timestamps and changing group/stratum assignments within a fly are
rejected. Existing metadata values cannot be relabelled through the overlay.

Required `endpoints_path`: a trusted CSV containing:

```csv
analysis_id,end_hours,event,reason
fly-a,48,1,Reviewed synthetic death at recording end
fly-b,72,0,Recording end with no detected death
```

- Use one analysis segment ID per selected physical fly, with exactly one row
  per fly. Extra known flies outside the selection are allowed.
- `end_hours` is in the recipe's **output time basis**, after baseline alignment
  and subtraction. It is an absolute endpoint, not duration since first sample.
- `event` is 1 for a reviewed death, 0 for censoring. Censored endpoints must
  equal the last recorded timestamp. Deaths must lie within the recorded range.
- Preserve algorithmic/manual provenance in `reason`. Do not automatically turn
  recording ends into deaths. A reviewed death at recording end is valid.
- Every selected fly needs an endpoint, including censored animals.
- Endpoint contents are hashed alongside data, mapping and recipe. Editing them
  requires a new preview/hash. Inputs are never overwritten.

For a reviewed survival-table export, map the animal/analysis ID to `analysis_id`,
absolute endpoint seconds divided by 3600 to `end_hours`, the event indicator
to `event`, and the algorithm/manual correction provenance to `reason`. Check
that the time basis matches the sleep recipe. No private data belong in Git.

## Recipe settings

```json
{
  "analysis_type": "sleep",
  "endpoints_path": "/trusted/project/reviewed_endpoints.csv",
  "strata_columns": ["temperature", "OD600"],
  "sleep": {
    "asleep_column": "asleep",
    "sample_period_seconds": 10,
    "bin_minutes": 30,
    "start_hours": 0,
    "end_hours": 72
  }
}
```

These fields extend the manifest/identity/group/alignment recipe structure;
see the executable synthetic example for a complete recipe. `end_hours` is
optional. Choose the actual annotation sampling period explicitly. This initial
workflow summarizes nonnegative output times only; `start_hours` defaults to 0.

Group levels select the groups to compare. Strata default to temperature and
OD600, which must be present in the mapping. Each group/stratum combination
gets its own summary and plot label. Set `strata_columns` explicitly for other
experiments. Preview warns if multiple temperatures or doses would be pooled.

A scalar OD filter also filters PBS: if PBS has OD600=0, filtering OD600=0.1
removes it. To retain PBS, select infection/control groups without that filter
and keep dose in strata, or supply an explicit composite group in the overlay.
A control is never synthesized for a missing temperature/dose. A control
recorded at 29 °C must not be described as a matched 25 °C control.

## Calculation and interpretation

Each valid annotation covers from its timestamp to the earliest of: next
observation, one configured sample period, reviewed endpoint, or requested
window end. Intervals crossing time bins are split. Missing annotations and
recording gaps contribute neither observed time nor sleep time. The final
recorded timestamp is a censor endpoint, not a newly inferred extra interval.

- Per-fly fraction = observed sleep seconds / observed seconds.
- Time-course means weight observed physical flies equally within each bin.
- Comparison means weight per-fly sleep fractions equally across the requested
  window, rather than treating every timestamp as an independent animal.
- Coverage, sample counts, observation duration and per-fly summaries are
  exported. Flies without usable observations remain in the individual table
  with a missing fraction, not zero sleep.
- Unequal follow-up and mortality can change which flies contribute over time.
  These are descriptive summaries of observed pre-endpoint data, not adjusted
  causal effects or significance tests. Use an explicit common window when
  appropriate, and inspect coverage. SEM is missing for groups with one fly.
- Existing notebook plots using `curate_dead_animals().plot_overtime()` can
  differ because their death truncation, pooling, interpolation and smoothing
  are different. This workflow is explicit, binned, and uses reviewed endpoints.

## Outputs

Add `dataset` to each output request:

| Dataset | CSV | Plot |
| --- | --- | --- |
| `primary` (default) | Per-fly, per-bin values and coverage | Group time course |
| `timecourse` | Group/stratum means, SEM, animals and coverage by bin | Group time course |
| `individuals` | Per-fly totals, fractions and endpoint reasons | Individual comparison |
| `comparison` | Group/stratum means, SEM and observation durations | Individual comparison |

CSV tables and PNG/SVG plots are supported. Each comparison point is a fly and
the black line is the group mean. Plot time-course lines use the exported means.
Sleep results leave the survival-only `group_outcomes` empty; counts are in the
sleep tables. Artifacts and endpoint provenance use the existing verified store.

## Reproducible example

```sh
MPLBACKEND=Agg python examples/synthetic_sleep/run_example.py /tmp/sleep-demo
```

This writes synthetic inputs, a complete `manifest.json` and `recipe.json`,
and tables/plots under `/tmp/sleep-demo/runs`. The same JSON objects can be
passed to MCP: inspect → preview → run with the current preview hash → retrieve.

Example request to an assistant:

> Use the sleep recipe for my experiment pickle with the corrected reviewed survival
> endpoints. Keep temperature and OD600 separate, retain available PBS controls,
> and export 30-minute sleep profiles, per-fly summaries and comparison plots.
> Show the preview before running.

For direct `heatmap`, `plot_overtime`, `plot_quantify`, optional Mann–Whitney tests,
and sleep-deprivation QC, use the separate [notebook workflow](NOTEBOOK_SLEEP.md).
Activity profiles, fresh annotation from raw movement, bout analysis and dedicated
light/dark phase summaries remain future work.
