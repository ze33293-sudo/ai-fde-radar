from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models import (
    AIConfig,
    ClassificationResult,
    Config,
    ContentAnalysis,
    ContentItem,
    DigestConfig,
    GoogleNewsConfig,
    MetricsConfig,
    ProcessingResult,
    SourceType,
    SourcesConfig,
)
from src.orchestrator import HorizonOrchestrator
from src.processing.history import HistoryStore
from src.services.webhook import redact_url


def config(**digest_overrides) -> Config:  # type: ignore[no-untyped-def]
    digest = {
        "max_items": 20,
        "profile_targets": {"ai-product-fde": 10, "tech-news": 10},
        "region_targets": {"global": 12, "china": 8},
        "matrix_targets": {
            "global/ai-product-fde": 6,
            "global/tech-news": 6,
            "china/ai-product-fde": 4,
            "china/tech-news": 4,
        },
        "deep_items": 5,
        "brief_items": 15,
    }
    digest.update(digest_overrides)
    return Config(
        ai=AIConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key_env="DEEPSEEK_API_KEY",
            languages=["zh"],
        ),
        sources=SourcesConfig(),
        digest=DigestConfig(**digest),
    )


def item(index: int, region: str, profile: str, score: float = 8.0) -> ContentItem:
    return ContentItem(
        id=f"item-{index}",
        source_type=SourceType.RSS,
        title=f"AI item {index}",
        url=f"https://example.com/{index}",
        content=f"Evidence {index}",
        published_at=datetime.now(timezone.utc) - timedelta(minutes=index),
        metadata={"region": region, "source_tier": 2},
        profile=profile,
        processing=ProcessingResult(
            classification=ClassificationResult(
                profile=profile, method="source_override"
            ),
            analysis=ContentAnalysis(
                score=score,
                reason="credible",
                summary="fact summary",
                tags=["ai"],
            ),
        ),
    )


def test_google_news_accepts_legacy_object_and_multi_query_array() -> None:
    legacy = SourcesConfig(
        google_news=GoogleNewsConfig(enabled=True, query="AI", region="global")
    )
    assert [entry.query for entry in legacy.google_news_queries()] == ["AI"]

    multiple = SourcesConfig(
        google_news=[
            GoogleNewsConfig(enabled=True, query="AI", region="global"),
            GoogleNewsConfig(enabled=True, query="大模型", region="china"),
        ]
    )
    assert [entry.region for entry in multiple.google_news_queries()] == [
        "global",
        "china",
    ]


def test_target_matrix_selects_twenty_and_marks_top_five_deep() -> None:
    orchestrator = HorizonOrchestrator(config(), SimpleNamespace())
    items = []
    index = 0
    for region, profile, count in [
        ("global", "ai-product-fde", 8),
        ("global", "tech-news", 8),
        ("china", "ai-product-fde", 6),
        ("china", "tech-news", 6),
    ]:
        for _ in range(count):
            items.append(item(index, region, profile, 10 - index / 100))
            index += 1

    result = orchestrator.apply_balanced_digest(items, log=False)

    assert len(result.items) == 20
    assert result.matrix_counts == {
        "global/ai-product-fde": 6,
        "global/tech-news": 6,
        "china/ai-product-fde": 4,
        "china/tech-news": 4,
    }
    assert [entry.metadata["summary_depth"] for entry in result.items[:5]] == [
        "deep"
    ] * 5
    assert all(
        entry.metadata["summary_depth"] == "brief" for entry in result.items[5:]
    )


def test_target_matrix_backfills_only_from_remaining_quality_candidates() -> None:
    orchestrator = HorizonOrchestrator(config(), SimpleNamespace())
    items = (
        [item(i, "global", "ai-product-fde", 9.0) for i in range(8)]
        + [item(20 + i, "global", "tech-news", 8.8) for i in range(10)]
        + [item(40 + i, "china", "ai-product-fde", 8.6) for i in range(2)]
        + [item(60 + i, "china", "tech-news", 8.4) for i in range(5)]
    )

    result = orchestrator.apply_balanced_digest(items, log=False)

    assert len(result.items) == 20
    assert result.matrix_counts["china/ai-product-fde"] == 2
    assert all(entry.processing.analysis.score >= 7 for entry in result.items)  # type: ignore[union-attr]


def test_prefilter_caps_model_scoring_and_drops_unresolved_google_links() -> None:
    radar_config = config()
    radar_config.collection.candidate_limit = 3
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    items = [item(i, "global", "tech-news") for i in range(5)]
    unresolved = item(99, "global", "tech-news")
    unresolved.source_type = SourceType.GOOGLE_NEWS
    unresolved.metadata["original_url_resolved"] = False

    selected = orchestrator.prefilter_candidates(items + [unresolved])

    assert len(selected) == 3
    assert unresolved not in selected


def test_prefilter_reserves_scoring_capacity_for_each_target_matrix_cell() -> None:
    radar_config = config()
    radar_config.collection.candidate_limit = 60
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    candidates = []
    index = 0
    for region, profile, count, tier in [
        ("global", "tech-news", 100, 1),
        ("global", "ai-product-fde", 30, 2),
        ("china", "tech-news", 30, 2),
        ("china", "ai-product-fde", 30, 2),
    ]:
        for source_index in range(count):
            candidate = item(index, region, profile)
            candidate.processing = None
            candidate.metadata.update(
                {
                    "source_tier": tier,
                    "feed_name": f"{region}-{profile}-source-{source_index % 5}",
                }
            )
            candidates.append(candidate)
            index += 1

    selected = orchestrator.prefilter_candidates(candidates)
    counts: dict[str, int] = {}
    for candidate in selected:
        key = f"{candidate.metadata['region']}/{candidate.profile}"
        counts[key] = counts.get(key, 0) + 1

    assert len(selected) == 60
    assert counts == {
        "global/ai-product-fde": 18,
        "global/tech-news": 18,
        "china/ai-product-fde": 12,
        "china/tech-news": 12,
    }


def test_prefilter_backfills_missing_matrix_supply_without_exceeding_limit() -> None:
    radar_config = config()
    radar_config.collection.candidate_limit = 10
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    scarce = [item(i, "china", "ai-product-fde") for i in range(1)]
    abundant = [item(100 + i, "global", "tech-news") for i in range(20)]
    candidates = scarce + abundant
    for candidate in candidates:
        candidate.processing = None

    selected = orchestrator.prefilter_candidates(candidates)

    assert len(selected) == 10
    assert selected.count(scarce[0]) == 1
    assert len({candidate.id for candidate in selected}) == 10


def test_candidate_practice_reserves_prioritize_scarce_columns() -> None:
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={
            "today-use": 5,
            "enterprise-case": 5,
            "method-pitfall": 4,
            "beginner-tech": 3,
            "china-career": 2,
            "hands-on": 1,
        },
        candidate_practice_reserves={
            "today-use": 6,
            "enterprise-case": 12,
            "method-pitfall": 8,
            "beginner-tech": 10,
            "china-career": 9,
        },
        generated_hands_on=True,
        practice_minimums={"hands-on": 1},
    )
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())

    assert orchestrator._candidate_practice_budgets(45) == {
        "today-use": 6,
        "enterprise-case": 12,
        "method-pitfall": 8,
        "beginner-tech": 10,
        "china-career": 9,
    }
    assert orchestrator._candidate_practice_budgets(
        15,
        categories={"enterprise-case", "beginner-tech", "china-career"},
    ) == {
        "enterprise-case": 6,
        "beginner-tech": 5,
        "china-career": 4,
    }


def test_prefilter_keeps_reserved_candidates_despite_high_volume_column() -> None:
    reserves = {
        "today-use": 6,
        "enterprise-case": 12,
        "method-pitfall": 8,
        "beginner-tech": 10,
        "china-career": 9,
    }
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={**reserves, "hands-on": 1},
        candidate_practice_reserves=reserves,
        generated_hands_on=True,
        practice_minimums={"hands-on": 1},
    )
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    candidates = []
    index = 0
    for practice_category, count in {
        "today-use": 60,
        "enterprise-case": 12,
        "method-pitfall": 8,
        "beginner-tech": 10,
        "china-career": 9,
    }.items():
        for _ in range(count):
            candidate = item(index, "global", "ai-product-fde")
            candidate.processing = None
            candidate.metadata.update(
                {
                    "practice_category": practice_category,
                    "feed_name": f"{practice_category}-{index}",
                }
            )
            candidates.append(candidate)
            index += 1

    selected = orchestrator.prefilter_candidates(candidates, limit=45)
    counts: dict[str, int] = {}
    for candidate in selected:
        practice_category = str(candidate.metadata["practice_category"])
        counts[practice_category] = counts.get(practice_category, 0) + 1

    assert counts == reserves


def test_prefilter_soft_source_cap_preserves_source_diversity() -> None:
    radar_config = config()
    radar_config.collection.candidate_limit = 20
    radar_config.digest.matrix_targets = {"global/tech-news": 20}
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    candidates = []
    for index in range(40):
        candidate = item(index, "global", "tech-news")
        candidate.processing = None
        candidate.metadata["feed_name"] = (
            "dominant-arxiv" if index < 20 else f"feed-{index % 5}"
        )
        candidates.append(candidate)

    selected = orchestrator.prefilter_candidates(candidates)
    source_counts: dict[str, int] = {}
    for candidate in selected:
        source = str(candidate.metadata["feed_name"])
        source_counts[source] = source_counts.get(source, 0) + 1

    assert len(selected) == 20
    assert source_counts["dominant-arxiv"] <= 5
    assert len(source_counts) >= 4


def test_practical_prefilter_prefers_evidenced_workflow_over_news_cycle_noise() -> None:
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={"enterprise-case": 1},
    )
    radar_config.collection.candidate_limit = 1
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())

    noise = item(1, "global", "ai-product-fde")
    noise.processing = None
    noise.title = "AI startup reaches new valuation after funding round"
    noise.metadata.update(
        {"practice_category": "enterprise-case", "source_tier": 1}
    )

    useful = item(2, "global", "ai-product-fde")
    useful.processing = None
    useful.title = "Customer support AI case study cuts handle time by 20%"
    useful.content = (
        "A deployed ticket-triage workflow documents rollout, human escalation, "
        "and resolution-rate measurement."
    )
    useful.published_at -= timedelta(hours=2)
    useful.metadata.update(
        {"practice_category": "enterprise-case", "source_tier": 2}
    )

    selected = orchestrator.prefilter_candidates([noise, useful])

    assert selected == [useful]
    assert useful.metadata["prefilter_practical_score"] >= 2


def test_practical_prefilter_requires_ai_signal_in_hacker_news_title() -> None:
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={"method-pitfall": 1},
    )
    radar_config.collection.candidate_limit = 2
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())

    unrelated = item(1, "global", "ai-product-fde")
    unrelated.processing = None
    unrelated.source_type = SourceType.HACKERNEWS
    unrelated.title = "The death of physical media"
    unrelated.content = "The comments briefly mention AI evaluation."
    unrelated.metadata["practice_category"] = "method-pitfall"

    useful = item(2, "global", "ai-product-fde")
    useful.processing = None
    useful.source_type = SourceType.HACKERNEWS
    useful.title = "AI agent eval harness shows cost per pass varies 17x"
    useful.content = "A reproducible evaluation compares production reliability."
    useful.metadata["practice_category"] = "method-pitfall"

    selected = orchestrator.prefilter_candidates([unrelated, useful])

    assert unrelated not in selected
    assert selected == [useful]


def test_practical_prefilter_deprioritizes_distant_infrastructure_tutorial() -> None:
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={"beginner-tech": 1},
    )
    radar_config.collection.candidate_limit = 1
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())

    distant = item(1, "global", "tech-news")
    distant.processing = None
    distant.title = "Step-by-step CUDA optimization walkthrough for GPU kernels"
    distant.metadata["practice_category"] = "beginner-tech"

    relevant = item(2, "global", "tech-news")
    relevant.processing = None
    relevant.title = "Beginner guide to evaluating RAG for customer support"
    relevant.content = "Compare answer accuracy on ten after-sales tickets."
    relevant.metadata["practice_category"] = "beginner-tech"

    selected = orchestrator.prefilter_candidates([distant, relevant])

    assert selected == [relevant]


def test_practical_prefilter_caps_one_source_during_deficit_fill() -> None:
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={"beginner-tech": 1},
    )
    radar_config.collection.candidate_limit = 9
    radar_config.digest.max_items_per_source = 3
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    candidates = []
    for index in range(12):
        candidate = item(index, "global", "tech-news")
        candidate.processing = None
        candidate.title = f"AI agent architecture tutorial {index}"
        candidate.metadata.update(
            {
                "practice_category": "beginner-tech",
                "feed_name": "version-firehose" if index < 8 else f"feed-{index}",
            }
        )
        candidates.append(candidate)

    selected = orchestrator.prefilter_candidates(candidates)

    assert len(selected) == 7
    assert sum(
        candidate.metadata["feed_name"] == "version-firehose"
        for candidate in selected
    ) == 3


def test_history_deduplicates_url_and_title_but_allows_marked_progress(
    tmp_path: Path,
) -> None:
    path = tmp_path / "seen.json"
    store = HistoryStore(path, retention_days=7)
    original = item(1, "global", "tech-news")
    store.record([original])
    store.save()

    loaded = HistoryStore(path, retention_days=7)
    loaded.load()
    same_url = original.model_copy(deep=True)
    same_url.id = "same-url"
    same_title = original.model_copy(deep=True)
    same_title.id = "same-title"
    same_title.url = "https://other.example/new"
    progress = original.model_copy(deep=True)
    progress.id = "progress"
    progress.title = "Update: AI item 1"
    progress.content = "Materially changed evidence"

    result = loaded.filter_new([same_url, same_title, progress])

    assert result.removed == 2
    assert result.items == [progress]
    assert progress.metadata["is_progress"] is True


def test_metrics_are_secret_free_and_include_distribution(tmp_path: Path) -> None:
    radar_config = config()
    radar_config.metrics = MetricsConfig(enabled=True, output_dir=str(tmp_path))
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    orchestrator.last_fetch_report = None
    selected = [
        item(1, "global", "ai-product-fde"),
        item(2, "china", "tech-news"),
    ]
    usage = SimpleNamespace(
        total_input_tokens=100,
        total_output_tokens=50,
        total_tokens=150,
    )

    orchestrator._write_run_metrics(
        date="2026-09-02",
        fetched_count=120,
        merged_count=110,
        history_removed=5,
        candidate_count=60,
        analyzed_count=60,
        analyzed_items=selected,
        threshold_count=22,
        selected_items=selected,
        usage=usage,
        dry_run=True,
    )

    payload = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert payload["pipeline"]["fetched"] == 120
    assert payload["selection"]["regions"] == {"global": 1, "china": 1}
    assert payload["selection"]["practice_categories"] == {"unclassified": 2}
    assert payload["analysis"]["numeric_scores"] == 2
    assert payload["analysis"]["score_buckets"] == {"8-8.9": 2}
    assert len(payload["analysis"]["top_candidates"]) == 2
    assert payload["analysis"]["top_candidates"][0]["model_score"] == 8.0
    assert "DEEPSEEK_API_KEY" not in json.dumps(payload)


def test_analysis_health_aborts_when_model_scores_are_missing() -> None:
    analyzed = [item(index, "global", "ai-product-fde") for index in range(10)]
    for candidate in analyzed[:3]:
        candidate.processing.analysis.score = None  # type: ignore[union-attr]

    with pytest.raises(RuntimeError, match="Delivery aborted"):
        HorizonOrchestrator.ensure_analysis_health(analyzed)


def test_analysis_health_allows_eighty_percent_valid_scores() -> None:
    analyzed = [item(index, "global", "ai-product-fde") for index in range(10)]
    for candidate in analyzed[:2]:
        candidate.processing.analysis.score = None  # type: ignore[union-attr]

    HorizonOrchestrator.ensure_analysis_health(analyzed)


def test_feishu_webhook_token_is_redacted_from_log_url() -> None:
    safe = redact_url(
        "https://open.feishu.cn/open-apis/bot/v2/hook/very-secret-token"
    )
    assert safe.endswith("/hook/<redacted>")
    assert "very-secret-token" not in safe


def test_github_config_has_expected_sources_and_targets() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "config.github.json"
    payload = Config.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert len(payload.sources.google_news_queries()) == 11
    assert len(payload.sources.github) == 13
    assert len(payload.sources.rss) == 12
    assert payload.collection.time_window_hours == 30
    assert payload.collection.fallback_window_hours == 168
    assert payload.collection.candidate_limit == 60
    assert payload.collection.fallback_candidate_limit == 15
    assert payload.digest.max_items == 20
    assert sum(payload.digest.practice_targets.values()) == 20
    assert payload.digest.practice_targets == {
        "today-use": 5,
        "enterprise-case": 5,
        "method-pitfall": 4,
        "beginner-tech": 3,
        "china-career": 2,
        "hands-on": 1,
    }
    assert payload.digest.practice_minimums == {
        "today-use": 1,
        "enterprise-case": 1,
        "method-pitfall": 1,
        "beginner-tech": 1,
        "china-career": 1,
        "hands-on": 1,
    }
    assert payload.digest.generated_hands_on is True
    assert payload.digest.fulltext_reserve == 15
    assert payload.digest.candidate_practice_reserves == {
        "today-use": 6,
        "enterprise-case": 12,
        "method-pitfall": 8,
        "beginner-tech": 10,
        "china-career": 9,
    }
    assert {
        source.repo
        for source in payload.sources.github
        if source.practice_category == "china-career"
    } == {"QwenPaw", "agentscope"}
    assert all(
        query.max_results <= 20
        for query in payload.sources.google_news_queries()
    )
    assert {
        source.name
        for source in payload.sources.rss
        if source.practice_category in {
            "enterprise-case",
            "method-pitfall",
            "beginner-tech",
        }
    } >= {
        "AWS Machine Learning - Enterprise Workflows",
        "AWS Contact Center - AI Delivery",
        "Salesforce AI Guides",
    }
    assert all(
        settings.threshold == 7.0
        and settings.require_actionable_within_7_days is False
        for settings in payload.processing.profile_settings.values()
    )
    assert payload.digest.category_groups["raw-papers"].limit == 1


def test_daily_workflow_authenticates_github_release_discovery() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "ai-fde-radar.yml"
    )
    workflow = path.read_text(encoding="utf-8")

    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in workflow


def test_practice_targets_select_each_beginner_pillar_and_limit_raw_papers() -> None:
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={
            "today-use": 2,
            "enterprise-case": 2,
            "method-pitfall": 1,
            "beginner-tech": 1,
            "china-career": 1,
            "hands-on": 1,
        },
        max_items=8,
        max_today_use_per_source=2,
        category_groups={
            "raw-papers": {
                "limit": 1,
                "categories": ["research-paper", "daily-papers"],
            }
        },
    )
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    categories = [
        "today-use",
        "today-use",
        "enterprise-case",
        "enterprise-case",
        "method-pitfall",
        "beginner-tech",
        "china-career",
        "hands-on",
    ]
    candidates = []
    for index, practice_category in enumerate(categories):
        candidate = item(index, "china" if practice_category == "china-career" else "global", "ai-product-fde", 9 - index / 10)
        candidate.processing.analysis.practice_category = practice_category  # type: ignore[union-attr]
        candidate.metadata["practice_category"] = practice_category
        candidates.append(candidate)

    extra_paper = item(99, "global", "tech-news", 9.9)
    extra_paper.processing.analysis.practice_category = "beginner-tech"  # type: ignore[union-attr]
    extra_paper.metadata.update(
        {"practice_category": "beginner-tech", "category": "research-paper"}
    )
    candidates[5].metadata["category"] = "daily-papers"

    result = orchestrator.apply_balanced_digest([extra_paper, *candidates], log=False)

    assert len(result.items) == 8
    assert result.practice_counts == {
        "today-use": 2,
        "enterprise-case": 2,
        "method-pitfall": 1,
        "beginner-tech": 1,
        "china-career": 1,
        "hands-on": 1,
    }
    assert sum(
        entry.metadata.get("category") in {"research-paper", "daily-papers"}
        for entry in result.items
    ) == 1


def test_selection_keeps_quality_reserve_for_fulltext_failures() -> None:
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={"today-use": 2},
        max_items=2,
        fulltext_reserve=2,
        max_today_use_per_source=2,
    )
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    candidates = [item(index, "global", "ai-product-fde", 9 - index / 10) for index in range(4)]
    for candidate in candidates:
        candidate.processing.analysis.practice_category = "today-use"  # type: ignore[union-attr]
        candidate.metadata["practice_category"] = "today-use"

    result = asyncio.run(
        orchestrator.select_digest_items(candidates, topic_dedup=False, log=False)
    )

    assert [entry.id for entry in result.items] == ["item-0", "item-1"]
    assert [entry.id for entry in result.reserve_items] == ["item-2", "item-3"]


def test_practice_reserve_uses_model_category_and_round_robins_columns() -> None:
    minimums = {
        "today-use": 1,
        "enterprise-case": 1,
        "method-pitfall": 1,
        "beginner-tech": 1,
        "china-career": 1,
    }
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={**minimums, "hands-on": 1},
        practice_minimums={**minimums, "hands-on": 1},
        generated_hands_on=True,
        max_items=6,
        fulltext_reserve=5,
    )
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())
    categories = ["today-use"] * 5 + [
        "enterprise-case",
        "method-pitfall",
        "beginner-tech",
        "china-career",
    ]
    candidates = []
    for index, category in enumerate(categories):
        candidate = item(index, "global", "ai-product-fde", 9 - index / 10)
        candidate.processing.analysis.practice_category = category  # type: ignore[union-attr]
        candidate.metadata["practice_category"] = "source-hint"
        candidates.append(candidate)

    reserve = orchestrator._build_practice_reserve(candidates, [], 5)

    assert {
        entry.processing.analysis.practice_category  # type: ignore[union-attr]
        for entry in reserve
    } == set(minimums)


def test_fulltext_shortfall_repairs_only_missing_column(monkeypatch: pytest.MonkeyPatch) -> None:
    minimums = {
        "today-use": 1,
        "enterprise-case": 1,
        "method-pitfall": 1,
        "beginner-tech": 1,
        "china-career": 1,
    }
    radar_config = config(
        profile_targets={},
        region_targets={},
        matrix_targets={},
        practice_targets={**minimums, "hands-on": 1},
        practice_minimums={**minimums, "hands-on": 1},
        generated_hands_on=True,
        max_items=6,
        fulltext_reserve=5,
    )
    orchestrator = HorizonOrchestrator(radar_config, SimpleNamespace())

    selected = []
    for index, category in enumerate(
        ["today-use", "method-pitfall", "beginner-tech", "china-career"]
    ):
        candidate = item(index, "global", "ai-product-fde", 9 - index / 10)
        candidate.processing.analysis.practice_category = category  # type: ignore[union-attr]
        candidate.metadata.update(
            {"practice_category": category, "fulltext_status": "success"}
        )
        selected.append(candidate)

    inaccessible = item(10, "global", "ai-product-fde", 9.5)
    inaccessible.processing.analysis.practice_category = "enterprise-case"  # type: ignore[union-attr]
    inaccessible.metadata.update(
        {
            "practice_category": "enterprise-case",
            "source_practice_category": "enterprise-case",
            "fulltext_status": "unavailable",
        }
    )
    alternate = item(11, "global", "ai-product-fde", 8.5)
    alternate.processing.analysis.practice_category = "enterprise-case"  # type: ignore[union-attr]
    alternate.metadata.update(
        {
            "practice_category": "enterprise-case",
            "source_practice_category": "enterprise-case",
        }
    )

    async def rescue(candidates, missing_categories):  # type: ignore[no-untyped-def]
        assert missing_categories == {"enterprise-case"}
        assert [entry.id for entry in candidates] == [alternate.id]
        alternate.metadata["fulltext_status"] = "success"
        return [alternate]

    monkeypatch.setattr(
        orchestrator,
        "_hydrate_and_reanalyze_practice_rescue",
        rescue,
    )

    repaired = asyncio.run(
        orchestrator._repair_fulltext_practice_shortfalls(
            selected,
            [*selected, inaccessible, alternate],
        )
    )

    assert {entry.metadata["practice_category"] for entry in repaired} == set(minimums)
    assert inaccessible not in repaired
