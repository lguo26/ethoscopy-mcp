# Experiment work records and offline dashboards

Registration is opt-in. Private work records live at
`ETHOSCOPY_ARTIFACT_ROOT/experiment_registry/records.json`; the generated
`dashboard.html` sits beside them. No research records belong in the code
repository. Source pickles and metadata are never edited by these tools.

## Tools and workflow

1. `register_experiment(record, expected_revision=0)` creates an experiment.
   Use its current revision from `list_experiments()` to update it. Registration
   stores the design, scientific question, next action, notes, and explicit
   recording/review status. Folder and declared sources must be trusted; source
   files must be inside the experiment folder. Planned/manual experiments can
   omit source paths. Conditions can remain empty pending review.
2. Run the usual inspect → preview → exactly approved analysis workflow.
   Once an analysis has completed and its canonical artifacts and adjacent exports
   have been verified, a matching registered experiment ID and source-path set
   receives the result, and the dashboard rebuilds automatically. Unregistered
   analyses keep their existing behavior. This applies to the service's survival
   and sleep execution paths, including the `run_kaplan_meier` MCP tool.
3. `link_experiment_analysis(analysis_id)` attaches an already completed analysis,
   using its verified provenance sources, then rebuilds the dashboard. Register
   the experiment first. Linking does not rerun scientific analysis.
4. `build_experiment_dashboard()` generates HTML on demand, including after an
   edit to work records. Open the returned local path and refresh the browser
   after subsequent rebuilds. No server or external assets are required for the
   dashboard and PNG previews; result-file links are relative to the artifact
   directory, so preserve that directory structure.

Folder creation alone does not discover/register an experiment. This first
version deliberately requires explicit registration; automatic discovery is
not implemented. It is also not a filesystem watcher or acquisition monitor.

## Example registration

Paths and identities below are synthetic placeholders. Use actual trusted paths.

```json
{
  "record": {
    "experiment_id": "synthetic-dose-study",
    "title": "Synthetic dose comparison",
    "experiment_date": "2025-01-01",
    "folder": "/trusted/synthetic-dose-study",
    "source_paths": ["/trusted/synthetic-dose-study/recordings.pkl"],
    "question": "Does inoculum concentration affect survival?",
    "recording_status": "unknown",
    "review_status": "needs_review",
    "next_action": "Confirm injection time and recording completion",
    "conditions": [
      {"condition_id": "pbs", "treatment": "PBS", "is_control": true,
       "food": "Normal food", "temperature_c": 25, "sex": "male", "planned_n": 20},
      {"condition_id": "low", "treatment": "Synthetic bacteria", "od600": 0.01,
       "food": "Normal food", "temperature_c": 25, "sex": "male", "planned_n": 20},
      {"condition_id": "high", "treatment": "Synthetic bacteria", "od600": 0.1,
       "food": "Normal food", "temperature_c": 25, "sex": "male", "planned_n": 20}
    ]
  },
  "expected_revision": 0
}
```

`recording_status` is `unknown`, `planned`, `recording`, or `finished`.
`review_status` is `needs_review`, `confirmed`, or `reviewed`. Analysis completion
changes neither. Review and recording status are not inferred from metadata
modification times, tracking duration, or censored flies. Exclusion decisions
remain in the approved analysis recipe, not the experiment register.

Conditions have stable IDs, treatment, method, food, temperature, sex, OD600,
control flag, OA route, and planned count. Missing values remain unknown.
The tree groups method → food → temperature → treatment → OD600 → date/sex.
Control conditions omit the dose branch. Unknown doses have a separate branch;
OA routes are recorded explicitly and never inferred from treatment names.

## Counts and current results

The dashboard filters condition rows and displays planned counts. Verified group
outcomes, plots, and artifact links appear separately for each analysis, preserving
its full cohort. It does not guess how outcome groups map to registered conditions
or sum overlapping runs as animals. The latest successfully linked run per
`recipe_id` replaces the previous link; different recipe IDs remain distinct.
Keep a stable recipe ID for revisions of one analysis. Re-linking the same analysis
is idempotent and does not advance the revision. Historical canonical run folders
are retained. The registered source set cannot change once results are attached;
use a new experiment ID for a different source set.

Every explicit record edit and new result link increments the revision. Atomic
writes and a local file lock serialize changes; stale expected revisions fail.
The registry uses the existing local Linux filesystem model (`fcntl` locking).
All linked artifacts are reverified before dashboard rendering. PNG previews
are embedded. User labels are escaped, including script terminators in embedded
JSON. Generated files and registry paths reject symlinks.

If automatic registry/dashboard updating fails **after analysis succeeds**, the
returned analysis includes `dashboard_warning` and remains retrievable. On success,
`dashboard_path` identifies the generated page. These are response fields, not
changes to immutable canonical analysis artifacts. Repair the registry/output
problem and use `link_experiment_analysis` or `build_experiment_dashboard` to retry.
A link can be persisted even if rendering subsequently fails; the old dashboard
is kept until a successful rebuild. `list_experiments` returns saved references;
use `get_analysis` or a dashboard rebuild to reverify their contents.

Restart/reconnect the MCP server after installing updated code to load the new
tool schemas. Existing project-specific HTML dashboards are not migrated or
modified automatically; register their experiments to use this generic dashboard.
