# Roadmap

## Phase 1 — Service contracts

- [x] Source manifest and trusted-root configuration
- [x] Metadata-overlay schema
- [x] Survival-analysis recipe schema
- [x] Structured results and warnings
- [x] Artifact and provenance schemas

## Phase 2 — Scientific workflows

- [x] Experiment inspection and validation
- [ ] Sleep summary and profile
- [ ] Activity profile
- [x] Transfer-aware survival analysis
- [x] Immune/S. aureus regression using a private external fixture

The private acceptance run reproduces the confirmed combined 0821 male survival
cohort: PBS 20 animals with one detected death and S. aureus 20 animals with two
detected deaths, while preserving the original source files and recording IDs.

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
- [ ] Change the GitHub repository visibility to public
- [ ] Enable GitHub private vulnerability reporting
- [ ] Confirm CI on the sanitized public branch
- [ ] Initial tagged release

## Next work

Work in this order so each milestone leaves a usable, testable system.

### 1. Complete the `0.1.0a1` public pre-release

- Make the repository public and enable private vulnerability reporting.
- Confirm all Python 3.12–3.14 CI jobs pass on the rewritten history.
- Create a signed or annotated `v0.1.0a1` tag and GitHub pre-release.

Acceptance: a new user can clone the repository, install it in a fresh virtual
environment, and run all tests without access to private research data.

### 2. Validate one real MCP client workflow

- Connect a compatible desktop or command-line MCP client over stdio.
- Inspect the committed synthetic experiment.
- Preview and approve its survival recipe using the exact recipe hash.
- Retrieve the completed analysis and artifact references through MCP.
- Document the verified client configuration and troubleshooting notes.

Acceptance: the complete inspect → preview → approve → run → retrieve flow works
without directly importing the Python service.

### 3. Stabilize public errors and compatibility

- Add compact, documented error codes for configuration, unsafe paths, invalid
  experiments, changed sources, approval mismatch, and artifact verification.
- Ensure MCP errors do not expose arbitrary local paths or raw data.
- Add explicit compatibility tests for the supported Ethoscopy 2.2–2.4 APIs.

Acceptance: client applications can handle expected failures without parsing
Python exception text.

### 4. Strengthen scientific regression coverage

- Add richer synthetic survival fixtures with detected deaths and censoring.
- Re-run the private combined 0821 regression against supported Ethoscopy
  versions without adding its data or outputs to Git.
- Record expected cohort counts, deaths, censoring, units, and artifact hashes.

Acceptance: dependency updates cannot silently change the validated survival
outcome.

### 5. Add workflows one at a time

- Implement sleep summary/profile as the next typed recipe.
- Follow with activity profiles after sleep validation is complete.
- Apply the same preview, exact-hash approval, immutable-source, artifact, and
  provenance rules used by survival analysis.

Acceptance: each workflow has synthetic examples, service tests, MCP contract
tests, and documented scientific assumptions before the next workflow starts.
