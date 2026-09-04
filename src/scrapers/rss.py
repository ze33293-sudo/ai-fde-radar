"""RSS feed scraper implementation."""

import calendar
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import List, Optional
from email.utils import parsedate_to_datetime
import httpx
import feedparser

from .base import BaseScraper
from ..extractors import ExtractorRegistry
from ..models import ContentItem, SourceType, RSSSourceConfig

logger = logging.getLogger(__name__)


class RSSScraper(BaseScraper):
    """Scraper for RSS/Atom feeds."""

    def __init__(
        self,
        sources: List[RSSSourceConfig],
        http_client: httpx.AsyncClient,
        extractors: Optional[ExtractorRegistry] = None,
    ):
        """Initialize RSS scraper.

        Args:
            sources: List of RSS feed configurations
            http_client: Shared async HTTP client
            extractors: Optional registry of content extractors for full article fetching
        """
        super().__init__({"sources": sources}, http_client)
        self._extractors = extractors

    async def fetch(self, since: datetime) -> List[ContentItem]:
        """Fetch RSS feed items.

        Args:
            since: Only fetch items published after this time

        Returns:
            List[ContentItem]: Fetched content items
        """
        items = []
        sources = self.config["sources"]

        for source in sources:
            if not source.enabled:
                continue

            feed_items = await self._fetch_feed(source, since)
            items.extend(feed_items)

        return items

    async def _fetch_feed(
        self, source: RSSSourceConfig, since: datetime
    ) -> List[ContentItem]:
        """Fetch items from a single RSS feed.

        Args:
            source: RSS feed configuration
            since: Only fetch items after this time

        Returns:
            List[ContentItem]: Feed content items
        """
        items = []

        try:
            # Expand environment variables in URL (e.g. ${LWN_TOKEN})
            feed_url = re.sub(
                r"\$\{(\w+)\}",
                lambda m: os.environ.get(m.group(1), m.group(0)).strip(),
                str(source.url),
            )

            # Fetch feed content
            response = await self.client.get(feed_url, follow_redirects=True)
            response.raise_for_status()

            # Parse feed
            feed = feedparser.parse(response.text)

            for entry in feed.entries:
                # Parse published date
                published_at = self._parse_date(entry)
                if not published_at or published_at < since:
                    continue

                # Generate unique ID from feed URL and entry ID
                feed_id = str(source.url).split("//")[1].replace("/", "_")
                entry_id = entry.get("id", entry.get("link", ""))
                entry_hash = hashlib.sha256(str(entry_id).encode("utf-8")).hexdigest()[
                    :16
                ]

                # Extract content. Prefer a feed's full ``content:encoded``
                # payload over its teaser so evidence-heavy official feeds can
                # be assessed without an unnecessary second network fetch.
                content = self._extract_content(entry)
                tags = [tag.term for tag in entry.get("tags", [])]
                if not self._matches_keyword_filters(
                    source,
                    title=entry.get("title", "Untitled"),
                    content=content,
                    tags=tags,
                ):
                    continue

                if source.content_extractor and self._extractors:
                    extractor = self._extractors.get(source.content_extractor)
                    if extractor:
                        url = entry.get("link", "")
                        if url:
                            full = await extractor.extract(url, self.client)
                            if full:
                                content = full

                item = ContentItem(
                    id=self._generate_id("rss", feed_id, entry_hash),
                    source_type=SourceType.RSS,
                    title=entry.get("title", "Untitled"),
                    url=entry.get("link", str(source.url)),
                    content=content,
                    author=entry.get("author", source.name),
                    published_at=published_at,
                    profile=source.profile,
                    metadata={
                        "feed_name": source.name,
                        "category": source.category,
                        "tags": tags,
                        "region": source.region,
                        "source_tier": source.source_tier,
                        "practice_category": source.practice_category,
                    },
                )
                items.append(item)

        except httpx.HTTPError as e:
            logger.warning("Error fetching RSS feed %s: %s", source.name, e)
        except Exception as e:
            logger.warning("Error parsing RSS feed %s: %s", source.name, e)

        return items

    def _parse_date(self, entry: dict) -> datetime:
        """Parse publication date from feed entry.

        Args:
            entry: Feed entry data

        Returns:
            datetime: Parsed publication date or None
        """
        # Try different date fields
        for field in ["published", "updated", "created"]:
            if field in entry:
                try:
                    # Try parsing structured time first
                    if f"{field}_parsed" in entry and entry[f"{field}_parsed"]:
                        return datetime.fromtimestamp(
                            calendar.timegm(entry[f"{field}_parsed"]), tz=timezone.utc
                        )
                    # Fallback to string parsing
                    date_str = entry[field]
                    return parsedate_to_datetime(date_str)
                except Exception:
                    continue

        return None

    def _extract_content(self, entry: dict) -> str:
        """Extract text content from feed entry.

        Args:
            entry: Feed entry data

        Returns:
            str: Extracted text content
        """
        # ``content:encoded`` is commonly the complete first-party article,
        # while ``summary``/``description`` is often only a one-line teaser.
        if "content" in entry and entry.content:
            content = entry.content[0].get("value", "")
            if content:
                return content
        if "summary" in entry:
            return entry.summary
        if "description" in entry:
            return entry.description

        return ""

    @staticmethod
    def _matches_keyword_filters(
        source: RSSSourceConfig,
        *,
        title: str,
        content: str,
        tags: List[str],
    ) -> bool:
        """Apply optional case-insensitive filters to a feed entry.

        Large official feeds are useful only when their entries are narrowed to
        the configured practice pillar. General includes search the title,
        body, and feed categories; title includes search only the title so
        boilerplate or broad feed tags cannot admit an unrelated vendor article.
        """
        haystack = "\n".join([title, content, *tags]).casefold()
        title_haystack = title.casefold()
        includes = [keyword.casefold() for keyword in source.include_keywords]
        title_includes = [
            keyword.casefold() for keyword in source.include_title_keywords
        ]
        excludes = [keyword.casefold() for keyword in source.exclude_keywords]
        if includes and not any(
            RSSScraper._keyword_matches(keyword, haystack) for keyword in includes
        ):
            return False
        if title_includes and not any(
            RSSScraper._keyword_matches(keyword, title_haystack)
            for keyword in title_includes
        ):
            return False
        if excludes and any(
            RSSScraper._keyword_matches(keyword, haystack) for keyword in excludes
        ):
            return False
        return True

    @staticmethod
    def _keyword_matches(keyword: str, haystack: str) -> bool:
        """Match short tokens as words and longer phrases as substrings."""
        if keyword.isalnum() and len(keyword) <= 3:
            return re.search(rf"\b{re.escape(keyword)}\b", haystack) is not None
        return keyword in haystack
