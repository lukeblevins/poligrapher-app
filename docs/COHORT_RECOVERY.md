# Cohort coverage recovery

Coverage recovery is a repeatable pipeline operation, not a list of company
overrides. From a collection page, **Recover** queues a `cohort-recovery` task;
the same operation is available at:

```http
POST /api/collections/{collection_id}/recover-failures
Content-Type: application/json

{"deep": true}
```

An optional `provider_ids` array can bound an API-triggered run, but every ID
must be a member of the collection.

## Invariants

1. Target only collection members without non-empty graph output whose latest
   non-recovery issue is in the auditable failure taxonomy.
   This includes bounded PDF download timeouts as well as source, crawl,
   validation, language, and empty-graph failures.
2. Audit all targets concurrently with the fast resolver pass, then run the
   deep pass only for unresolved or timed-out targets. A standardized transient
   failure retries its configured source directly instead of rediscovering it.
3. Auto-attempt only the current pipeline-valid source or a validated
   replacement on the provider's official domain that meets the resolver's
   shared auto-confidence threshold. Low-confidence, cross-domain, and
   audience-specific policies remain review items.
4. Run the normal company-analysis pipeline in its killable subprocess.
5. Keep a source only when analysis produces non-empty `graph_data.elements`.
   Otherwise restore the original URL and every source-status field.
6. Emit one JSON record per company plus a `RECOVERY SUMMARY` record. A worker
   restart resumes from the durable completed-company cursor.

The checked-in S&P 500 source catalog is only bootstrap data. Recovery does not
read company-specific corrections from it, and a fresh database can reproduce
the same discovery, validation, analysis, and rollback workflow.

`COHORT_AUDIT_MAX_WORKERS` controls audit concurrency and is capped at eight.
Analysis remains sequential within a recovery task so multiple memory-heavy NLP
pipelines do not contend inside one worker.
