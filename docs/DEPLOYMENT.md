# Deployment Guide

This document outlines the deployment and scheduling architecture for vietlott-predict (a fork of [vietvudanh/vietlott-data](https://github.com/vietvudanh/vietlott-data)).

## Architecture & Geo-blocking

The Vietlott web endpoints block HTTP requests originating from IP addresses outside Vietnam (see [upstream issue #13](https://github.com/vietvudanh/vietlott-data/issues/13)). As a result:

- Cloud-hosted runners (such as standard GitHub Actions environments) cannot crawl data from Vietlott directly.
- The crawler is deployed on local/on-premise hardware located in Vietnam.
- Crawled data and updated statistics are committed and pushed back to the GitHub repository.

## Prerequisites

- Go 1.27+
- Git configured with commit and push permissions to the repository

## Local Setup

```bash
git clone https://github.com/hieptd-ai/vietlott-predict.git
cd vietlott-predict
make build-crawler
```

## Local Runner Pipeline

The automated crawler runs via `bin/github_data.sh`.

### What the Runner Script Does

1. Pulls the latest changes from `main`:
   ```bash
   git pull --rebase --autostash origin main
   ```
2. Builds the Go crawler into `bin/vietlott-crawler`.
3. Fetches the latest draws and backfills missing ones for every product (`MAX_DRAWS` bounds each product's gap fill, `0` means no limit):
   ```bash
   ./bin/vietlott-crawler sync --all --max-draws "$MAX_DRAWS"
   ```
4. Regenerates repository documentation and web statistics:
   ```bash
   ./bin/vietlott-crawler render-readme
   ./bin/vietlott-crawler render-docs
   ```
5. Commits changed data files and documentation, then pushes to `origin main`.

A product that fails to sync does not stop the run; the other products are still rendered and committed.

### Scheduling

The runner can be scheduled via cron or a task runner (see `Procfile`):

```cron
0 * * * * cd /path/to/vietlott-data && bash bin/github_data.sh
```

On macOS, you can alternatively use `launchd` or a cron entry via `crontab -e`.
On Linux, a systemd timer or cron job can execute the script at your desired interval.

For a Raspberry Pi, cross-compile with `make build-arm-pi` and copy `bin/vietlott-crawler-arm64`.

## Manual Execution

```bash
./bin/vietlott-crawler status                      # existing vs latest draw per product
./bin/vietlott-crawler sync --product keno         # latest draws + backfill for one product
./bin/vietlott-crawler missing --product power655  # backfill missing draws only
./bin/vietlott-crawler render-readme
./bin/vietlott-crawler render-docs
```

Product names: `power655`, `power645`, `power535`, `keno`, `bingo18`, `3d`, `3d_pro`.

### Run Tests
```bash
cd crawler && go vet ./... && go test ./...
```

## Legacy Python Crawler (deprecated)

The Python crawler (`uv run vietlott-crawl <product>`, `vietlott-missing`, `vietlott-render-*`) is kept for the PyPI package and will be removed in a future release. Tests and linting for it:

```bash
uv sync --dev
uv run pytest
uv run ruff check --select I --fix ./src && uv run ruff format ./src
```

## Other Deployments

### GitHub Pages (Static Documentation)
- Workflow: `.github/workflows/deploy-pages.yml`
- Runs on every push to `main`, once a day, after each data sync, and on manual dispatch.
- Steps: run the Go and ML tests, then render `readme.md` and `docs/` with the Go renderer, then generate the analysis dashboard data (`src/machine_learning/render_analysis.py`), then verify freshness and SEO metadata (`test_freshness.py`), and finally deploy `docs/`.

## Automated Build & Deploy for this Fork (free, no local runner)

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | every push / pull request | ruff lint + pytest (Python), `go vet` / `go test` / `go build` (Go) |
| `sync-data.yml` | 00:41 and 12:41 UTC, manual | copies `data/*.jsonl` from the upstream project (crawled in Vietnam), re-renders README/docs, commits to `main`, dispatches the deploy |
| `deploy-pages.yml` | push to `main`, daily, dispatched by the sync | builds and deploys the site to GitHub Pages |

One-time setup in the GitHub repository:

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Actions:** enable workflows if GitHub disabled them (forks start with scheduled workflows off).
3. **Settings → Actions → General → Workflow permissions:** "Read and write permissions", so `sync-data.yml` can push the synced data. If `main` is protected, allow `github-actions[bot]` to push or turn the sync off.
4. Optional **Settings → Secrets and variables → Actions → Variables**:
   - `VIETLOTT_SITE_URL`: the public site URL when you use a custom domain (default `https://<owner>.github.io/<repo>/`).
   - `VIETLOTT_GA_ID`: your Google Analytics measurement id (`G-…`). Without it, no analytics tag is rendered.
   - `UPSTREAM_REPO`: the data source for the sync (default `vietvudanh/vietlott-data`).

### Site URLs & SEO
Templates keep the upstream URLs so the fork merges cleanly with upstream. `crawler/internal/render/site.go` rewrites every rendered page so that canonical/hreflang links, Open Graph and Twitter tags, JSON-LD, the sitemap, robots.txt, llms.txt and raw-data download links point to this repository and its Pages site. The site comes from `VIETLOTT_REPO` / `VIETLOTT_SITE_URL` and defaults to `hieptd-ai/vietlott-predict`. The upstream author stays credited as the dataset `creator`, and links to upstream issues are kept.

### PyPI Publishing
- Workflow: `.github/workflows/publish-to-pypi.yaml`
- Automatically triggers when a new version tag starting with `v` (e.g. `v0.2.7`) is pushed to GitHub.
