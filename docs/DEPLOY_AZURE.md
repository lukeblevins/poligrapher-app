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

The `Deploy to Azure` GitHub Action builds immutable web/worker images, previews
and applies `infra/main.bicep`, runs Alembic in a manual Container Apps Job, and
verifies the public API. It is intentionally manual and uses the protected
`azure-production` GitHub Environment, so merging code does not spend money or
change production by itself.

## One-time deployment setup

1. Create the resource group and deploy `infra/budget.bicep` at subscription
   scope. The workflow identity only needs `Contributor` on this resource group;
   it does not need subscription-wide ownership.
2. Create a Microsoft Entra application or user-assigned managed identity with a
   federated credential for
   `repo:lukeblevins/poligrapher-app:environment:azure-production`.
3. Assign that identity `Contributor` on the resource group. OIDC supplies a
   short-lived token to each run; do not create or store an Azure client secret.
4. Create the `azure-production` GitHub Environment. Add a required reviewer if
   deployments should pause for approval.
5. Ensure this repository's GHCR package is public. Container Apps scales from
   zero and pulls the immutable images anonymously, avoiding a long-lived GHCR
   PAT and the recurring cost of Azure Container Registry.

Configure these **environment variables**:

| Name | Example |
|---|---|
| `AZURE_CLIENT_ID` | Entra application or managed identity client ID |
| `AZURE_TENANT_ID` | Azure tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_RESOURCE_GROUP` | `poligrapher-rg` |
| `AZURE_LOCATION` | `eastus` |
| `AZURE_NAME_PREFIX` | Existing globally unique deployment prefix |
| `CRAWL_PROXY_MODE` | `fallback` |

Configure these **environment secrets**:

| Name | Required | Purpose |
|---|---:|---|
| `POSTGRES_PASSWORD` | yes | PostgreSQL administrator password |
| `EXPORT_TOKEN` | yes | Protected source, artifact, and task-output access |
| `CRAWL_PROXY` | no | Existing proxy endpoint |
| `CRAWL_PROXY_USERNAME` | no | Existing proxy username |
| `CRAWL_PROXY_PASSWORD` | no | Existing proxy password |
| `SCRAPE_API_URL` | no | Existing unblocker URL template |
| `SCRAPE_API_KEY` | no | Existing unblocker API key |

GitHub masks environment secrets, Bicep declares them with `@secure()`, Azure CLI
output is disabled by default in the workflow, and only the resulting Container
Apps secret references are placed in runtime environments.

Run **Actions → Deploy to Azure → Run workflow**. Keep the change preview
enabled unless diagnosing the preview itself. The workflow stops before
deployment if either immutable GHCR image cannot be pulled anonymously, and it
fails rather than declaring success when migrations or health checks fail.

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

Raw research archives are private and expire after 90 days. Uploaded source
PDFs use the `sources/` prefix and are not covered by the deletion lifecycle.
