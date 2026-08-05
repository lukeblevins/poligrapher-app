# Azure Deployment Plan

> **Status:** Deployed

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
| Actionable cohort recovery deployment | GitHub Actions run `30547050188` | Both immutable image builds, real-secret what-if, Bicep deployment, migrations, and endpoint verification succeeded at `0ecff136273896f07408e50bbea580c735042f1e` | 2026-07-30 09:40 EDT |
| Actionable cohort recovery live acceptance | Container Apps revision and production task API | Revision `poligrapherc1de43-app--0000015` is `Succeeded`; task issues resolve affected provider IDs to company names | 2026-07-30 09:41 EDT |
| Transient-only S&P retry | Task `6078146a-7be2-473b-b321-7518af6ec649` | Queued exactly 47 companies with transient-only error sets; worker claimed the task | 2026-07-30 09:42 EDT |
| Backend suite, post-navigation archive fallback | `./.venv/bin/pytest -q` | 72 passed, including bounded archive-fallback regression coverage | 2026-08-03 20:28 EDT |
| Frontend validation, post-navigation archive fallback | `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build` | Passed; 34 tests and production bundle built | 2026-08-03 20:28 EDT |
| Bicep compilation, post-navigation archive fallback | `az bicep build --file infra/main.bicep --stdout` | Passed; unchanged template hash `11706172348469164637` | 2026-08-03 20:28 EDT |
| ARM provider validation, post-navigation archive fallback | `az deployment group validate` against `poligrapher-rg` | Succeeded; correlation `0f4c75e7-f10e-4ead-940a-9a2e2c9e6c88` | 2026-08-03 20:29 EDT |
| ARM what-if, post-navigation archive fallback | `az deployment group what-if --result-format ResourceIdOnly` | Succeeded; 15 existing resources deploy, 1 identity ignored, 0 deletes | 2026-08-03 20:29 EDT |
| Static RBAC review, post-navigation archive fallback | `infra/main.bicep`; application storage and queue clients | No managed identities or role assignments; existing secret-backed connections unchanged | 2026-08-03 20:29 EDT |
| Diff validation, post-navigation archive fallback | `git diff --check` | Passed | 2026-08-03 20:29 EDT |
| Browser-replay fallback deployment | GitHub Actions run `30865789761` | Both immutable image builds, real-secret what-if, Bicep deployment, migrations, and endpoint verification succeeded at `6330bf7b41dd8d497fa4df4afd36427d45a42d49` | 2026-08-03 20:44 EDT |
| Browser-replay live acceptance | Container Apps revision and migration execution | Revision `poligrapherc1de43-app--0000016` and migration execution `poligrapherc1de43-migrations-sh228a7` report `Succeeded`; app and worker use immutable `6330bf7` images | 2026-08-03 20:45 EDT |
| Browser-replay recovery finding | Task `159a42b0-4aa3-44dd-9203-f7b401892070`; task output | Fallback executed, but Azure timed out on Wayback browser replay; task cancelled after preserving 5 terminal failures | 2026-08-03 20:48 EDT |
| Raw archive acquisition check | `fetch_wayback` against Delta Air Lines configured source | Returned 80,679 characters with privacy and personal-information markers | 2026-08-03 20:48 EDT |
| Backend suite, materialized archive fallback | `./.venv/bin/pytest -q` | 73 passed, including raw-archive precedence and temporary-file cleanup | 2026-08-03 20:49 EDT |
| Diff validation, materialized archive fallback | `git diff --check` | Passed | 2026-08-03 20:49 EDT |
| Materialized archive fallback deployment | GitHub Actions run `30866837764` | Both immutable image builds, real-secret what-if, Bicep deployment, migrations, and endpoint verification succeeded at `b83a948e802a5e1464e05e5d1bf53713557b3fc8` | 2026-08-03 21:04 EDT |
| Materialized archive live acceptance | Container Apps revision and migration execution | Revision `poligrapherc1de43-app--0000017` and migration execution `poligrapherc1de43-migrations-4nfpjxc` report `Succeeded`; app and worker use immutable `b83a948` images | 2026-08-03 21:04 EDT |
| S&P transient-subset recovery | Task `7b88d33c-cc1b-4b07-903f-c32c0dc1208e` | `partially_succeeded`: 46 completed, 2 recovered, and 44 failed with standardized root issues; Baker Hughes and Paccar now have analyses | 2026-08-03 21:41 EDT |
| S&P coverage reconciliation | Production `/api/bulk/preview` for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 500 providers, 411 already analyzed, and 89 still eligible; coverage increased from 409 to 411 | 2026-08-03 21:42 EDT |
| Remaining recovery taxonomy | Production task issue summary | 23 `crawl.navigation_failed`, 11 `source.not_policy`, 5 `source.unsupported_language`, 4 `source.inaccessible`, and one provider with both `graph.empty` and `model.incompatible`; 44 wrapper `execution.subprocess_failed` issues preserve process diagnostics | 2026-08-03 21:42 EDT |
| Curated source correction smoke test | Task `47031f78-bedd-415f-b04c-861ae2cec6fc` | `succeeded`: 5 completed and 0 failed after validated source corrections for Ares Management, FedEx, FedEx Freight, Paramount Skydance, and Qnity Electronics | 2026-08-04 12:46 EDT |
| S&P coverage reconciliation, curated batch | Production `/api/bulk/preview` for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 500 providers, 416 already analyzed, and 84 still eligible; coverage increased from 411 to 416 | 2026-08-04 12:47 EDT |
| Backend suite, warning semantics and source catalog | `./.venv/bin/pytest -q` | 74 passed; model compatibility warnings remain diagnostic output and no longer create blocked issues on successful tasks | 2026-08-04 12:49 EDT |
| Frontend validation, curated recovery release | `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build` | Passed; 34 tests and production bundle built | 2026-08-04 12:50 EDT |
| Bicep compilation, curated recovery release | `az bicep build --file infra/main.bicep --stdout` | Passed; SHA-256 `9f920f62bf6ed48ed91270fd3eed39d57495c310938573c700e17b5b5027504e` | 2026-08-04 12:48 EDT |
| ARM provider validation, curated recovery release | `az deployment group validate` against `poligrapher-rg` | Succeeded; correlation `d34bc6f7-887f-41c0-961c-b3e89b4770ab` | 2026-08-04 12:49 EDT |
| ARM what-if, curated recovery release | `az deployment group what-if --result-format ResourceIdOnly` | Succeeded; 15 existing resources deploy, 1 identity ignored, 0 deletes | 2026-08-04 12:49 EDT |
| Static RBAC review, curated recovery release | `infra/main.bicep`; live app identity configuration | No managed identities or role assignments; app identity remains `None` and existing secret-backed access is unchanged | 2026-08-04 12:48 EDT |
| Curated recovery production deployment | GitHub Actions run `30931110947` | Both immutable image builds, real-secret what-if, Bicep deployment, migrations, and endpoint verification succeeded at `46c3b581b831ac595b3b1f685fce5c67b18e9143` | 2026-08-04 13:07 EDT |
| Curated recovery live acceptance | Container Apps revision and migration execution | Revision `poligrapherc1de43-app--0000018` and migration execution `poligrapherc1de43-migrations-8y7k1y6` report `Succeeded`; app and worker use immutable `46c3b58` images | 2026-08-04 13:07 EDT |
| Warning-semantics production smoke test | Task `b2635d1a-c07c-4441-a3e1-6c82aa4b3d65` | Ares Management completed with outcome `succeeded`, 1 complete, 0 failed, and an empty issue list | 2026-08-04 13:10 EDT |
| Live role verification, curated recovery release | Container App identity configuration | App identity is `None`; managed-identity role verification is not applicable and existing secret-backed connections remain unchanged | 2026-08-04 13:07 EDT |
| Curated source correction batch two | Task `2371bd2c-c59a-4394-ae45-a7475ad86c05` | `succeeded`: Delta Air Lines, Expedia Group, and Sysco completed 3/3 with 0 failures and an empty issue list | 2026-08-04 13:18 EDT |
| S&P coverage reconciliation, curated batch two | Production `/api/bulk/preview` for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 500 providers, 419 already analyzed, and 81 still eligible; coverage increased from 416 to 419 | 2026-08-04 13:19 EDT |
| Backend suite, curated batch two catalog | `./.venv/bin/pytest -q` | 74 passed after persisting the three verified production sources in the versioned catalog | 2026-08-04 13:19 EDT |
| Curated source correction batch three | Task `1fb919f9-f992-4bb8-9df6-9a132c793001` | `partially_succeeded`: Marriott International completed; HP Inc. produced the standardized root issue `graph.empty` with manual recovery actions | 2026-08-04 15:04 EDT |
| S&P coverage reconciliation, curated batch three | Production `/api/bulk/preview` for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 500 providers, 420 already analyzed, and 80 still eligible; coverage increased from 419 to 420 | 2026-08-04 15:05 EDT |
| Validation, root-issue deduplication | `./.venv/bin/pytest -q`; `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build` | Passed: 75 backend tests, 34 frontend tests, type check, and production bundle | 2026-08-04 15:06 EDT |
| Root-failure preservation deployment | GitHub Actions run `30941797226` | Both immutable image builds, real-secret what-if, Bicep deployment, migrations, and endpoint verification succeeded at `4cd90f81942c49a8d809ab2a9d1c6cd56c0a93e9` | 2026-08-04 15:23 EDT |
| Root-failure preservation live acceptance | Container Apps revision and migration execution | Revision `poligrapherc1de43-app--0000019` is healthy; migration execution `poligrapherc1de43-migrations-5zundmi` succeeded; web and worker use immutable `4cd90f8` images | 2026-08-04 15:24 EDT |
| Root-issue deduplication smoke test | Task `17006841-f5c2-4a5d-ad28-564aba140a33` | HP Inc. completed with one `graph.empty` root issue and its manual recovery actions; no redundant `execution.subprocess_failed` wrapper was emitted | 2026-08-04 15:26 EDT |
| Comparison method isolation | `run_comparison`; `tests/test_comparison_persistence.py` | A failed website graph no longer discards a usable PDF-derived graph from the same comparison run | 2026-08-04 17:07 EDT |
| Validation, comparison method isolation | `./.venv/bin/pytest -q`; `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build`; `git diff --check` | Passed: 76 backend tests, 34 frontend tests, type check, production bundle, and whitespace validation | 2026-08-04 17:08 EDT |
| Comparison method isolation deployment | GitHub Actions run `30951035439` | Both immutable image builds, real-secret what-if, Bicep deployment, migrations, and endpoint verification succeeded at `9d3a2e488214918c5a6b4d3b3717770461dd4c7c` | 2026-08-04 17:23 EDT |
| Comparison method isolation live acceptance | Container Apps revision and migration execution | Revision `poligrapherc1de43-app--0000020` is healthy; migration execution `poligrapherc1de43-migrations-7ijj507` succeeded; web and worker use immutable `9d3a2e4` images | 2026-08-04 17:23 EDT |
| Representative graph-empty recovery | Task `6f1a7d9b-9d3f-46a4-96d3-38fca261807b` | Eight completed; Mondelez International recovered by preserving its successful website graph while seven providers remained empty in both methods | 2026-08-04 17:33 EDT |
| Remaining graph-empty class recovery | Task `c4a0ed7c-483a-4cd3-9c4c-9bb1e0c0a020` | 24 completed; ConocoPhillips, Genuine Parts Company, HP Inc., and PG&E Corporation recovered; 20 failed with standardized root issues | 2026-08-04 17:57 EDT |
| S&P coverage reconciliation, comparison isolation | Production `/api/bulk/preview` for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 500 providers, 425 already analyzed, and 75 still eligible; comparison isolation recovered 5 of the 32-company graph-empty class | 2026-08-04 17:57 EDT |
| Content-aware cohort source audit | `POST /api/collections/{collection_id}/audit-failures`; `cohort-source-audit` worker task | Read-only audit selects unresolved source-related root failures, validates current policy content, and records only application-validated replacement candidates | 2026-08-04 21:41 EDT |
| Validation, cohort source audit | `./.venv/bin/pytest -q`; `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build`; `git diff --check` | Passed: 78 backend tests, 34 frontend tests, type check, production bundle, and whitespace validation | 2026-08-04 21:42 EDT |

**Validated by:** azure-validate workflow

**Validation timestamp:** 2026-08-03 20:29 EDT

## 9. Files

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | Deployment source of truth | Complete |
| `infra/main.bicep` | Existing infrastructure and migration job | Updated |
| `poligrapher_app/data/sp500_sources.json` | Verified source snapshot | Generated |
| `poligrapher_app/services/source_catalog.py` | Safe importer | Implemented |
| `poligrapher_app/sync_source_catalog.py` | Migration-job entry point | Implemented |

## 10. Next Step

Audit the remaining 75 eligible companies by failure class. Run content-aware
source preflight for acquisition and validation failures, apply only validated
official replacements, then retry bounded class shards and reconcile coverage.
