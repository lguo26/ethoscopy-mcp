# ethoscopy-mcp

An open-source, local-first MCP integration for reproducible behavioural
analysis with [Ethoscopy](https://github.com/gilestrolab/ethoscopy).

`ethoscopy-mcp` allows compatible AI clients to inspect experiments, propose
typed analysis recipes, run approved Ethoscopy workflows, and retrieve compact
results and artifact references without sending raw behavioural datasets to a
language model.

## Status

Pre-alpha; not yet ready for public release. The local service can inspect
trusted Ethoscopy pickles, preview a transfer-aware survival recipe, and run an
exactly approved recipe into immutable, content-addressed artifacts. MCP
transport, broader recipe types, licensing review, and further scientific
regression coverage remain on the roadmap.

## Principles

- Ethoscopy remains the scientific engine.
- Original metadata, pickle files, databases, and recordings are immutable.
- Added columns and corrections are versioned overlays.
- MCP is a thin adapter around a reusable service.
- Important assumptions are previewed before execution.
- Results include provenance, warnings, units, exclusions, and artifact hashes.
- Raw behavioural rows are not returned to the model by default.

## Planned MCP tool surface

```text
list_experiments
inspect_experiment
validate_experiment
preview_analysis
run_analysis
get_analysis
get_artifact
```

`inspect_experiment`, survival `preview_analysis`, and survival `run_analysis`
already exist in the transport-independent Python service. `run_analysis`
requires the exact hash returned by a fresh preview, revalidates all inputs,
operates only on working copies, and atomically creates a new run directory.

## Repository layout

```text
src/ethoscopy_mcp/  Python package
docs/               architecture, safety, tools, and roadmap
tests/              unit, contract, and scientific regression tests
examples/           synthetic or redistributable examples only
```

See [the roadmap](docs/ROADMAP.md), [tool design](docs/TOOLS.md), and
[data-safety rules](docs/DATA_SAFETY.md). A preliminary Python API example is
available in the [quick start](docs/QUICKSTART.md).
