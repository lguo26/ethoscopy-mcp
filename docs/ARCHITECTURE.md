# Architecture

```text
AI client
    │ MCP
    ▼
ethoscopy-mcp adapter
    ▼
EthoscopyService
    ▼
Ethoscopy
    ▼
trusted local sources and versioned output artifacts
```

Scientific calculations remain in Ethoscopy. The service owns source
registration, metadata overlays, recipe validation, execution, structured
results, provenance, and artifact management. MCP translates protocol requests
into service calls and must not contain custom scientific calculations.

The service contracts should remain usable from Python and a future REST or CLI
adapter without requiring MCP.
