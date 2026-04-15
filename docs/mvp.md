# Gear Miner MVP

## Goal

Ship a practical agent that can crawl the web for gear products, normalize the results, and produce structured catalog snapshots. The first category is running shoes because the market is large, product attributes matter, and public product pages often expose useful structured data.

## Initial Outcomes

- Seed and manage a list of running-shoe sources
- Crawl a small number of source pages safely
- Extract product observations from structured HTML data
- Normalize brand, model, pricing, and URLs into one schema
- Save catalog snapshots that can be reviewed, diffed, or enriched later

## In Scope

- Source registry for direct brands and retailers
- Fetching HTML for category/product pages
- JSON-LD product extraction
- Brand/model normalization
- Snapshot persistence to JSON
- CLI commands for source listing and mining
- Local tests with fixture HTML

## Out of Scope For The First Pass

- Full JavaScript rendering
- Distributed crawling
- Proxy rotation
- Advanced anti-bot handling
- Embedding-based deduplication
- Review sentiment analysis
- Price history tracking
- Production scheduling or queue orchestration

## Why Start With Running Shoes

- Strong consumer demand and high product velocity
- Clear product families and variants
- Rich attributes that matter to buyers
- Good expansion path into other athletic and outdoor gear

## Product Principles

- Prefer structured data before brittle HTML selectors
- Preserve raw observations when confidence is low
- Treat extraction and normalization as separate concerns
- Keep the output audit-friendly so every record can be traced back to its source

## Suggested Next Releases

### Release 1

- direct brand and retailer sources
- JSON-LD extraction
- snapshot output
- basic tests

### Release 2

- review/editorial source ingestion
- richer attribute extraction
- source freshness and confidence scoring
- retry and rate-limit controls

### Release 3

- cross-source product entity resolution
- change detection across runs
- category expansion beyond running shoes
- job scheduling and automation
