# Public alpha release checklist

Target: `v0.1.0a1`, a prerelease for researchers evaluating trusted local
Ethoscopy survival and sleep workflows. This checklist separates implementation
checks from GitHub settings and publication steps.

## Local verification

- [x] Install the package and dependencies in a fresh virtual environment.
- [x] Run `python -m pip check` without dependency conflicts.
- [x] Complete the full test suite in that fresh environment.
- [x] Execute the synthetic survival example through export creation.
- [x] Document Ethoscopy 2.4.0 as the required engine version.
- [x] Provide synthetic examples, client setup, workflow guides and limitations.
- [x] Include a license, contribution guide and security reporting policy.
- [x] Review reachable Git history for research-data files, private paths and
  common credential patterns.

Evidence recorded on 22 September 2026:

- A fresh Python 3.14.7 environment installed the package from the repository,
  including Ethoscopy 2.4.0 and MCP 2.2.0; `pip check` found no broken requirements.
- All 46 tests passed in that environment, including MCP contract tests, when
  run outside the restricted agent sandbox. The sandboxed runs experienced
  transport delays; they are not counted as successful full-suite runs.
- The synthetic survival example completed with two controls censored and one
  detected death plus one censored animal in the synthetic treatment group.
  Its obsolete 12-hour detection window was changed to the documented 24-hour
  default. CI now executes this example, and preview rejects windows below 24
  because the adapter uses Ethoscopy's fixed default resolution of 24.
- A pattern-based audit of all 19 commits reachable from local refs at `1fbb360`
  examined 124 distinct blobs. No matching private-path or credential patterns,
  research pickle/database files, or generated research-output directories were
  found. This is a bounded scan, not a guarantee that all sensitive information
  has been detected; new commits and newly fetched refs need review too.
- Before publication, review prose for unpublished research results as well as
  file contents and names. Private acceptance results were removed from the
  current roadmap; earlier commits may still contain descriptive research text.

## GitHub release gates

- [ ] Confirm the exact release commit passes all hosted Python 3.12, 3.13 and
  3.14 jobs. Local Python 3.14 checks do not establish the other versions.
- [ ] Review repository visibility and make it public when publication is intended.
- [ ] Enable GitHub private vulnerability reporting and verify its availability.
- [ ] Create an annotated or signed `v0.1.0a1` tag at the verified commit.
- [ ] Publish a GitHub prerelease with scope, installation steps, test evidence
  and known limitations.

Repository settings and hosted CI status were not verified during the local
review: the unauthenticated GitHub API request returned HTTP 403. Checklist
entries remain open until their actual state is confirmed.

## Repeatable verification commands

From a fresh checkout and virtual environment:

```sh
python -m pip install .
python -m pip check
MPLBACKEND=Agg python -m unittest discover -s tests -v
MPLBACKEND=Agg python examples/synthetic_survival/run_example.py
MPLBACKEND=Agg python examples/synthetic_survival/run_example.py --approve
```

Use synthetic data to check the complete client workflow: inspect → preview →
approve the exact hash → run → retrieve. Confirm plots, tables and provenance
are accessible, including the export folder beside the first source pickle.

## Initial release notes

- Survival analysis with movement-based death detection, death-table CSVs,
  Kaplan–Meier curves and group death/censor counts.
- Sleep summaries using reviewed endpoints, plus notebook-style sleep plots,
  deprivation quality checks and optional two-group comparisons.
- Explicit recipes, hashed inputs, immutable sources, recorded provenance and
  verified artifact retrieval through both Python and local stdio MCP.
- Automatic exports into a run-specific folder beside the first source pickle.

Limitations: trusted pickles only; local filesystem access; writable source
folder required for exports; Ethoscopy 2.4.0 required. Survival CSVs contain
detected deaths only. Experimental confounding still requires review. Fresh
sleep plots can vary in bootstrap confidence intervals and point jitter.
The service does not package a complete software environment or generate
narrative reports. See the workflow guides for scientific assumptions.
