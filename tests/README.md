# Tests

Tests cover schemas, path safety, immutable-source behavior, service/MCP
contracts, and scientific regression results. Private experiment fixtures stay
outside Git; committed fixtures must be synthetic, anonymized, or explicitly
redistributable.

Sleep tests cover death endpoints, gaps, strata, transfer identity, immutable
inputs, direct public-library quantification and statistics, deprivation QC
threshold boundaries, missing recordings, and real MCP recipe dispatch.

```sh
MPLBACKEND=Agg python -m unittest discover -s tests -v
```
