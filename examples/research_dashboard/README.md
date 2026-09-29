# Two-page research dashboard

A portable example of the visual research notebook: matching page navigation,
experiment/reference icons, formatted Markdown reports, and a figure dialog with
zoom, scrolling, PNG/SVG downloads, Escape dismissal and focus restoration.
All experiment values and plots are synthetic. The Fly Cell Atlas citation is
an example reference; no downloaded research dataset is redistributed.

## Build and open

From the repository root, with Python 3.12 or newer:

```sh
python -m pip install -e '.[dashboard]'
python examples/research_dashboard/build.py
```

Open `examples/research_dashboard/generated/index.html` in a browser. Both pages,
reports and the viewer work offline; external paper links need internet access.
The generated directory is ignored by Git. Serve that directory with a static
HTTP server for shared access. Nothing is deployed by this command.

## Use with your own results

Copy `source/` to a **private directory outside this repository**. Edit its
`index.html` and `reference_results.html`, add reports and selected exports, then:

```sh
python examples/research_dashboard/build.py \
  --source /path/to/private/dashboard-source \
  --output /path/to/private/dashboard-site
```

Source and output directories must not overlap. Use a dedicated output directory.
The builder copies linked Markdown, CSV, CSS and PNG/SVG files within the source
root (up to 10 MB each), and follows supported links inside Markdown reports.
Existing PNG/SVG counterparts are included for downloads. Missing or unsupported
report targets and links outside the source root become “local archive” labels;
`archive_links.json` lists them. Unreferenced files are not copied. Old outputs
are not pruned; build into a new directory when removing previously served files.

Place reference reports in a `reference/` directory to make their “Back to
results” link return to Reference data; other reports return to Experiments.
The shared stylesheet in `source/assets/dashboard.css` keeps both navigation
bars consistent. `figure_viewer.html` supplies the viewer for pages and reports.

Only use **trusted HTML, Markdown, CSS and SVG**. This is an offline publishing
tool, not an upload service or HTML sanitizer. Select source files deliberately
before hosting them. The manifest records source and published hashes for
traceability; it does not verify scientific results or replace MCP provenance.

## Relationship to ethoscopy-mcp

This example is a presentation layer, separate from the service's existing
`build_experiment_dashboard` tool. It does not change tool schemas, execute
analyses, migrate existing work records, or automatically synchronize with MCP.
Use verified MCP exports as selected inputs when adapting it. Keep recording
status, experimental exclusions and scientific interpretations in the underlying
work records. The figure viewer never changes data or reruns an analysis.
