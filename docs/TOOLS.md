# MCP tool design

## Discovery

### `inspect_experiment(manifest)`

Return source identities, available columns and groups, time coverage, animal
counts, missingness, and warnings.

## Analysis

### `preview_analysis(manifest, recipe)`

Resolve a proposed recipe without executing it. Return cohorts, derived
columns, exclusions, timing, methods, parameters, expected artifacts, warnings,
and unresolved assumptions.

Transfer-aware survival preview validates
that the mapping covers all metadata IDs, preserves consistency fields within
each canonical individual, contains at most one segment per individual/date,
and references the movement columns required by the detector. It hashes the
recipe together with all source and overlay hashes for approval.

### `run_analysis(manifest, recipe, approved_recipe_hash)`

Execute only a freshly revalidated recipe whose hash exactly matches the
approved preview. Survival and interval sleep recipes write CSV/PNG/SVG outputs;
notebook sleep additionally supports PDF plots. Artifacts and provenance are written atomically to a
run directory identified by the recipe hash. The service checks that sources
and identity mappings are unchanged. Sleep recipes support reviewed endpoint truncation, time courses,
per-fly summaries and descriptive group comparisons. See
[Sleep analysis](SLEEP_ANALYSIS.md). Activity recipes remain planned.

### `run_kaplan_meier(manifest, recipe, approved_recipe_hash)`

Run a survival recipe using the same checks as `run_analysis`. Preview the
recipe first, then pass its unchanged settings and approval hash.

Choose CSV outputs by dataset:

- `individuals`: every animal's death or censoring time and event indicator.
- `kaplan_meier`: survival estimates, confidence intervals, and numbers at risk.
- `statistics`: requested log-rank comparisons with Holm-adjusted p-values.
- `primary`: the original death-only table, kept for compatibility.

Plots use `primary` with PNG or SVG format. Statistical tests require named
`logrank_comparisons`; each can specify metadata filters and strata such as
temperature. All requested comparisons form one Holm correction family.
See [Survival analysis](SURVIVAL_ANALYSIS.md) for settings and examples.

## Retrieval

### `get_analysis(analysis_id)`

Return structured results, warnings, provenance, and artifact references.

### `get_artifact(analysis_id, artifact_id)`

Resolve a generated table, PNG, SVG, or other output without embedding large
files directly in ordinary tool text.

These six tools run through the local MCP server. Inspection, preview, and
retrieval are marked read-only. The two run tools create new result files or
reuse matching results; they do not modify source data.

## Approval flow

```text
request
  → inspect and validate
  → proposed recipe
  → visible assumptions and warnings
  → user approval
  → immutable analysis run
  → results, artifacts, and provenance
```

The `sleep_notebook` recipe directly calls Ethoscopy heatmap/overtime/quantify
methods, optionally screens failed sleep deprivation, curates dead animals,
applies explicit metadata exclusions and runs one requested Mann–Whitney test.
See [Notebook sleep workflow](NOTEBOOK_SLEEP.md).
