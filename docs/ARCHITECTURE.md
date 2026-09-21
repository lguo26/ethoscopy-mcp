# Architecture

```text
Ethoscope devices or compatible sources
    │ recordings and metadata
    ▼
trusted local sources ──read-only──┐
                                  ▼
AI client ──MCP──▶ adapter ──▶ EthoscopyService ──▶ Ethoscopy
                                  │
                                  ▼
                         versioned output artifacts
```

Ethoscope hardware and its device-management software are outside this
repository. Scientific calculations remain in Ethoscopy. The service owns source
registration, metadata overlays, recipe validation, execution, structured
results, provenance, and artifact management. MCP translates protocol requests
into service calls and must not contain custom scientific calculations.

The service contracts should remain usable from Python and a future REST or CLI
adapter without requiring MCP.
