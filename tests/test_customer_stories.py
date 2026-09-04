from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from src.models import CustomerStoriesSourceConfig, SourceType
from src.scrapers.customer_stories import CustomerStoriesScraper


LISTING_HTML = """
<html><body>
  <nav><a href="/customers">Customer stories</a></nav>
  <article class="story-card">
    <a href="/customers/pictet"><h3>Pictet turns weeks of work into hours with Claude Code</h3></a>
    <p>Pictet rolled out Claude with training and an API gateway.</p>
    <time datetime="2026-09-02T00:00:00Z">September 2, 2026</time>
    <a href="/customers/pictet">View story</a>
  </article>
  <article class="story-card">
    <a href="https://claude.com/customers/dxc"><h3>DXC modernizes insurance workflows</h3></a>
    <p>DXC deployed an AI workflow and reduced processing time by 40%.</p>
    <span>September 1, 2026</span>
  </article>
  <article class="story-card">
    <a href="/customers/old"><h3>An older story</h3></a>
    <span>August 1, 2026</span>
  </article>
</body></html>
"""


def test_customer_story_listing_uses_canonical_links_dates_and_deduplicates(
    monkeypatch,
) -> None:
    source = CustomerStoriesSourceConfig(
        name="Claude Customer Stories",
        url="https://claude.com/customers",
        story_path_prefix="/customers/",
        max_results=10,
    )
    client = httpx.AsyncClient()
    scraper = CustomerStoriesScraper([source], client)

    async def fake_request(*args, **kwargs):  # type: ignore[no-untyped-def]
        return httpx.Response(
            200,
            text=LISTING_HTML,
            request=httpx.Request("GET", str(source.url)),
        )

    monkeypatch.setattr("src.scrapers.customer_stories.safe_request", fake_request)
    items = asyncio.run(
        scraper.fetch(datetime(2026, 8, 30, tzinfo=timezone.utc))
    )
    asyncio.run(client.aclose())

    assert [item.title for item in items] == [
        "Pictet turns weeks of work into hours with Claude Code",
        "DXC modernizes insurance workflows",
    ]
    assert [str(item.url) for item in items] == [
        "https://claude.com/customers/pictet",
        "https://claude.com/customers/dxc",
    ]
    assert all(item.source_type == SourceType.CUSTOMER_STORIES for item in items)
    assert all(item.metadata["practice_category"] == "enterprise-case" for item in items)
    assert all(item.metadata["publication_date_source"] == "official-listing" for item in items)


def test_customer_story_listing_failure_is_a_source_failure_not_fake_content(
    monkeypatch,
) -> None:
    source = CustomerStoriesSourceConfig(
        name="Claude Customer Stories",
        url="https://claude.com/customers",
    )
    client = httpx.AsyncClient()
    scraper = CustomerStoriesScraper([source], client)

    async def failed_request(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("src.scrapers.customer_stories.safe_request", failed_request)
    items = asyncio.run(scraper.fetch(datetime.now(timezone.utc)))
    asyncio.run(client.aclose())

    assert items == []
