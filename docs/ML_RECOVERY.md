# Machine-learned cohort recovery ranking

The recovery ranker predicts whether a candidate source is likely to survive
the existing acquisition and graph pipeline. It does not decide whether a
document is the correct policy scope, and it cannot override provenance,
canonical-host, audience, validation, or rollback rules.

## Runtime modes

- `off` uses only the existing heuristic.
- `shadow` records model scores but preserves heuristic ordering and decisions.
- `assist` may reorder validated, review-only candidates. A user still confirms
  the source, and automatic recovery remains heuristic-controlled.

Production starts in `shadow`. With no promoted artifact, the ranker records
features and falls back to the heuristic without failing recovery.

## Implicit labels

`retained_graph_success` is positive. Acquisition, validation, extraction, and
empty-graph rollbacks are negative. Unattempted candidates, hard rejections,
cancellations, timeouts, queue failures, and other transient execution failures
remain unlabeled. Policy text is never stored in the observation table.

## Training and promotion

Training is refused until there are at least 500 labelable attempts, 100 of
each class, and 200 providers:

```bash
python -m poligrapher_app.ml.recovery_training \
  --output-dir poligrapher_app/model_artifacts/recovery_ranker
```

The CLI uses provider-disjoint, approximately temporal splits; compares
regularized logistic regression with histogram gradient boosting; and emits a
checksum-pinned `skops` artifact, manifest, metrics, and model card. Gradient
boosting is selected only when validation average precision improves by at
least 0.02. Promotion is a reviewed commit that adds `active.json`; retraining
and promotion are never automatic.

### Source-viability experiments

Policy-attempt models are a separate, evaluation-only path. The structural
dataset can reproduce the historical baseline, while the enriched dataset uses
only attempts collected with the current telemetry schema:

```bash
python -m poligrapher_app.ml.recovery_training \
  --dataset enriched-policy-attempts --readiness

python -m poligrapher_app.ml.recovery_training \
  --dataset enriched-policy-attempts --evaluate-only
```

The enriched evaluation combines identity-free URL structure with two signal
groups. Preflight signals include HTTP status, media type, declared size,
redirect count, cross-domain redirect, and challenge status. Post-capture
signals include crawl duration, extracted-text length, fallback kind, and
artifact sizes available before annotation and graph construction. A bounded
header-only response stream collects preflight metadata; probe failures never
block analysis.

Legacy attempts are excluded rather than imputed as if missing telemetry were
meaningful. Policy text, source URLs, domains, response bodies, and raw error
messages are not model features. Failure-stage diagnostics are retained for
operations but excluded from training to prevent target leakage.

Both policy-attempt datasets use the same provider-disjoint temporal holdout
and must preserve at least 95% of successful attempts. Promotion additionally
requires a 0.05 average-precision gain, avoidance of at least 15% of failed
attempts, and avoidance of at least 10% of total attempts. These datasets cannot
write recovery-ranker artifacts; a distinct reviewed runtime design would be
required after an evaluation passes every gate.

Assist mode additionally requires 30 days and 100 new shadow labels across 50
providers, a holdout average-precision gain of at least 0.05 over the heuristic,
non-worse Brier score, a positive bootstrap confidence interval, zero safety
rule bypasses, and p95 inference below 50 ms. `build_shadow_summary()` and
`assess_assist_readiness()` calculate and enforce the complete checklist; the
deployment remains pinned to `shadow` until a reviewed configuration change.

## Concepts and libraries

- scikit-learn supplies `DictVectorizer`, `LogisticRegression`,
  `HistGradientBoostingClassifier`, pipelines, average precision, and Brier
  score.
- NumPy provides the numeric arrays used by scikit-learn; `skops` provides
  restricted, versioned model serialization.
- SQLAlchemy and Alembic persist candidate observations and versioned policy
  attempt telemetry; pytest covers feature, split, artifact, fallback,
  telemetry, and recovery invariants.

The most relevant concepts are classification versus ranking, regularization,
boosted trees, imbalanced precision-recall evaluation, probability calibration,
grouped/temporal splits, leakage, selection bias, censored observations,
bootstrap intervals, shadow deployments, model drift, and artifact provenance.
