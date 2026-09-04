"""Scraper for first-party customer-story listing pages."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseScraper
from ..extractors.trafilatura import ARTICLE_HEADERS
from ..models import ContentItem, CustomerStoriesSourceConfig, SourceType
from ..url_security import UnsafeURLError, safe_request


logger = logging.getLogger(__name__)

_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)
_GENERIC_LINK_TEXT = {
    "customer story",
    "read customer story",
    "read story",
    "view customer story",
    "view story",
    "learn more",
}


class CustomerStoriesScraper(BaseScraper):
    """Discover dated stories from official vendor customer-story indexes.

    Search indexes are useful for breadth but can surface stale redirects, copied
    headlines, and pages that block GitHub runners. A first-party listing supplies
    the canonical story URL and real publication date before model scoring.
    """

    def __init__(
        self,
        sources: List[CustomerStoriesSourceConfig],
        http_client: httpx.AsyncClient,
    ):
        super().__init__({"sources": sources}, http_client)

    async def fetch(self, since: datetime) -> List[ContentItem]:
        items: List[ContentItem] = []
        for source in self.config["sources"]:
            if source.enabled:
                items.extend(await self._fetch_listing(source, since))
        return items

    async def _fetch_listing(
        self,
        source: CustomerStoriesSourceConfig,
        since: datetime,
    ) -> List[ContentItem]:
        try:
            response = await safe_request(
                self.client,
                "GET",
                str(source.url),
                headers=ARTICLE_HEADERS,
            )
            response.raise_for_status()
        except (httpx.HTTPError, UnsafeURLError) as exc:
            logger.warning("Error fetching customer stories %s: %s", source.name, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        by_url: dict[str, ContentItem] = {}
        for anchor in soup.find_all("a", href=True):
            story_url = self._story_url(anchor, source)
            if not story_url:
                continue
            container = self._story_container(anchor, source)
            if container is None:
                continue
            published_at = self._published_at(container)
            if published_at is None or published_at < since:
                continue
            title = self._story_title(anchor, container)
            if not title:
                continue
            content = "\n".join(container.stripped_strings).strip()
            native_hash = hashlib.sha256(story_url.encode("utf-8")).hexdigest()[:16]
            item = ContentItem(
                id=self._generate_id("customer_stories", source.name, native_hash),
                source_type=SourceType.CUSTOMER_STORIES,
                title=title,
                url=story_url,
                content=content,
                author=source.name,
                published_at=published_at,
                profile=source.profile,
                metadata={
                    "source_name": source.name,
                    "listing_url": str(source.url),
                    "category": source.category,
                    "region": source.region,
                    "source_tier": source.source_tier,
                    "practice_category": source.practice_category,
                    "source_practice_category": source.practice_category,
                    "publication_date_source": "official-listing",
                },
            )
            previous = by_url.get(story_url)
            if previous is None or len(item.content) > len(previous.content):
                by_url[story_url] = item

        return sorted(
            by_url.values(),
            key=lambda item: item.published_at,
            reverse=True,
        )[: source.max_results]

    @staticmethod
    def _story_url(
        anchor: Tag,
        source: CustomerStoriesSourceConfig,
    ) -> Optional[str]:
        href = str(anchor.get("href") or "").strip()
        if not href:
            return None
        absolute = urljoin(str(source.url), href)
        path = urlsplit(absolute).path.rstrip("/") + "/"
        prefix = source.story_path_prefix
        if not path.startswith(prefix) or path == prefix:
            return None
        return absolute.split("#", 1)[0]

    @classmethod
    def _story_container(
        cls,
        anchor: Tag,
        source: CustomerStoriesSourceConfig,
    ) -> Optional[Tag]:
        current: Optional[Tag] = anchor
        for _ in range(8):
            if current is None or current.name in {"body", "html"}:
                break
            text = " ".join(current.stripped_strings)
            if _DATE_RE.search(text):
                story_urls = {
                    url
                    for nested in current.find_all("a", href=True)
                    if (url := cls._story_url(nested, source))
                }
                if len(story_urls) == 1:
                    return current
            parent = current.parent
            current = parent if isinstance(parent, Tag) else None
        return None

    @staticmethod
    def _published_at(container: Tag) -> Optional[datetime]:
        for time_tag in container.find_all("time"):
            raw = str(time_tag.get("datetime") or "").strip()
            if raw:
                try:
                    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    return (
                        parsed.replace(tzinfo=timezone.utc)
                        if parsed.tzinfo is None
                        else parsed.astimezone(timezone.utc)
                    )
                except ValueError:
                    pass
        match = _DATE_RE.search(" ".join(container.stripped_strings))
        if not match:
            return None
        try:
            return datetime.strptime(match.group(0), "%B %d, %Y").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None

    @staticmethod
    def _story_title(anchor: Tag, container: Tag) -> Optional[str]:
        candidates: Iterable[Tag] = (
            list(anchor.find_all(["h1", "h2", "h3", "h4"]))
            + list(container.find_all(["h1", "h2", "h3", "h4"]))
        )
        for heading in candidates:
            title = " ".join(heading.stripped_strings).strip()
            if title and title.casefold() not in _GENERIC_LINK_TEXT:
                return title

        aria_label = str(anchor.get("aria-label") or "").strip()
        if aria_label and aria_label.casefold() not in _GENERIC_LINK_TEXT:
            return aria_label

        for line in (" ".join(anchor.stripped_strings), *container.stripped_strings):
            normalized = " ".join(str(line).split()).strip()
            if (
                8 <= len(normalized) <= 220
                and normalized.casefold() not in _GENERIC_LINK_TEXT
                and not _DATE_RE.fullmatch(normalized)
            ):
                return normalized
        return None
