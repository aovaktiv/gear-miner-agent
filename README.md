# Gear Miner Agent

A focused web-mining project for building a structured gear catalog from public product pages, starting with running shoes.

## What This Project Is

Gear Miner is an agent-oriented pipeline that:

- keeps a registry of gear sources to crawl
- fetches product/category pages from the web
- extracts structured product data from JSON-LD
- normalizes raw observations into a catalog-friendly model
- writes repeatable catalog snapshots for downstream ranking, comparison, and enrichment

The first vertical is `running-shoe`, but the project is designed to expand into broader gear categories over time.

## Current MVP

The repo currently includes:

- a Python package with a CLI
- a local browser UI for prompting and managing mining runs
- a running-shoe source registry
- a JSON-LD product extractor
- a mining pipeline that fetches, extracts, normalizes, and saves a snapshot
- CSV and Excel export output for mined product results
- local tests with HTML fixtures so the core extraction path works without live network access

## Quickstart

Create an environment and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

List the seeded running-shoe sources:

```bash
python3 -m gear_miner list-sources
```

Run a prompted mining pass:

```bash
python3 -m gear_miner mine
```

Example prompt flow:

```text
Step 1: Enter brand name: Nike
Step 2: Enter product category: Running shoes
```

Run the same mining pass non-interactively and save a snapshot:

```bash
python3 -m gear_miner mine --brand Nike --category "Running shoes" --limit 3 --output data/running-shoes.json
```

Launch the local browser UI:

```bash
python3 -m gear_miner ui
```

The UI starts on `http://127.0.0.1:8765` by default and gives you:

- `Step 1: Brand`
- `Step 2: Product category`
- an output choice of `CSV` or `Excel`
- recent run history with download links for the export file and snapshot JSON

UI-managed exports and snapshots are saved under `data/ui/`.

## Public URL

This repo now includes a production deployment path for:

```text
https://brand.search.getaktiv.org
```

The deployment stack uses:

- `Dockerfile` for the Gear Miner app
- `docker-compose.yml` for the app plus reverse proxy
- `deploy/Caddyfile` for HTTPS and proxying on `brand.search.getaktiv.org`

Deployment instructions are in [Deployment](docs/deployment.md).

Run the local test suite:

```bash
python3 -m unittest discover -s tests -v
```

## Project Layout

```text
gear_miner/          Python package
docs/                product and system notes
tests/               local fixtures and unit tests
data/                generated snapshots
```

## Near-Term Roadmap

- add richer source strategies for review/editorial sites
- track product observations across multiple sources
- add attribute extraction for stack height, drop, weight, surface, and support type
- score source trust and freshness
- add configurable crawl politeness, retries, and robots-aware scheduling

## Docs

- [MVP](docs/mvp.md)
- [Domain model](docs/domain-model.md)
- [Architecture](docs/architecture.md)
