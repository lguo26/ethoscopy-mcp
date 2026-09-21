# Roadmap

## Phase 1 — Service contracts

- Source manifest and trusted-root configuration
- Metadata-overlay schema
- Analysis recipe schema
- Structured results and warnings
- Artifact and provenance schemas

## Phase 2 — Scientific workflows

- Experiment inspection and validation
- Sleep summary and profile
- Activity profile
- Survival analysis
- Immune/S. aureus regression tests using private external fixtures

The first acceptance test should reproduce the confirmed combined 0821 male
survival cohort: PBS 20 animals with one detected death and S. aureus 20 animals
with two detected deaths, while preserving original recording IDs.

## Phase 3 — MCP adapter

- [x] Local stdio transport
- [x] Typed tool inputs and outputs
- [x] Preview and approval workflow
- [x] Verified artifact-reference retrieval
- [ ] Compact public error codes and client-facing guidance

## Phase 4 — Public release

- [x] Synthetic end-to-end example
- [x] Installation and client configuration guides
- [x] Continuous integration for Python 3.12–3.14
- [x] Initial repository data and credential audit
- [x] License review and full license file
- [ ] Enable GitHub private vulnerability reporting
- [ ] Initial tagged release
