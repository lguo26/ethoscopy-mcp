# ethoscopy-mcp

An open-source tool that connects AI assistants to behavioural analysis with
[Ethoscopy](https://github.com/gilestrolab/ethoscopy).

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![CI](https://github.com/lguo26/ethoscopy-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/lguo26/ethoscopy-mcp/actions/workflows/ci.yml)

`ethoscopy-mcp` lets AI assistants inspect your experiments and run sleep and
survival analyses with Ethoscopy on your computer. It connects through the
Model Context Protocol (MCP), which lets AI assistants use external tools.
The assistant receives summaries and paths to result files, not raw behavioural
data. An analysis **recipe** records the settings and outputs you request.

[Supported Analyses](#supported-analyses) · [Reproducibility](#reproducibility) · [Quick Start](#quick-start) · [Available Tools](#available-tools) · [Example Usage](#example-usage)

## Features

- **Reproducibility:** saved settings, unchanged source files, and a record of
  how each result was produced.
- **Sleep analysis:** heatmaps, sleep time courses, and per-fly summaries.
- **Sleep-deprivation quality checks:** use recorded deprivation times and
  report which flies were excluded and why.
- **Survival analysis:** Kaplan–Meier curves, death and censoring tables, and
  log-rank comparisons with Holm correction for multiple tests.
- **Group comparisons:** sleep and rebound quantification, with optional
  Mann–Whitney tests.

## Supported Analyses

| Analysis | Recipe | What you can generate |
| --- | --- | --- |
| [Sleep summaries](docs/SLEEP_ANALYSIS.md) | `sleep` | Sleep profiles, per-fly summaries, and group summaries using reviewed death or censoring times. |
| [Sleep plots and deprivation analysis](docs/NOTEBOOK_SLEEP.md) | `sleep_notebook` | Heatmaps, sleep time courses, rebound comparisons, optional Mann–Whitney tests, and sleep-deprivation quality checks. |
| [Survival analysis](docs/SURVIVAL_ANALYSIS.md) | `survival` | Death or censoring times for every animal, Kaplan–Meier plots and curve tables, confidence intervals, and numbers still at risk. Optional log-rank tests can account for temperature or other groups and apply Holm correction. |

## Reproducibility

Each analysis follows **inspect → preview → approve → run → view results**.
The service saves the settings and file checks needed to review or repeat it.

- **Saved settings:** the recipe records which animals to include, how to group
  them, how to align recording times, and which analyses and outputs to produce.
- **File checks:** a hash is a digital fingerprint of a file or recipe. The
  service checks these fingerprints before running to confirm that the inputs
  and settings still match the approved preview. Source files stay unchanged.
- **Analysis record:** `provenance.json` records the recipe, file fingerprints,
  software versions, and warnings. This record is called provenance.
- **Saved results:** identical runs reuse existing results after checking that
  the files are unchanged. Plots, tables, and the analysis record are also
  copied beside your input file.

Keep the inputs, identity mappings, recipe, and software environment to repeat
an analysis. The record lists software versions but does not save a complete
copy of the environment. Survival recipes record comparisons, filters, and
strata (groups such as temperature that a statistical test accounts for).
Log-rank results include Holm-adjusted p-values.

Newly generated sleep plots may differ slightly because confidence intervals
can use random resampling and plotted points may be randomly offset for
readability. Previously saved results are checked for changes before reuse.
Reproducing a result does not rule out confounding or show that the statistical
assumptions are appropriate.

## Status

Version `0.1.0a1` is an early development release. The MCP server
supports survival analysis with complete event/censor tables, Kaplan–Meier
curves, and optional stratified log-rank tests with Holm correction. Sleep
workflows include reviewed-endpoint summaries, notebook-style plots, rebound
comparisons, and optional Mann–Whitney tests.

You can review the settings before running an analysis. Source files stay
unchanged, and results include a record of how they were produced. You can
supply reviewed death or censoring times; the original estimates are kept.

Sleep-deprivation quality checks use the deprivation schedule you set on the
Ethoscope when starting a recording, saved in its recording metadata. They
report which flies were excluded and why. Activity analysis and other
planned features are on the [roadmap](docs/ROADMAP.md).

Release checks are tracked in the [release checklist](docs/RELEASE_CHECKLIST.md).
This release is intended for researchers trying the documented analyses with
local data from a trusted source.

## Prerequisites

- **Python 3.12 or newer**, with an isolated virtual environment. Installing
  this package installs its declared dependencies, including Ethoscopy (`==2.4.0`)
  and MCP (`>=2,<3`).
- **An AI client that can start local MCP tools**, such as Codex or Claude
  Desktop, or Python to run analyses directly.
- **Trusted local Ethoscopy pickle files** with the behavioural columns and
  metadata required by your analysis. Sleep workflows require saved sleep
  annotations. Deprivation checks also need the recording metadata containing
  the deprivation schedule, either saved with the data or supplied as a metadata CSV.
- **Configured local directories:** set `ETHOSCOPY_DATA_ROOTS` to your experiment
  directories and `ETHOSCOPY_ARTIFACT_ROOT` to an existing, writable output
  directory.

Some workflows also require metadata CSV files for animal identity mapping or
reviewed death or censoring times. Censoring means an animal was observed up to
a known time without a detected death. See the [quick start](docs/QUICKSTART.md)
for installation and [client configuration](docs/CLIENT_CONFIGURATION.md) for
connecting a client.

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

Ask in plain language. You do not need to name tools or write a recipe:

- “Show me the groups in this experiment.”
- “Run survival analysis on `/path/to/experiment.pkl`.”
- “Compare survival between the treatment groups. Are the differences significant?”
- “Run sleep analysis on this file.”
- “Compare sleep between control and sleep-deprived flies.”
- “Compare these results with the previous analysis in the same folder.”
- “Show me the plots and results.”

Provide the file path with your first request. The assistant can use it for
follow-up requests, inspect the metadata, and prepare the analysis settings.
It will ask if important information is missing and show a preview before
running. You can also specify settings or ask it to use those in your notebook.

## Available Tools

| Tool | Purpose |
| --- | --- |
| `inspect_experiment` | Summarize input files, behavioural columns, and metadata. |
| `preview_analysis` | Check settings and show the selected animal groups, assumptions, and warnings. |
| `run_analysis` | Execute the recipe using its approved preview hash. |
| `run_kaplan_meier` | Run Kaplan–Meier analysis with a survival recipe and its approved preview hash. |
| `get_analysis` | Get a completed run's summary and paths to result files. |
| `get_artifact` | Check a result file and return its details and local path. |

All six tools are available through MCP. Python users can call the underlying
analysis service directly. Runs check the inputs, work on copies, and save
results with an analysis record. The hash returned by `preview_analysis`
identifies the exact recipe passed to a run tool; your AI client handles this
value when calling the tools.

### Where results are saved

Results are stored in `ETHOSCOPY_ARTIFACT_ROOT`. Each run also copies its outputs
to an `<analysis_id>_exports` folder beside the first input pickle file. The
response gives this folder as `export_directory`. The input folder must be
writable; when an analysis uses several input folders, only the first receives
this copy.

Identical runs reuse saved results after checking them. Changed or missing
export files cause an error instead of being silently replaced. If copying
fails, the original results remain in `ETHOSCOPY_ARTIFACT_ROOT` for retrieval.
Restart the MCP server after updating the package to load the new version.

## Principles

- Ethoscopy remains the scientific engine.
- Original metadata, pickle files, databases, and recordings stay unchanged.
- Added information and corrections are recorded separately.
- MCP and Python use the same analysis code.
- Important assumptions are previewed before execution.
- Results include settings, file checks, warnings, units, and exclusions.
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
toolbox that performs this project's scientific calculations. `ethoscopy-mcp`
lets AI clients run those analyses locally. It does not replace Ethoscopy or
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
