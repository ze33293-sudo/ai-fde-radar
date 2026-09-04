from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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

    with pytest.raises(ValueError, match="must cover every required external"):
        DigestConfig(
            max_items=20,
            practice_targets=TARGETS,
            practice_minimums=MINIMUMS,
            generated_hands_on=True,
            preflight_practice_reserves={"enterprise-case": 2},
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


def test_missing_columns_are_hydrated_and_reanalyzed_before_hard_gates(
    monkeypatch,
) -> None:
    config = radar_config()
    config.collection.fetch_fulltext = True
    config.digest.fulltext_reserve = 5
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    candidates = [
        radar_item(index, category, evidence=False, category_match=False)
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]
    for candidate in candidates:
        candidate.processing.analysis.practice_category = "method-pitfall"  # type: ignore[union-attr]
        candidate.metadata["practice_category"] = "method-pitfall"
        candidate.metadata["model_practice_category"] = "method-pitfall"

    hydrated_ids: list[str] = []

    async def hydrate(items):  # type: ignore[no-untyped-def]
        hydrated_ids.extend(item.id for item in items)
        for item in items:
            item.content = "Complete original evidence with the required workflow and result."
            item.metadata["fulltext_status"] = "success"
        return items

    async def analyze(items):  # type: ignore[no-untyped-def]
        for item in items:
            target = item.metadata["verification_target_practice_category"]
            analysis = item.processing.analysis
            analysis.practice_category = target
            analysis.evidence_complete = True
            analysis.category_requirements_met = True
            item.metadata["practice_category"] = target
            item.metadata["model_practice_category"] = target
        return items

    monkeypatch.setattr(orchestrator, "hydrate_selected_items", hydrate)
    monkeypatch.setattr(orchestrator, "analyze_items", analyze)

    verified = asyncio.run(
        orchestrator._hydrate_and_reanalyze_practice_rescue(
            candidates,
            set(EXTERNAL_CATEGORIES),
        )
    )

    assert len(hydrated_ids) == 5
    assert {item.metadata["practice_category"] for item in verified} == set(
        EXTERNAL_CATEGORIES
    )
    assert all(item.metadata["minimum_backfill"] for item in verified)
    assert all(item.metadata["fulltext_reanalyzed"] for item in verified)


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


def test_preflight_opens_reserves_and_rejects_inaccessible_items_before_ai(
    monkeypatch,
) -> None:
    config = radar_config()
    config.collection.fetch_fulltext = True
    config.digest.preflight_practice_reserves = {
        "today-use": 1,
        "enterprise-case": 2,
        "method-pitfall": 1,
        "beginner-tech": 1,
        "china-career": 1,
    }
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    candidates = [
        radar_item(index, category)
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]
    failed_enterprise = candidates[1]
    replacement = radar_item(20, "enterprise-case")
    candidates.append(replacement)

    async def hydrate(items):  # type: ignore[no-untyped-def]
        kept = []
        for candidate in items:
            if candidate.id == failed_enterprise.id:
                candidate.metadata["fulltext_status"] = "unavailable"
                continue
            candidate.metadata["fulltext_status"] = "success"
            if candidate.metadata["practice_category"] == "enterprise-case":
                candidate.title = "Pictet enterprise AI rollout result"
                candidate.content = (
                    "Pictet deployed an AI workflow through a staged rollout and "
                    "integrated an API gateway. The team reduced a two-week process "
                    "to two hours, improving delivery time by 90%. " * 3
                )
            else:
                candidate.content = "Accessible original source evidence. " * 20
            kept.append(candidate)
        return kept

    monkeypatch.setattr(orchestrator, "hydrate_selected_items", hydrate)
    usable, ready = asyncio.run(
        orchestrator._preflight_practice_source_supply(candidates)
    )

    assert failed_enterprise not in usable
    assert replacement in usable
    assert ready == set(EXTERNAL_CATEGORIES)
    assert replacement.metadata["analysis_input_fulltext"] is True
    assert (
        replacement.metadata["verification_target_practice_category"]
        == "enterprise-case"
    )


def test_run_aborts_before_model_when_required_source_preflight_is_empty(
    monkeypatch,
    tmp_path,
) -> None:
    config = radar_config()
    config.collection.fetch_fulltext = True
    config.collection.history_path = str(tmp_path / "seen.json")
    config.collection.sent_marker_dir = str(tmp_path / "sent")
    config.digest.preflight_practice_reserves = {
        category: 1 for category in EXTERNAL_CATEGORIES
    }
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    candidates = [
        radar_item(index, category)
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]
    for candidate in candidates:
        candidate.processing = None
        candidate.content = "Official AI workflow source with measurable results. " * 8

    async def fetch_primary(_since):  # type: ignore[no-untyped-def]
        orchestrator.last_fetch_report = FetchReport(
            [SourceFetchOutcome("fixture", "success", candidates)]
        )
        return candidates

    async def fetch_fallback(_since, _categories):  # type: ignore[no-untyped-def]
        orchestrator.last_fetch_report = FetchReport(
            [SourceFetchOutcome("fallback-fixture", "empty")]
        )
        return []

    async def hydrate(items):  # type: ignore[no-untyped-def]
        kept = []
        for candidate in items:
            if candidate.metadata["practice_category"] == "enterprise-case":
                candidate.metadata["fulltext_status"] = "unavailable"
                continue
            candidate.metadata["fulltext_status"] = "success"
            kept.append(candidate)
        return kept

    analyze = AsyncMock(side_effect=AssertionError("model must not be called"))
    monkeypatch.setattr(orchestrator, "fetch_all_sources", fetch_primary)
    monkeypatch.setattr(orchestrator, "fetch_targeted_sources", fetch_fallback)
    monkeypatch.setattr(orchestrator, "hydrate_selected_items", hydrate)
    monkeypatch.setattr(orchestrator, "analyze_items", analyze)

    with pytest.raises(RuntimeError, match="no model request was made"):
        asyncio.run(orchestrator.run(dry_run=True))

    analyze.assert_not_awaited()


def test_preflight_only_success_exits_without_model_or_delivery(
    monkeypatch,
    tmp_path,
) -> None:
    config = radar_config()
    config.collection.fetch_fulltext = True
    config.collection.history_path = str(tmp_path / "seen.json")
    config.collection.sent_marker_dir = str(tmp_path / "sent")
    config.digest.preflight_practice_reserves = {
        category: 1 for category in EXTERNAL_CATEGORIES
    }
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    candidates = [
        radar_item(index, category)
        for index, category in enumerate(EXTERNAL_CATEGORIES, start=1)
    ]
    for candidate in candidates:
        candidate.processing = None

    async def fetch_primary(_since):  # type: ignore[no-untyped-def]
        orchestrator.last_fetch_report = FetchReport(
            [SourceFetchOutcome("fixture", "success", candidates)]
        )
        return candidates

    async def hydrate(items):  # type: ignore[no-untyped-def]
        for candidate in items:
            candidate.metadata["fulltext_status"] = "success"
            if candidate.metadata["practice_category"] == "enterprise-case":
                candidate.title = "企业客服智能体落地案例"
                candidate.content = (
                    "某企业部署售后智能体工作流并接入知识库，逐步实施人工复核。"
                    "上线后处理时间从两小时缩短到20分钟，自动化率提升到80%。" * 5
                )
            else:
                candidate.content = "Accessible official AI source evidence. " * 20
        return items

    analyze = AsyncMock(side_effect=AssertionError("model must not be called"))
    notifier = SimpleNamespace(
        send_daily_summary=AsyncMock(),
        send_failure=AsyncMock(),
    )
    orchestrator.webhook_notifier = notifier
    create_client = MagicMock(side_effect=AssertionError("AI client must not be created"))
    monkeypatch.setattr("src.orchestrator.create_ai_client", create_client)
    monkeypatch.setattr(orchestrator, "fetch_all_sources", fetch_primary)
    monkeypatch.setattr(orchestrator, "hydrate_selected_items", hydrate)
    monkeypatch.setattr(orchestrator, "analyze_items", analyze)

    asyncio.run(orchestrator.run(dry_run=True, preflight_only=True))

    analyze.assert_not_awaited()
    create_client.assert_not_called()
    notifier.send_daily_summary.assert_not_awaited()
    notifier.send_failure.assert_not_awaited()


def test_official_full_feed_copy_survives_article_page_403_equivalent(
    monkeypatch,
) -> None:
    config = radar_config()
    config.collection.fetch_fulltext = True
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    candidate = radar_item(90, "today-use")
    candidate.content = "Official complete release article with availability details. " * 20
    candidate.metadata.update(
        {
            "source_tier": 1,
            "feed_content_kind": "full",
            "minimum_backfill": True,
        }
    )

    async def unavailable(_self, _url, _client):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(
        "src.orchestrator.TrafilaturaExtractor.extract",
        unavailable,
    )
    kept = asyncio.run(orchestrator.hydrate_selected_items([candidate]))

    assert kept == [candidate]
    assert candidate.metadata["fulltext_status"] == "official-feed"
    assert candidate.metadata["original_evidence_source"] == "official-feed"


def test_github_release_api_body_survives_article_page_failure(
    monkeypatch,
) -> None:
    config = radar_config()
    config.collection.fetch_fulltext = True
    orchestrator = HorizonOrchestrator(config, SimpleNamespace())
    candidate = radar_item(91, "today-use")
    candidate.source_type = SourceType.GITHUB
    candidate.content = "Official release notes with usable feature details. " * 20
    candidate.metadata.update(
        {
            "api_content_kind": "release-body",
            "minimum_backfill": True,
        }
    )

    async def unavailable(_self, _url, _client):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(
        "src.orchestrator.TrafilaturaExtractor.extract",
        unavailable,
    )
    kept = asyncio.run(orchestrator.hydrate_selected_items([candidate]))

    assert kept == [candidate]
    assert candidate.metadata["fulltext_status"] == "official-api"
    assert candidate.metadata["original_evidence_source"] == "github-release-api"
