# Synthetic sleep comparison

Run from the repository with its dependencies installed:

```sh
MPLBACKEND=Agg python examples/synthetic_sleep/run_example.py /tmp/sleep-demo
```

Four artificial flies have stored sleep annotations sampled every 60 seconds.
One has a reviewed death after one hour. Outputs demonstrate exclusion of
post-death samples, separate control/dose labels, per-fly summaries, profiles,
and comparison figures without any private experiment data.

See [sleep documentation](../../docs/SLEEP_ANALYSIS.md) for endpoint contracts
and interpretation. All generated data and figures stay in the chosen directory.
