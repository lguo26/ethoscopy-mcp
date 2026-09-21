# Local quick start

This API is pre-alpha and currently supports trusted local Ethoscopy pickle
inspection plus previewed and approved survival execution. Do not load unknown
or uploaded pickle files.

## Configure trusted roots

Paths must be supplied locally and must not be committed:

```bash
export ETHOSCOPY_DATA_ROOTS=/absolute/path/to/trusted/experiments
export ETHOSCOPY_ARTIFACT_ROOT=/absolute/path/to/local/artifacts
```

Multiple data roots use the platform path separator (`:` on Linux and macOS).

## Inspect an experiment

```python
from pathlib import Path

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings

settings = Settings.from_env()
service = EthoscopyService(settings)

summary = service.inspect_experiment(
    ExperimentManifest(
        experiment_id="example-001",
        source_paths=(Path("/absolute/path/to/trusted/experiment.pkl"),),
    )
)

print(summary.model_dump_json(indent=2))
```

Inspection records source hashes, validates the data/metadata relationship,
summarizes columns and low-cardinality metadata groups, and verifies that each
source still has the registered hash after loading.

## Preview and execute a survival recipe

Construct a typed `SurvivalRecipe`, then keep preview and execution separate:

```python
preview = service.preview_analysis(manifest, recipe)
print(preview.model_dump_json(indent=2))

# Execute only after a person approves this exact preview.
result = service.run_analysis(
    manifest,
    recipe,
    approved_recipe_hash=preview.recipe_hash,
)
print(result.model_dump_json(indent=2))
```

`baseline_alignment` is an explicit required part of a survival recipe. The
runner concatenates the loaded recordings, applies that baseline exactly once,
and performs identity mapping, time alignment, cohort filtering, and group
labelling only in a working copy. The artifact root must already exist. A
successful run contains requested CSV/PNG/SVG outputs, `provenance.json`, and
`run-result.json`; rerunning the same hash verifies and reuses that directory.

## Run the tests

The initial suite uses the Python standard library and requires no separate
test-runner dependency:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The committed tests generate temporary synthetic Ethoscopy data. Private
regression datasets remain outside Git.
