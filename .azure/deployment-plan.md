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

- [x] All validation checks pass
  - [x] Core Validation (CLI, auth, build, validate, what-if)
  - [x] Linting (Bicep compilation and application suites)
  - [x] Azure Policy Validation
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
| Validation, cohort source audit | `./.venv/bin/pytest -q`; `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build`; `git diff --check` | Passed: 78 backend tests, 34 frontend tests, type check, production bundle, and whitespace validation | 2026-08-04 |
| Bicep and ARM validation, cohort source audit | `az bicep build`; `az deployment group validate`; `az deployment group what-if --result-format ResourceIdOnly` | Passed; ARM correlation `3375a44e-2fe3-4a0c-9076-1efbc7c55a90`; preview succeeded with 16 resources and 0 deletes | 2026-08-04 |
| Policy and static RBAC review, cohort source audit | Subscription policy assignment inventory; `infra/main.bicep`; live app and worker identity configuration | Enforced Security Center default policy remains assigned; no Bicep role assignments; app and worker identities remain `None` with existing secret-backed access unchanged | 2026-08-04 |
| Representative graph-empty recovery | Task `6f1a7d9b-9d3f-46a4-96d3-38fca261807b` | Eight completed; Mondelez International recovered by preserving its successful website graph while seven providers remained empty in both methods | 2026-08-04 17:33 EDT |
| Remaining graph-empty class recovery | Task `c4a0ed7c-483a-4cd3-9c4c-9bb1e0c0a020` | 24 completed; ConocoPhillips, Genuine Parts Company, HP Inc., and PG&E Corporation recovered; 20 failed with standardized root issues | 2026-08-04 17:57 EDT |
| S&P coverage reconciliation, comparison isolation | Production `/api/bulk/preview` for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 500 providers, 425 already analyzed, and 75 still eligible; comparison isolation recovered 5 of the 32-company graph-empty class | 2026-08-04 17:57 EDT |
| Content-aware cohort source audit | `POST /api/collections/{collection_id}/audit-failures`; `cohort-source-audit` worker task | Read-only audit selects unresolved source-related root failures, validates current policy content, and records only application-validated replacement candidates | 2026-08-04 21:41 EDT |
| Validation, cohort source audit | `./.venv/bin/pytest -q`; `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build`; `git diff --check` | Passed: 78 backend tests, 34 frontend tests, type check, production bundle, and whitespace validation | 2026-08-04 21:42 EDT |
| Cohort source audit deployment | GitHub Actions run `30967433455` | Both immutable image builds, real-secret what-if, Bicep deployment, migrations, and endpoint verification succeeded at `33bb527b6c1e5892adcd8e0f125804c46ada4b53` | 2026-08-04 22:04 EDT |
| Cohort source audit live acceptance | Container Apps revision and migration execution | Revision `poligrapherc1de43-app--0000021` is healthy; migration execution `poligrapherc1de43-migrations-n9z4l5f` succeeded; web and worker use immutable `33bb527` images and have no managed identities | 2026-08-04 22:04 EDT |
| S&P source-failure audit | Task `3486b68c-1a6c-4d4a-99a8-48bd818ec3d1` | `succeeded`: all 51 source-related failures audited with 9 current sources valid, 26 validated candidates, 16 unresolved, and 0 audit errors | 2026-08-04 22:14 EDT |
| Current-source retry batch | Task `56f26788-43f6-49f9-8d07-bad063e03ddc` | 9/9 remained failures: 5 navigation, 2 unsupported-language, 1 not-policy, and 1 graph-empty; proved source preflight alone does not imply analyzer recovery | 2026-08-04 22:25 EDT |
| Curated replacement recovery batch | Task `f43dfad3-96a7-4e75-8dd6-0e72adbad397` | 9 of 11 recovered; Northern Trust remained `source.not_policy` and Yum! Brands shifted to `graph.empty` | 2026-08-04 22:29 EDT |
| S&P coverage reconciliation, source audit | Production graph-aware preview and latest root-issue summary | 434 analyzed and 66 eligible; remaining taxonomy is 26 `graph.empty`, 18 `crawl.navigation_failed`, 9 `source.inaccessible`, 7 `source.not_policy`, 4 `source.unsupported_language`, and 2 `pdf.invalid_source` | 2026-08-04 22:30 EDT |
| Audit-loop hardening | `cohort_audit`; official-domain tests | Validated candidates are no longer fetched twice; off-domain matches are surfaced as `review_required` instead of safe replacements | 2026-08-04 23:02 EDT |
| Validation, source-audit recovery | `./.venv/bin/pytest -q`; `git diff --check` | Passed: 79 backend tests and whitespace validation | 2026-08-04 23:02 EDT |
| Source-audit hardening deployment | GitHub Actions run `30971135255` | Immutable image builds, real-secret what-if, deployment, durable source import, migrations, and endpoint verification succeeded at `028d45a67837a228f1e5eaf3da48d7fe2d903ff6` | 2026-08-04 23:27 EDT |
| Source-audit hardening live acceptance | Container Apps revision, migration execution, and graph-aware preview | Revision `poligrapherc1de43-app--0000022` is healthy; migration `poligrapherc1de43-migrations-rpz3ynh` succeeded; web and worker use immutable `028d45a` images; coverage remains 434/500 | 2026-08-04 23:27 EDT |
| Graph-empty root-cause reproduction | Allegion direct Chromium crawl and sanitized HTTP fallback | The direct browser representation generated 60 nodes and 63 links (35 nodes and 43 links after trimming), while the same production fallback path generated an empty graph from a JavaScript policy shell; `graph.empty` is therefore a source-representation failure for this cohort, not a graph persistence failure | 2026-08-04 23:35 EDT |
| Graph-empty alternate-source audit | Local content-aware audit of the exact 26-company cohort | Found 20 same-domain candidates, 5 off-domain candidates requiring review, and 1 unresolved company; narrow or unrelated pages were excluded before changing any source | 2026-08-04 23:41 EDT |
| Curated graph-empty recovery batch | Task `161cd1ab-d749-4e5b-ae55-02900c5db2ae` | 5 of 7 recovered: Allegion, Duke Energy, Electronic Arts, PulteGroup, and Welltower; Cooper Companies and Johnson Controls retained standardized `crawl.navigation_failed` issues | 2026-08-04 23:45 EDT |
| S&P coverage reconciliation, graph-empty sources | Production graph-aware preview and latest root-issue summary | 439 analyzed and 61 eligible; remaining taxonomy is 20 `crawl.navigation_failed`, 19 `graph.empty`, 9 `source.inaccessible`, 7 `source.not_policy`, 4 `source.unsupported_language`, and 2 `pdf.invalid_source` | 2026-08-04 23:46 EDT |
| Validation, graph-empty source recovery | `./.venv/bin/pytest -q`; JSON catalog parse; `git diff --check` | Passed: 80 backend tests, durable source catalog validation, and whitespace validation | 2026-08-04 23:49 EDT |
| Graph-empty source recovery deployment | GitHub Actions run `30973475374` | Both immutable image builds, real-secret preview, Azure deployment, durable source import, migrations, and endpoint verification succeeded at `6eb27a7a6cedbdf7de566c0120113da61adfab0b` | 2026-08-05 00:03 EDT |
| Graph-empty source recovery live acceptance | Container Apps revision, worker job, migration execution, source API, and graph-aware preview | Revision `poligrapherc1de43-app--0000023` is healthy; migration `poligrapherc1de43-migrations-xjq8omf` succeeded; web and worker use immutable `6eb27a7` images; all seven curated URLs are live; coverage is 439/500 | 2026-08-05 00:04 EDT |
| Full unresolved-cohort audit | Task `418025b3-ed45-42cf-8077-108e37d4935f` | `succeeded`: 61 checked, 10 current sources valid, 26 nominal replacements, 14 review-required candidates, 11 unresolved, and 0 audit errors; manual scope review excluded investor, product, regional, employment, event, search, and lookalike-domain false positives | 2026-08-05 00:14 EDT |
| Content-bearing graph-empty batch | Task `e4ebf384-cfbc-4caf-afad-9a79b4f52ac3` | `partially_succeeded`: Cintas recovered through its official general-policy representation; Yum! Brands retained `graph.empty`, and its experimental query-parameter source was reverted | 2026-08-05 00:22 EDT |
| S&P coverage reconciliation, full audit | Production graph-aware preview and latest root-issue summary | 440 analyzed and 60 eligible; remaining taxonomy is 20 `crawl.navigation_failed`, 18 `graph.empty`, 9 `source.inaccessible`, 7 `source.not_policy`, 4 `source.unsupported_language`, and 2 `pdf.invalid_source` | 2026-08-05 00:23 EDT |
| Production baseline, validated-source recovery | Container Apps revision and graph-aware preview | Revision `poligrapherc1de43-app--0000023` is healthy on immutable `6eb27a7` images; coverage remains 440 analyzed and 60 eligible | 2026-08-14 EDT |
| Failed-cohort cause refinement | Strict reproduction of the 10 prior `current_valid` results against the analyzer's language and policy-pattern contract | Four HTML sources are directly pipeline-valid (Cooper Companies, Lumentum, Otis, and Targa); PNC is a retryable PDF download; American Tower and Snap-on are non-English, Digital Realty and Northern Trust are false-positive policy pages, and ServiceNow remains inaccessible | 2026-08-14 EDT |
| Direct-source fallback acceptance | Forced the production navigation/fallback error for Cooper Companies, then ran the real pipeline from application-fetched validated HTML | Generated `graph-original.yml` (11,038 bytes) and `output.pdf`; temporary materialized HTML was removed | 2026-08-14 EDT |
| Validation, validated-source recovery | `./.venv/bin/pytest -q`; `git diff --check` | Passed: 86 backend tests, including strict HTML validation, direct-source fallback, audit classification, and transient PDF retry; whitespace validation passed | 2026-08-14 EDT |
| Validated-source recovery deployment | GitHub Actions run `31809614999` | Both immutable image builds, infrastructure preview, Azure deployment, migrations, and endpoint verification succeeded at `5f7ea3e745f978fe75e9b4417bdb2d6d27b5d279` | 2026-08-14 EDT |
| Validated-source recovery live acceptance | Container Apps revision, worker job, and migration execution | Revision `poligrapherc1de43-app--0000024` is healthy; web and worker use immutable `5f7ea3e` images; migration `poligrapherc1de43-migrations-tczslby` succeeded | 2026-08-14 EDT |
| Five-company recovery smoke | Task `bf27564a-2761-4b37-a626-dc011c4a320d` | `partially_succeeded`: Cooper Companies and Otis Worldwide recovered through validated direct HTML; Lumentum and Targa produced usable website graphs but their optional PDF-from-page branches failed language validation; PNC exhausted two direct PDF attempts and exposed a scheme-less proxy configuration boundary | 2026-08-14 EDT |
| S&P coverage reconciliation, direct-source fallback | Production graph-aware preview for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 442 analyzed and 58 eligible; coverage increased from 440 to 442 | 2026-08-14 EDT |
| Validation, comparison and proxy follow-up | `./.venv/bin/pytest -q`; Python bytecode compilation; `git diff --check` | Passed: 90 backend tests; scheme-less proxy normalization, `pdf.download_timeout`, and generation-time comparison isolation covered | 2026-08-14 EDT |
| Comparison and proxy follow-up deployment | GitHub Actions run `31812047309` | Both immutable image builds, infrastructure preview, Azure deployment, migrations, and endpoint verification succeeded at `846b4cfdfe5d7db82625a7b87dbf54991febc5bf` | 2026-08-14 EDT |
| Comparison and proxy live acceptance | Container Apps revision, worker job, and migration execution | Revision `poligrapherc1de43-app--0000025` is healthy; web and worker use immutable `846b4cf` images; migration `poligrapherc1de43-migrations-l0ehpoj` succeeded | 2026-08-14 EDT |
| Three-company comparison-isolation acceptance | Task `b355add6-6d7b-4cd4-bc9a-1b410ddb7824` | `partially_succeeded`: Lumentum and Targa recovered because their website graphs survived optional PDF failures; PNC's direct PDF attempts timed out and its proxy transfer reached the 900-second worker guard as standardized `execution.timeout` | 2026-08-14 EDT |
| S&P coverage reconciliation, comparison isolation | Production graph-aware preview for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 444 analyzed and 56 eligible; coverage increased from 442 to 444 | 2026-08-14 EDT |
| Validation, remote-PDF wall-clock bound | `./.venv/bin/pytest -q`; `git diff --check` | Passed: 91 backend tests; trickling proxy streams are bounded per attempt and retain `pdf.download_timeout` taxonomy | 2026-08-14 EDT |
| Remote-PDF wall-clock deployment | GitHub Actions run `31813958859` | Immutable images, infrastructure, migrations, and endpoint verification succeeded at `2f979ff`; revision `poligrapherc1de43-app--0000026` and migration `poligrapherc1de43-migrations-vohlsrq` became healthy | 2026-08-14 EDT |
| Chunk-level deadline acceptance | Task `7db07b86-cb2a-44e8-ab0f-0b98da0e94fe` | PNC still reached the 900-second worker guard because the proxy blocked before yielding a response chunk; terminal taxonomy remained `execution.timeout` | 2026-08-14 EDT |
| Signal deadline deployment | GitHub Actions run `31815691933` | Immutable images, infrastructure, migrations, and endpoint verification succeeded at `c708bdd`; revision `poligrapherc1de43-app--0000027` and migration `poligrapherc1de43-migrations-657yh5q` became healthy | 2026-08-14 EDT |
| Signal deadline acceptance | Task `0ab81ffb-9530-4cf9-b37f-0cb7da70b3bb`; worker execution `poligrapherc1de43-worker-594pw` | PNC proved `SIGALRM` could not reliably interrupt the proxy handshake inside the HTTP/OpenSSL stack; the superseded task was cancelled without changing coverage, establishing the need for a killable process boundary | 2026-08-14 EDT |
| Validation, isolated PDF attempts | `./.venv/bin/pytest -q`; `git diff --check` | Passed: 92 backend tests, including forced termination for pre-response and continuously trickling stalls; whitespace validation passed | 2026-08-14 EDT |
| Isolated PDF-attempt deployment | GitHub Actions run `31817527600` | Both immutable image builds, infrastructure preview and deployment, migrations, and endpoint verification succeeded at `e3f8aeeeccb5aebc84f277866019bc74f4d2d5aa` | 2026-08-14 EDT |
| Isolated PDF-attempt live acceptance | Container Apps revision, worker job, and migration execution | Revision `poligrapherc1de43-app--0000028` is healthy; web and worker use exact immutable `e3f8aee` images; migration `poligrapherc1de43-migrations-98lftsn` succeeded | 2026-08-14 EDT |
| PNC terminal-failure acceptance | Task `9196a8f3-8073-4d3e-8932-f3c649fdbe90` | `partially_succeeded` in about 211 seconds with root issue `pdf.download_timeout`; the issue exposes retry, replacement-source, and official-PDF-upload actions, with no `execution.timeout` or `execution.unclassified` escape | 2026-08-14 EDT |
| Final S&P coverage reconciliation | Production graph-aware preview for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 444 analyzed and 56 eligible; this recovery released four analyses (Cooper Companies, Otis Worldwide, Lumentum, and Targa) while leaving PNC safely retryable | 2026-08-14 EDT |
| Fast-audit failure reproduction | Task `e6118028-3002-4f36-9496-98408b29eaab`; worker `poligrapherc1de43-worker-ksjs8` | Legacy audit stalled at 5/55 and surfaced invalid no-op replacements that repeated the current URL; the read-only task and exact worker execution were cancelled and later settled terminally | 2026-08-15 EDT |
| Validation, bounded two-phase audit | `./.venv/bin/pytest -q`; Python bytecode compilation; `git diff --check` | Passed: 95 backend tests; fast/deep budgets, cross-path source exclusion, strict replacement validation, and eight-lane audit concurrency covered | 2026-08-15 EDT |
| Bounded two-phase audit deployment | GitHub Actions run `31905175512` | Both immutable images, infrastructure, migrations, and endpoint verification succeeded at `c35b8df2364fa02be5062bc2719296bb54615554` | 2026-08-15 EDT |
| Bounded two-phase audit live acceptance | Container Apps revision, worker job, and migration execution | Revision `poligrapherc1de43-app--0000029` was healthy on exact `c35b8df` images; migration `poligrapherc1de43-migrations-ldysy1a` succeeded | 2026-08-15 EDT |
| Full fast source audit | Task `9a49740c-1708-45ba-8fb3-02631e6f6a27` | `succeeded`: 55/55 completed in about one minute with 0 audit errors; 37 unresolved, 9 nominal same-domain candidates, and 9 review-required candidates; scope review rejected investor, annual-report, jobs, manuals, app-specific, regional, subsidiary, competitor, and lookalike pages | 2026-08-15 EDT |
| Reviewed two-source recovery | Task `fb21a52f-e829-4b58-b05d-573284e6f092` | `partially_succeeded`: GE Aerospace recovered on its official corporate privacy page; Costco remained `graph.empty` and its experimental URL was reverted | 2026-08-15 EDT |
| S&P coverage reconciliation, fast audit | Production graph-aware preview | 445 analyzed and 55 eligible; GE Aerospace raised coverage by one | 2026-08-15 EDT |
| Deep-audit process-boundary finding | Task `07b9d6e1-7a78-41ea-8745-143e50e02824`; worker `poligrapherc1de43-worker-h2q5p` | Deep discovery stalled at 12/54 inside homepage/proxy requests; the read-only execution was cancelled, establishing that HTTP timeouts alone did not bound a complete company audit | 2026-08-15 EDT |
| Validation, isolated audit attempts | `./.venv/bin/pytest -q`; Python bytecode compilation; `git diff --check` | Passed: 96 backend tests; every fast/deep company audit runs in a killable spawn process with 75/150-second wall-clock deadlines | 2026-08-15 EDT |
| Isolated audit-attempt deployment | GitHub Actions run `31906534240` | Both immutable images, infrastructure, durable GE Aerospace source import, migrations, and endpoint verification succeeded at `b5dade5fb450babca14d46b6a51f8ba4d2af89a8` | 2026-08-15 EDT |
| Isolated audit-attempt live acceptance | Container Apps revision, worker job, and migration execution | Revision `poligrapherc1de43-app--0000030` is healthy; web and worker use exact `b5dade5` images; migration `poligrapherc1de43-migrations-o0mjk7p` succeeded | 2026-08-15 EDT |
| Full bounded deep audit | Task `1f1a989c-7bd1-41d0-9fec-cb3f4450f5a4` | `partially_succeeded`: all 54 completed; 27 unresolved, 4 distinct validated candidates, and 23 explicit 150-second audit errors. The process boundary resumed progress beyond the prior 12-company stall and settled the parent task | 2026-08-15 EDT |
| Deep-source recovery batch | Task `e29e1c25-f92f-41fa-8743-918c562b70da` | `partially_succeeded`: General Mills and Snap-on recovered; Vulcan Materials returned `source.unsupported_language` and its experimental URL was reverted; Northrop Grumman's audience-specific prospect notice was not applied | 2026-08-15 EDT |
| Final S&P maximized-safe coverage | Production graph-aware preview and deep-audit root summary | 447 analyzed and 53 eligible. Remaining roots: 17 `graph.empty`, 15 `crawl.navigation_failed`, 9 `source.inaccessible`, 7 `source.not_policy`, 2 `source.unsupported_language`, 2 `pdf.invalid_source`, and 1 `pdf.download_timeout`; no remaining audited replacement is safe for automatic application | 2026-08-15 EDT |
| Repeatable cohort recovery pipeline | `POST /api/collections/{collection_id}/recover-failures`; collection **Recover** action | Selects only unresolved auditable failures, uses bounded parallel fast/deep audits, retries standardized transient failures directly, runs normal isolated analysis, retains only non-empty graphs, restores every source field on failure/cancellation, and emits resumable JSONL evidence | 2026-08-15 EDT |
| Recovery safety-gate deployment | GitHub Actions run `31915414696` | Exact `8802ba99d4c8d25c7cafd7c6ce399d6511a2b50b` images deployed; revision `poligrapherc1de43-app--0000038` is healthy and migration `poligrapherc1de43-migrations-56m9aeb` succeeded | 2026-08-15 EDT |
| Guarded full-cohort recovery acceptance | Task `81239bec-2a9f-44c5-aca6-6ac4f109aea7` | 53/53 terminal: 17 attempted, Henry Schein recovered on its existing canonical source, 16 analysis failures settled, 15 audit errors bounded, and 21 manual failures remained unresolved; no replacement URL was auto-committed | 2026-08-15 EDT |
| S&P coverage reconciliation, repeatable recovery | Production graph-aware preview and provider drift comparison | 448 analyzed and 52 eligible. Confirmed narrow eCummins and 2011 annual-report experiments were exact-deleted and their source URLs restored; final run introduced no replacement-source drift | 2026-08-15 EDT |
| Validation, recovery architecture consolidation | `./.venv/bin/pytest -q`; `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build`; `git diff --check` | Passed: 111 backend tests, 35 frontend tests, TypeScript validation, production bundle, and whitespace validation | 2026-08-15 22:40 EDT |
| Bicep core validation, recovery architecture consolidation | Azure validation helper against `poligrapher-rg` | Azure CLI authentication, Bicep compilation, ARM validation, and what-if completed successfully | 2026-08-15 22:40 EDT |
| Resource-level what-if, recovery architecture consolidation | `az deployment group what-if --result-format ResourceIdOnly` | 15 existing resources deploy, 1 GitHub identity ignored, and 0 resources delete | 2026-08-15 22:40 EDT |
| Policy and RBAC validation, recovery architecture consolidation | Azure Policy assignment inventory; `infra/main.bicep`; live app and worker identity configuration | East US 2 remains permitted; MFA write/delete and audit-only Security Center policies reviewed; no Bicep role assignments; app and worker identities remain `None` with existing secret-backed access unchanged | 2026-08-15 22:40 EDT |
| Recovery architecture deployment | GitHub Actions run `31922495243` | Exact `bc38bbda6ff3a9f400ce47f2fbdee7ef405e5753` images deployed; revision `poligrapherc1de43-app--0000039`, migrations, and endpoint verification succeeded | 2026-08-15 22:53 EDT |
| Representative recovery smoke | Task `6c25d88a-ae1c-4d6b-910d-c95ecc24f642` | 3/3 terminal with standardized unresolved, audit-error, and crawl-failure outcomes; all original source fields were preserved | 2026-08-15 23:03 EDT |
| Full repeatable cohort recovery | Task `f7f93b4b-8d72-4180-b767-304f03e9efb5` | 52/52 terminal: 16 attempted, Johnson Controls, Newmont, and SBA Communications recovered, 13 analyses failed, 15 audits timed out, 21 remained unresolved, and no replacement source was auto-committed | 2026-08-16 00:03 EDT |
| S&P coverage reconciliation, consolidated recovery | Production graph-aware bulk preview | 451 analyzed and 49 eligible; coverage increased from 89.6% to 90.2% through the generic retry-current path | 2026-08-16 00:03 EDT |
| Validation, queue resilience and cohort retry | `./.venv/bin/pytest -q`; frontend typecheck, tests, and build; `az bicep build`; `git diff --check` | Passed: 112 backend tests, 35 frontend tests, production bundle, Bicep compilation, and whitespace validation | 2026-08-16 00:05 EDT |
| ARM validation, queue resilience and cohort retry | `az deployment group validate`; resource-level what-if | Validation succeeded with correlation `c5954a42-a2cc-4945-9386-ae0213b92a80`; 15 existing resources deploy, 1 GitHub identity ignored, and 0 resources delete | 2026-08-16 00:07 EDT |
| Queue resilience and cohort retry deployment | GitHub Actions run `31925892068` | Exact `118b6e0cdeea2ea53765c4de3b434fba005ed177` images deployed; revision `poligrapherc1de43-app--0000040`, migration `poligrapherc1de43-migrations-bj4w31m`, and endpoint verification succeeded; worker `maxExecutions` is 2 | 2026-08-16 00:18 EDT |
| Production task-level transient retry | Task `00613732-0cde-4d49-99ae-a19a118644cd` | Retry action selected exactly 26 transient-only providers; 26/26 settled with 11 analysis failures, 15 bounded audit errors, 0 recoveries, 0 rollbacks, and no manual-only targets | 2026-08-16 00:55 EDT |
| Final S&P coverage reconciliation | Production graph-aware bulk preview | 451 analyzed and 49 eligible (90.2% coverage); the transient-only retry produced no additional safe graphs and confirms the automatic boundary | 2026-08-16 00:55 EDT |
| Worker queue-resilience acceptance | Container Apps Job configuration and execution history | Two post-queue scaler executions both exited successfully in 44 seconds; the two-slot configuration avoided blockage and left no running worker execution | 2026-08-16 00:56 EDT |
| Production recovery UI audit | In-app browser, Tasks workspace | Standardized recovery issues and recommended actions rendered, but recovery cards lacked the task-level `Retry failed` control despite backend support | 2026-08-16 00:58 EDT |
| Validation, recovery retry control | Frontend typecheck, test suite, production build, and `git diff --check` | Passed: 36 frontend tests; completed cohort-recovery tasks expose transient-only retry while active tasks remain inert | 2026-08-16 00:59 EDT |
| Recovery retry control deployment | GitHub Actions run `31927946905` | Exact `7f6cd3764eca5cd895481f784a4fe1158e5c99cc` images deployed; revision `poligrapherc1de43-app--0000041`, migration `poligrapherc1de43-migrations-mhrivwl`, and endpoint verification succeeded; worker `maxExecutions` remains 2 | 2026-08-16 01:05 EDT |
| Recovery retry control production acceptance | In-app browser, Tasks workspace | Completed 26-company and 52-company cohort-recovery cards expose `Retry failed` alongside standardized issues and recommended actions; the control was verified without queuing another retry | 2026-08-16 01:06 EDT |
| Reviewed source recovery | Tasks `edcab660-3401-4384-8551-80cf84be3b34` and `fbf37e4b-1caf-4907-898e-b078d4dd016d` | Xcel Energy, American Water Works, Fortive, and Tyson Foods recovered through versioned official sources; graph-aware coverage increased from 451 to 455 | 2026-08-16 EDT |
| Source-freshness and worker-cache deployment | GitHub Actions run `31970066339`; commit `43e81f79444a8ad4b4432ec0f9fa031de823072c` | Newly verified sources are retried when their catalog timestamp is newer than the original failure; revision `poligrapherc1de43-app--0000043` succeeded, and the cold worker build fell from 10m27s to 6m19s | 2026-08-16 EDT |
| Warm catalog deployment acceptance | GitHub Actions runs `31970438994` and `31971143229` | Exact `6307d46` and `e3afafd` source snapshots deployed as revisions `--0000044` and `--0000045`; warm worker builds completed in 1m31s and 1m26s | 2026-08-16 EDT |
| Reachability hard-deadline deployment | GitHub Actions run `31971342188`; commit `eb79a6b5cc4501258364ef41e1c3705f421a8fd9` | Revision `poligrapherc1de43-app--0000046`, exact web/worker images, and migration `poligrapherc1de43-migrations-dhw6wef` succeeded; Amazon's previously 6m15s probe settled in 61 seconds | 2026-08-16 EDT |
| Browser-challenge routing deployment | GitHub Actions run `31971967524`; commit `520c23ef620178fc5de9dd24395b2e7e2f281238` | Revision `poligrapherc1de43-app--0000047`, exact images, and migration `poligrapherc1de43-migrations-8mmold5` succeeded; website 403/429 responses now proceed directly to bounded Chromium while binary document checks remain strict | 2026-08-16 EDT |
| Browser-challenge recovery acceptance | Tasks `12d7d02a-315b-4545-9854-c40742677de6` and `7e436f45-b02b-4dd6-a8c6-58be4baa950a` | CMS Energy, Pinnacle West Capital, Prologis, and United Rentals recovered with non-empty graphs; Amazon, Extra Space Storage, and IFF retained standardized terminal failures | 2026-08-16 EDT |
| Canonical challenged-source deployment | GitHub Actions run `31972761839`; commit `82b044a1917fb7a9ae2002e44304a7a084aecd4c` | Revision `poligrapherc1de43-app--0000048`, exact web/worker images, and migration `poligrapherc1de43-migrations-9hulej7` succeeded; canonical live URLs now precede stale Wayback finals only for persisted 403/429 sources, while Jina and non-challenge archive provenance remain unchanged | 2026-08-16 EDT |
| Validation, challenge-class recovery | `./.venv/bin/pytest -q`; focused pipeline and comparison tests; `git diff --check` | Passed: 119 backend tests, including hard probe termination, strict PDF probing, browser-challenge routing, and canonical-vs-archive source selection; whitespace validation passed | 2026-08-16 EDT |
| Final S&P coverage reconciliation | Production graph-aware bulk preview for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 459 analyzed and 41 eligible (91.8% coverage), up from 451 analyzed at the start of this recovery phase; all remaining companies retain terminal or bounded recovery evidence | 2026-08-16 EDT |
| Remaining recovery taxonomy | Latest issue per graph-uncovered provider | 13 `recovery.unresolved`, 12 `crawl.navigation_failed`, 9 bounded `recovery.audit_error`, 3 `graph.empty`, 2 `pdf.download_timeout`, and 2 `source.not_policy`; no `execution.unclassified` result remains | 2026-08-16 EDT |
| Validation, bounded fallback and recovery-result preservation | `./.venv/bin/pytest -q`; `git diff --check` | Passed: 133 backend tests and whitespace validation; ordinary analysis fallback is bounded to 12 seconds and two candidates, while successful fast-audit results survive an optional deep-audit failure | 2026-08-16 EDT |
| Bounded fallback and recovery-result deployment | GitHub Actions run `31978816480`; commits `933c9f9` and `d3fdda9` | Exact `933c9f9` images, infrastructure, migrations, and endpoint verification succeeded as revision `poligrapherc1de43-app--0000052` | 2026-08-16 EDT |
| Nine-company residual recovery | Task `b794b214-1bfc-4d3c-b6d9-fae7e3599242` | 9/9 settled terminally; Cummins and Warner Bros. Discovery recovered with non-empty graphs, while seven failures retained standardized root causes. Cummins completed fallback discovery and comparison in under one second instead of repeating multi-minute deep discovery | 2026-08-16 EDT |
| Stale-archive origin recovery deployment | GitHub Actions run `31979619557`; commit `e374f44` | Exact immutable images, infrastructure, migrations, and endpoint verification succeeded; unreachable Wayback replay URLs now yield their embedded official origins before a bounded archive lookup of that origin | 2026-08-16 EDT |
| Content-negotiation challenge deployment | GitHub Actions run `31980218911`; commit `67ff7ed` | Exact immutable images, infrastructure, migrations, and endpoint verification succeeded; website status 406 joins the centralized 403/429 browser-challenge path while binary PDF validation remains strict | 2026-08-16 EDT |
| Content-negotiation production acceptance | Task `709b9989-b1d6-478c-84a7-d53081b9298e` | Mettler Toledo's unavailable archive resolved to its official origin; an HTTP 406 probe was admitted to Chromium and captured successfully. Both analysis modes produced no canonical elements, so the terminal root was correctly refined to `graph.empty` | 2026-08-16 EDT |
| Non-policy residual recovery | Task `61b33e17-4faa-4e61-a616-a1636395899c` | 6/6 settled terminally with no audit errors or unsafe source mutation; Coca-Cola's current official policy reached both analyzers but remained `graph.empty`, and five companies retained `recovery.unresolved` evidence | 2026-08-16 EDT |
| Acquisition and document residual recovery | Task `16deb7f4-4e0c-468e-8e4e-54495ff99d87` | 18/18 settled terminally: Medtronic recovered through a validated official replacement and non-empty graphs; 11 attempts failed analysis, 4 remained unresolved, and 2 lower-confidence candidates were retained for manual review instead of being auto-applied | 2026-08-16 EDT |
| Final S&P maximized-safe coverage | Production graph-aware preview for collection `4cac831c-a33d-438c-a0d5-55ee871418e9` | 471 analyzed and 29 eligible (94.2% coverage), up from 468 before the final residual batches and from 440 before the broader recovery work; all remaining providers have terminal, bounded, or manual-review evidence | 2026-08-16 EDT |
| Final residual taxonomy | Latest root class for the 29 graph-uncovered providers | 9 `crawl.navigation_failed`, 7 `graph.empty`, 11 unresolved or review-required source cases, and 2 `pdf.download_timeout`; direct, proxy, archive-origin, bounded discovery, isolated analysis, and graph-verification paths are exhausted without forcing unsafe one-off source changes | 2026-08-16 EDT |
| Validation, linked-policy recovery | `./.venv/bin/pytest -q`; `git diff --check` | Passed: 141 backend tests for bounded official-page link discovery, byte-level HTML/PDF validation, PDF text extraction, derived document-type headings, and rollback-safe recovery; whitespace validation passed | 2026-08-17 EDT |
| Linked-policy recovery deployment | GitHub Actions run `31994256513`; commit `234ade4405` | Exact immutable images, infrastructure, migrations, and endpoint verification succeeded as revision `poligrapherc1de43-app--0000055`; migration `poligrapherc1de43-migrations-13rbv36` succeeded | 2026-08-17 EDT |
| Seven-company linked-source recovery | Task `610fd6af-4576-4be0-855d-0c2b9be66b90` | 7/7 settled terminally without unsafe source mutation. Ameriprise's official linked PDF was found, but its uppercase `.PDF` filename exposed a shared case-sensitive artifact lookup; the attempted replacement was rolled back. Coca-Cola's candidate was rejected as `source.not_policy`, and the other five remained unresolved | 2026-08-17 EDT |
| Validation, case-insensitive PDF artifacts | `./.venv/bin/pytest -q`; `git diff --check` | Passed: 143 backend tests, including uppercase PDF discovery and standardized `pdf.invalid_source` classification; whitespace validation passed | 2026-08-17 EDT |
| Uppercase-PDF correction deployment | GitHub Actions run `31995123957`; commit `f987e14d8910dcd29313659e5ca08472f7d391d6` | Exact web and worker images deployed as revision `poligrapherc1de43-app--0000056`; migration `poligrapherc1de43-migrations-ut1j4vk` and endpoint verification succeeded; app and worker identities remain `None`, so managed-identity role verification is not applicable | 2026-08-17 EDT |
| Generic linked-PDF production acceptance | Task `99209480-8cd8-4f89-9680-73f65295c9a0` | Ameriprise recovered through the bounded official-hub link path with confidence 0.86; the exact official uppercase PDF was archived, normal analysis produced a non-empty standard graph, and the provider source was committed only after success | 2026-08-17 EDT |
| S&P coverage reconciliation, linked-policy recovery | Production graph-aware bulk preview | 472 analyzed and 28 eligible (94.4% coverage). Ameriprise is now skipped as already analyzed; the remaining capability classes are 9 navigation failures, 6 graph-empty policies, 11 unresolved or review-required source cases, and 2 PDF timeouts | 2026-08-17 EDT |
| Deep residual recovery | Task `701f7699-17de-490f-9a07-3cb67b475d62` | 28/28 settled terminally: LyondellBasell recovered through a validated official subpage; 12 analyses failed, 1 replacement was rolled back, 6 candidates require review, and 8 remained unresolved. Coverage reached 473/500 | 2026-08-17 EDT |
| Validation, official-hub portal recovery | `./.venv/bin/pytest -q`; frontend typecheck, tests, and build; `git diff --check` | Passed: 147 backend tests, 36 frontend tests, TypeScript validation, production bundle, and whitespace validation | 2026-08-17 EDT |
| Bicep and ARM validation, official-hub portal recovery | Azure validation helper; resource-level `az deployment group what-if` | CLI authentication, Bicep compilation, ARM validation, and what-if passed; exact preview has 15 existing resources to deploy, 1 GitHub identity ignored, and 0 resource deletions | 2026-08-17 EDT |
| Policy and RBAC validation, official-hub portal recovery | Subscription policy inventory; `infra/main.bicep`; live app and worker identity configuration | Existing Security Center policy remains assigned; no Bicep role assignments; app and worker identities remain `None`, with no access or cost changes | 2026-08-17 EDT |
| Validation, recovery ranker and graph artifacts | `./.venv/bin/pytest -q`; frontend typecheck, tests, and build; fresh SQLite Alembic upgrade; OpenAPI inspection; `git diff --check` | Passed: 176 backend tests, 41 frontend tests, TypeScript validation, production bundle, migration through `20260817_09`, public graph-only endpoint boundary, and whitespace validation | 2026-08-17 12:14 EDT |
| Bicep and ARM validation, recovery ranker and graph artifacts | `az bicep lint`; `az deployment group validate`; resource-level `az deployment group what-if --result-format ResourceIdOnly` | Bicep lint and ARM validation passed with correlation `7da08a13-26ad-48a4-8a41-09be17677458`; preview has 15 existing resources to deploy, 1 GitHub identity ignored, and 0 resource deletions | 2026-08-17 12:14 EDT |
| Policy and RBAC validation, recovery ranker and graph artifacts | Azure MCP policy assignment inventory; `infra/main.bicep`; live app and worker provisioning state | East US 2 remains allowed; MFA write/delete policies and audit-only Security Center policy reviewed; no Bicep role assignments or new identities; both live resources report `Succeeded` | 2026-08-17 12:14 EDT |
| Container image validation gate, recovery ranker and graph artifacts | Local Docker availability; `.github/workflows/deploy-azure.yml` | Docker daemon is unavailable locally; both immutable production image builds remain blocking CI prerequisites before deployment | 2026-08-17 12:14 EDT |

**Validated by:** azure-validate workflow

**Validation timestamp:** 2026-08-17 12:14 EDT

## 9. Files

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | Deployment source of truth | Complete |
| `infra/main.bicep` | Existing infrastructure and migration job | Updated |
| `poligrapher_app/data/sp500_sources.json` | Verified source snapshot | Generated |
| `poligrapher_app/services/source_catalog.py` | Safe importer | Implemented |
| `poligrapher_app/sync_source_catalog.py` | Migration-job entry point | Implemented |

## 10. Next Step

Deploy the recovery-ranker observation schema and keep the worker in `shadow`.
Run normal cohort recovery to collect implicit labels; do not train until the
minimum population gate passes, and do not enable `assist` until every coded
promotion check passes. The model remains subordinate to source validation,
provenance, audience, graph acceptance, and rollback rules.

Keep coverage recovery as a pipeline feature: standardized issue selection,
bounded parallel audit, direct/proxy/archive-origin acquisition, bounded
official-page link discovery, strict HTML/PDF validation, case-insensitive PDF
artifact handling, isolated normal analysis, non-empty-graph acceptance,
complete rollback, JSONL evidence, and task-level retry or manual actions. Do
not add provider-specific code or force a source mutation merely to reach a
nominal 500/500 count.
