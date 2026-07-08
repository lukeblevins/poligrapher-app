# Deploying to Google Cloud Run

This app can't run on GitHub Pages — the backend needs a live Python process
(FastAPI + torch/spaCy NLP, a Playwright browser, SQLite, schedulers). **Cloud
Run** runs the same container we built (`Dockerfile`), scales to zero when idle,
and stays within the free tier for light demo traffic.

The app serves the API and the built SPA on one origin, so no CORS or API-base
changes are needed. Cloud Run injects a `PORT` env var; the app already honors it
(`poligrapher_app/__main__.py`).

> **Know before you go:**
> - **Cold starts (~30–60 s).** With scale-to-zero, the first request after idle
>   spins up an instance and loads the NLP models. Fine for a demo; set
>   `--min-instances 1` (costs more) if you want it always warm.
> - **Ephemeral SQLite.** Cloud Run's filesystem is in-memory, so the DB resets
>   between instances. The container re-seeds from `policy_list.csv` on each
>   start; anything a visitor adds is lost on restart. For durable data, use
>   Cloud SQL (Postgres) and set `DATABASE_URL`.
> - **Scheduled acquisition won't fire while scaled to zero.** APScheduler only
>   runs when an instance is alive. Use `--min-instances 1` if you need it.
> - **Memory.** We request `4Gi`; bump to `8Gi` if the model load OOMs.

## Quick manual deploy (no CI)

With the [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and
`gcloud init` done:

```sh
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com

gcloud run deploy poligrapher-app \
    --source . \
    --region us-central1 \
    --allow-unauthenticated \
    --port 8080 --memory 4Gi --cpu 2 --timeout 3600 \
    --min-instances 0 --max-instances 3 --no-cpu-throttling
```

`--source .` uses Cloud Build to build the `Dockerfile`, pushes the image to
Artifact Registry, and deploys — no manual registry steps. The command prints the
public URL when it finishes.

## Auto-deploy from GitHub (`.github/workflows/deploy-cloud-run.yml`)

The committed workflow builds + deploys on every push to `main`, using **Workload
Identity Federation** (keyless — no service-account JSON stored in GitHub).

### 1. One-time GCP setup

Run these once (replace `PROJECT_ID`; adjust names as you like):

```sh
PROJECT_ID=your-project-id
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
REPO=lukeblevins/poligrapher-app     # your GitHub owner/repo

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com iamcredentials.googleapis.com

# Deployer service account + roles
gcloud iam service-accounts create gh-deployer --display-name="GitHub deployer"
SA=gh-deployer@$PROJECT_ID.iam.gserviceaccount.com
for role in roles/run.admin roles/cloudbuild.builds.editor \
            roles/artifactregistry.writer roles/storage.admin \
            roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:$SA" --role="$role"
done

# Workload Identity pool + GitHub provider
gcloud iam workload-identity-pools create github --location=global \
    --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc github \
    --location=global --workload-identity-pool=github \
    --display-name="GitHub OIDC" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='$REPO'" \
    --issuer-uri="https://token.actions.githubusercontent.com"

# Let this repo impersonate the deployer SA
POOL=projects/$PROJECT_NUM/locations/global/workloadIdentityPools/github
gcloud iam service-accounts add-iam-policy-binding "$SA" \
    --role=roles/iam.workloadIdentityUser \
    --member="principalSet://iam.googleapis.com/$POOL/attribute.repository/$REPO"

# Print the provider resource name for the GitHub secret below
echo "$POOL/providers/github"
```

### 2. GitHub config (Settings → Secrets and variables → Actions)

| Kind | Name | Value |
|---|---|---|
| Variable | `GCP_PROJECT_ID` | your project id |
| Variable | `GCP_REGION` | e.g. `us-central1` |
| Variable | `CLOUD_RUN_SERVICE` | e.g. `poligrapher-app` |
| Secret | `GCP_WORKLOAD_IDENTITY_PROVIDER` | the `projects/…/providers/github` string printed above |
| Secret | `GCP_SERVICE_ACCOUNT` | `gh-deployer@PROJECT_ID.iam.gserviceaccount.com` |

### 3. Deploy

Push to `main` (or run the workflow from the **Actions** tab). The job fails fast
with a clear message if any of the five values is missing.

## Cost

For a low-traffic demo with scale-to-zero, expect **$0–a few dollars/month**:
Cloud Run's monthly free tier covers 2M requests plus generous vCPU/memory-seconds,
and you're billed only while an instance is alive. Watch out for
`--min-instances 1` (keeps one instance always running = steady cost) and any GPU
(we don't use one — the image installs CPU-only torch).

## Other hosts

The same `Dockerfile` runs unchanged on Fly.io, Render, or a plain VM — set
`PORT` (Cloud Run/Fly inject it) and, for durable data, a persistent
`DATABASE_URL`.
