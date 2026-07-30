# Azure Deployment Plan

> **Status:** Validated

Generated: 2026-07-28

## 1. Project Overview

**Goal:** Deploy the verified S&P 500 source catalog and harden long-running
collection analysis so an individual provider timeout becomes a recoverable
subtask failure instead of stalling the parent task.

**Path:** Modify existing production deployment

## 2. Requirements

| Attribute | Value |
|-----------|-------|
| Classification | Production |
| Scale | Small, asynchronous research workload |
| Budget | Cost-optimized; preserve scale-to-zero jobs |
| Subscription | `c1de4381-a30a-4465-b101-989aff15ea21` (existing deployment) |
| Location | `eastus2` (existing workload region) |

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| SPA | Frontend | React, Vite | `frontend/` |
| API | API | FastAPI, SQLAlchemy | `poligrapher_app/` |
| Analysis worker | Worker | Python, Azure Queue Storage | `poligrapher_app/worker.py` |
| Database migration job | Job | Alembic, source-catalog importer | `infra/main.bicep` |
| Infrastructure | IaC | Bicep | `infra/` |
| Release pipeline | CI/CD | GitHub Actions, OIDC | `.github/workflows/deploy-azure.yml` |

## 4. Recipe Selection

**Selected:** Bicep through the existing GitHub Actions workflow.

**Rationale:** This is an in-place update to the established, gated production path. No new resources or credentials are needed.

## 5. Architecture

**Stack:** Azure Container Apps

| Component | Azure Service | SKU |
|-----------|---------------|-----|
| Web/API | Container App | Consumption |
| Analysis worker | Container Apps Job | Consumption, queue-triggered |
| Scheduled work | Container Apps Job | Consumption, scheduled |
| Schema and catalog sync | Container Apps Job | Consumption, manual |
| Relational state | PostgreSQL Flexible Server | Existing Burstable server |
| Durable artifacts and queue | Storage account | Existing Standard account |

The migration job runs `alembic upgrade head` and then applies the packaged,
non-secret source snapshot. The importer matches providers by CIK/ticker,
preserves newer production checks, fails on unmatched companies, and does not
replace policies, analyses, schedules, collections, or blob data.

## 6. Provisioning Limit Checklist

This release creates no additional Azure resources. It updates existing
Container App revisions and the existing migration-job template.

| Resource Type | Number to Deploy | Current / Total After | Limit | Evidence |
|---------------|------------------|-----------------------|-------|----------|
| Microsoft.App managed environments | 0 | 1 / 1 | 20 | Azure quota check, eastus2 |
| Microsoft.DBforPostgreSQL flexible-server cores | 0 | 1 / 1 | 384 | Azure quota check, eastus2 |
| PostgreSQL Burstable family | 0 | 1 / 1 | 40 | Azure quota check, eastus2 |
| Microsoft.Storage storage accounts | 0 | 1 / 1 | 250 | Azure quota check, eastus2 |

**Status:** All resources within limits.

## 7. Execution Checklist

### Planning

- [x] Analyze workspace and live resource group
- [x] Gather requirements
- [x] Prepare resource inventory
- [x] Fetch quota usage and limits
- [x] Select existing Bicep/GitHub Actions recipe
- [x] Plan source-only PostgreSQL synchronization
- [x] Confirm reuse of the existing subscription and eastus2 region
- [x] User approved this plan

### Preparation

- [x] Add versioned 500-company source snapshot
- [x] Add idempotent source-only importer
- [x] Run importer after Alembic in the migration job
- [x] Add importer and deployment-contract tests
- [x] Run backend test suite
- [x] Build application artifacts and run all local suites
- [x] Set status to Ready for Validation

### Validation

- [x] Compile Bicep
- [x] Validate and preview the resource-group deployment
- [x] Validate application builds locally; production image builds remain a required CI prerequisite
- [x] Review static RBAC and secret handling
- [x] Record validation proof
- [x] Set status to Validated

### Deployment

- [x] Commit and push the coherent release
- [x] Trigger the gated Azure production workflow
- [x] Confirm migration-job success
- [x] Verify the deployed API reports all 500 S&P sources ready
- [x] Set status to Deployed

## 8. Validation Proof

| Check | Command Run | Result | Timestamp |
|-------|-------------|--------|-----------|
| Backend suite | `./.venv/bin/pytest -q` | 47 passed | 2026-07-28 |
| Source importer repeatability | `python -m poligrapher_app.sync_source_catalog` twice | 500 unchanged on repeat | 2026-07-28 |
| Local S&P source count | SQLite membership query | 500 available with URLs | 2026-07-28 |
| Azure quota | Azure quota usage check | Existing capacity within limits | 2026-07-28 |
| Backend suite, final | `./.venv/bin/pytest -q` | 48 passed | 2026-07-28 02:18 EDT |
| Frontend type check | `npm --prefix frontend run typecheck` | Passed | 2026-07-28 02:18 EDT |
| Frontend suite | `npm --prefix frontend test -- --run` | 20 passed | 2026-07-28 02:18 EDT |
| Frontend production build | `npm --prefix frontend run build` | Passed | 2026-07-28 02:18 EDT |
| Bicep compilation | `az bicep build --file infra/main.bicep --stdout` | Passed | 2026-07-28 02:15 EDT |
| ARM validation | `az deployment group validate` | Succeeded | 2026-07-28 02:17 EDT |
| ARM what-if | `az deployment group what-if --result-format ResourceIdOnly` | Succeeded | 2026-07-28 02:17 EDT |
| Diff validation | `git diff --check` | Passed | 2026-07-28 02:18 EDT |
| Backend suite, collection recovery | `./.venv/bin/pytest -q` | 55 passed | 2026-07-28 16:07 EDT |
| Frontend suite, collection recovery | `npm --prefix frontend test -- --run` | 22 passed | 2026-07-28 16:07 EDT |
| Frontend type check and build, collection recovery | `npm --prefix frontend run typecheck && npm --prefix frontend run build` | Passed | 2026-07-28 16:07 EDT |
| Bicep compilation, collection recovery | `az bicep build --file infra/main.bicep --stdout` | Passed | 2026-07-28 16:08 EDT |
| Diff validation, collection recovery | `git diff --check` | Passed | 2026-07-28 16:08 EDT |
| Release commit | `git rev-parse origin/main` | `3a5e3980dab5704f9979b5913c3fd573267e860e` | 2026-07-30 02:22 EDT |
| Backend suite, model release | `./.venv/bin/pytest -q` | 60 passed | 2026-07-30 02:22 EDT |
| Frontend suite, model release | `npm --prefix frontend test -- --run` | 32 passed | 2026-07-30 02:22 EDT |
| Frontend type check and build, model release | `npm --prefix frontend run typecheck`; `npm --prefix frontend run build` | Passed | 2026-07-30 02:22 EDT |
| Bicep compilation, model release | `az bicep build --file infra/main.bicep --stdout` | Passed; template hash `11706172348469164637` | 2026-07-30 02:22 EDT |
| ARM provider validation, model release | `az deployment group validate` against `poligrapher-rg` | Succeeded; correlation `3483d0b5-24d1-4433-9a5e-9110365ffa7d` | 2026-07-30 02:23 EDT |
| ARM what-if, model release | `az deployment group what-if --result-format ResourceIdOnly` | Succeeded; 15 existing resources deploy, 1 identity ignored, 0 deletes | 2026-07-30 02:24 EDT |
| Azure policy review | Azure MCP `policy_assignment_list` | Audit-only Security Center policy and inherited regional/MFA controls reviewed; eastus2 remains allowed | 2026-07-30 02:25 EDT |
| Static RBAC review | `infra/main.bicep`; live resource inventory | No new role assignments; existing connection-string data-plane access and GitHub OIDC identity unchanged | 2026-07-30 02:25 EDT |
| Diff validation, model release | `git diff --check` | Passed before validation-proof update | 2026-07-30 02:22 EDT |
| Initial model deployment | GitHub Actions run `30519712592` | Images, what-if, deployment, migrations, and API verification succeeded at `d7eec6a`; bounded analysis then exposed missing `phrase_map.yml` in the worker image | 2026-07-30 02:43 EDT |
| Worker packaging correction | `./.venv/bin/pytest -q`; pinned phrase-map digest check | 60 passed; SHA-256 `cae2e134e550884583cad6b9b021f862cce9e75801b5c7f26251090b44f9c127` matched | 2026-07-30 02:48 EDT |
| Corrected production deployment | GitHub Actions run `30520874932` | Image builds, what-if, deployment, migrations, and API verification succeeded at `0075063557646f34cc9849ed56c265b7f858b86b` | 2026-07-30 03:02 EDT |
| Live image inventory | Azure Resource Graph | App, worker, scheduled-run, and migration resources all `Succeeded` on immutable `0075063` images in `eastus2` | 2026-07-30 03:02 EDT |
| S&P source acceptance | Production `/api/collections` and `/api/providers` | 500 collection members; 500 with source URLs | 2026-07-30 03:05 EDT |
| Upgraded model smoke test | Task `44c83570-c72b-4763-a3c5-519bf9242825`; policy graph API | Succeeded with 1/1 complete and no issues; persisted 146 elements (65 nodes, 81 edges) | 2026-07-30 03:04 EDT |
| Failure recovery release commit | `git rev-parse origin/main` | `42c5abfa3cac121015c86998c2423fc6e997db33` | 2026-07-30 |
| Backend suite, failure recovery | `./.venv/bin/pytest -q` | 69 passed | 2026-07-30 |
| Frontend suite, failure recovery | `npm --prefix frontend test -- --run` | 33 passed | 2026-07-30 |
| Frontend type check and build, failure recovery | `npm --prefix frontend run typecheck`; `npm --prefix frontend run build` | Passed; production bundle built | 2026-07-30 |
| Bicep compilation, failure recovery | `az bicep build --file infra/main.bicep --stdout` | Passed; template hash `11706172348469164637` | 2026-07-30 |
| ARM provider validation, failure recovery | `az deployment group validate` against `poligrapher-rg` | Succeeded; correlation `d3aa1d2f-bc04-49a1-a2d4-8007d113f2e8` | 2026-07-30 |
| ARM what-if, failure recovery | `az deployment group what-if --result-format ResourceIdOnly` | Succeeded | 2026-07-30 |
| Azure resource and policy review, failure recovery | Azure MCP resource inventory and `policy_assignment_list` | Existing workload remains in `eastus2`; audit, regional, and MFA policies reviewed | 2026-07-30 |
| Static RBAC review, failure recovery | `infra/main.bicep`; application storage and queue clients | No new identities or role assignments; existing secret-backed storage and database access unchanged | 2026-07-30 |
| Container image validation gate | Local Docker availability; `.github/workflows/deploy-azure.yml` | Docker daemon unavailable locally; both production image builds remain blocking CI prerequisites | 2026-07-30 |
| Failure recovery production deployment | GitHub Actions run `30523625758` | Image builds, real-secret what-if, Bicep deployment, migrations, and deployed-app verification succeeded at `2f2d9b53a86485fea7db5364937e23c90ae1dcb0` | 2026-07-30 |
| Failure recovery live resource inventory | Azure Resource Graph | App revision `poligrapherc1de43-app--0000014`, worker, and migration job report `Succeeded` on immutable `2f2d9b5` images in `eastus2` | 2026-07-30 |
| Failure recovery migration | Container Apps job execution `poligrapherc1de43-migrations-0emciug` | Succeeded | 2026-07-30 |
| Failure recovery API acceptance | Production `/api/providers`; `/api/tasks` | 510 providers and 510 source URLs; task history exposes terminal partial-failure state | 2026-07-30 |
| Failure recovery analysis smoke test | Task `2381bf40-fc3a-41a8-9be8-f4d40b7066e6` | Abbott policy analysis completed with outcome `succeeded`, 1 complete, 0 failed, and no issues | 2026-07-30 |
| Failure recovery UI acceptance | Production Tasks workspace in the in-app browser | Successful smoke run renders Completed; historical partial runs render Completed with issues and failure counts; failed runs expose Retry, View run, and Details | 2026-07-30 |
| Live access review | Container Apps identity configuration | App identity is disabled; managed-identity role verification is not applicable and existing secret-backed connections remain unchanged | 2026-07-30 |
| Backend suite, actionable cohort recovery | `./.venv/bin/pytest -q` | 69 passed | 2026-07-30 09:26 EDT |
| Frontend suite, actionable cohort recovery | `npm --prefix frontend test -- --run` | 34 passed | 2026-07-30 09:26 EDT |
| Frontend type check and build, actionable cohort recovery | `npm --prefix frontend run typecheck`; `npm --prefix frontend run build` | Passed; production bundle built | 2026-07-30 09:26 EDT |
| Bicep compilation, actionable cohort recovery | `az bicep build --file infra/main.bicep --stdout` | Passed; template hash `11706172348469164637` | 2026-07-30 09:26 EDT |
| ARM provider validation, actionable cohort recovery | `az deployment group validate` against `poligrapher-rg` | Succeeded; correlation `b3596a04-454d-43dc-bd49-f1480dea5d8f` | 2026-07-30 09:27 EDT |
| ARM what-if, actionable cohort recovery | `az deployment group what-if --result-format ResourceIdOnly` | Succeeded; 15 existing resources deploy, 1 identity ignored, 0 deletes | 2026-07-30 09:27 EDT |
| Static RBAC review, actionable cohort recovery | `infra/main.bicep`; application storage and queue clients | No managed identities or role assignments; existing secret-backed connections unchanged | 2026-07-30 09:27 EDT |
| Container image validation gate, actionable cohort recovery | Local Docker availability; `.github/workflows/deploy-azure.yml` | Docker daemon unavailable locally; both immutable production image builds remain blocking CI prerequisites | 2026-07-30 09:26 EDT |

**Validated by:** azure-validate workflow

**Validation timestamp:** 2026-07-30

## 9. Files

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | Deployment source of truth | Complete |
| `infra/main.bicep` | Existing infrastructure and migration job | Updated |
| `poligrapher_app/data/sp500_sources.json` | Verified source snapshot | Generated |
| `poligrapher_app/services/source_catalog.py` | Safe importer | Implemented |
| `poligrapher_app/sync_source_catalog.py` | Migration-job entry point | Implemented |

## 10. Next Step

Monitor new production analyses for newly classified issue codes. Historical
tasks are intentionally not backfilled, so failures created before this release
may continue to display the legacy unclassified recommendation.
