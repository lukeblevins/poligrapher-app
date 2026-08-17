# Recovery ranker artifacts

This directory intentionally contains no active model until the minimum
training population and shadow evaluation gates in `docs/ML_RECOVERY.md` pass.

A manually reviewed promotion adds the `.skops` artifact, its manifest,
metrics, and model card, then creates `active.json`:

```json
{"artifact": "recovery-ranker-YYYYMMDDTHHMMSSZ.skops"}
```

The worker verifies the artifact checksum and feature-schema version before
loading it. Missing or invalid artifacts preserve heuristic recovery behavior.
