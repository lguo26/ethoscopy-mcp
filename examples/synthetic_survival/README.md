# Synthetic survival example

This is a small, redistributable end-to-end example. It creates two synthetic
recordings representing the same four flies before and after a machine
transfer, plus metadata and an identity overlay. All generated pickles and
outputs are written under the ignored `generated/` directory.

From the repository root, first preview the recipe:

```bash
MPLBACKEND=Agg PYTHONPATH=src python examples/synthetic_survival/run_example.py
```

Review the printed cohort, transformation, warning, and hash information. Then
execute exactly that freshly previewed recipe:

```bash
MPLBACKEND=Agg PYTHONPATH=src python examples/synthetic_survival/run_example.py --approve
```

The approved run creates a death-table CSV, presentation PNG/SVG,
`provenance.json`, and `run-result.json`. Rerunning it verifies and reuses the
same content-addressed directory.

The synthetic values demonstrate software behavior only; they are not a
biological reference dataset.
