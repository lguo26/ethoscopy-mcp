# ethoscopy-mcp

An open-source, local-first MCP integration for reproducible behavioural
analysis with [Ethoscopy](https://github.com/gilestrolab/ethoscopy).

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![CI](https://github.com/lguo26/ethoscopy-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/lguo26/ethoscopy-mcp/actions/workflows/ci.yml)

`ethoscopy-mcp` allows compatible AI clients to inspect experiments, propose
typed analysis recipes, run approved Ethoscopy workflows, and retrieve compact
results and artifact references without sending raw behavioural datasets to a
language model.

## Status

Version `0.1.0a1` is a pre-alpha public preview. The local stdio MCP server
supports survival analysis, reviewed-endpoint sleep summaries, and notebook-style
sleep plots and comparisons. Recipes are previewed before execution, inputs stay
immutable, and saved results include verified artifacts and provenance.

Sleep-deprivation QC uses the ethoscope's `stimulus_range` metadata, with explicit
time alignment and a per-fly exclusion audit. There is no fixed deprivation
window. Activity analysis and additional scientific workflows remain on the
[roadmap](docs/ROADMAP.md).

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
available in the [quick start](docs/QUICKSTART.md), with MCP client setup in
[client configuration](docs/CLIENT_CONFIGURATION.md).

## Relationship to Ethoscopes and Ethoscopy

[Ethoscopes](https://github.com/gilestrolab/ethoscope) are open-source devices
and software for high-throughput behavioural monitoring. They produce tracking
data that can be analysed with
[Ethoscopy](https://github.com/gilestrolab/ethoscopy), the Python analysis
toolbox used as this project's scientific engine. `ethoscopy-mcp` adds a typed,
local MCP and service layer around Ethoscopy; it does not replace Ethoscopy or
control Ethoscope hardware.

## Contributors

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for project ownership and transparent
AI-assistance attribution. Contributions are welcome under the process in
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

`ethoscopy-mcp` is licensed under the
[GNU General Public License version 3 only](LICENSE), expressed as
`GPL-3.0-only`. Third-party packages remain under their own licenses. Private
research datasets and generated experiment artifacts are not distributed by
this repository and are not licensed by this software license.

## Available Tools

- **Survival analysis:** movement-based death detection, survival tables, and
  Kaplan–Meier plots.
- **Sleep analysis:** heatmaps, sleep time courses, and per-fly summaries.
- **Group comparisons:** sleep and rebound quantification, with optional
  Mann–Whitney tests.
- **Sleep-deprivation quality checks:** metadata-driven deprivation windows and
  recorded per-fly exclusions.

The typed `sleep` recipe reuses saved Ethoscopy sleep annotations, applies reviewed
death/censor endpoints (including manual corrections), and exports sleep profiles,
per-fly summaries and descriptive comparison plots. Temperature and OD600 remain
separate by default. Python and MCP call the same shared implementation.

See [Sleep analysis](docs/SLEEP_ANALYSIS.md) and the
[synthetic example](examples/synthetic_sleep/README.md). A direct Ethoscopy notebook workflow also provides heatmaps, rebound quantification,
optional Mann–Whitney tests and recorded sleep-deprivation exclusions. Activity
analysis is not implemented. See [Notebook workflow](docs/NOTEBOOK_SLEEP.md).

## Example Usage

Once configured, you can ask Codex/Claude things like:

- “Inspect the experiment in `/path/to/experiment` and show the available groups
  and metadata.”
- “Preview a survival analysis using `moving` and `walk`, with a 12-hour zero-run
  threshold. Plot each OD600 group alongside PBS controls at the same temperature.”
- “Create sleep heatmaps and time-course plots for control and sleep-deprived
  flies using the saved sleep annotations.”
- “Use `stimulus_range` metadata to identify each fly's deprivation window.
  Exclude deprived flies sleeping more than 5% during that window, keep controls,
  and export the exclusion audit.”
- “Compare sleep during the first three hours after deprivation ends, using the
  aligned rebound window. Show per-fly values and run a two-sided Mann–Whitney
  test between control and deprived flies.”
- “Use my reviewed death/censor endpoint CSV for sleep summaries, keeping
  temperature and OD600 groups separate.”
- “Retrieve the plots, summary tables, and provenance for the completed analysis.”

Replace example paths with files inside your configured data roots. The client
uses the available MCP tools to inspect inputs and preview a recipe before
running it. Required metadata, time alignment, and analysis windows must be
resolved before execution; rebound comparisons require recorded post-deprivation
sleep data. See [client configuration](docs/CLIENT_CONFIGURATION.md) for setup.
