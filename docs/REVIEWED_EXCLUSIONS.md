# Persistent reviewed survival exclusions

Exclusions in one analysis recipe do not automatically become decisions for later analyses. Use `record_exclusion_decision` to explicitly save a researcher-confirmed decision in the private experiment registry. Never infer an exclusion from an estimated time-zero death alone.

## Record a decision

Register an experiment with its source paths, then call:

```json
{
  "experiment_id": "example-experiment",
  "expected_revision": 1,
  "decision": {
    "decision_id": "reviewed-tracking-exclusions",
    "scope_description": "Reviewed exclusions for this survival dataset",
    "exclusions": [{"original_id": "example-animal-id", "reason": "Researcher-confirmed tracking failure"}],
    "confirmed_by": "Researcher name",
    "confirmation_note": "Confirmed during review; explain when/how",
    "originating_analysis_id": null,
    "status": "active"
  }
}
```

Confirmation fields are caller assertions, not authenticated user signatures. The service validates that IDs exist in registered metadata and captures the current source fingerprints. Decision IDs are scoped to the registered experiment. `expected_revision` is the current experiment revision, including any linked-run updates. Each recording appends a decision revision and preserves previous decisions and linked runs. Ordinary experiment edits cannot erase decisions. Record status `retired` as a new version to withdraw a decision.

Stored privately under `ARTIFACT_ROOT/experiment_registry/records.json`. This is not embedded into source pickles or a global rule about time-zero deaths. Do not commit private records to Git.

## Inspect, resolve and preview

Inspection surfaces latest matching `reviewed_exclusions`. Survival preview returns `decision_reviews`. Records are discovered by experiment ID, overlapping canonical source paths or matching source bytes, so a renamed experiment or an identical copied file does not hide them. Arbitrarily renamed AND modified files cannot be identified automatically without experiment registration.

An applicable active decision blocks approval until the recipe includes a resolution:

```json
"decision_resolutions": [{
  "experiment_id": "example-experiment",
  "decision_id": "reviewed-tracking-exclusions",
  "revision": 1,
  "action": "apply",
  "reason": "Retain the researcher's reviewed exclusions"
}]
```

`apply` adds applicable exclusions to the returned `effective_survival_recipe`; preview counts and execution use this recipe. All mapped segments of the animal are excluded. Decisions outside the filtered cohort are displayed without removing other animals.

For an intentional all-flies sensitivity analysis, choose `sensitivity_include` and supply the researcher's reason. This preserves the underlying decision. A conflicting explicit exclusion or another applied decision blocks execution. Unknown or stale references are rejected. The client should present the proposed exclusions/resolution to the researcher; hashes alone do not prove human review occurred.

## Source changes and execution

The current input hash multiset must equal the decision's source hash multiset. Changed or incomplete source sets block execution pending applicability review. For changed bytes at registered paths, record a new decision version after researcher review. For a new source-path set, register a new experiment and explicitly retire/supersede the old decision as appropriate; do not bypass a conflict with a different experiment name.

The preview hash binds decision snapshots and resolutions. A later decision revision invalidates an earlier approval. Registry writes use a lock; survival execution holds that lock through fresh preview and execution, then releases it before result linking/dashboard updates. Long runs can delay concurrent registry writes. Provenance records decision snapshots, resolutions and effective exclusions.

## Scope and limitations

This first implementation applies persistent decisions to survival recipes only. Sleep inspections may display the records, but sleep exclusion mechanisms remain unchanged. Source-file integrity checks retain their existing limitations; the registry lock is not a universal filesystem snapshot. There is no automatic authentication, approval UI, biological adjudication, or general rule to discard time-zero estimates. No analysis is rerun merely by recording a decision.
