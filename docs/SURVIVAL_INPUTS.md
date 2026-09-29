# Survival exclusions, metadata checks and plot labels

These additive fields belong to `SurvivalRecipe`, accepted by `preview_analysis`,
`run_analysis` and `run_kaplan_meier`. Existing survival recipes can omit them.
Sleep recipe behavior is unchanged. Restart the MCP server after updating the
package so the client receives the new tool schemas.

## Explicit animal exclusions

```json
{
  "exclusions": [
    {"original_id": "synthetic-recording-001", "reason": "Confirmed tracking failure"}
  ]
}
```

Supply a **source recording ID** from the identity mapping. Excluding any segment
excludes the entire mapped animal across all linked segments. Unknown IDs,
duplicate exclusions for one animal, and exclusions outside the selected cohort
are rejected. To remove a group entirely, also remove its configured group level;
an empty requested group is a blocking preview error.

The preview lists each requested ID, its reason, all affected source IDs and the
remaining per-group counts. A run automatically exports `exclusions.csv` with one
row per excluded recording segment. Curves, death counts, individual endpoints
and log-rank tests all use the remaining cohort. Never substitute exclusion for
right censoring without an experimental reason. Sources are not edited.

## Metadata checks and corrections

Source pickle metadata and the identity mapping are compared for shared standard
scientific fields (including temperature, food, injection date and baseline),
configured consistency fields, and grouping/filter/statistics fields. Synthetic
mapping-only filter columns remain supported for older recipes. Identity fields
are handled by the transfer mapping, not overwritten by metadata corrections.

An external CSV can be checked explicitly:

```json
{
  "metadata_csv": {
    "path": "/trusted/metadata.csv",
    "key_columns": ["date", "machine_name", "region_id"],
    "columns": ["temperature", "injection_time", "food"]
  }
}
```

Those are the default join columns. A CSV with source IDs can instead use
`key_columns: ["original_id"]`. Joins use the **original recording metadata**, before
canonical machine remapping. Keys must be complete and unique on both sides;
the CSV must cover exactly the manifest's recording segments. Omit `columns` to
compare all shared standard scientific and analysis fields. No CSV is discovered
or trusted implicitly. It is registered as an auxiliary source and hash-verified.

Disagreements appear in `metadata_conflicts`: source name, column, mismatch count,
and up to five example IDs and values. They set `ready_to_approve=false`. Resolve
the input disagreement, or explicitly record a confirmed correction:

```json
{
  "metadata_corrections": [
    {
      "original_id": "synthetic-recording-001",
      "column": "temperature",
      "value": 29,
      "reason": "Experimenter confirmed the incubator setting"
    }
  ]
}
```

Each correction targets one recording segment and an existing shared metadata
column. It updates source, mapping and external-CSV **working copies**, before
filtering, baseline alignment, plotting or statistics. Specify corrections for
all affected segments; consistency checks still apply across a linked animal.
Identity/join columns cannot be corrected this way. Use typed values (e.g. numeric
`29`, boolean `false`) matching the intended analysis. Unknown targets and
duplicate target/column pairs are rejected.

The preview displays the corrections. The automatic `metadata_corrections.csv`
records original source/mapping/CSV values, the confirmed value and reason;
provenance also includes the correction declarations. Original files are never
rewritten. Both reasons and values, exclusion IDs, optional CSV contents and plot
title are included in the freshly validated approval hash. Changing them requires
a new preview hash. The updated engine version also gives old recipes a new hash;
completed older results remain readable.

## Readable survival plots

Default titles describe the selected sex, food and temperature from working
metadata, without internal filter names. Optional `plot_title` supplies a custom
title (up to 160 characters). Choose readable `group.levels[].label` values for
legends; sample sizes are supplied by the survival plotting engine. Legends are
placed below the curves and long text wraps to avoid clipping. Reviewed-endpoint
plots receive the same title/layout rules.

The x-axis remains **Days from first recorded sample**. Changing the title does
not change the time origin or convert the curves to time since injection.

## Validation

Synthetic tests cover transfer-spanning exclusions, audit artifacts, group
counts, immutability, source/mapping/CSV disagreements, explicit corrections,
CSV identity joins, approval invalidation, and rendering bounds. Run:

```sh
MPLBACKEND=Agg PYTHONPATH=src python -m unittest discover -s tests -v
```
