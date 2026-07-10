# Deploying safely to Azure

The checked-in Bicep configuration uses Container Apps Consumption with hard
scaling bounds (`minReplicas=0`, `maxReplicas=1`), PostgreSQL B1ms without HA,
private Standard LRS Blob Storage, 30-day log retention, and a $35 monthly
notification budget. Budgets notify; the replica and SKU limits provide the
actual spending guardrails.

Scheduled acquisition is handled by an daily Container Apps Job. The job exits
immediately when nothing is due and permits only one execution with no automatic
retries; due analyses reuse the same 4-vCPU/8-GiB pipeline allocation.

No resources are created by these files alone. Before deployment:

1. Build and push the container image to a registry.
2. Create a resource group and preview changes with `az deployment group what-if`.
3. Deploy `infra/main.bicep`, run `alembic upgrade head` as a one-off migration,
   and deploy `infra/budget.bicep` at subscription scope.
4. Confirm the app reaches zero replicas after idle and review Cost Management.

Example preview (replace placeholders; never commit passwords or tokens):

```sh
az deployment group what-if --resource-group poligrapher-rg \
  --template-file infra/main.bicep \
  --parameters namePrefix=poligrapherabc123 image=REGISTRY/IMAGE:TAG \
  postgresPassword='...' exportToken='...'
```

Raw research archives are private and expire after 90 days. Uploaded source
PDFs use the `sources/` prefix and are not covered by the deletion lifecycle.
