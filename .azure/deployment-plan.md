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

- [ ] Commit and push the coherent release
- [ ] Trigger the gated Azure production workflow
- [ ] Confirm migration-job success
- [ ] Verify the deployed API reports all 500 S&P sources ready
- [ ] Set status to Deployed

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

**Validated by:** azure-validate workflow

**Validation timestamp:** 2026-07-28 02:18 EDT

## 9. Files

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | Deployment source of truth | Complete |
| `infra/main.bicep` | Existing infrastructure and migration job | Updated |
| `poligrapher_app/data/sp500_sources.json` | Verified source snapshot | Generated |
| `poligrapher_app/services/source_catalog.py` | Safe importer | Implemented |
| `poligrapher_app/sync_source_catalog.py` | Migration-job entry point | Implemented |

## 10. Next Step

Approve reuse of the existing subscription and `eastus2` deployment context,
then run the formal validation and production workflow.
