# Deploying safely to Azure

The checked-in Bicep configuration uses a lightweight web Container App with
hard scaling bounds (`minReplicas=0`, `maxReplicas=1`), plus an event-driven
analysis job triggered by Azure Queue Storage (`minExecutions=0`,
`maxExecutions=1`). PostgreSQL uses B1ms without HA; storage is private Standard
LRS; logs retain 30 days; and a $35 monthly budget sends notifications. Budgets
notify, while the scale and SKU limits provide the actual spending guardrails.

The web and hourly scheduler images request only 0.5 vCPU/1 GiB. Chromium, Torch,
spaCy, transformers, and model data exist only in the 4-vCPU/8-GiB analysis
worker image, which runs only while an analysis queue message exists.

No resources are created by these files alone. Before deployment:

1. Build and push both Docker targets (`web` and `worker`) to a registry.
2. Create a resource group and preview changes with `az deployment group what-if`.
3. Deploy `infra/main.bicep`, run `alembic upgrade head` as a one-off migration,
   and deploy `infra/budget.bicep` at subscription scope.
4. Confirm the app reaches zero replicas after idle and review Cost Management.

## Existing crawl proxy / unblocker

The Azure definition can reuse the same external proxy or unblocker account as
the previous Cloud Run environment. It does not create a metered proxy appliance
inside Azure. The endpoint and credentials are stored as Container Apps secrets
and injected into both the web app and the scheduled-acquisition job:

- `CRAWL_PROXY`, with optional `CRAWL_PROXY_USERNAME` and
  `CRAWL_PROXY_PASSWORD`, routes HTTP and Chromium acquisition through an
  existing residential/ISP proxy.
- `SCRAPE_API_URL` and optional `SCRAPE_API_KEY` configure an existing web
  unblocker API. The URL template can contain `{key}` and `{url}` placeholders.

Pass only the mode used by the existing service. For example:

```sh
az deployment group what-if --resource-group poligrapher-rg \
  --template-file infra/main.bicep \
  --parameters namePrefix=poligrapherabc123 \
  webImage=REGISTRY/IMAGE:WEB_TAG workerImage=REGISTRY/IMAGE:WORKER_TAG \
  postgresPassword='...' exportToken='...' \
  crawlProxy='http://gate.decodo.com:7000' crawlProxyMode='fallback' \
  crawlProxyUsername='...' crawlProxyPassword='...'
```

For Decodo residential proxies, use the rotating gateway
`http://gate.decodo.com:7000` with the proxy user and generated password from
Residential → Proxy setup. Username/password authentication is preferable to IP
whitelisting because Container Apps Consumption does not provide a stable
outbound address by default. Keep `crawlProxyMode=fallback`: direct HTTP and
Chromium are attempted first, and Decodo bandwidth is used only after blocking.
Decodo also supports a traffic limit on each proxy user; set that limit before
deploying. A dedicated proxy user makes the research application's usage easy
to isolate and revoke.

Do not put these values in a checked-in parameter file. Azure Cost Management
cannot cap charges billed directly by an external proxy vendor, so configure a
hard monthly spending or bandwidth limit and usage alerts in that vendor's
account. Container Apps remains limited to one replica and the scheduled job to
one execution at a time, which bounds concurrency but not per-gigabyte vendor
charges.

Decodo's public free offer is currently a 3-day, 100 MB trial rather than a
permanent free tier, and the selected plan activates automatically after the
trial unless cancelled. Treat the dashboard traffic limit—not the Azure budget—
as the primary proxy-cost guardrail.

To transfer an already migrated local dataset, set `TARGET_DATABASE_URL` and
`AZURE_STORAGE_CONNECTION_STRING`, then run
`python -m poligrapher_app.migrate_cloud`. It replaces the target seed rows in a
single database transaction and uploads the local private object store.

Example preview (replace placeholders; never commit passwords or tokens):

```sh
az deployment group what-if --resource-group poligrapher-rg \
  --template-file infra/main.bicep \
  --parameters namePrefix=poligrapherabc123 \
  webImage=REGISTRY/IMAGE:WEB_TAG workerImage=REGISTRY/IMAGE:WORKER_TAG \
   postgresPassword='...' exportToken='...'
```

Raw research archives are private and expire after 90 days. Uploaded source
PDFs use the `sources/` prefix and are not covered by the deletion lifecycle.
