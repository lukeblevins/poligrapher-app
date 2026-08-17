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
   replacement on the provider's canonical apex or `www` host that meets the
   resolver's shared auto-confidence threshold. Low-confidence, cross-domain,
   noncanonical-subdomain, and audience-specific policies remain review items.
4. Run the normal company-analysis pipeline in its killable subprocess.
5. Keep a source only when analysis produces non-empty `graph_data.elements`.
   Otherwise restore the original URL and every source-status field.
6. Emit one JSON record per company plus a `RECOVERY SUMMARY` record. A worker
   restart resumes from the durable completed-company cursor.

## Internal contracts

- `SourceAuditResult` and `AuditStatus` are the single contract between source
  discovery, recovery, reporting, and tests. Adding a status updates aggregate
  audit counters automatically instead of requiring parallel string-key lists.
- `CohortRecoveryRunner` owns the recovery state machine. The generic task
  executor only dispatches the durable payload and supplies the existing
  killable company-analysis function.
- Active recovery tasks publish fast-audit, deep-audit, and analysis phases in
  their task label while `completed` remains the restart-safe company cursor.
- Results that cannot be attempted safely become structured `TaskIssue`
  records. The Status Center can therefore identify affected companies and
  show supported review actions without asking users to interpret JSON logs.
- Policy completion everywhere is defined by the shared `has_graph_elements`
  predicate.

Audience- or document-specific search results are rejected by named,
reason-bearing rules such as `audience.workforce`, `audience.investor`, and
`document.report`. These are general source-selection rules, not company
exceptions.

The checked-in S&P 500 source catalog is only bootstrap data. Recovery does not
read company-specific corrections from it, and a fresh database can reproduce
the same discovery, validation, analysis, and rollback workflow.

`COHORT_AUDIT_MAX_WORKERS` controls audit concurrency and is capped at eight.
Analysis remains sequential within a recovery task so multiple memory-heavy NLP
pipelines do not contend inside one worker.

## Browser-rendered text fallback

When an official policy is visible to a researcher but automated acquisition is
blocked by a JavaScript shell, bot protection, or an obsolete route, the company
workspace exposes **Paste policy text**. The form requires the official source
URL, capture date, title, and at least 500 characters of policy text.

The API normalizes that text into a paginated PDF with the provenance embedded
on the first page, stores it with the existing object-storage abstraction, and
queues the standard upload pipeline. The resulting run uses the distinct
`captured_text` method but otherwise shares graph generation, scoring, task
issues, history, deletion, and rerun behavior with PDF uploads. The source URL
is metadata, not a fetch target, so this fallback does not introduce a second
network-acquisition implementation.

```http
POST /api/providers/{provider_id}/text-uploads
Content-Type: application/json

{
  "title": "Example Privacy Notice",
  "source_url": "https://example.com/privacy",
  "capture_date": "2026-08-17",
  "text": "...captured policy text..."
}
```
