# Gear Miner Domain Model

## Core Objects

### Gear Category

The top-level catalog segment being mined.

Examples:

- running-shoe
- trail-shoe
- hiking-boot
- hydration-pack

### Source Seed

A configured entry point for a crawl.

Fields:

- name
- url
- source kind
- category
- tags
- notes

### Raw Product Observation

A single product record extracted from one page on one run. This is not yet the global truth about the product. It is an observation tied to a source.

Fields:

- source metadata
- source URL
- product URL
- extracted name
- extracted brand
- price
- currency
- SKU or model identifiers
- raw metadata
- extraction method

### Catalog Product

A normalized product entity derived from one or more raw observations.

Early in the project this can still be source-biased. Over time it should merge observations across retailers, brands, and editorial sources.

Fields:

- canonical key
- category
- brand
- model
- normalized display name
- known URLs
- observed prices
- attribute facts
- supporting observations

### Attribute Fact

A normalized product attribute and its evidence.

Examples for running shoes:

- support type
- use case
- surface
- stack height
- heel-to-toe drop
- weight
- plate presence
- cushioning family

Each fact should eventually track:

- value
- unit
- confidence
- source
- timestamp

### Crawl Outcome

The result of attempting one source during a run.

Fields:

- source
- status
- extracted count
- error message

### Mine Report

A summary of one mining run.

Fields:

- category
- started at
- finished at
- attempted sources
- succeeded sources
- failed sources
- product observations
- outcomes by source

## Modeling Notes

- A source seed is a crawl input.
- A raw observation is evidence.
- A catalog product is a normalized entity.
- Attribute facts should remain traceable to the observations that produced them.
- Cross-source entity resolution should be layered on later instead of hard-coded into the first extractor.
