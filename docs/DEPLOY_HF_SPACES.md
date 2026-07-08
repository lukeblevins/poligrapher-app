# Deploying to Hugging Face Spaces (free Docker Space)

This app **cannot** run on GitHub Pages — Pages only serves static files, and the
backend needs a live Python process (FastAPI + torch/spaCy NLP, a Playwright
browser, a SQLite database, and background schedulers). A **Docker Space** on
Hugging Face runs the whole thing — API + SPA on one origin — for free.

> **Free-tier caveat:** the free CPU Space (2 vCPU / 16 GB RAM) has an
> **ephemeral disk**. The SQLite DB resets whenever the Space restarts, so on
> every boot the container re-seeds from `poligrapher_app/policy_list.csv`
> (see `docker/entrypoint.sh`). Anything a visitor adds at runtime is lost on
> restart. For durable storage, attach [persistent
> storage](https://huggingface.co/docs/hub/spaces-storage) (paid) and point
> `DATABASE_URL` at it, or use an external Postgres.

## What's in the repo

| File | Purpose |
|---|---|
| `Dockerfile` | Two-stage build: compiles the React SPA, then a Python image that installs the backend, **bakes in** the ~700 MB poligrapher models + spaCy model + Playwright Firefox, and serves API + SPA on port **7860**. |
| `docker/entrypoint.sh` | Seeds the DB (idempotent) then starts the app. |
| `.dockerignore` | Keeps the build context small. |
| README frontmatter | `sdk: docker` + `app_port: 7860` — how a Space knows to build the Dockerfile. |

No CORS or API-base-URL changes are needed: FastAPI serves the built SPA, and the
SPA calls `/api` on the same origin.

## Option A — push this repo straight to a Space (simplest)

1. Create a Space at <https://huggingface.co/new-space> → **Docker** → **Blank**.
   (Free **CPU basic** hardware is enough.)
2. Push this repo to the Space's git remote:

   ```sh
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space <your-branch>:main
   ```

   You'll be prompted for your HF username and a
   [token](https://huggingface.co/settings/tokens) (use it as the password).
3. The Space builds the Dockerfile and boots. First build is slow (torch +
   models); later builds are cached. App comes up at
   `https://huggingface.co/spaces/<your-username>/<space-name>`.

The README frontmatter travels with the repo, so the Space picks up the Docker
SDK and port automatically.

## Option B — auto-deploy from GitHub on every push

Keep GitHub as the source of truth and mirror to the Space in CI. Add an
`HF_TOKEN` repo secret (a **write** token), then a workflow:

```yaml
# .github/workflows/deploy-hf-space.yml
name: Deploy to HF Spaces
on:
  push:
    branches: [main]        # or your deployment branch
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Push to Space
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          git push --force \
            https://user:$HF_TOKEN@huggingface.co/spaces/<your-username>/<space-name> \
            HEAD:main
```

This isn't committed by default — create the Space first, then drop it in and set
`<your-username>/<space-name>`.

## Local smoke test (optional)

```sh
docker build -t poligrapher-app .
docker run --rm -p 7860:7860 poligrapher-app
# open http://localhost:7860
```

## Trimming image size (optional)

The default `torch` wheel pulls CUDA libraries you don't need on a CPU Space. To
slim the image, install the CPU build before the project in the Dockerfile:

```dockerfile
RUN pip install --user --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --user --no-cache-dir .
```

## Other hosts

If you outgrow the free tier, the same `Dockerfile` runs unchanged on Render,
Fly.io, Railway, or Google Cloud Run — set `PORT` (and a persistent
`DATABASE_URL`) via their env config.
