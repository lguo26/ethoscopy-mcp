# Short analysis requests

Users can say “Run survival analysis on [folder/pickle]” or “Run death alignment analysis on [folder/pickle]”. Use established project settings and identity mappings when available; a folder alone does not establish whether recordings contain the same animals. Keep sources immutable and save the exact recipe, source hashes and output provenance. Existing user authorization applies; still preview and validate the exact recipe before execution.

## Run survival analysis

1. Inspect trusted sources, metadata, timing and animal identities.
2. Preview the survival recipe with `preview_analysis()`.
3. Execute `run_kaplan_meier()` with the matching preview hash.
4. Request `primary` CSV named `km_death_table`, `individuals` CSV, `kaplan_meier` CSV, primary PNG/SVG plots, and requested statistical comparisons.
5. Verify artifacts and save the methods and results.

The service calls the recipe-selected `km_death_table()` and `km_survival_plot()` implementation. Backend `user_km_76e23fd` shares the user `_build_km_survival_table()` detector; backend `ethoscopy_3` uses installed `survival_table()`. Use the death-only CSV for estimated deaths and retain full event/censor records for surviving controls.

## Run death alignment analysis

Reuse a compatible, hash-verified MCP survival run, or run survival first. Use `ethoscopy_mcp.align_to_death()` from the Python package with the MCP death-only times, full endpoint recording bounds and correctly mapped/time-aligned observations. This is not a standalone server tool or recipe. Do not represent downstream plotting or PBS matching as a server capability.

Use the project's documented windows, coverage criteria and aggregation. Where those settings are absent, state the chosen settings before running. Common outputs are hourly curves, 24/48-hour heatmaps, per-animal summaries and matched controls where available. Controls must be observed and eligible at the case's anchor; do not assign a death to a censored animal. Keep independent experiments and temperatures identifiable.

The service selects sleep rule `k`. Stored annotations must be checked; `etho.set_sleep_rule("k")` does not recalculate an existing pickle. Death detection uses the recipe's movement settings independently of sleep scoring. Do not silently substitute `walking` for the older `walk` detector column.

See [survival settings](SURVIVAL_ANALYSIS.md) and [alignment API](DEATH_ALIGNMENT.md). Project-specific experiment dates, PBS availability and coverage thresholds belong in the project's methods, not universal server defaults.

## Verify the intended implementation

When a user specifies a custom `km_death_table()`, inspect its source revision and detector semantics before assuming equivalence with the installed package. A method with the same name may call a different backend or enforce different data coverage. Record the exact implementation and do not silently substitute it. The integration provides the pinned `user_km_76e23fd` backend as well as the installed `ethoscopy_3` backend. Select explicitly in the recipe and retain the implementation provenance.
