"""Resolve experiment-level exclusions without inferring biological decisions."""
from __future__ import annotations

import hashlib
import json

from ethoscopy_mcp.schemas import DecisionReview, ValidationWarning, WarningSeverity


def matching_decisions(store, experiment_id, sources):
    """Match identity, canonical paths or identical bytes, including changed sources.

    An active decision is never lost merely because a client chooses a new name.
    Arbitrarily renamed AND edited files require explicit experiment registration.
    """
    paths = {s.path for s in sources}
    hashes = {s.sha256 for s in sources}
    result = []
    for entry in store.list().experiments:
        latest = {}
        for decision in entry.exclusion_decisions:
            latest[decision.decision_id] = decision
        for decision in latest.values():
            history = [d for d in entry.exclusion_decisions if d.decision_id == decision.decision_id]
            if (entry.record.experiment_id == experiment_id
                or any(s.path in paths or s.sha256 in hashes for d in history for s in d.sources)):
                result.append(decision)
    return tuple(sorted(result, key=lambda d: (d.experiment_id, d.decision_id)))


def resolve_decisions(decisions, sources, recipe, mapping):
    from ethoscopy_mcp.preview import _apply_filters

    warnings, reviews = [], []
    resolutions = {}
    for resolution in recipe.decision_resolutions:
        key = (resolution.experiment_id, resolution.decision_id)
        if key in resolutions:
            raise ValueError("Duplicate decision resolution")
        resolutions[key] = resolution
    known = {(d.experiment_id, d.decision_id) for d in decisions}
    if set(resolutions) - known:
        raise ValueError("Recipe refers to an unknown or inapplicable reviewed decision")
    overlay = recipe.identity_overlay
    source_col = overlay.source_id_column
    keys = list(overlay.individual_key_columns)
    selected = _apply_filters(mapping, recipe.cohort_filters)
    selected_keys = set(selected[keys].itertuples(index=False, name=None))
    by_id = {str(row[source_col]): tuple(row[k] for k in keys) for _, row in mapping.iterrows()}
    exclusions = list(recipe.exclusions)
    expected_hashes = sorted(s.sha256 for s in sources)

    def block(message):
        warnings.append(ValidationWarning(code="reviewed_exclusion_conflict",
            severity=WarningSeverity.ERROR, message=message))

    for decision in decisions:
        key = (decision.experiment_id, decision.decision_id)
        resolution = resolutions.get(key)
        if resolution and resolution.revision != decision.revision:
            block(f"Decision {key} changed to revision {decision.revision}; review again.")
        if decision.status == "retired":
            if resolution:
                block(f"Decision {key} is retired; remove its stale resolution.")
            reviews.append(DecisionReview(decision=decision, status="retired"))
            continue
        if expected_hashes != sorted(s.sha256 for s in decision.sources):
            block(f"Sources for decision {key} changed or are incomplete. Reconfirm applicability "
                  "by recording a new decision version against the registered current sources.")
            reviews.append(DecisionReview(decision=decision, status="source_changed", resolution=resolution))
            continue
        if any(e.original_id not in by_id for e in decision.exclusions):
            block(f"Decision {key} contains IDs missing from the identity mapping.")
            reviews.append(DecisionReview(decision=decision, status="unresolved", resolution=resolution))
            continue
        applicable = [e for e in decision.exclusions if by_id[e.original_id] in selected_keys]
        affected = tuple(str(row[source_col]) for _, row in mapping.iterrows()
                         if tuple(row[k] for k in keys) in {by_id[e.original_id] for e in applicable})
        status = "outside_cohort" if not applicable else "unresolved"
        if applicable:
            if resolution is None:
                block(f"Prior exclusion {key} revision {decision.revision} applies to {affected}. "
                      "Choose apply or sensitivity_include with a reason in decision_resolutions.")
            elif resolution.revision == decision.revision:
                status = "applied" if resolution.action == "apply" else "sensitivity_include"
                if resolution.action == "apply":
                    existing = {by_id.get(e.original_id) for e in exclusions}
                    for exclusion in applicable:
                        if by_id[exclusion.original_id] not in existing:
                            exclusions.append(exclusion)
                            existing.add(by_id[exclusion.original_id])
                # Inclusion conflicts checked after all decisions have been resolved.
        reviews.append(DecisionReview(decision=decision, status=status,
                                      affected_source_ids=affected, resolution=resolution))
    excluded_keys = {by_id.get(e.original_id) for e in exclusions}
    for review in reviews:
        if review.status == "sensitivity_include" and any(by_id[x] in excluded_keys for x in review.affected_source_ids):
            block("Sensitivity inclusion conflicts with another applied decision or explicit exclusion.")
    effective = recipe.model_copy(update={"exclusions": tuple(exclusions)})
    return effective, tuple(reviews), tuple(warnings)


def bind_decisions(base_hash, reviews):
    if not reviews:
        return base_hash
    payload = {"analysis_hash": base_hash, "reviewed_decisions": [r.model_dump(mode="json") for r in reviews]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
