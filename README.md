# ethoscopy-mcp

An open-source, local-first MCP integration for reproducible behavioural
analysis with [Ethoscopy](https://github.com/gilestrolab/ethoscopy).

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![CI](https://github.com/lguo26/ethoscopy-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/lguo26/ethoscopy-mcp/actions/workflows/ci.yml)

`ethoscopy-mcp` allows compatible AI clients to inspect experiments, propose
typed analysis recipes, run approved Ethoscopy workflows, and retrieve compact
results and artifact references without sending raw behavioural datasets to a
language model.

[Supported Analyses](#supported-analyses) · [Quick Start](#quick-start) · [Available Tools](#available-tools) · [Example Usage](#example-usage)

## Features

- **Sleep analysis:** heatmaps, sleep time courses, and per-fly summaries.
- **Sleep-deprivation quality checks:** metadata-driven deprivation windows and
  recorded per-fly exclusions.
- **Survival analysis:** movement-based death detection, survival tables, and
  Kaplan–Meier plots.
- **Group comparisons:** sleep and rebound quantification, with optional
  Mann–Whitney tests.

## Supported Analyses

| Analysis | Recipe | What you can generate |
| --- | --- | --- |
| [Sleep summaries](docs/SLEEP_ANALYSIS.md) | `sleep` | Sleep profiles, per-fly summaries, and descriptive group comparisons using reviewed death/censor endpoints. |
| [Sleep plots and deprivation analysis](docs/NOTEBOOK_SLEEP.md) | `sleep_notebook` | Heatmaps, sleep time courses, rebound comparisons, optional Mann–Whitney tests, and SD quality checks using `stimulus_range`. |
| Survival analysis | `survival` | Movement-based death detection, survival tables, and Kaplan–Meier plots. |

All three workflows use `preview_analysis` and `run_analysis` from the
[five available MCP tools](#available-tools). You can request them in plain
language; see [Example Usage](#example-usage). Python and MCP use the same
shared implementation.

Try the [synthetic sleep example](examples/synthetic_sleep/README.md) or
[synthetic deprivation and rebound example](examples/synthetic_notebook_sleep/README.md)
without private experiment data.

## Status

Version `0.1.0a1` is a pre-alpha public preview. The local stdio MCP server
supports survival analysis, reviewed-endpoint sleep summaries, and notebook-style
sleep plots and comparisons. Recipes are previewed before execution, inputs stay
immutable, and saved results include verified artifacts and provenance.

Sleep-deprivation QC uses the ethoscope's `stimulus_range` metadata, with explicit
time alignment and a per-fly exclusion audit. There is no fixed deprivation
window. Activity analysis and additional scientific workflows remain on the
[roadmap](docs/ROADMAP.md).

## Prerequisites

- **Python 3.12 or newer**, with an isolated virtual environment. Installing
  this package installs its declared dependencies, including Ethoscopy (`==2.4.0`)
  and MCP (`>=2,<3`).
- **An MCP client with local stdio support** to launch the server, or Python
  to use the service directly.
- **Trusted local Ethoscopy pickle files** with the behavioural columns and
  metadata required by your analysis. Sleep workflows require saved sleep
  annotations; metadata-driven deprivation checks require `stimulus_range`
  in the saved metadata or an exported acquisition-metadata CSV.
- **Configured local directories:** set `ETHOSCOPY_DATA_ROOTS` to your experiment
  directories and `ETHOSCOPY_ARTIFACT_ROOT` to an existing, writable output
  directory.

Some workflows also require CSV overlays for animal identity or reviewed
death/censor endpoints. See the [quick start](docs/QUICKSTART.md) for installation
and [client configuration](docs/CLIENT_CONFIGURATION.md) for connecting a client.

## Quick Start

1. Install the package using the commands below.
2. Connect [Codex](#add-to-codex) or [Claude Desktop](#add-to-claude-desktop)
   with your local experiment and output paths.
3. Ask: “Inspect `/absolute/path/to/experiments/experiment.pkl` and show the
   available groups, behavioural columns, and metadata.”
4. Request a survival or sleep analysis, review its preview, then run it and
   retrieve the plots and tables.

For a complete walkthrough and runnable examples using synthetic data, see
[Quick Start](docs/QUICKSTART.md).

## Installation

On Linux or macOS, with Git and Python 3.12 or newer installed:

```bash
git clone https://github.com/lguo26/ethoscopy-mcp.git
cd ethoscopy-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Create a local output directory and configure your data paths, replacing the
example paths with your own:

```bash
mkdir -p /absolute/path/to/analysis-output
export ETHOSCOPY_DATA_ROOTS="/absolute/path/to/experiments"
export ETHOSCOPY_ARTIFACT_ROOT="/absolute/path/to/analysis-output"
```

Your experiment directory should contain trusted Ethoscopy `.pkl` files and any
required metadata CSVs. Configure your MCP client to launch
`/absolute/path/to/ethoscopy-mcp/.venv/bin/ethoscopy-mcp`, with the two environment
variables above included in its server configuration. See
[client configuration](docs/CLIENT_CONFIGURATION.md) for the configuration
example. The client starts the stdio server when it connects.

## Add to Codex

With the Codex CLI installed, register the local server using absolute paths:

```bash
codex mcp add ethoscopy \
  --env ETHOSCOPY_DATA_ROOTS=/absolute/path/to/experiments \
  --env ETHOSCOPY_ARTIFACT_ROOT=/absolute/path/to/analysis-output \
  -- /absolute/path/to/ethoscopy-mcp/.venv/bin/ethoscopy-mcp
```

Check the saved configuration with `codex mcp get ethoscopy`. Start a new Codex
session to use the server, then try a prompt from [Example Usage](#example-usage).

## Add to Claude Desktop

Open **Settings → Developer → Edit Config** and add the `ethoscopy` entry below
to `claude_desktop_config.json`. If you already have MCP servers configured,
merge the entry into the existing `mcpServers` object.

```json
{
  "mcpServers": {
    "ethoscopy": {
      "command": "/absolute/path/to/ethoscopy-mcp/.venv/bin/ethoscopy-mcp",
      "env": {
        "ETHOSCOPY_DATA_ROOTS": "/absolute/path/to/experiments",
        "ETHOSCOPY_ARTIFACT_ROOT": "/absolute/path/to/analysis-output"
      }
    }
  }
}
```

Replace all paths with paths on the computer running Claude Desktop. The output
directory must already exist. On Windows, use the virtual environment's
`Scripts/ethoscopy-mcp.exe` executable and Windows paths with forward slashes
or escaped backslashes in JSON.

Save the file, fully quit and reopen Claude Desktop, and check that `ethoscopy`
appears among its available MCP servers. See the official
[local MCP setup guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
for configuration locations and troubleshooting.

## Example Usage

Once configured, you can ask Codex/Claude things like:

- “Inspect the experiment in `/path/to/experiment` and show the available groups
  and metadata.”
- “Preview a survival analysis using `moving` and `walk`, with a 12-hour zero-run
  threshold. Compare experimental groups, such as sleep-deprived versus control
  or 25 °C versus 29 °C.”
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

## Available Tools

| Tool | Purpose |
| --- | --- |
| `inspect_experiment` | Summarize input files, behavioural columns, and metadata. |
| `preview_analysis` | Validate a recipe and review cohorts, assumptions, and warnings. |
| `run_analysis` | Execute the recipe using its approved preview hash. |
| `get_analysis` | Retrieve a completed run's summary and artifact references. |
| `get_artifact` | Retrieve a verified artifact's metadata and local path. |

All five tools are available through the local stdio adapter and the Python
service. Execution revalidates inputs, operates on working copies, and saves
results with provenance. Retrieval verifies artifact paths, sizes, and hashes.

## Principles

- Ethoscopy remains the scientific engine.
- Original metadata, pickle files, databases, and recordings are immutable.
- Added columns and corrections are versioned overlays.
- MCP is a thin adapter around a reusable service.
- Important assumptions are previewed before execution.
- Results include provenance, warnings, units, exclusions, and artifact hashes.
- Raw behavioural rows are not returned to the model by default.

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

### Survival settings matching Ethoscopy 2.4 notebooks

Survival analysis requires Ethoscopy 2.4.0 in the running MCP process. Restart
or reconnect the server after upgrading. The default recipe calls
`km_death_table` and `km_survival_plot` with `moving`, secondary `walk`,
`time_window=24`, `proportion_immobile=0.01`, and `zero_run_hours=12`.
No `min_coverage` override is applied: incomplete final windows are evaluated
as in the notebook. Either movement column can trigger detection.

The table reports hours and the plot days from each subject's first retained
sample. `cumulative` must be false; old recipes with true must be re-previewed
with false. Baseline and explicit source-time alignment still apply before
analysis. These are not automatically times since injection.

Survival approval hashes include the loaded engine version and adapter revision,
so older cached results cannot substitute for a new 2.4 analysis. Previously
saved results remain available for retrieval.
