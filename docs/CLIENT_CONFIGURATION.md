# MCP client configuration

Install the package first using the [Quick Start](QUICKSTART.md).
`ethoscopy-mcp` runs locally over stdio; your client launches the executable.
Use absolute paths on the computer running the client, and create the artifact
output directory before connecting.

## Add to Codex

With the Codex CLI installed, register the local server using absolute paths:

```bash
codex mcp add ethoscopy \
  --env ETHOSCOPY_DATA_ROOTS=/absolute/path/to/experiments \
  --env ETHOSCOPY_ARTIFACT_ROOT=/absolute/path/to/analysis-output \
  -- /absolute/path/to/ethoscopy-mcp/.venv/bin/ethoscopy-mcp
```

Check the saved configuration with `codex mcp get ethoscopy`. Start a new Codex
session to use the server, then try a prompt from [Example Usage](../README.md#example-usage).

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

## Data and output directories

`ETHOSCOPY_DATA_ROOTS` contains trusted Ethoscopy pickle sources and CSV
overlays. Multiple roots use the platform path separator (`:` on Linux/macOS,
`;` on Windows). `ETHOSCOPY_ARTIFACT_ROOT` is an existing, writable output
directory, separate from your source data.

Set these variables in the client configuration even if you also export them
in a terminal; desktop applications may not inherit your shell environment.

## Check the connection

Ask the client to inspect a specific `.pkl` file inside a configured data root.
A successful inspection returns columns and metadata summaries. If connection
fails, check the executable path, installed dependencies, directory permissions,
and the client's MCP logs. The server uses stdio, so it does not provide a
browser URL or a web interface.

## Safety notes

- Never configure an upload directory or untrusted shared directory as a data
  root. Python pickle loading can execute code.
- Use the narrowest practical data root instead of a home directory or drive.
- Do not place credentials in the client configuration.
- Review `preview_analysis` assumptions, warnings, cohorts, transformations,
  and recipe hash before supplying that exact hash to `run_analysis`.
- `get_artifact` returns verified metadata and a local path, not file contents.

See the [quick start](QUICKSTART.md) for installation and the Python service
example.
