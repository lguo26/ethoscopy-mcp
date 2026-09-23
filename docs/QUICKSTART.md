# Quick Start

This pre-alpha package supports survival analysis, reviewed-endpoint sleep
summaries, and notebook-style sleep plots and comparisons. Start with a synthetic
example or connect an MCP client to trusted local Ethoscopy data.

## 1. Install

Use Python 3.12 or newer. On Linux or macOS:

```bash
git clone https://github.com/lguo26/ethoscopy-mcp.git
cd ethoscopy-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows PowerShell, create the environment with `py -3.12 -m venv .venv`,
activate it with `.\.venv\Scripts\Activate.ps1`, then run the same pip install command from the repository root.

## 2. Try a synthetic analysis

From the repository root, run either example with a new output directory:

```bash
python examples/synthetic_sleep/run_example.py /absolute/path/to/new-sleep-demo
python examples/synthetic_notebook_sleep/run_example.py /absolute/path/to/new-notebook-demo
```

The first example demonstrates sleep summaries with reviewed death/censor
endpoints. The second demonstrates heatmaps, sleep profiles, rebound comparison,
and deprivation QC using synthetic `stimulus_range` metadata. It includes a
Mann–Whitney test and an exclusion audit. These examples create their own data
and outputs; no experiment pickle or MCP client is needed.

See the [sleep example](../examples/synthetic_sleep/README.md) and
[notebook example](../examples/synthetic_notebook_sleep/README.md) for details.

## 3. Prepare your experiment

Use trusted Ethoscopy `.pkl` files containing behavioural data and associated
metadata. The server analyses existing pickles; it does not import raw ethoscope
databases. Sleep workflows require saved sleep annotations, normally `asleep`.

Choose an existing experiment directory and create a separate output directory.
For direct Python use, set the following environment variables; MCP clients
need the same values in their server configuration:

```bash
mkdir -p /absolute/path/to/analysis-output
export ETHOSCOPY_DATA_ROOTS="/absolute/path/to/experiments"
export ETHOSCOPY_ARTIFACT_ROOT="/absolute/path/to/analysis-output"
```

Multiple data roots use `:` on Linux/macOS and `;` on Windows.

## 4. Connect your client

Follow [Add to Codex](CLIENT_CONFIGURATION.md#add-to-codex) or
[Add to Claude Desktop](CLIENT_CONFIGURATION.md#add-to-claude-desktop).
The client starts the installed `ethoscopy-mcp` program and provides six tools:
`inspect_experiment`, `preview_analysis`, `run_analysis`, `run_kaplan_meier`,
`get_analysis`, and `get_artifact`. You can ask for analyses in plain language;
the client handles the tool calls.

## 5. Inspect, preview, and run

Start with a specific file:

> Inspect `/absolute/path/to/experiments/experiment.pkl`. Show the available
> groups, behavioural columns, and metadata.

Then choose an analysis:

| Recipe | Use it for | Additional inputs or decisions |
| --- | --- | --- |
| `survival` | Death and censoring tables, Kaplan–Meier plots, optional log-rank tests with Holm correction | Movement columns, death-detection settings, identity and time alignment; named comparisons and any filters or strata for statistical tests. |
| `sleep` | Interval-based sleep profiles and per-fly summaries | Reviewed death/censor endpoint CSV and sampling interval. |
| `sleep_notebook` | Heatmaps, time courses, rebound plots, optional Mann–Whitney tests | Endpoint policy, profile and quantification windows; deprivation metadata if QC is requested. |

For example:

> Preview sleep heatmaps and time-course plots for control and deprived flies.
> Use `stimulus_range` for deprivation QC, excluding deprived flies with more
> than 5% sleep during that window. Show the resolved windows and exclusions.

The preview identifies assumptions, cohort counts, warnings, and a recipe hash.
Resolve missing metadata and time alignment, review the preview, and then ask
the client to run that recipe. `run_analysis` requires the exact fresh preview
hash and revalidates the inputs before execution.

Deprivation windows have no fixed default. Rebound analysis requires recorded
post-deprivation data and an explicitly aligned quantification window. Manual
death corrections can be supplied as reviewed endpoints for sleep; the survival
recipe does not automatically apply those corrections.

See [sleep summaries](SLEEP_ANALYSIS.md), [notebook-style analysis](NOTEBOOK_SLEEP.md),
and [tool design](TOOLS.md) for the complete recipe contracts.

## 6. Retrieve results

Ask the client to retrieve the completed analysis and its plots and tables.
Each run saves requested artifacts, `provenance.json`, and `run-result.json`
inside the configured artifact root. `get_artifact` returns verified metadata
and a local path. Repeating an identical run verifies and reuses its results.

## Use the Python service directly

With the environment variables above set, inspection also works without an MCP
client:

```python
from pathlib import Path
from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings

service = EthoscopyService(Settings.from_env())
manifest = ExperimentManifest(
    experiment_id="example-001",
    source_paths=(Path("/absolute/path/to/experiments/experiment.pkl"),),
)
summary = service.inspect_experiment(manifest)
print(summary.model_dump_json(indent=2))
```

The runnable synthetic examples above show complete recipe construction,
preview, execution, and artifact retrieval using the same service.

## Development checks

From the repository root with dependencies installed:

```bash
python -m unittest discover -s tests -v
```

Tests use synthetic fixtures; private experiment data are not included.
