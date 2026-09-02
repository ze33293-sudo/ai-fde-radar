"""Hugging Face Daily Papers public API scraper."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from .base import BaseScraper
from ..models import ContentItem, HuggingFacePapersConfig, SourceType


logger = logging.getLogger(__name__)


class HuggingFacePapersScraper(BaseScraper):
    API_URL = "https://huggingface.co/api/daily_papers"

    def __init__(
        self, config: HuggingFacePapersConfig, http_client: httpx.AsyncClient
    ):
        super().__init__({"hf_papers": config}, http_client)
        self.hf_config = config

    async def fetch(self, since: datetime) -> list[ContentItem]:
        if not self.hf_config.enabled:
            return []
        try:
            response = await self.client.get(
                self.API_URL,
                params={
                    "limit": self.hf_config.max_results,
                    "sort": self.hf_config.sort,
                },
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Error fetching Hugging Face Daily Papers: %s", exc)
            return []

        rows = payload if isinstance(payload, list) else payload.get("papers", [])
        items = []
        for raw in rows[: self.hf_config.max_results]:
            item = self._to_item(raw, since)
            if item is not None:
                items.append(item)
        return items

    def _to_item(
        self, raw: dict[str, Any], since: datetime
    ) -> Optional[ContentItem]:
        paper = raw.get("paper") if isinstance(raw.get("paper"), dict) else raw
        paper_id = str(paper.get("id") or paper.get("paperId") or "").strip()
        title = str(paper.get("title") or "").strip()
        if not paper_id or not title:
            return None

        published = self._parse_datetime(
            raw.get("publishedAt")
            or paper.get("publishedAt")
            or paper.get("published_at")
        )
        if published is None:
            published = datetime.now(timezone.utc)
        if published < self._ensure_utc(since):
            return None

        authors = paper.get("authors") or []
        author_names = []
        for author in authors:
            if isinstance(author, dict):
                name = author.get("name") or author.get("user")
            else:
                name = author
            if name:
                author_names.append(str(name))

        summary = (
            paper.get("summary")
            or paper.get("ai_summary")
            or raw.get("summary")
            or ""
        )
        return ContentItem(
            id=self._generate_id("hf_papers", "paper", paper_id),
            source_type=SourceType.HF_PAPERS,
            title=title,
            url=f"https://huggingface.co/papers/{paper_id}",
            content=str(summary),
            author=", ".join(author_names[:5]) or "Hugging Face Daily Papers",
            published_at=published,
            profile=self.hf_config.profile,
            metadata={
                "paper_id": paper_id,
                "upvotes": raw.get("upvotes") or paper.get("upvotes"),
                "github_repo": paper.get("githubRepo") or paper.get("github_repo"),
                "category": self.hf_config.category,
                "region": self.hf_config.region,
                "source_tier": self.hf_config.source_tier,
                "practice_category": self.hf_config.practice_category,
                "source_name": "Hugging Face Daily Papers",
            },
        )

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return HuggingFacePapersScraper._ensure_utc(parsed)

    @staticmethod
    def _ensure_utc(moment: datetime) -> datetime:
        if moment.tzinfo is None:
            return moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc)
