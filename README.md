# ethoscopy-mcp

An open-source, local-first MCP integration for reproducible behavioural
analysis with [Ethoscopy](https://github.com/gilestrolab/ethoscopy).

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

`ethoscopy-mcp` allows compatible AI clients to inspect experiments, propose
typed analysis recipes, run approved Ethoscopy workflows, and retrieve compact
results and artifact references without sending raw behavioural datasets to a
language model.

## Status

Pre-alpha; not yet ready for public release. The local stdio MCP server can
inspect trusted Ethoscopy pickles, preview a transfer-aware survival recipe,
run an exactly approved recipe into immutable, content-addressed artifacts,
and retrieve verified result metadata. Broader recipe types and further
scientific regression coverage remain on the roadmap.

## Principles

- Ethoscopy remains the scientific engine.
- Original metadata, pickle files, databases, and recordings are immutable.
- Added columns and corrections are versioned overlays.
- MCP is a thin adapter around a reusable service.
- Important assumptions are previewed before execution.
- Results include provenance, warnings, units, exclusions, and artifact hashes.
- Raw behavioural rows are not returned to the model by default.

## MCP tool surface

```text
inspect_experiment
preview_analysis
run_analysis
get_analysis
get_artifact
```

All five tools are available through the local stdio adapter and the
transport-independent Python service. `run_analysis` requires the exact hash
returned by a fresh preview, revalidates all inputs, operates only on working
copies, and atomically creates a new run directory. Retrieval verifies artifact
paths, sizes, and hashes before returning metadata.

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

## Contributors

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for project ownership and transparent
AI-assistance attribution.

## License

`ethoscopy-mcp` is licensed under the
[GNU General Public License version 3 only](LICENSE), expressed as
`GPL-3.0-only`. Third-party packages remain under their own licenses. Private
research datasets and generated experiment artifacts are not distributed by
this repository and are not licensed by this software license.
