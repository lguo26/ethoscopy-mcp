# Contributing

Thank you for helping improve `ethoscopy-mcp`. The project welcomes focused bug
fixes, documentation, synthetic examples, tests, and well-validated scientific
workflows.

## Before opening a change

- Open an issue before making a large architectural or scientific change.
- Never submit private research data, credentials, real participant or animal
  identifiers, generated private artifacts, or untrusted pickle files.
- Use synthetic or explicitly redistributable fixtures only.
- Preserve original Ethoscopy sources: transformations belong in working copies
  or versioned overlays.
- Keep MCP handlers thin; reusable scientific behavior belongs in the service.

## Development

Create an isolated Python 3.12 or newer environment, then install the project:

```bash
python -m pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
```

Add tests for behavior changes. Scientific changes should document assumptions,
units, exclusions, expected cohort counts, and provenance consequences.

## Pull requests

A pull request should explain the problem, the chosen approach, safety or
scientific implications, and verification performed. Keep unrelated changes in
separate pull requests. By contributing, you agree that your contribution is
distributed under `GPL-3.0-only` and confirm that you have the right to submit
it.

Follow [SECURITY.md](SECURITY.md) for vulnerability reports. Do not include
sensitive research data in any report.
