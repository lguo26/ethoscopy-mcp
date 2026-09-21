# Data safety

## Immutable originals

```text
original file
    │ read only
    ▼
working copy + metadata overlay
    ▼
approved recipe
    ▼
new analysis run and artifacts
```

Legitimate derived columns include canonical identities, time since injection,
treatment labels, inclusion flags, and exclusion reasons. They must be recorded
as versioned transformations with a parent source hash.

## Provenance minimum

Every completed analysis records:

- analysis and recipe IDs;
- input and metadata-overlay hashes;
- Ethoscopy version and Git commit when available;
- parameters, units, grouping, and filters;
- included and excluded animals;
- missingness, interpolation, events, and censoring when relevant;
- warnings and unresolved assumptions;
- output artifact hashes; and
- execution timestamp.

## Model context

Return compact schemas, summaries, warnings, and artifact references. Do not
place millions of behavioural rows or sensitive metadata into model context.
