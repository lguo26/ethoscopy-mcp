# MCP client configuration

`ethoscopy-mcp` is a local stdio server. Install it in an isolated environment
and configure the client to launch the absolute path to its executable.

Many MCP clients represent local servers with a configuration shaped like this:

```json
{
  "mcpServers": {
    "ethoscopy": {
      "command": "/absolute/path/to/venv/bin/ethoscopy-mcp",
      "env": {
        "ETHOSCOPY_DATA_ROOTS": "/absolute/path/to/trusted/experiments",
        "ETHOSCOPY_ARTIFACT_ROOT": "/absolute/path/to/local/artifacts"
      }
    }
  }
}
```

The exact settings filename and outer keys depend on the MCP client. Keep both
directories local. The data root may contain trusted pickle sources and CSV
overlays; the artifact root must already exist and should be a separate output
directory.

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
