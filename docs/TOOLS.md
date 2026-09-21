# MCP tool design

## Discovery

### `list_experiments()`

List experiments registered under configured roots.

### `inspect_experiment(experiment_id)`

Return source identities, available columns and groups, time coverage, animal
counts, missingness, and warnings.

### `validate_experiment(experiment_id)`

Validate source integrity, metadata linkage, identities, timestamps, and the
requirements of supported analyses.

## Analysis

### `preview_analysis(experiment_id, recipe)`

Resolve a proposed recipe without executing it. Return cohorts, derived
columns, exclusions, timing, methods, parameters, expected artifacts, warnings,
and unresolved assumptions.

### `run_analysis(approved_recipe)`

Execute only a validated recipe on working copies. Initial recipe types are
sleep summary, sleep profile, sleep comparison, activity profile, and survival.

## Retrieval

### `get_analysis(analysis_id)`

Return structured results, warnings, provenance, and artifact references.

### `get_artifact(artifact_id)`

Resolve a generated table, PNG, SVG, or other output without embedding large
files directly in ordinary tool text.

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
