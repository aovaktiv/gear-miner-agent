import unittest

from gear_miner.crawler import CrawlSettings, MultiPageCrawler
from gear_miner.models import GearCategory, SourceKind, SourceSeed


def product_page(name: str, brand: str, slug: str) -> str:
    return f"""
    <html>
      <body>
        <script type="application/ld+json">
          {{
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "{name}",
            "brand": {{"@type": "Brand", "name": "{brand}"}},
            "category": "Running Shoes",
            "url": "https://example.com/products/{slug}",
            "offers": {{"@type": "Offer", "price": "140.00", "priceCurrency": "USD"}}
          }}
        </script>
      </body>
    </html>
    """


ROOT_HTML = (
    product_page("Brooks Ghost 16", "Brooks", "brooks-ghost-16")
    + """
    <a href="/running?page=2">Next</a>
    <a href="/products/brooks-glycerin-21">Brooks Glycerin 21</a>
    <a href="https://shop.example.com/products/brooks-hyperion-max-2">Shop product</a>
    <a href="https://external.example.net/running?page=2">External result</a>
    """
)

PAGE_2_HTML = product_page("Brooks Adrenaline GTS 23", "Brooks", "brooks-adrenaline-gts-23")
PRODUCT_HTML = product_page("Brooks Glycerin 21", "Brooks", "brooks-glycerin-21")
SHOP_HTML = product_page("Brooks Hyperion Max 2", "Brooks", "brooks-hyperion-max-2")


class MultiPageCrawlerTest(unittest.TestCase):
    def test_follows_pagination_and_same_domain_product_links(self) -> None:
        payloads = {
            "https://example.com/running": ROOT_HTML,
            "https://example.com/running?page=2": PAGE_2_HTML,
            "https://example.com/products/brooks-glycerin-21": PRODUCT_HTML,
            "https://shop.example.com/products/brooks-hyperion-max-2": SHOP_HTML,
        }

        def fetch_html(url: str) -> str:
            if url not in payloads:
                raise AssertionError(f"Unexpected fetch for {url}")
            return payloads[url]

        crawler = MultiPageCrawler(fetch_html=fetch_html)
        seed = SourceSeed(
            name="Brooks Running",
            url="https://example.com/running",
            kind=SourceKind.BRAND,
            category=GearCategory.RUNNING_SHOE,
            brand="Brooks",
        )

        result = crawler.crawl_source(
            seed=seed,
            category=GearCategory.RUNNING_SHOE,
            requested_brand="Brooks",
            settings=CrawlSettings(max_pages_per_source=4, max_depth=2),
        )

        self.assertEqual(result.pages_crawled, 4)
        self.assertEqual(len(result.products), 4)
        self.assertIn("https://example.com/running?page=2", result.visited_urls)
        self.assertIn("https://example.com/products/brooks-glycerin-21", result.visited_urls)
        self.assertIn("https://shop.example.com/products/brooks-hyperion-max-2", result.visited_urls)

    def test_respects_allow_and_block_domains(self) -> None:
        payloads = {
            "https://example.com/running": ROOT_HTML,
            "https://example.com/running?page=2": PAGE_2_HTML,
        }

        def fetch_html(url: str) -> str:
            if url == "https://shop.example.com/products/brooks-hyperion-max-2":
                raise AssertionError("Blocked domain should not be fetched")
            if url not in payloads:
                raise AssertionError(f"Unexpected fetch for {url}")
            return payloads[url]

        crawler = MultiPageCrawler(fetch_html=fetch_html)
        seed = SourceSeed(
            name="Brooks Running",
            url="https://example.com/running",
            kind=SourceKind.BRAND,
            category=GearCategory.RUNNING_SHOE,
            brand="Brooks",
        )

        result = crawler.crawl_source(
            seed=seed,
            category=GearCategory.RUNNING_SHOE,
            requested_brand="Brooks",
            settings=CrawlSettings(
                allow_domains=("example.com", "shop.example.com"),
                block_domains=("shop.example.com",),
                max_pages_per_source=4,
                max_depth=2,
            ),
        )

        self.assertEqual(result.pages_crawled, 2)
        self.assertEqual(len(result.products), 2)
        self.assertNotIn("https://shop.example.com/products/brooks-hyperion-max-2", result.visited_urls)


if __name__ == "__main__":
    unittest.main()
