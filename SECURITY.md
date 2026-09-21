# Security policy

## Source data

Registered experiment files are read-only. Tools operate on deliberate working
copies and write new versioned artifacts. Metadata changes are stored as
overlays and never overwrite the original file.

## Pickle files

Loading an untrusted Python pickle can execute code. Only trusted pickles from
explicitly allow-listed roots may be loaded. Unknown or uploaded pickles must
be rejected or converted in an isolated process.

## Paths

The server must use configured project roots, resolve symlinks, reject path
traversal, and never expose arbitrary filesystem access to an MCP client.

## AI execution

Scientific operations use typed recipes. Identity mapping, time alignment,
baseline changes, death detection, censoring, exclusions, pooling, and
statistical tests require a visible preview before execution.

## Secrets and research data

Never commit credentials, API keys, access tokens, real private experiment
data, deployment secrets, or private storage paths. Security reports must not
include sensitive research data in public issues.
