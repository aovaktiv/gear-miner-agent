# Architecture Notes

## Pipeline Shape

The current system is intentionally small and composable:

1. Source registry selects URLs for a category.
2. Fetcher downloads HTML for each source.
3. Extractor parses JSON-LD blocks and yields product observations.
4. Normalizer derives brand, model, canonical keys, and simple cleanup.
5. Store writes a repeatable snapshot to disk.

## Why JSON-LD First

Structured data gives us a much better baseline than brittle selectors:

- product names are usually cleaner
- pricing is often already normalized
- brand and SKU data are easier to capture
- extraction logic stays generic across many sites

When JSON-LD is missing or weak, the next layers should be:

- meta tag extraction
- targeted HTML selectors
- rendered-page support for JavaScript-heavy pages

## Future Components

### Source Strategy Layer

Different source kinds need different handling:

- direct brand sites
- retailers
- marketplaces
- review/editorial publications

Each strategy may eventually define crawl depth, allowed URL patterns, extraction rules, and trust scoring.

### Entity Resolution

The same running shoe will appear across many sources with slightly different names. A later resolver should merge observations into a single catalog product using:

- brand and model similarity
- SKU and GTIN hints
- canonical product URLs
- attribute agreement

### Compliance And Politeness

This scaffold does not implement robots parsing yet, but the project should evolve toward:

- robots-aware crawling
- source-level rate limits
- retry backoff
- clear user-agent identification
- snapshot logging for reproducibility
