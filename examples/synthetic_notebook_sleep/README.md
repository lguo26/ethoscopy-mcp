# Notebook-style synthetic sleep analysis

```sh
MPLBACKEND=Agg python examples/synthetic_notebook_sleep/run_example.py /tmp/notebook-sleep-demo
```

Use a new output directory. Four synthetic flies have 60-second stored sleep
annotations. Machine `stimulus_range` metadata resolves to hours 1–2; deprivation QC removes the unsuccessful deprived
fly while retaining both controls. Hours 2–3 are quantified using Ethoscopy's
public `plot_quantify`, with an explicit two-sided exact Mann–Whitney test.

Outputs include heatmaps, rolling profiles, rebound quantification, statistics,
per-fly results, an exclusion audit, and complete recipe/manifest JSON for MCP.
No real experiment data are included. See [workflow documentation](../../docs/NOTEBOOK_SLEEP.md).
