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
- a running-shoe source registry
- a JSON-LD product extractor
- a mining pipeline that fetches, extracts, normalizes, and saves a snapshot
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

Run a mining pass and save a snapshot:

```bash
python3 -m gear_miner mine --category running-shoe --limit 3 --output data/running-shoes.json
```

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
