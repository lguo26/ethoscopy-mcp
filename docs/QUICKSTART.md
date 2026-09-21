# Local quick start

This API is pre-alpha and currently supports trusted local Ethoscopy pickle
inspection. Do not load unknown or uploaded pickle files.

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

## Run the tests

The initial suite uses the Python standard library and requires no separate
test-runner dependency:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The committed tests generate temporary synthetic Ethoscopy data. Private
regression datasets remain outside Git.
