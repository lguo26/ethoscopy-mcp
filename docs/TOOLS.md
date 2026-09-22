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
content-addressed run directory, then verifies that sources and overlays are
unchanged. Sleep recipes support reviewed endpoint truncation, time courses,
per-fly summaries and descriptive group comparisons. See
[Sleep analysis](SLEEP_ANALYSIS.md). Activity recipes remain planned.

## Retrieval

### `get_analysis(analysis_id)`

Return structured results, warnings, provenance, and artifact references.

### `get_artifact(analysis_id, artifact_id)`

Resolve a generated table, PNG, SVG, or other output without embedding large
files directly in ordinary tool text.

These five tools are implemented over local stdio. Inspection, preview, and
retrieval are annotated read-only. Execution is a non-destructive, idempotent
local write because it creates or reuses only content-addressed artifacts.

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
