from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.ai.summarizer import DailySummarizer, PRACTICE_CATEGORY_ORDER
from src.models import (
    AIConfig,
    ClassificationResult,
    CollectionConfig,
    Config,
    ContentAnalysis,
    ContentItem,
    DigestConfig,
    GitHubSourceConfig,
    ProcessingConfig,
    ProcessingResult,
    ProfileSettingsConfig,
    SourceType,
    SourcesConfig,
)
from src.orchestrator import FetchReport, HorizonOrchestrator, SourceFetchOutcome


TARGETS = {
    "today-use": 5,
    "enterprise-case": 5,
    "method-pitfall": 4,
    "beginner-tech": 3,
    "china-career": 2,
    "hands-on": 1,
}
MINIMUMS = {category: 1 for category in TARGETS}
EXTERNAL_CATEGORIES = list(TARGETS)[:-1]


def radar_config(*, sources: SourcesConfig | None = None) -> Config:
    return Config(
        ai=AIConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key_env="DEEPSEEK_API_KEY",
            languages=["zh"],
        ),
        processing=ProcessingConfig(
            profile_settings={
                "ai-product-fde": ProfileSettingsConfig(
                    threshold=7,
                    require_actionable_within_7_days=False,
                ),
                "tech-news": ProfileSettingsConfig(
                    threshold=7,
                    require_actionable_within_7_days=False,
                ),
            }
        ),
        sources=sources or SourcesConfig(),
        collection=CollectionConfig(
            time_window_hours=30,
            fallback_window_hours=168,
            candidate_limit=60,
        ),
        digest=DigestConfig(
            max_items=20,
            practice_targets=TARGETS,
            practice_minimums=MINIMUMS,
            generated_hands_on=True,
            deep_items=5,
            brief_items=15,
            max_items_per_source=20,
            max_today_use_per_source=5,
        ),
    )


def radar_item(
    index: int,
    category: str,
    *,
    score: float = 8,
    fallback: bool = False,
    evidence: bool = True,
    category_match: bool = True,
) -> ContentItem:
    published_at = datetime.now(timezone.utc) - (
        timedelta(days=3) if fallback else timedelta(minutes=index)
    )
    return ContentItem(
        id=f"radar-{index}",
        source_type=SourceType.RSS,
        title=f"{category} item {index}",
        url=f"https://source{index}.example.com/item",
        content="Source-grounded evidence about an applied AI workflow and result.",
        author="Original source",
        published_at=published_at,
        metadata={
            "region": "china" if category == "china-career" else "global",
            "practice_category": category,
            "source_practice_category": category,
            "model_practice_category": category,
            "is_fallback": fallback,
            "freshness_bucket": "fallback" if fallback else "fresh",
            "freshness_label": "近 7 日补充" if fallback else "今日新内容",
        },
        profile="ai-product-fde",
        processing=ProcessingResult(
            classification=ClassificationResult(
                profile="ai-product-fde", method="source_override"
            ),
            analysis=ContentAnalysis(
                score=score,
                reason="Reliable and relevant",
                summary="A source-grounded fact with product implications.",
                tags=["ai-product"],
                practice_category=category,
                actionable_within_7_days=False,
                action="",
                project_relevance="Changes one ticket-Agent product decision.",
                evidence_complete=evidence,
                category_requirements_met=category_match,
                evidence_note="Primary source contains the central evidence.",
            ),
        ),
    )


def test_minimum_selection_prefers_fresh_below_threshold_over_fallback() -> None:
    orchestrator = HorizonOrchestrator(radar_config(), SimpleNamespace())
    candidates = [
        radar_item(index, category)
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]
    fresh_low = radar_item(20, "today-use", score=6.2)
    fallback_high = radar_item(21, "today-use", score=9.5, fallback=True)
    candidates = [
        item for item in candidates if item.metadata["practice_category"] != "today-use"
    ] + [fallback_high, fresh_low]

    result = orchestrator.apply_balanced_digest(candidates, log=False)

    assert len(result.items) == 5
    assert {item.metadata["practice_category"] for item in result.items} == set(
        EXTERNAL_CATEGORIES
    )
    assert fresh_low in result.items
    assert fallback_high not in result.items
    assert fresh_low.metadata["minimum_backfill"] is True
    assert fresh_low.metadata["below_threshold_minimum"] is True


def test_digest_config_rejects_impossible_minimums_and_generated_card_shape() -> None:
    with pytest.raises(ValueError, match="cannot exceed its target"):
        DigestConfig(
            max_items=6,
            practice_targets={"today-use": 1},
            practice_minimums={"today-use": 2},
        )
    with pytest.raises(ValueError, match="practice_targets.hands-on"):
        DigestConfig(
            max_items=6,
            practice_targets={"hands-on": 2},
            practice_minimums={"hands-on": 1},
            generated_hands_on=True,
        )


def test_evidence_and_category_hard_gates_reject_minimum_filler() -> None:
    orchestrator = HorizonOrchestrator(radar_config(), SimpleNamespace())
    candidates = [
        radar_item(index, category)
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]
    candidates[1].processing.analysis.evidence_complete = False  # type: ignore[union-attr]

    result = orchestrator.apply_balanced_digest(candidates, log=False)

    assert "enterprise-case" in result.shortfall_reasons
    with pytest.raises(RuntimeError, match="enterprise-case"):
        orchestrator._assert_external_practice_minimums(result.items)


def test_generated_hands_on_card_is_one_unranked_ticket_agent_exercise() -> None:
    orchestrator = HorizonOrchestrator(radar_config(), SimpleNamespace())
    external = [
        radar_item(index, category)
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]

    card = orchestrator._build_hands_on_card(external, today="2026-09-03")
    digest = [*external, card]
    orchestrator._assert_complete_practice_digest(digest)

    assert sum(item.metadata.get("generated_hands_on", False) for item in digest) == 1
    assert card.metadata["practice_category"] == "hands-on"
    assert card.processing is not None
    assert card.processing.analysis is not None
    assert card.processing.analysis.score is None
    block_ids = {block.id for block in card.processing.artifacts["zh"].blocks}
    assert {"time", "input", "steps", "completion", "project_mapping"} <= block_ids
    assert "15–30 分钟" in card.processing.artifacts["zh"].blocks[0].title


def test_summary_keeps_six_columns_order_counts_dates_and_fallback_label() -> None:
    orchestrator = HorizonOrchestrator(radar_config(), SimpleNamespace())
    external = [
        radar_item(index, category, fallback=category == "china-career")
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]
    card = orchestrator._build_hands_on_card(external, today="2026-09-03")
    items = [*external, card]
    summarizer = DailySummarizer(practice_targets=TARGETS)

    view = summarizer.build_view(items, "zh")
    markdown = asyncio.run(
        summarizer.generate_summary(items, "2026-09-03", 120, language="zh")
    )

    assert [group.profile_id for group in view.groups] == PRACTICE_CATEGORY_ORDER
    assert [group.actual_count for group in view.groups] == [1, 1, 1, 1, 1, 1]
    assert "今天可以用 1/5" in markdown
    assert "企业落地案例 1/5" in markdown
    assert "近 7 日补充" in markdown
    assert "9月" in markdown
    hands_on_section = markdown.split("## 今天动手做 1/1", 1)[1]
    assert "⭐️ ?/10" not in hands_on_section


def test_targeted_fetch_only_uses_sources_for_missing_categories(monkeypatch) -> None:
    sources = SourcesConfig(
        github=[
            GitHubSourceConfig(
                type="repo_releases",
                owner="one",
                repo="today",
                practice_category="today-use",
            ),
            GitHubSourceConfig(
                type="repo_releases",
                owner="two",
                repo="methods",
                practice_category="method-pitfall",
            ),
        ]
    )
    orchestrator = HorizonOrchestrator(radar_config(sources=sources), SimpleNamespace())
    seen_repositories: list[list[str | None]] = []

    async def fake_fetch(name, scraper, since):  # type: ignore[no-untyped-def]
        if name == "Fallback GitHub":
            seen_repositories.append(
                [source.repo for source in scraper.config["sources"]]
            )
        return SourceFetchOutcome(name, "empty")

    monkeypatch.setattr(orchestrator, "_fetch_with_progress", fake_fetch)
    asyncio.run(
        orchestrator.fetch_targeted_sources(
            datetime.now(timezone.utc) - timedelta(days=7),
            {"method-pitfall"},
        )
    )

    assert seen_repositories == [["methods"]]


def test_run_uses_seven_day_fallback_then_builds_complete_external_digest(
    tmp_path, monkeypatch
) -> None:
    config = radar_config()
    config.ai.languages = []
    config.metrics.enabled = False
    config.collection.history_path = str(tmp_path / "seen.json")
    config.collection.sent_marker_dir = str(tmp_path / "sent")
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    fresh = [
        radar_item(index, category)
        for index, category in enumerate(EXTERNAL_CATEGORIES[:-1], start=1)
    ]
    fallback = radar_item(50, "china-career", score=6.5, fallback=True)
    searched: list[set[str]] = []
    enriched: list[ContentItem] = []

    async def fetch_all(since):  # type: ignore[no-untyped-def]
        orchestrator.last_fetch_report = FetchReport(
            [SourceFetchOutcome("fresh", "success", fresh)]
        )
        return fresh

    async def fetch_targeted(since, categories):  # type: ignore[no-untyped-def]
        searched.append(set(categories))
        orchestrator.last_fetch_report = FetchReport(
            [SourceFetchOutcome("fallback", "success", [fallback])]
        )
        return [fallback]

    async def analyze(items):  # type: ignore[no-untyped-def]
        return items

    async def no_topic_dedup(items, *, log=True):  # type: ignore[no-untyped-def]
        return items

    async def enrich(items):  # type: ignore[no-untyped-def]
        enriched.extend(items)
        return SimpleNamespace()

    monkeypatch.setattr(orchestrator, "fetch_all_sources", fetch_all)
    monkeypatch.setattr(orchestrator, "fetch_targeted_sources", fetch_targeted)
    monkeypatch.setattr(orchestrator, "analyze_items", analyze)
    monkeypatch.setattr(orchestrator, "merge_topic_duplicates", no_topic_dedup)
    monkeypatch.setattr(orchestrator, "enrich_items", enrich)

    asyncio.run(orchestrator.run(dry_run=True))

    assert searched == [{"china-career"}]
    assert {item.id for item in enriched} == {item.id for item in [*fresh, fallback]}
    selected_fallback = next(item for item in enriched if item.id == fallback.id)
    assert selected_fallback.metadata["minimum_backfill"] is True
    assert selected_fallback.metadata["freshness_label"] == "近 7 日补充"


def test_run_aborts_before_delivery_when_fallback_still_misses_a_column(
    tmp_path, monkeypatch
) -> None:
    config = radar_config()
    config.ai.languages = ["zh"]
    config.metrics.enabled = False
    config.collection.history_path = str(tmp_path / "seen.json")
    config.collection.sent_marker_dir = str(tmp_path / "sent")
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    fresh = [
        radar_item(index, category)
        for index, category in enumerate(EXTERNAL_CATEGORIES[:-1], start=1)
    ]
    notifier = SimpleNamespace(
        send_daily_summary=AsyncMock(),
        send_failure=AsyncMock(),
    )
    orchestrator.webhook_notifier = notifier

    async def fetch_all(since):  # type: ignore[no-untyped-def]
        orchestrator.last_fetch_report = FetchReport(
            [SourceFetchOutcome("fresh", "success", fresh)]
        )
        return fresh

    async def fetch_targeted(since, categories):  # type: ignore[no-untyped-def]
        orchestrator.last_fetch_report = FetchReport(
            [SourceFetchOutcome("fallback", "empty")]
        )
        return []

    async def analyze(items):  # type: ignore[no-untyped-def]
        return items

    async def no_topic_dedup(items, *, log=True):  # type: ignore[no-untyped-def]
        return items

    monkeypatch.setattr(orchestrator, "fetch_all_sources", fetch_all)
    monkeypatch.setattr(orchestrator, "fetch_targeted_sources", fetch_targeted)
    monkeypatch.setattr(orchestrator, "analyze_items", analyze)
    monkeypatch.setattr(orchestrator, "merge_topic_duplicates", no_topic_dedup)

    with pytest.raises(RuntimeError, match="china-career"):
        asyncio.run(orchestrator.run())

    notifier.send_daily_summary.assert_not_awaited()
    notifier.send_failure.assert_awaited_once()


def test_metrics_report_each_column_funnel_and_generated_card(tmp_path) -> None:
    config = radar_config()
    config.metrics.output_dir = str(tmp_path / "metrics")
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    external = [
        radar_item(index, category, fallback=category == "china-career")
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]
    card = orchestrator._build_hands_on_card(external, today="2026-09-03")
    usage = SimpleNamespace(
        total_input_tokens=100,
        total_output_tokens=50,
        total_tokens=150,
    )

    orchestrator._write_run_metrics(
        date="2026-09-03",
        fetched_count=len(external),
        merged_count=len(external),
        history_removed=0,
        candidate_count=len(external),
        analyzed_count=len(external),
        analyzed_items=external,
        threshold_count=len(external),
        selected_items=[*external, card],
        usage=usage,
        dry_run=True,
        fetched_items=external,
    )

    payload = json.loads(
        (tmp_path / "metrics" / "latest.json").read_text(encoding="utf-8")
    )
    diagnostics = payload["selection"]["practice_diagnostics"]
    assert diagnostics["today-use"]["fetched"] == 1
    assert diagnostics["today-use"]["scored"] == 1
    assert diagnostics["china-career"]["fallback"] == 1
    assert diagnostics["hands-on"]["final"] == 1
    assert payload["selection"]["generated_hands_on_cards"] == 1
