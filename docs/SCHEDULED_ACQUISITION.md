# Scheduled policy acquisition & re-analysis (design)

**Status:** implemented (vertical slice). Task: let a user schedule routine
"fetch current privacy policy → generate poligraph → score" for a provider, from
a source more reliable than a hard-coded URL or file path.

Implementation: `services/acquisition.py` (resolver), `services/scheduler.py`
(APScheduler engine), `api/routers/schedules.py`, `Provider.domain` + `Schedule`
model, and a `ScheduleModal` in the frontend reached from the provider header.

## The real problem: acquisition, not scheduling

Scheduling is the easy half (a cron trigger that re-runs the existing pipeline).
The hard, valuable half is **reliably obtaining an up-to-date copy of a
company's privacy policy over time**. A stored deep URL rots: pages move, get
renamed, 404, redirect, sit behind consent walls, or are rendered client-side.

### Evidence (measured against real S&P-500 providers already in the DB)

Naive **static** discovery (fetch `https://www.<domain>`, scan `<a>` tags for
privacy links) on 8 domains:

| Domain | Static httpx result |
|---|---|
| apple.com | ✅ found `/legal/privacy/` |
| abbott.com | ✅ found current policy |
| accenture.com | ✅ matches stored URL |
| microsoft.com | ✅ found `/en-us/privacy` |
| aflac.com | ⚠️ **wrong** — matched `trupanion.com` (cross-domain) |
| adobe.com | ❌ NO_LINK — homepage is a JS SPA, no links in static HTML |
| akamai.com | ❌ HTTP 403 — bot mitigation blocks static fetch |
| amd.com | ❌ timeout |

Direct static fetch of a *known* policy URL is also unreliable:
`microsoft.com/.../privacy` returned **403** to httpx but **200** in a browser.

Follow-ups that were confirmed by testing:
- **Same-domain preference** fixes the aflac→trupanion false positive and
  re-resolves aflac to its own `aflac.com` policy.
- A **headless browser is necessary but not sufficient**: it recovers SPA/JS
  homepages, but lazy-loaded footers and aggressive bot walls (akamai) still
  need waiting/retries, and some sites will resist automation entirely.

**Conclusion:** no single fetch strategy is reliable. Acquisition must be a
**layered resolver with confidence scoring and a human-verify fallback**, not a
single URL. Also note the DB has **no provider domain field today** — only
per-policy `url` — but every provider's policy URLs share a stable domain
(`abbott.com`, `adobe.com`…), so a domain is trivially derivable/storable and is
the stable anchor for discovery.

## Recommended acquisition method: `PolicySourceResolver`

A strategy chain that returns a **resolved source** (final URL + extracted policy
text + a confidence score + provenance), tried in order until one clears a
confidence threshold:

1. **Open Terms Archive declaration** (highest quality when available). OTA is a
   maintained, federated standard: a service declaration is JSON like
   ```json
   { "name": "Adobe", "terms": { "Privacy Policy": {
       "fetch": "https://www.adobe.com/privacy/policy.html",
       "select": ".content", "executeClientScripts": true } } }
   ```
   It gives us (a) a curated fetch URL, (b) a **content selector** that extracts
   just the policy text — excluding nav/footer, which also improves poligraph
   quality — and (c) an `executeClientScripts` flag telling us when a headless
   browser is required. We can consume existing OTA declarations for covered
   services and reuse the declaration *shape* as our own per-provider override.

2. **Stored canonical policy URL** (what we have today) — fetched through the
   **headless crawler**, following redirects. Kept as an explicit override.

3. **Discovery from the provider domain** — load `https://www.<domain>` in the
   headless browser, collect footer/`<a>` links, score by link text + href
   against privacy patterns (`privacy policy|notice|statement`, `privacy[-_]?…`),
   **constrain to the same registrable domain**, demote cookie-only links.

4. **Sitemap fallback** — fetch `robots.txt` → `sitemap.xml`, grep for URLs
   matching privacy patterns.

5. **Agentic fallback (optional): Webwright.** For the residual hard cases
   (bot/consent walls, multi-step navigation, region gating) an LLM browser
   agent can navigate and extract. It is heavyweight (Playwright + an LLM API key,
   latency, cost), so it is a **last resort behind the cheap strategies**, never
   the default. Fits cleanly as one more `Resolver` implementation.

Interface sketch (new `services/acquisition.py`):
```python
class ResolvedSource(NamedTuple):
    url: str; text: str; content_hash: str
    confidence: float; strategy: str

class PolicySourceResolver:
    def resolve(self, provider_domain: str, hint_url: str | None) -> ResolvedSource | None: ...
```

### Reliability engineering (independent of which strategy wins)

- **Change detection** — hash the *extracted main text* (boilerplate removed),
  not raw HTML (which changes every load via nonces/timestamps). Only run the
  expensive poligraph+score when the hash differs from the last successful run.
  Store `content_hash` on the schedule/run.
- **Provenance snapshot** — save the fetched text/HTML as a run artifact (like
  OTA's versioned history) so results are auditable and diffable over time.
- **Confidence + human-in-the-loop** — a low-confidence discovery (e.g. only a
  weak footer match, or a cross-domain candidate) does **not** silently run; it
  surfaces a "confirm source" prompt in the UI. Once a user confirms a URL it is
  promoted to the stored canonical override (strategy 2) for all future runs.
- **Fallback + alerting** — on repeated resolution failure, mark the schedule
  `needs_attention` and surface it (Status Center / provider status dot).

## Scheduler engine

- **APScheduler** as the in-process timer, started in `api/main.py` `lifespan`.
  The `Schedule` DB table is the **single source of truth**; on startup we
  re-register one job per enabled schedule, so schedules survive restarts without
  relying on APScheduler's own job serialization.
- A fired job **enqueues through the existing `TaskRegistry`**, so scheduled runs
  appear in the Status Center and reuse the atomic-cancellation machinery already
  built. Run = `resolve source → (hash changed?) → generate_graph → score`.
- Reuse the existing dated `output/<Provider_Slug>/<date>_<source>/` convention
  so each scheduled capture is a normal `Policy` row + artifact dir.

## Data model changes

- `Provider.domain` (new, nullable) — the stable discovery anchor; backfill by
  deriving the registrable domain from existing policy URLs.
- New `Schedule` table: `id`, `provider_id`, `cadence` (cron/interval),
  `source_strategy`/`source_override_url`, `enabled`, `last_run_at`,
  `next_run_at`, `last_status`, `last_content_hash`, `needs_attention`.

## Why not just "store a better URL"

Because URLs are the thing that rots. Anchoring on the **domain** + re-discovering
the policy each run (with an OTA/override fast-path and content-hash gating) is
what makes acquisition *dynamic and reliable* rather than a snapshot that
silently goes stale.

## Sources
- Open Terms Archive declaration reference — https://docs.opentermsarchive.org/terms/reference/declaration/
- Webwright — https://github.com/microsoft/Webwright
