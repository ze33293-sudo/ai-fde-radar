from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

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
        threshold_count=22,
        selected_items=selected,
        usage=usage,
        dry_run=True,
    )

    payload = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert payload["pipeline"]["fetched"] == 120
    assert payload["selection"]["regions"] == {"global": 1, "china": 1}
    assert "DEEPSEEK_API_KEY" not in json.dumps(payload)


def test_feishu_webhook_token_is_redacted_from_log_url() -> None:
    safe = redact_url(
        "https://open.feishu.cn/open-apis/bot/v2/hook/very-secret-token"
    )
    assert safe.endswith("/hook/<redacted>")
    assert "very-secret-token" not in safe


def test_github_config_has_expected_sources_and_targets() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "config.github.json"
    payload = Config.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert len(payload.sources.google_news_queries()) == 4
    assert payload.collection.time_window_hours == 30
    assert payload.collection.candidate_limit == 60
    assert payload.digest.max_items == 20
    assert sum(payload.digest.matrix_targets.values()) == 20
