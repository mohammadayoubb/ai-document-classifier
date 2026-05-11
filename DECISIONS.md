# Architectural Decisions

> Complete in Phase 12 with full context, options considered, decision, and consequences.

## Decision template

```
## [Date] — Decision title
Context: Why we faced this choice
Options: What we considered
Decision: What we chose
Consequences: Trade-offs we accepted
```

## Decisions to document

- Why RQ over Celery
- Why ConvNeXt Tiny vs Small
- Freeze policy rationale (partial_unfreeze)
- Cache TTL choices (300s / 60s / 30s / 15s)
- Why Vault dev mode (not production mode)
- How we handle Redis queue loss on container restart
