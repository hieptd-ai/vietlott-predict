# Vietlott-data Architecture

Production crawling and rendering are implemented in the Go crawler (`/crawler`, binary `bin/vietlott-crawler`). Legacy Python code and the PyPI package live in `/src`.

## Product Configuration

The Go crawler configures products in `crawler/internal/model/product.go` and `crawler/internal/client/products.go`. The legacy Python package uses `vietlott.config.products.ProductConfig`.

Key points:
- Cookies are no longer required for crawling.
- Vietlott serves data across paginated endpoints. The crawler and backfill mechanism are designed around page-based fetching with targeted gap calculation.

## Runner

The Go crawler runs via scheduled execution on local/on-premise hardware (see `bin/github_data.sh` and `Procfile`) and commits updated data back to GitHub. GitHub Actions is no longer used for data crawling because the Vietlott website blocks non-Vietnam IP addresses (see [issue #13](https://github.com/vietvudanh/vietlott-data/issues/13) and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

### Go CLI Commands (Recommended)
- `./bin/vietlott-crawler status`: Compare existing stored draws vs. latest upstream draws.
- `./bin/vietlott-crawler sync --all`: Crawl latest draw results and backfill missing draws.
- `./bin/vietlott-crawler render-readme`: Update `readme.md` with current data statistics.
- `./bin/vietlott-crawler render-docs`: Update `docs/index.html`, English `/en/`, individual product pages, and `docs/sitemap.xml` with current data statistics.

### Legacy Python CLI Commands (Deprecated)
- `vietlott-crawl`: Crawl latest draw results.
- `vietlott-missing`: Detect and backfill missing draws.
- `vietlott-render-readme`: Update repository README with current data statistics.
- `vietlott-render-docs`: Update `docs/index.html` with current data statistics.
## Analysis & ML Dashboard

`src/machine_learning/` holds the prediction strategies and the analysis pipeline behind `docs/analysis/`:

- `games.py`: prize tiers and exact hypergeometric probabilities for Power 6/55 and Mega 6/45. The Power 6/55 bonus number only decides Jackpot 2.
- `features.py` + `strategies/ml_classifier.py`: causal per-number features and walk-forward scikit-learn classifiers.
- `analysis.py` + `render_analysis.py`: frequency and randomness tests, strategy backtests and ML evaluation. They write `docs/analysis/analysis.json` and `analysis-data.js`.

Regenerate with `make render-analysis`. The Deploy GitHub Pages workflow also does this before every deploy. Research notes are in [docs/ML_RESEARCH.md](docs/ML_RESEARCH.md).
