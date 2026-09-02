from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from src.models import HuggingFacePapersConfig
from src.scrapers.hf_papers import HuggingFacePapersScraper


def test_hugging_face_daily_papers_are_mapped_with_region_and_profile() -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = [
        {
            "publishedAt": datetime.now(timezone.utc).isoformat(),
            "upvotes": 42,
            "paper": {
                "id": "2609.12345",
                "title": "A Useful Agent Evaluation",
                "summary": "We introduce a reproducible benchmark.",
                "authors": [{"name": "Ada"}, {"name": "Lin"}],
                "githubRepo": "example/agent-eval",
            },
        }
    ]
    client = AsyncMock()
    client.get.return_value = response
    config = HuggingFacePapersConfig(
        enabled=True, profile="tech-news", region="global"
    )

    items = asyncio.run(
        HuggingFacePapersScraper(config, client).fetch(
            datetime.now(timezone.utc) - timedelta(hours=30)
        )
    )

    assert len(items) == 1
    assert str(items[0].url) == "https://huggingface.co/papers/2609.12345"
    assert items[0].profile == "tech-news"
    assert items[0].metadata["region"] == "global"
    assert items[0].metadata["github_repo"] == "example/agent-eval"


def test_old_daily_paper_is_filtered_out() -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = [
        {
            "publishedAt": "2020-01-01T00:00:00Z",
            "paper": {"id": "2001.00001", "title": "Old paper"},
        }
    ]
    client = AsyncMock()
    client.get.return_value = response
    config = HuggingFacePapersConfig(enabled=True)

    items = asyncio.run(
        HuggingFacePapersScraper(config, client).fetch(
            datetime.now(timezone.utc) - timedelta(hours=30)
        )
    )

    assert items == []
