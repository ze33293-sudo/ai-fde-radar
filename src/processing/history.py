"""Seven-day cross-run deduplication for selected digest items."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .._file_utils import _atomic_write_text
from ..models import ContentItem


_TRACKING_KEYS = {
    "dclid", "fbclid", "gclid", "mc_cid", "mc_eid", "msclkid", "twclid"
}
_PROGRESS_WORDS = re.compile(
    r"\b(?:update|updated|progress|follow[- ]?up|v\d+(?:\.\d+)*)\b|"
    r"进展|更新|新增|后续|版本|正式发布",
    re.IGNORECASE,
)


def canonical_url(url: str) -> str:
    """Return a stable URL identity without common tracking parameters."""
    parsed = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(query), "")
    )


def title_fingerprint(title: str) -> str:
    """Hash a Unicode-normalized title after removing punctuation and spacing."""
    normalized = unicodedata.normalize("NFKC", title).casefold()
    normalized = "".join(character for character in normalized if character.isalnum())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_fingerprint(item: ContentItem) -> str:
    material = f"{item.title}\n{item.content or ''}".strip()
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass
class HistoryFilterResult:
    items: list[ContentItem]
    removed: int


class HistoryStore:
    """Persist and filter URL/title fingerprints from recently selected items."""

    def __init__(self, path: Path, retention_days: int = 7):
        self.path = path
        self.retention_days = retention_days
        self.entries: list[dict[str, str]] = []

    def load(self) -> None:
        if not self.path.exists():
            self.entries = []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            entries = payload.get("items", []) if isinstance(payload, dict) else []
            self.entries = [entry for entry in entries if isinstance(entry, dict)]
        except (OSError, json.JSONDecodeError):
            self.entries = []

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=self.retention_days)
        retained = []
        for entry in self.entries:
            try:
                seen_at = datetime.fromisoformat(entry["seen_at"])
                if seen_at.tzinfo is None:
                    seen_at = seen_at.replace(tzinfo=timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            if seen_at >= cutoff:
                retained.append(entry)
        self.entries = retained

    def filter_new(
        self, items: list[ContentItem], now: datetime | None = None
    ) -> HistoryFilterResult:
        now = now or datetime.now(timezone.utc)
        self._prune(now)
        urls = {entry.get("url") for entry in self.entries}
        titles = {entry.get("title") for entry in self.entries}
        by_url = {entry.get("url"): entry for entry in self.entries}
        kept: list[ContentItem] = []

        for item in items:
            url_key = canonical_url(str(item.url))
            title_key = title_fingerprint(item.title)
            duplicate = url_key in urls or title_key in titles
            if duplicate:
                previous = by_url.get(url_key, {})
                materially_changed = (
                    previous.get("content") != content_fingerprint(item)
                    and bool(_PROGRESS_WORDS.search(item.title))
                )
                if not materially_changed:
                    continue
                item.metadata["is_progress"] = True
            kept.append(item)

        return HistoryFilterResult(items=kept, removed=len(items) - len(kept))

    def record(
        self, items: list[ContentItem], now: datetime | None = None
    ) -> None:
        now = now or datetime.now(timezone.utc)
        self._prune(now)
        for item in items:
            self.entries.append(
                {
                    "url": canonical_url(str(item.url)),
                    "title": title_fingerprint(item.title),
                    "content": content_fingerprint(item),
                    "seen_at": now.isoformat(),
                }
            )

        # Keep the newest entry for each URL/title pair.
        latest: dict[tuple[str, str], dict[str, str]] = {}
        for entry in self.entries:
            latest[(entry.get("url", ""), entry.get("title", ""))] = entry
        self.entries = list(latest.values())

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "retention_days": self.retention_days,
            "items": self.entries,
        }
        _atomic_write_text(
            self.path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
