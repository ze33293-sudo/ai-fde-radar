"""Google News RSS search scraper.

Pulls recent news articles from Google News' key-less RSS search endpoint
(https://news.google.com/rss/search) for a configured query and maps each
feed entry into a ContentItem so the rest of the Horizon pipeline
(deduplication, AI scoring, enrichment, summarization) treats them the same
way as RSS, Hacker News, or GDELT items.

Design notes:

* No API key is required; Google News exposes an open RSS search endpoint.
* The desired time window is expressed as a Google News query *operator*
  rather than a request parameter. ``since`` is converted to an integer
  number of hours; for windows up to 100 hours we use ``when:<hours>h``
  (Google News supports ``when:Nh`` / ``when:Nd``), and for longer windows
  we fall back to ``after:YYYY-MM-DD`` using the ``since`` date. This keeps
  the mapping deterministic and lets Google bound the result set.
* Localization is expressed through the ``hl`` (language), ``gl`` (country)
  and ``ceid`` params; ``ceid`` defaults to ``"{country}:{language}"`` when
  not configured.
* Google News headlines are usually formatted "Headline - Publisher" and the
  publisher is also exposed via ``entry.source.title``; it is captured into
  the ``source_name`` metadata key defensively.
* A single malformed entry is skipped, not allowed to abort the batch.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, List, Optional
from urllib.parse import urlsplit

import feedparser
import httpx

from .base import BaseScraper
from ..models import ContentItem, GoogleNewsConfig, SourceType
from ..url_security import UnsafeURLError, safe_request

logger = logging.getLogger(__name__)


class GoogleNewsScraper(BaseScraper):
    """Scraper backed by the Google News RSS search endpoint."""

    SOURCE_TYPE = SourceType.GOOGLE_NEWS
    BASE_URL = "https://news.google.com/rss/search"
    DECODER_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
    DECODER_RPC_ID = "Fbv4je"

    def __init__(
        self,
        config: GoogleNewsConfig,
        http_client: httpx.AsyncClient,
        resolution_semaphore: Optional[asyncio.Semaphore] = None,
    ):
        """Initialize the scraper.

        Args:
            config: Google News source configuration.
            http_client: Shared async HTTP client.
        """
        super().__init__({"google_news": config}, http_client)
        self.gn_config = config
        self._resolution_semaphore = resolution_semaphore

    async def fetch(self, since: datetime) -> List[ContentItem]:
        """Fetch articles from the Google News RSS search endpoint.

        Args:
            since: Only fetch items published after this time (used to derive
                the Google News ``when:``/``after:`` query operator).

        Returns:
            List[ContentItem]: Fetched content items.
        """
        if not self.gn_config.enabled:
            return []

        base_query = (self.gn_config.query or "").strip()
        if not base_query:
            return []

        query = f"{base_query} {self._time_operator(since)}"

        ceid = self.gn_config.ceid or f"{self.gn_config.country}:{self.gn_config.language}"
        params: dict[str, Any] = {
            "q": query,
            "hl": self.gn_config.language,
            "gl": self.gn_config.country,
            "ceid": ceid,
        }

        try:
            response = await self.client.get(
                self.BASE_URL, params=params, follow_redirects=True
            )
            response.raise_for_status()

            feed = feedparser.parse(response.text)

            entries = list(feed.entries[: self.gn_config.max_results])
            raw_links = [
                str(entry.get("link") or "").strip() for entry in entries
            ]
            resolved_links = await self._resolve_original_urls(raw_links)

            items: List[ContentItem] = []
            for entry, resolved_link in zip(entries, resolved_links):
                raw_link = str(entry.get("link") or "").strip()
                item = self._entry_to_item(
                    entry,
                    link_override=resolved_link,
                    original_url_resolved=self._is_original_url(resolved_link),
                )
                if item is not None:
                    items.append(item)
            return items

        except httpx.HTTPError as exc:
            logger.warning("Error fetching Google News feed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("Error parsing Google News feed: %s", exc)
            return []

    def _time_operator(self, since: datetime) -> str:
        """Build the Google News time operator from ``since``.

        Computes the number of whole hours between ``since`` and now (min 1).
        For windows up to 100 hours we use ``when:<hours>h``; for longer
        windows Google News' relative operator is unreliable, so we fall back
        to ``after:YYYY-MM-DD`` using the ``since`` date.
        """
        since_utc = self._ensure_utc(since)
        now_utc = datetime.now(timezone.utc)
        seconds = (now_utc - since_utc).total_seconds()
        hours = max(1, math.ceil(seconds / 3600))
        if hours <= 100:
            return f"when:{hours}h"
        return f"after:{since_utc.strftime('%Y-%m-%d')}"

    def _entry_to_item(
        self,
        entry: Any,
        *,
        link_override: Optional[str] = None,
        original_url_resolved: Optional[bool] = None,
    ) -> Optional[ContentItem]:
        """Map one Google News RSS entry into a ContentItem.

        Returns None when the entry has no title/link or an unparseable
        published date (published_at is required), so a single bad entry is
        skipped rather than aborting the batch.
        """
        try:
            title = (entry.get("title") or "").strip()
            if not title:
                return None

            link = (link_override or entry.get("link") or "").strip()
            if not link:
                return None

            published = self._parse_date(entry)
            if published is None:
                return None

            source_name = self._extract_source_name(entry)

            entry_id = entry.get("id") or link
            entry_hash = hashlib.sha256(str(entry_id).encode("utf-8")).hexdigest()[:16]

            meta = {
                "gn_query": self.gn_config.query,
                "source_name": source_name,
                "category": self.gn_config.category,
                "region": self.gn_config.region,
                "source_tier": self.gn_config.source_tier,
                "practice_category": self.gn_config.practice_category,
                "original_url_resolved": (
                    self._is_original_url(link)
                    if original_url_resolved is None
                    else original_url_resolved
                ),
            }

            return ContentItem(
                id=self._generate_id("google_news", "article", entry_hash),
                source_type=self.SOURCE_TYPE,
                title=title,
                url=link,
                content=self._extract_content(entry),
                author=source_name,
                published_at=published,
                profile=self.gn_config.profile,
                metadata={k: v for k, v in meta.items() if v is not None},
            )
        except Exception as exc:
            logger.warning("Skipping invalid Google News entry: %s", exc)
            return None

    async def _resolve_original_urls(self, links: List[str]) -> List[str]:
        """Resolve Google News article IDs through its batched web RPC.

        Google News RSS article links currently return an HTML shell instead of
        redirecting to publishers. The shell carries a short-lived signature and
        timestamp used by the same public batchexecute request as the news page.
        Failures remain unresolved and are rejected later by the evidence gate.
        """
        resolved = list(links)
        # The orchestrator shares this semaphore across every configured query.
        # Without a shared limit, N queries each opened four decoder requests
        # and Google routinely disconnected the burst before URLs were resolved.
        semaphore = self._resolution_semaphore or asyncio.Semaphore(4)

        async def fetch_parameters(
            index: int, link: str
        ) -> Optional[tuple[int, str, int, str]]:
            if not link or self._is_original_url(link):
                return None
            async with semaphore:
                parameters = await self._fetch_decoding_parameters(link)
            if parameters is None:
                return None
            article_id, timestamp, signature = parameters
            return index, article_id, timestamp, signature

        parameters = await asyncio.gather(
            *(fetch_parameters(index, link) for index, link in enumerate(links))
        )
        requested = [parameter for parameter in parameters if parameter is not None]
        if not requested:
            return resolved

        async with semaphore:
            decoded = await self._decode_article_ids(
                [
                    (article_id, timestamp, signature)
                    for _, article_id, timestamp, signature in requested
                ]
            )
        for (index, _, _, _), decoded_url in zip(requested, decoded):
            if decoded_url and self._is_original_url(decoded_url):
                resolved[index] = decoded_url
        return resolved

    async def _fetch_decoding_parameters(
        self, link: str
    ) -> Optional[tuple[str, int, str]]:
        article_id = urlsplit(link).path.rstrip("/").rsplit("/", 1)[-1]
        if not article_id:
            return None
        try:
            response = await safe_request(self.client, "GET", link)
            response.raise_for_status()
            signature_match = re.search(
                r"data-n-a-sg=[\"']([^\"']+)[\"']", response.text
            )
            timestamp_match = re.search(
                r"data-n-a-ts=[\"'](\d+)[\"']", response.text
            )
            if not signature_match or not timestamp_match:
                return None
            return article_id, int(timestamp_match.group(1)), signature_match.group(1)
        except (httpx.HTTPError, UnsafeURLError, AttributeError, ValueError):
            return None

    async def _decode_article_ids(
        self, parameters: List[tuple[str, int, str]]
    ) -> List[Optional[str]]:
        locale = self.gn_config.ceid or (
            f"{self.gn_config.country}:{self.gn_config.language}"
        )
        requests = []
        for article_id, timestamp, signature in parameters:
            request = [
                "garturlreq",
                [
                    [
                        "X",
                        "X",
                        ["X", "X"],
                        None,
                        None,
                        1,
                        1,
                        locale,
                        None,
                        1,
                        None,
                        None,
                        None,
                        None,
                        None,
                        0,
                        1,
                    ],
                    "X",
                    "X",
                    1,
                    [1, 1, 1],
                    1,
                    1,
                    None,
                    0,
                    0,
                    None,
                    0,
                ],
                article_id,
                timestamp,
                signature,
            ]
            requests.append(
                [
                    self.DECODER_RPC_ID,
                    json.dumps(request, ensure_ascii=False, separators=(",", ":")),
                ]
            )

        try:
            response = await safe_request(
                self.client,
                "POST",
                self.DECODER_URL,
                data={
                    "f.req": json.dumps(
                        [requests], ensure_ascii=False, separators=(",", ":")
                    )
                },
                headers={
                    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "user-agent": "Mozilla/5.0 (compatible; AI-FDE-Radar/1.0)",
                },
            )
            response.raise_for_status()
            decoded = self._parse_decoder_response(response.text)
        except (httpx.HTTPError, UnsafeURLError, AttributeError, ValueError):
            decoded = []

        # Preserve positional mapping even if the RPC returns fewer results.
        return (decoded + [None] * len(parameters))[: len(parameters)]

    @classmethod
    def _parse_decoder_response(cls, text: str) -> List[Optional[str]]:
        """Extract publisher URLs from a Google batchexecute response."""
        frames: list[Any] = []
        for segment in re.split(r"\n\s*\n", text):
            candidate = segment.strip()
            if not candidate.startswith("["):
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, list):
                frames.extend(payload)

        decoded: List[Optional[str]] = []
        for frame in frames:
            if (
                not isinstance(frame, list)
                or len(frame) < 3
                or frame[1] != cls.DECODER_RPC_ID
                or not isinstance(frame[2], str)
            ):
                continue
            try:
                inner = json.loads(frame[2])
            except json.JSONDecodeError:
                decoded.append(None)
                continue
            url = inner[1] if isinstance(inner, list) and len(inner) > 1 else None
            decoded.append(url if isinstance(url, str) else None)
        return decoded

    @staticmethod
    def _is_original_url(url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return bool(host) and host not in {"news.google.com", "news.googleusercontent.com"}

    @staticmethod
    def _extract_source_name(entry: Any) -> Optional[str]:
        """Extract the publisher name from a Google News entry, guarding misses."""
        source = entry.get("source")
        if isinstance(source, dict):
            name = source.get("title")
            if name:
                return str(name).strip()
        # feedparser may expose source as an attribute-bearing object.
        title = getattr(source, "title", None)
        if title:
            return str(title).strip()
        return None

    @staticmethod
    def _parse_date(entry: Any) -> Optional[datetime]:
        """Parse the publication date of an entry into aware UTC."""
        for field in ["published", "updated", "created"]:
            if field in entry:
                try:
                    parsed = entry.get(f"{field}_parsed")
                    if parsed:
                        return datetime.fromtimestamp(
                            calendar.timegm(parsed), tz=timezone.utc
                        )
                    return parsedate_to_datetime(entry[field])
                except Exception:
                    continue
        return None

    @staticmethod
    def _extract_content(entry: Any) -> Optional[str]:
        """Extract text content from a Google News entry, if any."""
        if "summary" in entry:
            return entry.summary
        if "description" in entry:
            return entry.description
        content = entry.get("content")
        if content:
            try:
                return content[0].get("value", "")
            except Exception:
                return None
        return None

    @staticmethod
    def _ensure_utc(moment: datetime) -> datetime:
        if moment.tzinfo is None:
            return moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc)
