"""Main orchestrator coordinating the entire workflow."""

import asyncio
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional
from urllib.parse import unquote_plus, urlsplit
from zoneinfo import ZoneInfo
import httpx
from rich.console import Console

from .console_icons import get_icons
from .models import (
    ArtifactSource,
    ClassificationResult,
    Config,
    ContentAnalysis,
    ContentArtifact,
    ContentBlock,
    ContentItem,
    ProcessingResult,
    SourceType,
    TrafilaturaExtractorConfig,
)
from ._file_utils import _atomic_write_text
from .storage.manager import StorageManager, safe_output_path
from .services.email import EmailManager
from .services.webhook import WebhookNotifier
from .scrapers.github import GitHubScraper
from .scrapers.hackernews import HackerNewsScraper
from .scrapers.rss import RSSScraper
from .scrapers.reddit import RedditScraper
from .scrapers.telegram import TelegramScraper
from .scrapers.twitter import TwitterScraper
from .scrapers.twitter_playwright import TwitterPlaywrightScraper
from .scrapers.openbb import OpenBBScraper
from .scrapers.ossinsight import OSSInsightScraper
from .scrapers.gdelt import GDELTScraper
from .scrapers.google_news import GoogleNewsScraper
from .scrapers.hf_papers import HuggingFacePapersScraper
from .ai.client import create_ai_client
from .ai.analyzer import ContentAnalyzer
from .ai.summarizer import DailySummarizer
from .ai.enricher import ContentEnricher, EnrichmentBatchResult
from .ai.tokens import get_usage_snapshot
from .processing import ProfileRegistry
from .processing.history import HistoryStore
from .extractors.trafilatura import TrafilaturaExtractor


_TRACKING_QUERY_PARAMETERS = {
    "_ga",
    "dclid",
    "fbclid",
    "gclid",
    "igshid",
    "li_fat_id",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ttclid",
    "twclid",
    "vero_id",
}

_AI_SIGNAL_TERMS = {
    "ai",
    "llm",
    "machine learning",
    "artificial intelligence",
    "neural",
    "transformer",
    "inference",
    "openai",
    "anthropic",
    "deepseek",
    "qwen",
    "gemini",
    "claude",
    "chatgpt",
    "agent",
    "embedding",
    "vector database",
    "rag",
    "mcp",
    "大模型",
    "人工智能",
    "智能体",
}

_PRACTICAL_ACTION_SIGNALS = {
    "how to",
    "tutorial",
    "guide",
    "walkthrough",
    "step-by-step",
    "quickstart",
    "cookbook",
    "template",
    "starter",
    "playbook",
    "case study",
    "customer story",
    "postmortem",
    "lessons learned",
    "production incident",
    "available now",
    "generally available",
    "教程",
    "指南",
    "实战",
    "手把手",
    "复盘",
    "踩坑",
    "案例",
    "落地",
    "上线",
    "工作流",
}

_PROJECT_RELEVANCE_SIGNALS = {
    "customer support",
    "customer service",
    "support agent",
    "service desk",
    "ticket triage",
    "ticketing",
    "case management",
    "knowledge base",
    "knowledge management",
    "human escalation",
    "human-in-the-loop",
    "售后",
    "客服",
    "工单",
    "知识库",
    "人工转接",
    "人工审核",
}

_PRACTICAL_NEGATIVE_TITLE_SIGNALS = {
    "funding",
    "fundraise",
    "valuation",
    "stock price",
    "earnings",
    "lawsuit",
    "copyright suit",
    "government sides",
    "bans ai",
    "rumor",
    "opinion",
    "融资",
    "估值",
    "股价",
    "财报",
    "诉讼",
    "版权案",
    "传闻",
    "高管观点",
}

_DISTANT_TECH_TITLE_SIGNALS = {
    "cuda",
    "gpu kernel",
    "speculative decoding",
    "model training",
    "training infrastructure",
    "robotics",
    "芯片",
    "算力集群",
    "训练框架",
    "机器人",
}

_PRACTICE_CATEGORY_SIGNALS = {
    "today-use": {
        "released",
        "release",
        "introducing",
        "launch",
        "launched",
        "available",
        "update",
        "new feature",
        "changelog",
        "发布",
        "推出",
        "上线",
        "开放使用",
        "更新",
        "新功能",
    },
    "enterprise-case": {
        "case study",
        "customer story",
        "deployed",
        "deployment",
        "rollout",
        "adoption",
        "roi",
        "workflow",
        "customer support",
        "customer service",
        "case management",
        "案例",
        "落地",
        "部署",
        "采用率",
        "工作流",
        "客服",
        "售后",
        "工单",
    },
    "method-pitfall": {
        "evaluation",
        "evals",
        "benchmark methodology",
        "failure",
        "reliability",
        "observability",
        "guardrail",
        "permissions",
        "security",
        "postmortem",
        "human-in-the-loop",
        "cost per",
        "评测",
        "评估",
        "失败",
        "可靠性",
        "可观测",
        "权限",
        "安全",
        "成本",
        "踩坑",
        "复盘",
    },
    "beginner-tech": {
        "explained",
        "introduction",
        "beginner",
        "guide",
        "tutorial",
        "walkthrough",
        "architecture",
        "comparison",
        "入门",
        "科普",
        "原理",
        "指南",
        "教程",
        "架构",
        "对比",
    },
    "china-career": {
        "product manager",
        "forward deployed engineer",
        "fde",
        "job description",
        "hiring",
        "interview",
        "portfolio",
        "career",
        "产品经理",
        "应用实施",
        "岗位",
        "招聘",
        "面试",
        "作品集",
        "能力要求",
        "厦门",
    },
    "hands-on": {
        "hands-on",
        "tutorial",
        "template",
        "starter",
        "quickstart",
        "cookbook",
        "code example",
        "sample app",
        "github repo",
        "demo",
        "实战",
        "教程",
        "模板",
        "示例代码",
        "开源项目",
    },
}

_MEASURABLE_EVIDENCE_PATTERN = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?x\b|"
    r"\b(?:latency|accuracy|resolution rate|handle time|cost|roi|csat)\b|"
    r"(?:准确率|解决率|转人工率|响应时间|处理时长|成本|采用率|满意度))",
    re.IGNORECASE,
)

_VERSION_ONLY_RELEASE_PATTERN = re.compile(
    r"\breleased?\s+(?:v?\d|b\d)|\b(?:v?\d+(?:\.\d+){1,3}|b\d{3,})\b",
    re.IGNORECASE,
)


def _contains_signal(text: str, signal: str) -> bool:
    """Match ASCII terms on token boundaries and CJK terms as substrings."""
    folded_text = text.casefold()
    folded_signal = signal.casefold()
    if folded_signal.isascii():
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(folded_signal)}(?![a-z0-9])",
                folded_text,
            )
        )
    return folded_signal in folded_text


def _signal_count(text: str, signals: set[str]) -> int:
    return sum(_contains_signal(text, signal) for signal in signals)


def _deduplication_url_key(url: str) -> tuple[str, str, str, str, Optional[int], str, str]:
    """Return a conservative URL identity key for cross-source deduplication."""
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if (scheme, port) in {("http", 80), ("https", 443)}:
        port = None

    path = parsed.path.rstrip("/") or "/"
    query_parts = []
    for part in parsed.query.split("&") if parsed.query else []:
        name = unquote_plus(part.partition("=")[0]).lower()
        if name.startswith("utm_") or name in _TRACKING_QUERY_PARAMETERS:
            continue
        query_parts.append(part)

    return (
        scheme,
        parsed.username or "",
        parsed.password or "",
        host,
        port,
        path,
        "&".join(query_parts),
    )


@dataclass
class BalancedDigestResult:
    """Items and selection statistics from balanced digest filtering."""

    items: List[ContentItem]
    enabled: bool = False
    group_counts: Dict[str, int] = field(default_factory=dict)
    group_limits: Dict[str, Optional[int]] = field(default_factory=dict)
    duplicate_categories: List[str] = field(default_factory=list)
    profile_counts: Dict[str, int] = field(default_factory=dict)
    region_counts: Dict[str, int] = field(default_factory=dict)
    matrix_counts: Dict[str, int] = field(default_factory=dict)
    practice_counts: Dict[str, int] = field(default_factory=dict)
    practice_minimum_counts: Dict[str, int] = field(default_factory=dict)
    fallback_counts: Dict[str, int] = field(default_factory=dict)
    shortfall_reasons: Dict[str, str] = field(default_factory=dict)


@dataclass
class FilteringPipelineResult:
    """Items and statistics from score, topic, and digest filtering."""

    items: List[ContentItem]
    threshold_count: int
    topic_dedup_count: int
    topic_dedup_removed: int
    balanced_digest: BalancedDigestResult
    eligible_count: Optional[int] = None
    reserve_items: List[ContentItem] = field(default_factory=list)


@dataclass
class SourceFetchOutcome:
    """Result of fetching one configured source."""

    source_name: str
    status: Literal["success", "empty", "failure"]
    items: List[ContentItem] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        result: Dict[str, object] = {
            "source": self.source_name,
            "status": self.status,
            "item_count": len(self.items),
        }
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass
class FetchReport:
    """Aggregate diagnostics for one fetch across configured sources."""

    outcomes: List[SourceFetchOutcome] = field(default_factory=list)

    @property
    def status(self) -> Literal["not_attempted", "success", "partial_failure", "failure"]:
        if not self.outcomes:
            return "not_attempted"
        if self.failed_count == len(self.outcomes):
            return "failure"
        if self.failed_count:
            return "partial_failure"
        return "success"

    @property
    def failed_count(self) -> int:
        return sum(outcome.status == "failure" for outcome in self.outcomes)

    @property
    def all_failed(self) -> bool:
        return bool(self.outcomes) and self.failed_count == len(self.outcomes)

    def failure_message(self) -> str:
        failures = "; ".join(
            f"{outcome.source_name}: {outcome.error or 'unknown error'}"
            for outcome in self.outcomes
            if outcome.status == "failure"
        )
        return f"All {len(self.outcomes)} attempted sources failed ({failures})"

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "attempted": len(self.outcomes),
            "successful": len(self.outcomes) - self.failed_count,
            "empty": sum(outcome.status == "empty" for outcome in self.outcomes),
            "failed": self.failed_count,
            "item_count": sum(len(outcome.items) for outcome in self.outcomes),
            "sources": [outcome.to_dict() for outcome in self.outcomes],
        }


class HorizonOrchestrator:
    """Orchestrates the complete workflow for content aggregation and analysis."""

    icons = get_icons()

    def __init__(
        self,
        config: Config,
        storage: StorageManager,
        console: Optional[Console] = None,
        profiles: Optional[ProfileRegistry] = None,
    ):
        """Initialize orchestrator.

        Args:
            config: Application configuration
            storage: Storage manager
            console: Shared Rich Console instance
        """
        self.config = config
        self.storage = storage
        self.console = console or Console(stderr=True)
        self.icons = get_icons(config.display.icon_style)
        self.profiles = profiles or ProfileRegistry.load(
            Path(config.processing.profiles_dir), config.processing.default_profile
        )
        self.profiles.validate_source_references(
            config.sources.model_dump(mode="json")
        )
        for profile_id in config.processing.profile_settings:
            self.profiles.get(profile_id)
        if config.digest.profile_order:
            configured_profiles = set(config.digest.profile_order)
            unknown_profiles = configured_profiles - self.profiles.ids
            if unknown_profiles:
                raise ValueError(
                    "digest.profile_order contains unknown profiles "
                    f"({', '.join(sorted(unknown_profiles))})"
                )
            config.digest.profile_order.extend(
                profile.id
                for profile in self.profiles.profiles
                if profile.id not in configured_profiles
            )
        self.email_manager = EmailManager(config.email, console=self.console) if config.email else None
        self.webhook_notifier = (
            WebhookNotifier(config.webhook, console=self.console, icons=self.icons)
            if config.webhook and config.webhook.enabled
            else None
        )
        self.last_fetch_report: Optional[FetchReport] = None

    async def run(
        self,
        force_hours: int = None,
        *,
        dry_run: bool = False,
        force_send: bool = False,
    ) -> None:
        """Execute the complete workflow.

        Args:
            force_hours: Optional override for time window in hours
            dry_run: Generate artifacts without external delivery or state commits.
            force_send: Bypass the same-day successful-send guard.
        """
        local_today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
        sent_marker = self._sent_marker_path(local_today)
        if sent_marker.exists() and not force_send and not dry_run:
            self.console.print(
                f"[yellow]A successful delivery is already recorded for {local_today}; "
                "skipping. Use --force-send to send again.[/yellow]"
            )
            return
        self.console.print(
            f"[bold cyan]{self.icons['start']} AI FDE Radar - Starting aggregation...[/bold cyan]\n"
        )

        # Check email subscriptions if configured
        if (
            self.email_manager
            and self.config.email
            and self.config.email.enabled
            and self.config.email.imap_enabled
        ):
            self.console.print(f"{self.icons['email']} Checking for new email subscriptions...")
            self.email_manager.check_subscriptions(self.storage)

        try:
            # 1. Determine time window
            since = self._determine_time_window(force_hours)
            self.console.print(
                f"{self.icons['date']} Fetching content since: "
                f"{since.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )

            # 2. Fetch the main 30-hour window from all sources.
            fresh_items = await self.fetch_all_sources(since)
            primary_fetch_report = self.last_fetch_report
            self.console.print(
                f"{self.icons['fetched']} Fetched {len(fresh_items)} items from all sources\n"
            )

            if primary_fetch_report and primary_fetch_report.all_failed:
                raise RuntimeError(primary_fetch_report.failure_message())

            configured_minimums = getattr(
                getattr(self.config, "digest", None), "practice_minimums", {}
            )
            if not fresh_items and not configured_minimums:
                self.console.print("[yellow]No new content found. Exiting.[/yellow]")
                return

            history = HistoryStore(
                Path(self.config.collection.history_path),
                self.config.collection.history_days,
            )
            history.load()
            external_minimums = self._external_practice_minimums()
            all_items = list(fresh_items)
            merged_items = self.merge_cross_source_duplicates(all_items)
            self._annotate_candidate_freshness(merged_items, since)
            history_result = history.filter_new(merged_items)

            # Reserve a few of the 60 scoring slots for a post-analysis,
            # category-specific seven-day fallback.
            candidate_limit = self.config.collection.candidate_limit
            configured_fallback_reserve = int(
                getattr(self.config.collection, "fallback_candidate_limit", 10)
            )
            fallback_reserve = (
                min(
                    configured_fallback_reserve,
                    candidate_limit - len(external_minimums),
                )
                if external_minimums and candidate_limit > len(external_minimums)
                else 0
            )
            initial_limit = max(1, candidate_limit - fallback_reserve)
            model_candidates = self.prefilter_candidates(
                history_result.items, limit=initial_limit
            )
            analyzed_items = await self.analyze_items(model_candidates)
            self.console.print(
                f"{self.icons['ai']} Analyzed {len(analyzed_items)} items with AI\n"
            )
            self.ensure_analysis_health(analyzed_items)

            qualified_categories = {
                str(item.metadata.get("practice_category"))
                for item in analyzed_items
                if self._passes_practice_hard_gates(item)
            }
            missing_for_search = {
                category
                for category in external_minimums
                if category not in qualified_categories
            }
            fallback_items: List[ContentItem] = []
            fallback_window = self._determine_fallback_window(force_hours)
            remaining_slots = max(0, candidate_limit - len(analyzed_items))
            if missing_for_search and fallback_window < since and remaining_slots:
                self.console.print(
                    f"{self.icons['fetch']} Targeted seven-day fallback search after "
                    f"scoring: {', '.join(sorted(missing_for_search))}\n"
                )
                fallback_items = await self.fetch_targeted_sources(
                    fallback_window, missing_for_search
                )
                fallback_fetch_report = self.last_fetch_report
                self.last_fetch_report = FetchReport(
                    outcomes=(primary_fetch_report.outcomes if primary_fetch_report else [])
                    + (fallback_fetch_report.outcomes if fallback_fetch_report else [])
                )
                all_items.extend(fallback_items)
                combined_merged = self.merge_cross_source_duplicates(all_items)
                self._annotate_candidate_freshness(combined_merged, since)
                combined_history = history.filter_new(combined_merged)
                initial_keys = {
                    _deduplication_url_key(str(item.url))
                    for item in history_result.items
                }
                additional_items = [
                    item
                    for item in combined_history.items
                    if _deduplication_url_key(str(item.url)) not in initial_keys
                    and self._source_practice_category(item) in missing_for_search
                ]
                fallback_candidates = self.prefilter_candidates(
                    additional_items,
                    limit=remaining_slots,
                    practice_categories=missing_for_search,
                )
                fallback_analyzed = await self.analyze_items(fallback_candidates)
                self.ensure_analysis_health(fallback_analyzed)
                model_candidates.extend(fallback_candidates)
                analyzed_items.extend(fallback_analyzed)
                merged_items = combined_merged
                history_result = combined_history
            else:
                self.last_fetch_report = primary_fetch_report

            # Feed/index snippets are intentionally cheap to score, but they are
            # often too thin for the model to verify an original source or all
            # category-specific evidence (especially enterprise workflow +
            # outcome).  Hydrate only a small, balanced set for still-missing
            # columns, then re-run analysis on the complete source before the
            # hard gates are applied.  This keeps the gates strict without
            # creating the impossible "verify before fetching" ordering.
            qualified_categories = {
                str(item.metadata.get("practice_category"))
                for item in analyzed_items
                if self._passes_practice_hard_gates(item)
            }
            missing_for_verification = {
                category
                for category in external_minimums
                if category not in qualified_categories
            }
            if missing_for_verification:
                await self._hydrate_and_reanalyze_practice_rescue(
                    analyzed_items,
                    missing_for_verification,
                )

            if not all_items:
                if external_minimums:
                    raise RuntimeError(
                        "No unseen candidates were found for the required practice columns."
                    )
                self.console.print("[yellow]No new content found. Exiting.[/yellow]")
                return

            if len(merged_items) < len(all_items):
                self.console.print(
                    f"{self.icons['merge']} Merged "
                    f"{len(all_items) - len(merged_items)} cross-source duplicates "
                    f"→ {len(merged_items)} unique items\n"
                )
            if history_result.removed:
                self.console.print(
                    f"{self.icons['cleanup']} Removed {history_result.removed} "
                    "items seen in the recent history window\n"
                )

            # 7. Filter, deduplicate, and balance the digest
            filtering_result = await self.select_digest_items(
                analyzed_items,
            )
            important_items = filtering_result.items

            # Fetch full text for the selected digest first. If indexed articles
            # cannot be opened, hydrate a small quality reserve and rebalance so
            # transient paywalls/403s do not unnecessarily shrink the edition.
            important_items = await self.hydrate_selected_items(important_items)
            target_size = self._external_item_limit()
            if (
                len(important_items) < target_size
                and filtering_result.reserve_items
                and self.config.digest.fulltext_reserve > 0
            ):
                reserve_items = await self.hydrate_selected_items(
                    filtering_result.reserve_items[
                        : self.config.digest.fulltext_reserve
                    ]
                )
                important_items = self.apply_balanced_digest(
                    important_items + reserve_items,
                    log=False,
                ).items
            self._assert_external_practice_minimums(important_items)
            self._annotate_digest_depth(important_items)

            # Show per-sub-source selection breakdown
            selected_counts: Dict[str, int] = defaultdict(int)
            for item in important_items:
                key = f"{item.source_type.value}/{self._sub_source_label(item)}"
                selected_counts[key] += 1
            for source_key, count in sorted(selected_counts.items()):
                self.console.print(f"      {self.icons['detail']} {source_key}: {count}")
            self.console.print("")

            # 8. Search related stories + enrich with background knowledge (2nd AI pass)
            await self.enrich_items(important_items)
            if self.config.digest.generated_hands_on:
                important_items.append(self._build_hands_on_card(important_items, today=local_today))
            self._assert_complete_practice_digest(important_items)

            # 9. Generate and save daily summaries for each configured language
            today = local_today
            for lang in self.config.ai.languages:
                summarizer = DailySummarizer(
                    profile_names=self.profiles.names,
                    profile_order=self.config.digest.profile_order,
                    practice_targets=self.config.digest.practice_targets,
                )
                summary = await summarizer.generate_summary(important_items, today, len(all_items), language=lang)

                # Save to data/summaries/
                summary_path = self.storage.save_daily_summary(today, summary, language=lang)
                self.console.print(
                    f"{self.icons['save']} Saved {lang.upper()} summary to: {summary_path}\n"
                )

                # Copy to docs/ for GitHub Pages
                try:
                    post_filename = f"{today}-summary-{lang}.md"
                    posts_dir = Path("docs/_posts")
                    posts_dir.mkdir(parents=True, exist_ok=True)

                    dest_path = safe_output_path(posts_dir, post_filename)

                    # Add Jekyll front matter
                    front_matter = (
                        "---\n"
                        "layout: default\n"
                        f"title: \"AI FDE Radar: {today} ({lang.upper()})\"\n"
                        f"date: {today}\n"
                        f"lang: {lang}\n"
                        "---\n\n"
                    )

                    # Strip leading H1 header to avoid duplication with Jekyll title
                    summary_content = summary
                    first_line = summary_content.strip().split("\n")[0]
                    if first_line.startswith("# "):
                        parts = summary_content.split("\n", 1)
                        if len(parts) > 1:
                            summary_content = parts[1].strip()

                    with open(dest_path, "w", encoding="utf-8") as f:
                        f.write(front_matter + summary_content)

                    self.console.print(
                        f"{self.icons['document']} Copied {lang.upper()} summary "
                        f"to GitHub Pages: {dest_path}\n"
                    )
                except Exception as e:
                    self.console.print(
                        f"[yellow]{self.icons['warning']} Failed to copy "
                        f"{lang.upper()} summary to docs/: {e}[/yellow]\n"
                    )

                # Send email if configured
                if (
                    not dry_run
                    and self.email_manager
                    and self.config.email
                    and self.config.email.enabled
                ):
                    self.console.print(
                        f"{self.icons['email']} Sending {lang.upper()} email summary..."
                    )
                    subscribers = self.storage.load_subscribers()
                    subject = f"Horizon Summary ({lang.upper()}) - {today}"
                    self.email_manager.send_daily_summary(summary, subject, subscribers)

                # Send webhook notification if configured
                if self.webhook_notifier and not dry_run:
                    await self.webhook_notifier.send_daily_summary(
                        summary=summary,
                        important_items=important_items,
                        all_items_count=len(all_items),
                        date=today,
                        lang=lang,
                        summarizer=summarizer,
                    )

            if not dry_run:
                history.record(
                    [
                        item
                        for item in important_items
                        if not item.metadata.get("generated_hands_on")
                    ]
                )
                history.save()
                if self.webhook_notifier:
                    self._mark_sent(sent_marker)

            self.console.print(
                f"[bold green]{self.icons['success']} "
                "AI FDE Radar completed successfully![/bold green]"
            )
            usage = get_usage_snapshot()
            self._write_run_metrics(
                date=today,
                fetched_count=len(all_items),
                merged_count=len(merged_items),
                history_removed=history_result.removed,
                candidate_count=len(model_candidates),
                analyzed_count=len(analyzed_items),
                analyzed_items=analyzed_items,
                fetched_items=all_items,
                threshold_count=filtering_result.threshold_count,
                selected_items=important_items,
                usage=usage,
                dry_run=dry_run,
            )
            if usage.total_tokens > 0:
                self.console.print(
                    f"\n{self.icons['tokens']} Token usage this run: "
                    f"{usage.total_tokens} tokens "
                    f"(input: {usage.total_input_tokens}, output: {usage.total_output_tokens})"
                )
                for provider, u in sorted(usage.per_provider.items()):
                    if u.total <= 0:
                        continue
                    self.console.print(
                        f"   {self.icons['detail']} {provider}: {u.total} tokens "
                        f"(in: {u.input_tokens}, out: {u.output_tokens})"
                    )

        except Exception as e:
            self.console.print(
                f"[bold red]{self.icons['error']} Error: {e}[/bold red]"
            )

            # Send webhook failure notification if configured
            if self.webhook_notifier and not dry_run:
                await self.webhook_notifier.send_failure(
                    date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    error_message=str(e),
                )

            raise

    def _sent_marker_path(self, date: str) -> Path:
        marker_dir = getattr(
            self.config.collection, "sent_marker_dir", "data/state/sent"
        )
        return Path(marker_dir) / f"{date}.json"

    @staticmethod
    def _mark_sent(marker: Path) -> None:
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "success",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write_text(
            marker,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )

    def prefilter_candidates(
        self,
        items: List[ContentItem],
        *,
        limit: Optional[int] = None,
        practice_categories: Optional[set[str]] = None,
    ) -> List[ContentItem]:
        """Apply evidence checks and build a balanced AI-scoring candidate pool.

        The final digest matrix is expanded proportionally to ``candidate_limit``
        so a high-volume feed (for example arXiv) cannot consume every model
        scoring slot before China or product/FDE candidates are considered.
        Empty cells are backfilled from the remaining best evidence, preserving
        the configured quality-first behavior.
        """
        limit = limit or self.config.collection.candidate_limit
        practice_budgets = self._candidate_practice_budgets(
            limit,
            categories=practice_categories,
        )
        eligible = []
        for item in items:
            if (
                item.source_type == SourceType.GOOGLE_NEWS
                and item.metadata.get("original_url_resolved") is False
            ):
                continue
            if item.source_type == SourceType.HACKERNEWS:
                if not any(
                    _contains_signal(item.title, term) for term in _AI_SIGNAL_TERMS
                ):
                    continue
            practical_score = self._practical_signal_score(item)
            item.metadata["prefilter_practical_score"] = practical_score
            # Actionability is a bonus, not an admission gate. Only discard
            # candidates carrying multiple strong negative/noise signals.
            if practice_budgets and practical_score < -4:
                continue
            eligible.append(item)

        eligible.sort(
            key=self._candidate_priority
        )
        matrix_budgets = (
            {} if practice_budgets else self._candidate_matrix_budgets(limit)
        )
        quota_budgets = practice_budgets or matrix_budgets
        quota_matcher = (
            self._candidate_matches_practice
            if practice_budgets
            else self._candidate_matches_matrix
        )
        if not quota_budgets:
            limited = eligible[:limit]
        else:
            limited = []
            selected_ids: set[str] = set()
            selected_source_counts: Dict[str, int] = defaultdict(int)
            hard_source_cap = (
                max(2, self.config.digest.max_items_per_source or 3)
                if practice_budgets
                else limit
            )

            for quota_key, budget in quota_budgets.items():
                cell_candidates = [
                    item
                    for item in eligible
                    if item.id not in selected_ids
                    and quota_matcher(item, quota_key)
                ]
                # Four distinct sources per full cell is a soft diversity goal.
                # A second pass below relaxes it when the open-web supply is thin.
                per_source_soft_cap = max(1, math.ceil(budget / 4))
                source_counts: Dict[str, int] = defaultdict(int)
                cell_selected: List[ContentItem] = []

                for item in cell_candidates:
                    source_key = self._candidate_source_key(item)
                    if (
                        source_counts[source_key] >= per_source_soft_cap
                        or selected_source_counts[source_key] >= hard_source_cap
                    ):
                        continue
                    cell_selected.append(item)
                    source_counts[source_key] += 1
                    selected_source_counts[source_key] += 1
                    if len(cell_selected) >= budget:
                        break

                if len(cell_selected) < budget:
                    cell_ids = {item.id for item in cell_selected}
                    for item in cell_candidates:
                        if item.id in cell_ids:
                            continue
                        source_key = self._candidate_source_key(item)
                        if selected_source_counts[source_key] >= hard_source_cap:
                            continue
                        cell_selected.append(item)
                        selected_source_counts[source_key] += 1
                        if len(cell_selected) >= budget:
                            break

                limited.extend(cell_selected)
                selected_ids.update(item.id for item in cell_selected)

            # Quality-first deficit fill: cells with insufficient supply donate
            # their unused slots to the strongest remaining eligible evidence.
            for item in eligible:
                if len(limited) >= limit:
                    break
                if item.id not in selected_ids:
                    source_key = self._candidate_source_key(item)
                    if selected_source_counts[source_key] >= hard_source_cap:
                        continue
                    limited.append(item)
                    selected_ids.add(item.id)
                    selected_source_counts[source_key] += 1

        if len(limited) < len(items):
            self.console.print(
                f"{self.icons['filter']} Rule prefilter retained {len(limited)}/"
                f"{len(items)} candidates for model scoring\n"
            )
        if quota_budgets:
            quota_counts: Dict[str, int] = defaultdict(int)
            for item in limited:
                for quota_key in quota_budgets:
                    if quota_matcher(item, quota_key):
                        quota_counts[quota_key] += 1
                        break
            quota_label = "practice" if practice_budgets else "candidate"
            for quota_key, budget in quota_budgets.items():
                self.console.print(
                    f"      {self.icons['detail']} {quota_label} {quota_key}: "
                    f"{quota_counts.get(quota_key, 0)}/{budget}"
                )
            self.console.print("")
        return limited

    @staticmethod
    def _candidate_priority(item: ContentItem) -> tuple[int, int, float, int]:
        return (
            int(item.metadata.get("source_tier", 2)),
            -int(item.metadata.get("prefilter_practical_score") or 0),
            -item.published_at.timestamp(),
            1 if item.metadata.get("is_fallback") else 0,
        )

    @staticmethod
    def _practical_signal_score(item: ContentItem) -> int:
        """Estimate whether an item contains evidence worth a paid AI review.

        This is intentionally a recall-oriented heuristic, not the publication
        score.  It rewards concrete actions, project proximity, measurements,
        and pillar-specific evidence while removing obvious news-cycle noise.
        DeepSeek remains responsible for the final 0-10 judgment.
        """
        title = item.title or ""
        body = (item.content or "")[:3000]
        combined = f"{title}\n{body}"
        practice = str(item.metadata.get("practice_category") or "")

        title_actions = min(3, _signal_count(title, _PRACTICAL_ACTION_SIGNALS))
        body_actions = min(2, _signal_count(body, _PRACTICAL_ACTION_SIGNALS))
        project_hits = min(2, _signal_count(combined, _PROJECT_RELEVANCE_SIGNALS))
        category_hits = min(
            3,
            _signal_count(combined, _PRACTICE_CATEGORY_SIGNALS.get(practice, set())),
        )

        score = title_actions * 2 + body_actions + project_hits * 2 + category_hits * 2
        if _MEASURABLE_EVIDENCE_PATTERN.search(combined):
            score += 2
        score -= min(
            6,
            _signal_count(title, _PRACTICAL_NEGATIVE_TITLE_SIGNALS) * 3,
        )
        score -= min(6, _signal_count(title, _DISTANT_TECH_TITLE_SIGNALS) * 4)

        # A bare library build/version is release churn, not beginner learning.
        if (
            len(title) <= 100
            and _VERSION_ONLY_RELEASE_PATTERN.search(title)
            and title_actions <= 1
            and project_hits == 0
        ):
            score -= 3
        return score

    def _candidate_matrix_budgets(self, limit: int) -> Dict[str, int]:
        """Scale final matrix targets to the model-scoring candidate limit."""
        targets = {
            key: target
            for key, target in self.config.digest.matrix_targets.items()
            if target > 0
        }
        total = sum(targets.values())
        if not targets or total <= 0:
            return {}

        exact = {key: limit * target / total for key, target in targets.items()}
        budgets = {key: math.floor(value) for key, value in exact.items()}
        remainder = limit - sum(budgets.values())
        order = {key: index for index, key in enumerate(targets)}
        for key in sorted(
            targets,
            key=lambda candidate: (-(exact[candidate] - budgets[candidate]), order[candidate]),
        )[:remainder]:
            budgets[key] += 1
        return budgets

    def _candidate_practice_budgets(
        self,
        limit: int,
        *,
        categories: Optional[set[str]] = None,
    ) -> Dict[str, int]:
        """Build configurable, scarcity-aware model-scoring reserves.

        Candidate reserves are intentionally independent from final display
        targets: evidence-heavy or low-volume columns may need more articles
        reviewed to yield one publishable result.  When the configured
        reserves exceed the available budget they are scaled proportionally;
        otherwise unused scoring slots remain available for quality-first fill.
        """
        configured = (
            self.config.digest.candidate_practice_reserves
            or self.config.digest.practice_targets
        )
        targets = {
            key: target
            for key, target in configured.items()
            if target > 0
            and (categories is None or key in categories)
            and not (
                key == "hands-on" and self.config.digest.generated_hands_on
            )
        }
        total = sum(targets.values())
        if not targets or total <= 0:
            return {}

        if total <= limit:
            return dict(targets)

        minimum = 1 if limit >= len(targets) else 0
        budgets = {key: minimum for key in targets}
        remaining = limit - sum(budgets.values())
        exact = {
            key: remaining * target / total
            for key, target in targets.items()
        }
        for key, value in exact.items():
            budgets[key] += math.floor(value)
        remainder = limit - sum(budgets.values())
        order = {key: index for index, key in enumerate(targets)}
        for key in sorted(
            targets,
            key=lambda candidate: (
                -(exact[candidate] - math.floor(exact[candidate])),
                order[candidate],
            ),
        )[:remainder]:
            budgets[key] += 1
        return budgets

    def _candidate_profiles(self, item: ContentItem) -> set[str]:
        requested = item.profile
        if isinstance(requested, list):
            profiles = {profile.strip() for profile in requested if profile.strip()}
        elif isinstance(requested, str) and requested.strip():
            profiles = {requested.strip()}
        elif item.processing:
            profiles = {item.processing.classification.profile}
        else:
            profiles = {self.profiles.default_profile}
        return profiles

    def _candidate_matches_matrix(self, item: ContentItem, matrix_key: str) -> bool:
        region, _, profile = matrix_key.partition("/")
        item_region = str(item.metadata.get("region") or "global")
        return item_region == region and profile in self._candidate_profiles(item)

    @staticmethod
    def _candidate_matches_practice(item: ContentItem, category: str) -> bool:
        return (
            item.metadata.get("source_practice_category")
            or item.metadata.get("practice_category")
        ) == category

    @staticmethod
    def _candidate_source_key(item: ContentItem) -> str:
        """Return a stable source bucket used only for prefilter diversity."""
        if item.source_type == SourceType.HACKERNEWS:
            return SourceType.HACKERNEWS.value
        metadata = item.metadata
        for field_name in (
            "feed_name",
            "source_name",
            "subreddit",
            "repo",
            "watchlist",
            "domain",
            "gn_query",
        ):
            value = metadata.get(field_name)
            if value:
                return f"{item.source_type.value}:{value}"
        hostname = urlsplit(str(item.url)).hostname or "unknown"
        return f"{item.source_type.value}:{hostname.casefold()}"

    async def hydrate_selected_items(
        self, items: List[ContentItem]
    ) -> List[ContentItem]:
        """Fetch complete article text for final items only."""
        if not items:
            return []
        if not getattr(self.config.collection, "fetch_fulltext", False):
            return items
        extractor = TrafilaturaExtractor(TrafilaturaExtractorConfig())
        semaphore = asyncio.Semaphore(5)

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async def hydrate(item: ContentItem) -> tuple[ContentItem, bool]:
                async with semaphore:
                    extracted = await extractor.extract(str(item.url), client)
                if extracted and len(extracted.strip()) >= 200:
                    if item.source_type in {SourceType.HACKERNEWS, SourceType.REDDIT}:
                        community = item.content or ""
                        item.content = extracted + (
                            f"\n\n--- Community context ---\n{community}"
                            if community
                            else ""
                        )
                    else:
                        item.content = extracted
                    item.metadata["fulltext_status"] = "success"
                    return item, True

                item.metadata["fulltext_status"] = "unavailable"
                requires_strict_verification = bool(
                    item.metadata.get("minimum_backfill")
                    or item.metadata.get("is_fallback")
                    or not self.passes_profile_filter(item)
                )
                has_reliable_fallback = (
                    not requires_strict_verification
                    and item.source_type
                    not in {SourceType.GOOGLE_NEWS, SourceType.GDELT}
                    and len((item.content or "").strip()) >= 160
                )
                return item, has_reliable_fallback

            outcomes = await asyncio.gather(*(hydrate(item) for item in items))

        kept = [item for item, usable in outcomes if usable]
        removed = len(items) - len(kept)
        if removed:
            self.console.print(
                f"[yellow]{self.icons['warning']} Dropped {removed} final items "
                "without usable original content.[/yellow]\n"
            )
        return kept

    async def _hydrate_and_reanalyze_practice_rescue(
        self,
        items: List[ContentItem],
        missing_categories: set[str],
    ) -> List[ContentItem]:
        """Verify a bounded, category-balanced rescue pool against full text.

        Initial model scoring operates on feed/index excerpts to keep discovery
        affordable.  When those excerpts are insufficient for the evidence hard
        gates, this method fetches complete original content for at most the
        configured full-text reserve and analyzes those same candidates again.
        The source category is only a targeting hint; the second model pass may
        still reject or reclassify the item.
        """
        categories = [
            category
            for category in self.config.digest.practice_targets
            if category in missing_categories and category != "hands-on"
        ]
        if (
            not categories
            or not getattr(self.config.collection, "fetch_fulltext", False)
        ):
            return []

        budget = max(
            len(categories),
            int(self.config.digest.fulltext_reserve or 0),
        )
        budget = min(budget, len(items))
        if budget <= 0:
            return []

        def rescue_priority(
            item: ContentItem,
            category: str,
        ) -> tuple[int, int, int, int, float, float]:
            analysis = item.processing.analysis if item.processing else None
            return (
                0 if analysis and analysis.practice_category == category else 1,
                0 if analysis and analysis.category_requirements_met is True else 1,
                0 if analysis and analysis.evidence_complete is True else 1,
                0 if self.passes_profile_filter(item) else 1,
                -self._analysis_score(item),
                -item.published_at.timestamp(),
            )

        pools: Dict[str, List[ContentItem]] = {}
        for category in categories:
            matching = [
                item
                for item in items
                if (
                    self._source_practice_category(item) == category
                    or (
                        item.processing
                        and item.processing.analysis
                        and item.processing.analysis.practice_category == category
                    )
                )
                and item.processing
                and item.processing.analysis
                and item.processing.analysis.score is not None
            ]
            matching.sort(key=lambda item: rescue_priority(item, category))
            pools[category] = matching

        rescue_items: List[ContentItem] = []
        rescue_ids: set[str] = set()
        while len(rescue_items) < budget:
            added = False
            for category in categories:
                pool = pools[category]
                while pool and pool[0].id in rescue_ids:
                    pool.pop(0)
                if not pool:
                    continue
                item = pool.pop(0)
                item.metadata["verification_target_practice_category"] = category
                # Force original-source success in hydrate_selected_items even
                # when this is a fresh item with an otherwise high model score.
                item.metadata["minimum_backfill"] = True
                rescue_items.append(item)
                rescue_ids.add(item.id)
                added = True
                if len(rescue_items) >= budget:
                    break
            if not added:
                break

        if not rescue_items:
            return []

        self.console.print(
            f"{self.icons['fetch']} Fetching original content for "
            f"{len(rescue_items)} evidence-verification candidates across "
            f"{len(categories)} missing columns\n"
        )
        hydrated = await self.hydrate_selected_items(rescue_items)
        if not hydrated:
            return []

        verified = await self.analyze_items(hydrated)
        for item in verified:
            item.metadata["fulltext_reanalyzed"] = True
        passed = sum(self._passes_practice_hard_gates(item) for item in verified)
        self.console.print(
            f"{self.icons['ai']} Full-text verification passed "
            f"{passed}/{len(verified)} candidates\n"
        )
        return verified

    def _annotate_digest_depth(self, items: List[ContentItem]) -> None:
        for rank, item in enumerate(items, start=1):
            item.metadata["digest_rank"] = rank
            if rank <= self.config.digest.deep_items:
                item.metadata["summary_depth"] = "deep"
                item.metadata["summary_length_zh"] = "300-500字"
            else:
                item.metadata["summary_depth"] = "brief"
                item.metadata["summary_length_zh"] = "100-180字"

    def _write_run_metrics(
        self,
        *,
        date: str,
        fetched_count: int,
        merged_count: int,
        history_removed: int,
        candidate_count: int,
        analyzed_count: int,
        analyzed_items: List[ContentItem],
        threshold_count: int,
        selected_items: List[ContentItem],
        usage,
        dry_run: bool,
        fetched_items: Optional[List[ContentItem]] = None,
    ) -> None:
        """Write public run metrics without URLs, content, or secret values."""
        if not self.config.metrics.enabled:
            return

        profile_counts: Dict[str, int] = defaultdict(int)
        region_counts: Dict[str, int] = defaultdict(int)
        practice_counts: Dict[str, int] = defaultdict(int)
        for item in selected_items:
            profile = (
                item.processing.classification.profile
                if item.processing
                else "unclassified"
            )
            profile_counts[profile] += 1
            region_counts[str(item.metadata.get("region") or "global")] += 1
            practice_counts[
                str(item.metadata.get("practice_category") or "unclassified")
            ] += 1

        score_buckets: Dict[str, int] = defaultdict(int)
        analyzed_practice_counts: Dict[str, int] = defaultdict(int)
        actionable_count = 0
        practice_gate_capped = 0
        numeric_scores: List[float] = []
        for item in analyzed_items:
            analysis = item.processing.analysis if item.processing else None
            score = analysis.score if analysis else None
            if score is None:
                score_buckets["missing"] += 1
                continue
            numeric_scores.append(score)
            lower = int(score)
            bucket = "10" if lower >= 10 else f"{lower}-{lower + 0.9:.1f}"
            score_buckets[bucket] += 1
            practice = (
                analysis.practice_category
                or item.metadata.get("practice_category")
                or "unclassified"
            )
            analyzed_practice_counts[str(practice)] += 1
            if analysis.actionable_within_7_days:
                actionable_count += 1
            if "score capped at 5.9" in analysis.reason:
                practice_gate_capped += 1

        input_rate = self.config.metrics.input_cost_per_million_usd
        output_rate = self.config.metrics.output_cost_per_million_usd
        estimated_cost = None
        if input_rate is not None and output_rate is not None:
            estimated_cost = round(
                usage.total_input_tokens / 1_000_000 * input_rate
                + usage.total_output_tokens / 1_000_000 * output_rate,
                6,
            )

        source_metrics = []
        if self.last_fetch_report:
            source_metrics = [
                {
                    "source": outcome.source_name,
                    "status": outcome.status,
                    "item_count": len(outcome.items),
                }
                for outcome in self.last_fetch_report.outcomes
            ]

        category_metrics: Dict[str, Dict[str, object]] = {}
        ordered_categories = list(self.config.digest.practice_targets)
        fetched_category_counts: Dict[str, int] = defaultdict(int)
        for item in fetched_items or []:
            source_category = self._source_practice_category(item)
            if source_category:
                fetched_category_counts[source_category] += 1
        scored_category_counts: Dict[str, int] = defaultdict(int)
        qualified_category_counts: Dict[str, int] = defaultdict(int)
        for item in analyzed_items:
            analysis = item.processing.analysis if item.processing else None
            category = str(
                (analysis.practice_category if analysis else None)
                or item.metadata.get("practice_category")
                or "unclassified"
            )
            if analysis and analysis.score is not None:
                scored_category_counts[category] += 1
            if self._passes_practice_hard_gates(item) and self.passes_profile_filter(item):
                qualified_category_counts[category] += 1
        selected_category_counts: Dict[str, int] = defaultdict(int)
        selected_fallback_counts: Dict[str, int] = defaultdict(int)
        for item in selected_items:
            category = str(item.metadata.get("practice_category") or "unclassified")
            selected_category_counts[category] += 1
            if item.metadata.get("is_fallback"):
                selected_fallback_counts[category] += 1
        for category in ordered_categories:
            target = self.config.digest.practice_targets.get(category, 0)
            minimum = self.config.digest.practice_minimums.get(category, 0)
            final_count = selected_category_counts.get(category, 0)
            if final_count < minimum:
                gap_reason = "minimum not met; delivery should have been aborted"
            elif final_count < target:
                gap_reason = "quality supply below target; minimum satisfied"
            else:
                gap_reason = ""
            category_metrics[category] = {
                "fetched": fetched_category_counts.get(category, 0),
                "scored": scored_category_counts.get(category, 0),
                "qualified_at_threshold": qualified_category_counts.get(category, 0),
                "final": final_count,
                "fallback": selected_fallback_counts.get(category, 0),
                "minimum": minimum,
                "target": target,
                "shortfall_reason": gap_reason,
            }
        ranked_selected_count = sum(
            not item.metadata.get("generated_hands_on") for item in selected_items
        )

        payload = {
            "date": date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "pipeline": {
                "fetched": fetched_count,
                "url_duplicates_removed": fetched_count - merged_count,
                "history_duplicates_removed": history_removed,
                "model_candidates": candidate_count,
                "model_scored": analyzed_count,
                "above_threshold": threshold_count,
                "selected": len(selected_items),
            },
            "selection": {
                "profiles": dict(profile_counts),
                "regions": dict(region_counts),
                "practice_categories": dict(practice_counts),
                "deep_items": min(
                    ranked_selected_count, self.config.digest.deep_items
                ),
                "brief_items": max(
                    0, ranked_selected_count - self.config.digest.deep_items
                ),
                "generated_hands_on_cards": sum(
                    bool(item.metadata.get("generated_hands_on"))
                    for item in selected_items
                ),
                "practice_diagnostics": category_metrics,
            },
            "analysis": {
                "numeric_scores": len(numeric_scores),
                "score_buckets": dict(sorted(score_buckets.items())),
                "top_scores": sorted(numeric_scores, reverse=True)[:10],
                "actionable_within_7_days": actionable_count,
                "practice_gate_capped": practice_gate_capped,
                "actionability_gate_enabled": any(
                    settings.require_actionable_within_7_days
                    for settings in self.config.processing.profile_settings.values()
                ),
                "practice_categories": dict(analyzed_practice_counts),
            },
            "sources": source_metrics,
            "model": {
                "provider": self.config.ai.provider.value,
                "model": self.config.ai.model,
                "input_tokens": usage.total_input_tokens,
                "output_tokens": usage.total_output_tokens,
                "total_tokens": usage.total_tokens,
                "estimated_cost_usd": estimated_cost,
                "pricing_configured": estimated_cost is not None,
                "pricing_note": self.config.metrics.pricing_note,
            },
        }

        if dry_run:
            ranked_diagnostics = sorted(
                analyzed_items,
                key=lambda candidate: (
                    -(
                        candidate.processing.analysis.score
                        if candidate.processing
                        and candidate.processing.analysis
                        and candidate.processing.analysis.score is not None
                        else -1
                    ),
                    -int(candidate.metadata.get("prefilter_practical_score") or 0),
                ),
            )[:20]
            payload["analysis"]["top_candidates"] = [
                {
                    "title": candidate.title[:200],
                    "source": self._candidate_source_key(candidate)[:160],
                    "practice_category": str(
                        (
                            candidate.processing.analysis.practice_category
                            if candidate.processing and candidate.processing.analysis
                            else None
                        )
                        or candidate.metadata.get("practice_category")
                        or "unclassified"
                    ),
                    "source_practice_category": str(
                        candidate.metadata.get("source_practice_category")
                        or "unclassified"
                    ),
                    "model_practice_category": str(
                        candidate.metadata.get("model_practice_category")
                        or "unclassified"
                    ),
                    "freshness": str(
                        candidate.metadata.get("freshness_bucket") or "unknown"
                    ),
                    "prefilter_score": int(
                        candidate.metadata.get("prefilter_practical_score") or 0
                    ),
                    "model_score": (
                        candidate.processing.analysis.score
                        if candidate.processing and candidate.processing.analysis
                        else None
                    ),
                    "actionable_within_7_days": (
                        candidate.processing.analysis.actionable_within_7_days
                        if candidate.processing and candidate.processing.analysis
                        else None
                    ),
                    "reason": (
                        candidate.processing.analysis.reason[:400]
                        if candidate.processing and candidate.processing.analysis
                        else ""
                    ),
                    "action": (
                        candidate.processing.analysis.action[:400]
                        if candidate.processing
                        and candidate.processing.analysis
                        and candidate.processing.analysis.action
                        else ""
                    ),
                    "project_relevance": (
                        candidate.processing.analysis.project_relevance[:400]
                        if candidate.processing
                        and candidate.processing.analysis
                        and candidate.processing.analysis.project_relevance
                        else ""
                    ),
                }
                for candidate in ranked_diagnostics
            ]

        output_dir = Path(self.config.metrics.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        _atomic_write_text(output_dir / f"{date}.json", serialized)
        _atomic_write_text(output_dir / "latest.json", serialized)

    def _determine_time_window(self, force_hours: int = None) -> datetime:
        if force_hours:
            since = datetime.now(timezone.utc) - timedelta(hours=force_hours)
        else:
            hours = self.config.collection.time_window_hours
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return since

    def _determine_fallback_window(self, force_hours: int = None) -> datetime:
        """Return the oldest allowed fallback time, distinct from the main window."""
        primary_hours = force_hours or self.config.collection.time_window_hours
        configured_hours = (
            self.config.collection.fallback_window_hours
            or primary_hours
        )
        hours = max(configured_hours, primary_hours)
        return datetime.now(timezone.utc) - timedelta(hours=hours)

    @staticmethod
    def _source_practice_category(item: ContentItem) -> Optional[str]:
        value = item.metadata.get("source_practice_category")
        if value is None:
            value = item.metadata.get("practice_category")
        return str(value) if value else None

    def _annotate_candidate_freshness(
        self, items: List[ContentItem], fresh_since: datetime
    ) -> None:
        for item in items:
            item.metadata.setdefault(
                "source_practice_category", item.metadata.get("practice_category")
            )
            is_fallback = item.published_at < fresh_since
            item.metadata["is_fallback"] = is_fallback
            item.metadata["freshness_bucket"] = "fallback" if is_fallback else "fresh"
            item.metadata["freshness_label"] = (
                "近 7 日补充" if is_fallback else "今日新内容"
            )

    def _external_practice_minimums(self) -> Dict[str, int]:
        return {
            category: minimum
            for category, minimum in self.config.digest.practice_minimums.items()
            if minimum > 0
            and not (
                category == "hands-on" and self.config.digest.generated_hands_on
            )
        }

    def _external_item_limit(self) -> int:
        max_items = self.config.digest.max_items
        if max_items is None:
            return 10_000_000
        reserved = 1 if self.config.digest.generated_hands_on else 0
        return max(0, max_items - reserved)

    @staticmethod
    def _analysis_score(item: ContentItem) -> float:
        analysis = item.processing.analysis if item.processing else None
        return analysis.score if analysis and analysis.score is not None else -1.0

    def _assert_external_practice_minimums(
        self, items: List[ContentItem]
    ) -> None:
        counts: Dict[str, int] = defaultdict(int)
        for item in items:
            counts[str(item.metadata.get("practice_category") or "unclassified")] += 1
        missing = [
            f"{category} ({counts.get(category, 0)}/{minimum})"
            for category, minimum in self._external_practice_minimums().items()
            if counts.get(category, 0) < minimum
        ]
        if missing:
            raise RuntimeError(
                "Required practice columns remain empty after the targeted seven-day "
                f"fallback; delivery aborted: {', '.join(missing)}"
            )

    def _assert_complete_practice_digest(self, items: List[ContentItem]) -> None:
        counts: Dict[str, int] = defaultdict(int)
        for item in items:
            counts[str(item.metadata.get("practice_category") or "unclassified")] += 1
        missing = [
            f"{category} ({counts.get(category, 0)}/{minimum})"
            for category, minimum in self.config.digest.practice_minimums.items()
            if minimum > 0 and counts.get(category, 0) < minimum
        ]
        if missing:
            raise RuntimeError(
                "Incomplete six-column digest; delivery aborted: " + ", ".join(missing)
            )
        if self.config.digest.max_items is not None and len(items) > self.config.digest.max_items:
            raise RuntimeError(
                f"Digest contains {len(items)} items, above max_items="
                f"{self.config.digest.max_items}."
            )

    def _build_hands_on_card(
        self, items: List[ContentItem], *, today: str
    ) -> ContentItem:
        """Build one deterministic 15–30 minute ticket-Agent exercise."""
        if not items:
            raise RuntimeError("Cannot generate a hands-on card without a source item.")
        anchor = max(items, key=self._analysis_score)
        category = str(anchor.metadata.get("practice_category") or "method-pitfall")
        templates = {
            "today-use": (
                "用一张脱敏工单验证新能力",
                "一张已脱敏的历史售后工单、当前 Agent 输出、纸或表格",
                "1. 写下当前输出；2. 用资讯中的已开放能力处理同一输入；"
                "3. 对比事实准确、步骤完整和人工接管点；4. 记录一个保留或拒绝理由。",
                "得到一行可复核结论：该能力是否值得进入下一轮原型，以及依据是什么。",
            ),
            "enterprise-case": (
                "拆一张企业案例流程卡",
                "本期案例、售后工单 Agent 的现有流程图或空白纸",
                "1. 标出案例的业务对象；2. 写出实施前后流程；3. 圈出可验证结果；"
                "4. 把其中一个环节映射到工单分流、知识检索或人工升级。",
                "产出一张含对象、流程、结果和可迁移环节的四格案例卡。",
            ),
            "method-pitfall": (
                "把一个方法变成坏案例检查项",
                "本期方法或踩坑资讯、5 条脱敏工单样例或自拟边界样例",
                "1. 提炼一个失败条件；2. 写成可判断的评估规则；3. 检查 5 条样例；"
                "4. 记录误判及需要人工复核的位置。",
                "新增 1 条评估规则、至少 1 个坏案例，并说明通过标准。",
            ),
            "beginner-tech": (
                "写一张技术选型决策卡",
                "本期技术翻译资讯、售后工单 Agent 当前方案",
                "1. 用一句话解释概念；2. 写适用与不适用各一条；3. 选择它影响的"
                "可靠性、成本、时延、隐私或人工复核决策；4. 写下待验证问题。",
                "得到一张可用于 PRD 或面试的“是什么—何时用—如何验证”决策卡。",
            ),
            "china-career": (
                "把行业信号映射到作品集证据",
                "本期中国/求职信号、你的岗位清单或作品集目录",
                "1. 提取一个真实能力要求；2. 找出现有项目中能证明它的材料；"
                "3. 补一句量化或可演示证据；4. 若无证据，登记为下一项作品任务。",
                "完成一条“岗位要求—项目证据—缺口”的三列表记录。",
            ),
        }
        title, input_text, steps, completion = templates.get(
            category, templates["method-pitfall"]
        )
        source = ArtifactSource(id="source-1", title=anchor.title, url=str(anchor.url))
        artifacts: Dict[str, ContentArtifact] = {}
        for language in self.config.ai.languages:
            artifacts[language] = ContentArtifact(
                language=language,
                title=f"今天动手做｜{title}",
                sources=[source],
                blocks=[
                    ContentBlock(
                        id="summary",
                        title="15–30 分钟行动卡",
                        content=f"基于本期《{anchor.title}》生成，不要求额外寻找教程。",
                        source_refs=["source-1"],
                        primary=True,
                    ),
                    ContentBlock(id="time", title="时间", content="15–30 分钟"),
                    ContentBlock(id="input", title="输入", content=input_text),
                    ContentBlock(id="steps", title="步骤", content=steps),
                    ContentBlock(
                        id="completion", title="完成标准", content=completion
                    ),
                    ContentBlock(
                        id="project_mapping",
                        title="映射到售后工单 Agent",
                        content="把产出保存到项目的评估集、PRD 决策记录或作品集证据中。",
                    ),
                ],
            )
        now = datetime.now(timezone.utc)
        return ContentItem(
            id=f"generated:hands-on:{today}",
            source_type=anchor.source_type,
            title=f"今天动手做｜{title}",
            url=anchor.url,
            content=f"基于本期资讯生成的 15–30 分钟售后工单 Agent 行动卡：{steps}",
            author="AI FDE Radar",
            published_at=now,
            fetched_at=now,
            metadata={
                "practice_category": "hands-on",
                "source_practice_category": "hands-on",
                "model_practice_category": "hands-on",
                "generated_hands_on": True,
                "freshness_bucket": "generated",
                "freshness_label": "今日生成",
                "summary_depth": "action",
                "based_on_item_id": anchor.id,
            },
            profile="ai-product-fde",
            processing=ProcessingResult(
                classification=ClassificationResult(
                    profile="ai-product-fde", method="source_override"
                ),
                analysis=ContentAnalysis(
                    score=None,
                    reason="Generated from the selected digest; excluded from ranking.",
                    summary=completion,
                    tags=["ticket-agent", "hands-on"],
                    practice_category="hands-on",
                    actionable_within_7_days=True,
                    action=steps,
                    project_relevance="售后工单 Agent 的评估、PRD 或作品集证据",
                    evidence_complete=True,
                    category_requirements_met=True,
                    evidence_note="Editorial exercise derived from one selected source.",
                ),
                artifacts=artifacts,
            ),
        )

    @staticmethod
    def ensure_analysis_health(
        analyzed_items: List[ContentItem],
        min_success_ratio: float = 0.8,
    ) -> None:
        """Abort delivery when model scoring failed for too many candidates."""
        if not analyzed_items:
            return
        valid_scores = sum(
            1
            for item in analyzed_items
            if item.processing
            and item.processing.analysis
            and item.processing.analysis.score is not None
        )
        required = max(1, math.ceil(len(analyzed_items) * min_success_ratio))
        if valid_scores < required:
            raise RuntimeError(
                "AI analysis health check failed: "
                f"{valid_scores}/{len(analyzed_items)} candidates received valid scores; "
                f"at least {required} are required. Delivery aborted."
            )

    async def fetch_all_sources(self, since: datetime) -> List[ContentItem]:
        """Fetch content from all configured sources.

        This is a stable stage entry point for integrations such as MCP.

        Args:
            since: Fetch items published after this time

        Returns:
            List[ContentItem]: All fetched items
        """
        self.last_fetch_report = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []

            # GitHub sources
            if self.config.sources.github:
                github_scraper = GitHubScraper(self.config.sources.github, client)
                tasks.append(self._fetch_with_progress("GitHub", github_scraper, since))

            # Hacker News
            if self.config.sources.hackernews.enabled:
                hn_scraper = HackerNewsScraper(self.config.sources.hackernews, client)
                tasks.append(self._fetch_with_progress("Hacker News", hn_scraper, since))

            # RSS feeds
            if self.config.sources.rss:
                from .extractors import ExtractorRegistry
                rss_scraper = RSSScraper(
                    self.config.sources.rss,
                    client,
                    ExtractorRegistry(self.config.extractors),
                )
                tasks.append(self._fetch_with_progress("RSS Feeds", rss_scraper, since))

            # Reddit
            if self.config.sources.reddit.enabled:
                reddit_scraper = RedditScraper(self.config.sources.reddit, client)
                tasks.append(self._fetch_with_progress("Reddit", reddit_scraper, since))

            # Telegram
            if self.config.sources.telegram.enabled:
                telegram_scraper = TelegramScraper(self.config.sources.telegram, client)
                tasks.append(self._fetch_with_progress("Telegram", telegram_scraper, since))

            # Twitter (Apify or Playwright mode)
            if self.config.sources.twitter and self.config.sources.twitter.enabled:
                tw_cfg = self.config.sources.twitter
                if tw_cfg.mode == "playwright":
                    twitter_scraper = TwitterPlaywrightScraper(tw_cfg)
                else:
                    twitter_scraper = TwitterScraper(tw_cfg, client)
                tasks.append(self._fetch_with_progress("Twitter", twitter_scraper, since))

            # OpenBB (financial news / filings via the OpenBB Platform SDK)
            if self.config.sources.openbb and self.config.sources.openbb.enabled:
                openbb_scraper = OpenBBScraper(self.config.sources.openbb, client)
                tasks.append(self._fetch_with_progress("OpenBB", openbb_scraper, since))

            # OSS Insight trending repos
            if self.config.sources.ossinsight and self.config.sources.ossinsight.enabled:
                oss_scraper = OSSInsightScraper(self.config.sources.ossinsight, client)
                tasks.append(self._fetch_with_progress("OSS Insight", oss_scraper, since))

            # GDELT 2.0 DOC API (key-less global news)
            if self.config.sources.gdelt and self.config.sources.gdelt.enabled:
                gdelt_scraper = GDELTScraper(self.config.sources.gdelt, client)
                tasks.append(self._fetch_with_progress("GDELT", gdelt_scraper, since))

            # Google News RSS (key-less news search). A single legacy object and
            # the newer multi-query array are both normalized by SourcesConfig.
            google_news_resolution_semaphore = asyncio.Semaphore(6)
            google_news_queries = getattr(
                self.config.sources, "google_news_queries", None
            )
            if callable(google_news_queries):
                normalized_google_news = google_news_queries()
            else:
                legacy_google_news = getattr(
                    self.config.sources, "google_news", None
                )
                normalized_google_news = (
                    legacy_google_news
                    if isinstance(legacy_google_news, list)
                    else [legacy_google_news] if legacy_google_news else []
                )
            for index, gn_config in enumerate(normalized_google_news, start=1):
                if not gn_config.enabled:
                    continue
                gn_scraper = GoogleNewsScraper(
                    gn_config,
                    client,
                    google_news_resolution_semaphore,
                )
                tasks.append(
                    self._fetch_with_progress(
                        f"Google News [{index}: {gn_config.query[:36]}]",
                        gn_scraper,
                        since,
                    )
                )

            # Hugging Face Daily Papers (public, no API key).
            hf_papers_config = getattr(self.config.sources, "hf_papers", None)
            if hf_papers_config and hf_papers_config.enabled:
                hf_papers_scraper = HuggingFacePapersScraper(
                    hf_papers_config, client
                )
                tasks.append(
                    self._fetch_with_progress(
                        "Hugging Face Daily Papers", hf_papers_scraper, since
                    )
                )

            # Fetch all concurrently
            outcomes = await asyncio.gather(*tasks)
            self.last_fetch_report = FetchReport(outcomes=list(outcomes))

            # Flatten successful and empty outcomes; failures remain in the report.
            all_items: List[ContentItem] = []
            for outcome in outcomes:
                all_items.extend(outcome.items)

            return all_items

    async def fetch_targeted_sources(
        self,
        since: datetime,
        practice_categories: set[str],
    ) -> List[ContentItem]:
        """Refetch only sources assigned to under-supplied practice pillars."""
        self.last_fetch_report = None

        def wanted(config) -> bool:
            return bool(
                getattr(config, "enabled", True)
                and getattr(config, "practice_category", None)
                in practice_categories
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []
            github_sources = [source for source in self.config.sources.github if wanted(source)]
            if github_sources:
                tasks.append(
                    self._fetch_with_progress(
                        "Fallback GitHub", GitHubScraper(github_sources, client), since
                    )
                )

            if wanted(self.config.sources.hackernews):
                tasks.append(
                    self._fetch_with_progress(
                        "Fallback Hacker News",
                        HackerNewsScraper(self.config.sources.hackernews, client),
                        since,
                    )
                )

            rss_sources = [source for source in self.config.sources.rss if wanted(source)]
            if rss_sources:
                from .extractors import ExtractorRegistry

                tasks.append(
                    self._fetch_with_progress(
                        "Fallback RSS Feeds",
                        RSSScraper(
                            rss_sources,
                            client,
                            ExtractorRegistry(self.config.extractors),
                        ),
                        since,
                    )
                )

            reddit_config = self.config.sources.reddit
            if reddit_config.enabled:
                targeted_reddit = reddit_config.model_copy(
                    update={
                        "subreddits": [
                            source for source in reddit_config.subreddits if wanted(source)
                        ],
                        "users": [source for source in reddit_config.users if wanted(source)],
                    }
                )
                if targeted_reddit.subreddits or targeted_reddit.users:
                    tasks.append(
                        self._fetch_with_progress(
                            "Fallback Reddit",
                            RedditScraper(targeted_reddit, client),
                            since,
                        )
                    )

            oss_config = self.config.sources.ossinsight
            if wanted(oss_config):
                tasks.append(
                    self._fetch_with_progress(
                        "Fallback OSS Insight", OSSInsightScraper(oss_config, client), since
                    )
                )

            gdelt_config = self.config.sources.gdelt
            if gdelt_config and wanted(gdelt_config):
                fallback_hours = max(
                    1,
                    math.ceil(
                        (datetime.now(timezone.utc) - since).total_seconds() / 3600
                    ),
                )
                targeted_gdelt = gdelt_config.model_copy(
                    update={"timespan": f"{fallback_hours}h"}
                )
                tasks.append(
                    self._fetch_with_progress(
                        "Fallback GDELT", GDELTScraper(targeted_gdelt, client), since
                    )
                )

            google_news_queries = self.config.sources.google_news_queries()
            google_news_resolution_semaphore = asyncio.Semaphore(6)
            for index, gn_config in enumerate(google_news_queries, start=1):
                if not wanted(gn_config):
                    continue
                tasks.append(
                    self._fetch_with_progress(
                        f"Fallback Google News [{index}: {gn_config.query[:36]}]",
                        GoogleNewsScraper(
                            gn_config,
                            client,
                            google_news_resolution_semaphore,
                        ),
                        since,
                    )
                )

            hf_config = self.config.sources.hf_papers
            if wanted(hf_config):
                tasks.append(
                    self._fetch_with_progress(
                        "Fallback Hugging Face Daily Papers",
                        HuggingFacePapersScraper(hf_config, client),
                        since,
                    )
                )

            outcomes = await asyncio.gather(*tasks) if tasks else []
            self.last_fetch_report = FetchReport(outcomes=list(outcomes))
            return [item for outcome in outcomes for item in outcome.items]

    async def _fetch_with_progress(
        self, name: str, scraper, since: datetime
    ) -> SourceFetchOutcome:
        """Fetch from a scraper with progress indication.

        Args:
            name: Source name for display
            scraper: Scraper instance
            since: Fetch items after this time

        Returns:
            SourceFetchOutcome: Named fetch result and diagnostics
        """
        self.console.print(f"{self.icons['fetch']} Fetching from {name}...")
        try:
            items = await scraper.fetch(since)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.console.print(f"[red]   Failed to fetch {name}: {error}[/red]")
            return SourceFetchOutcome(
                source_name=name,
                status="failure",
                error=error,
            )

        self.console.print(f"   Found {len(items)} items from {name}")

        # Show per-sub-source breakdown when there are multiple sub-sources
        sub_counts: Dict[str, int] = defaultdict(int)
        for item in items:
            sub_counts[self._sub_source_label(item)] += 1
        if len(sub_counts) > 1:
            for sub, count in sorted(sub_counts.items()):
                self.console.print(f"      {self.icons['detail']} {sub}: {count}")

        return SourceFetchOutcome(
            source_name=name,
            status="success" if items else "empty",
            items=items,
        )

    @staticmethod
    def _sub_source_label(item: ContentItem) -> str:
        """Return a human-readable sub-source label for an item."""
        meta = item.metadata
        if meta.get("subreddit"):
            return f"r/{meta['subreddit']}"
        if meta.get("feed_name"):
            return meta["feed_name"]
        if meta.get("channel"):
            return f"@{meta['channel']}"
        if meta.get("period") and meta.get("repo"):
            return f"ossinsight:{meta.get('primary_language', 'all')}"
        if meta.get("repo"):
            return meta["repo"]
        if meta.get("watchlist"):
            return meta["watchlist"]
        if meta.get("source_name"):
            return meta["source_name"]
        if meta.get("gn_query"):
            return f"google_news:{meta['gn_query']}"
        if meta.get("domain"):
            return meta["domain"]
        return item.author or "unknown"

    def merge_cross_source_duplicates(self, items: List[ContentItem]) -> List[ContentItem]:
        """Merge items that point to the same URL from different sources.

        This is a stable stage helper for integrations such as MCP.

        Keeps the item with the richest content and combines metadata.

        Args:
            items: Items to deduplicate

        Returns:
            List[ContentItem]: Deduplicated items
        """
        # Group by normalized URL
        url_groups: Dict[tuple[object, ...], List[ContentItem]] = {}
        for item in items:
            if isinstance(item.profile, list):
                requested_profile: object = tuple(
                    profile_id.strip() for profile_id in item.profile
                )
            else:
                requested_profile = (item.profile or "auto").strip() or "auto"
            key = (*_deduplication_url_key(str(item.url)), requested_profile)
            url_groups.setdefault(key, []).append(item)

        merged = []
        for group in url_groups.values():
            group_copies = [item.model_copy(deep=True) for item in group]
            if len(group) == 1:
                merged.append(group_copies[0])
                continue

            # Pick the item with the richest content as primary
            primary = max(group_copies, key=lambda x: len(x.content or ""))

            # Merge metadata and source info from other items
            all_sources = []
            for item in group_copies:
                if item.source_type.value not in all_sources:
                    all_sources.append(item.source_type.value)
                # Merge metadata (engagement, discussion, etc.)
                for mk, mv in item.metadata.items():
                    if mk not in primary.metadata or not primary.metadata[mk]:
                        primary.metadata[mk] = mv

                # Append content (e.g., comments from another source)
                if item is not primary and item.content:
                    if primary.content and item.content not in primary.content:
                        primary.content = (primary.content or "") + f"\n\n--- From {item.source_type.value} ---\n" + item.content

            primary.metadata["merged_sources"] = all_sources
            merged.append(primary)

        return merged

    async def merge_topic_duplicates(
        self,
        items: List[ContentItem],
        *,
        log: bool = True,
    ) -> List[ContentItem]:
        """Merge items covering the same topic using AI semantic deduplication.

        This is a stable stage helper for integrations such as MCP.

        Sends all item titles, tags, and summaries to AI in a single call.
        Items must already be sorted by analysis score descending so that the first
        item in each duplicate group is always the highest-scored one.
        Content (comments) from duplicate items is merged into the primary.

        Falls back to returning items unchanged if the AI call fails.
        """
        if len(items) <= 1:
            return items

        from .ai.prompting.deduplication import TOPIC_DEDUP_SYSTEM, TOPIC_DEDUP_USER
        from .ai.utils import parse_json_response

        # Build the item list for the prompt
        lines = []
        for i, item in enumerate(items):
            analysis = item.processing.analysis if item.processing else None
            tags = ", ".join(analysis.tags) if analysis and analysis.tags else "—"
            summary = analysis.summary if analysis else "—"
            lines.append(f"[{i}] {item.title}\n    Tags: {tags}\n    Summary: {summary}")
        items_text = "\n\n".join(lines)

        try:
            ai_client = create_ai_client(self.config.ai)
            response = await ai_client.complete(
                system=TOPIC_DEDUP_SYSTEM,
                user=TOPIC_DEDUP_USER.format(items=items_text),
            )
            result = parse_json_response(response)
            if result is None:
                if log:
                    self.console.print("[yellow]  dedup: could not parse AI response, skipping[/yellow]")
                return items

            duplicate_groups = result.get("duplicates", [])
        except Exception as e:
            if log:
                self.console.print(f"[yellow]  dedup: AI call failed ({e}), skipping[/yellow]")
            return items

        if not duplicate_groups:
            return items

        # Build a set of indices to drop (all non-primary duplicates)
        drop_indices: set[int] = set()
        for group in duplicate_groups:
            if not isinstance(group, list) or len(group) < 2:
                continue
            primary_idx = group[0]
            if primary_idx < 0 or primary_idx >= len(items):
                continue
            primary = items[primary_idx]
            for dup_idx in group[1:]:
                if not isinstance(dup_idx, int) or dup_idx < 0 or dup_idx >= len(items):
                    continue
                if dup_idx == primary_idx:
                    continue
                dup = items[dup_idx]
                # Merge comments/content from the duplicate into the primary
                if dup.content:
                    if not primary.content or dup.content not in primary.content:
                        label = dup.source_type.value
                        primary.content = (primary.content or "") + f"\n\n--- From {label} ---\n{dup.content}"
                if log:
                    self.console.print(
                        f"   [dim]dedup: keep [{primary_idx}] {primary.title}[/dim]\n"
                        f"   [dim]       drop [{dup_idx}] {dup.title}[/dim]"
                    )
                drop_indices.add(dup_idx)

        return [item for i, item in enumerate(items) if i not in drop_indices]

    async def filter_items(
        self,
        items: List[ContentItem],
        *,
        threshold: Optional[float] = None,
        topic_dedup: bool = True,
        apply_balance: bool = True,
        log: bool = True,
    ) -> FilteringPipelineResult:
        """Apply score thresholding, optional topic dedup, and digest balancing."""
        threshold_items = []
        for item in items:
            if self.passes_profile_filter(item, threshold):
                threshold_items.append(item)
        threshold_items.sort(
            key=lambda item: (
                item.processing.analysis.score
                if item.processing and item.processing.analysis and item.processing.analysis.score is not None
                else -1
            ),
            reverse=True,
        )

        if log:
            self.console.print(
                f"{self.icons['filter']} Selected {len(threshold_items)} items "
                "with profile filters\n"
            )

        deduped_items = threshold_items
        if topic_dedup and deduped_items:
            profile_groups: Dict[str, List[ContentItem]] = defaultdict(list)
            for item in deduped_items:
                profile_id = (
                    item.processing.classification.profile
                    if item.processing
                    else self.profiles.default_profile
                )
                profile_groups[profile_id].append(item)
            deduped_items = []
            for profile_id, profile_items in profile_groups.items():
                settings = self.config.processing.profile_settings.get(profile_id)
                if settings is None or settings.topic_dedup:
                    deduped_items.extend(
                        await self.merge_topic_duplicates(profile_items, log=log)
                    )
                else:
                    deduped_items.extend(profile_items)
            deduped_items.sort(
                key=lambda item: (
                    item.processing.analysis.score
                    if item.processing
                    and item.processing.analysis
                    and item.processing.analysis.score is not None
                    else -1
                ),
                reverse=True,
            )
        topic_dedup_removed = len(threshold_items) - len(deduped_items)

        if log and topic_dedup_removed:
            self.console.print(
                f"{self.icons['cleanup']} Removed {topic_dedup_removed} topic duplicates "
                f"→ {len(deduped_items)} unique items\n"
            )

        balanced_digest = (
            self.apply_balanced_digest(deduped_items, log=log)
            if apply_balance
            else BalancedDigestResult(items=deduped_items)
        )
        return FilteringPipelineResult(
            items=balanced_digest.items,
            threshold_count=len(threshold_items),
            topic_dedup_count=len(deduped_items),
            topic_dedup_removed=topic_dedup_removed,
            balanced_digest=balanced_digest,
        )

    async def select_digest_items(
        self,
        items: List[ContentItem],
        *,
        threshold: Optional[float] = None,
        topic_dedup: bool = True,
        log: bool = True,
    ) -> FilteringPipelineResult:
        """Select final digest items using the same stages for every entry point."""
        if self.config.digest.practice_minimums:
            gated_items = [
                item for item in items if self._passes_practice_hard_gates(item)
            ]
            initial = await self.filter_items(
                gated_items,
                threshold=0,
                topic_dedup=topic_dedup,
                apply_balance=False,
                log=False,
            )
            candidates = initial.items
            await self._expand_twitter_discussion(candidates)
            candidates = [
                item for item in candidates if self._passes_practice_hard_gates(item)
            ]
            threshold_count = sum(
                self.passes_profile_filter(item, threshold) for item in candidates
            )
            balanced = self.apply_balanced_digest(candidates, log=log)
            reserve_items = self._build_practice_reserve(
                candidates, balanced.items, self.config.digest.fulltext_reserve
            )
            return FilteringPipelineResult(
                items=balanced.items,
                threshold_count=threshold_count,
                topic_dedup_count=len(candidates),
                topic_dedup_removed=len(gated_items) - len(candidates),
                balanced_digest=balanced,
                eligible_count=len(candidates),
                reserve_items=reserve_items,
            )

        initial = await self.filter_items(
            items,
            threshold=threshold,
            topic_dedup=topic_dedup,
            apply_balance=False,
            log=log,
        )
        candidates = initial.items
        await self._expand_twitter_discussion(candidates)

        # Targeted re-analysis can lower a score, so reapply profile filters.
        eligible = [
            item
            for item in candidates
            if self.passes_profile_filter(item, threshold)
        ]
        eligible.sort(
            key=lambda item: (
                item.processing.analysis.score
                if item.processing
                and item.processing.analysis
                and item.processing.analysis.score is not None
                else -1
            ),
            reverse=True,
        )
        balanced = self.apply_balanced_digest(eligible, log=log)
        selected_ids = {item.id for item in balanced.items}
        reserve_items = [
            item for item in eligible if item.id not in selected_ids
        ][: self.config.digest.fulltext_reserve]
        return FilteringPipelineResult(
            items=balanced.items,
            threshold_count=initial.threshold_count,
            topic_dedup_count=initial.topic_dedup_count,
            topic_dedup_removed=initial.topic_dedup_removed,
            balanced_digest=balanced,
            eligible_count=len(eligible),
            reserve_items=reserve_items,
        )

    def _passes_practice_hard_gates(self, item: ContentItem) -> bool:
        analysis = item.processing.analysis if item.processing else None
        if not analysis or analysis.score is None or not analysis.practice_category:
            return False
        profile_id = item.processing.classification.profile
        settings = self.config.processing.profile_settings.get(profile_id)
        uses_evidence_contract = bool(
            settings and not settings.require_actionable_within_7_days
        )
        if uses_evidence_contract and (
            analysis.evidence_complete is not True
            or analysis.category_requirements_met is not True
        ):
            return False
        if analysis.practice_category == "hands-on" and self.config.digest.generated_hands_on:
            return False
        return True

    def _build_practice_reserve(
        self,
        candidates: List[ContentItem],
        selected: List[ContentItem],
        limit: int,
    ) -> List[ContentItem]:
        if limit <= 0:
            return []
        selected_ids = {item.id for item in selected}
        remaining = [item for item in candidates if item.id not in selected_ids]
        remaining.sort(key=self._minimum_candidate_priority)
        reserve: List[ContentItem] = []
        reserve_ids: set[str] = set()
        for category in self._external_practice_minimums():
            for item in remaining:
                if item.id in reserve_ids:
                    continue
                if item.metadata.get("practice_category") == category:
                    reserve.append(item)
                    reserve_ids.add(item.id)
                    break
            if len(reserve) >= limit:
                return reserve
        for item in remaining:
            if len(reserve) >= limit:
                break
            if item.id not in reserve_ids:
                reserve.append(item)
                reserve_ids.add(item.id)
        return reserve

    def passes_profile_filter(
        self,
        item: ContentItem,
        threshold: Optional[float] = None,
    ) -> bool:
        if not item.processing or not item.processing.analysis:
            return False
        profile_id = item.processing.classification.profile
        settings = self.config.processing.profile_settings.get(profile_id)
        effective_threshold = threshold
        if effective_threshold is None and settings is not None:
            effective_threshold = settings.threshold
        if effective_threshold is None:
            return True
        score = item.processing.analysis.score
        return score is not None and score >= effective_threshold

    def apply_balanced_digest(
        self,
        items: List[ContentItem],
        *,
        log: bool = True,
    ) -> BalancedDigestResult:
        """Apply configured category quotas and the final item cap.

        Categories are read from ``item.metadata["category"]``. If a category
        appears in more than one configured group, the first group in config
        order wins.
        """
        digest = self.config.digest
        groups = digest.category_groups
        max_items = digest.max_items

        if (
            digest.practice_targets
            or digest.matrix_targets
            or digest.profile_targets
            or digest.region_targets
        ):
            return self._apply_targeted_digest(items, log=log)

        if not groups and max_items is None:
            return BalancedDigestResult(items=items)

        sorted_items = sorted(
            items,
            key=lambda item: (
                item.processing.analysis.score
                if item.processing and item.processing.analysis and item.processing.analysis.score is not None
                else -1
            ),
            reverse=True,
        )

        category_to_group: Dict[str, str] = {}
        duplicate_categories: List[str] = []
        for group_key, group in groups.items():
            for category in group.categories:
                if category in category_to_group:
                    if category_to_group[category] != group_key:
                        duplicate_categories.append(category)
                    continue
                category_to_group[category] = group_key

        if log:
            for category in sorted(set(duplicate_categories)):
                first_group = category_to_group[category]
                self.console.print(
                    f"[yellow]Warning: category '{category}' is configured in multiple "
                    f"groups; using '{first_group}'.[/yellow]"
                )

        selected: List[tuple[ContentItem, str]] = []
        group_counts: Dict[str, int] = defaultdict(int)
        default_group = digest.default_group

        for item in sorted_items:
            category = item.metadata.get("category")
            group_key = (
                category_to_group.get(category, default_group)
                if isinstance(category, str)
                else default_group
            )

            if group_key in groups:
                limit = groups[group_key].limit
            else:
                limit = digest.default_group_limit

            if limit is not None and group_counts[group_key] >= limit:
                continue

            selected.append((item, group_key))
            group_counts[group_key] += 1

        if max_items is not None:
            selected = selected[:max_items]

        final_counts: Dict[str, int] = defaultdict(int)
        for _, group_key in selected:
            final_counts[group_key] += 1

        group_limits: Dict[str, Optional[int]] = {
            group_key: group.limit for group_key, group in groups.items()
        }
        group_limits.setdefault(default_group, digest.default_group_limit)

        if log:
            self.console.print(
                f"{self.icons['balance']} Balanced digest selected "
                f"{len(selected)}/{len(items)} items"
            )
            for group_key, group in groups.items():
                label = group.name or group_key
                self.console.print(
                    f"      {self.icons['detail']} {label}: "
                    f"{final_counts.get(group_key, 0)}/{group.limit}"
                )
            if (
                final_counts.get(default_group, 0)
                or digest.default_group_limit is not None
            ):
                limit_label = (
                    str(digest.default_group_limit)
                    if digest.default_group_limit is not None
                    else "unlimited"
                )
                self.console.print(
                    f"      {self.icons['detail']} {default_group}: "
                    f"{final_counts.get(default_group, 0)}/{limit_label}"
                )
            self.console.print("")

        return BalancedDigestResult(
            items=[item for item, _ in selected],
            enabled=True,
            group_counts=dict(final_counts),
            group_limits=group_limits,
            duplicate_categories=sorted(set(duplicate_categories)),
        )

    def _apply_targeted_digest(
        self,
        items: List[ContentItem],
        *,
        log: bool = True,
    ) -> BalancedDigestResult:
        """Fill practice or legacy targets, then backfill with quality items.

        Practice-pillar quotas are the strongest constraint when configured.
        Every candidate has already passed the profile threshold, so backfill
        cannot introduce low-quality filler. Source and category caps keep one
        vendor or raw-paper feed from dominating the result.
        """
        if self.config.digest.practice_minimums:
            return self._apply_practice_minimum_digest(items, log=log)

        digest = self.config.digest
        sorted_items = sorted(
            items,
            key=lambda item: (
                item.processing.analysis.score
                if item.processing
                and item.processing.analysis
                and item.processing.analysis.score is not None
                else -1
            ),
            reverse=True,
        )
        limit = digest.max_items or len(sorted_items)
        selected: List[ContentItem] = []
        selected_ids: set[str] = set()
        matrix_counts: Dict[str, int] = defaultdict(int)
        profile_counts: Dict[str, int] = defaultdict(int)
        region_counts: Dict[str, int] = defaultdict(int)
        practice_counts: Dict[str, int] = defaultdict(int)
        source_counts: Dict[str, int] = defaultdict(int)
        product_source_counts: Dict[str, int] = defaultdict(int)
        group_counts: Dict[str, int] = defaultdict(int)

        category_to_group: Dict[str, str] = {}
        for group_key, group in digest.category_groups.items():
            for category in group.categories:
                category_to_group.setdefault(category, group_key)

        def dimensions(item: ContentItem) -> tuple[str, str, str, str]:
            region = str(item.metadata.get("region") or "global")
            profile = (
                item.processing.classification.profile
                if item.processing
                else self.profiles.default_profile
            )
            analysis = item.processing.analysis if item.processing else None
            practice = (
                analysis.practice_category
                if analysis and analysis.practice_category
                else str(item.metadata.get("practice_category") or "unclassified")
            )
            return region, profile, f"{region}/{profile}", practice

        def source_key(item: ContentItem) -> str:
            hostname = (urlsplit(str(item.url)).hostname or "unknown").casefold()
            return hostname.removeprefix("www.")

        def group_key(item: ContentItem) -> Optional[str]:
            category = item.metadata.get("category")
            return category_to_group.get(category) if isinstance(category, str) else None

        def can_add(item: ContentItem) -> bool:
            _, _, _, practice = dimensions(item)
            key = source_key(item)
            if (
                digest.max_items_per_source is not None
                and source_counts[key] >= digest.max_items_per_source
            ):
                return False
            if (
                practice == "today-use"
                and digest.max_today_use_per_source is not None
                and product_source_counts[key] >= digest.max_today_use_per_source
            ):
                return False
            item_group = group_key(item)
            if item_group is not None:
                limit_for_group = digest.category_groups[item_group].limit
                if group_counts[item_group] >= limit_for_group:
                    return False
            return True

        def add(item: ContentItem) -> None:
            region, profile, matrix_key, practice = dimensions(item)
            key = source_key(item)
            selected.append(item)
            selected_ids.add(item.id)
            matrix_counts[matrix_key] += 1
            profile_counts[profile] += 1
            region_counts[region] += 1
            practice_counts[practice] += 1
            source_counts[key] += 1
            if practice == "today-use":
                product_source_counts[key] += 1
            item_group = group_key(item)
            if item_group is not None:
                group_counts[item_group] += 1
            item.metadata["practice_category"] = practice

        if digest.practice_targets:
            for practice, target in digest.practice_targets.items():
                for item in sorted_items:
                    if len(selected) >= limit or practice_counts[practice] >= target:
                        break
                    if item.id in selected_ids or not can_add(item):
                        continue
                    if dimensions(item)[3] == practice:
                        add(item)
        elif digest.matrix_targets:
            for item in sorted_items:
                if len(selected) >= limit:
                    break
                _, _, matrix_key, _ = dimensions(item)
                target = digest.matrix_targets.get(matrix_key, 0)
                if target and matrix_counts[matrix_key] < target and can_add(item):
                    add(item)
        else:
            # Backward-compatible independent targets when no matrix is supplied.
            for item in sorted_items:
                if len(selected) >= limit:
                    break
                region, profile, _, _ = dimensions(item)
                needs_profile = profile_counts[profile] < digest.profile_targets.get(
                    profile, 0
                )
                needs_region = region_counts[region] < digest.region_targets.get(
                    region, 0
                )
                if (needs_profile or needs_region) and can_add(item):
                    add(item)

        if digest.quality_fill and len(selected) < limit:
            for item in sorted_items:
                if len(selected) >= limit:
                    break
                if item.id not in selected_ids and can_add(item):
                    add(item)

        for rank, item in enumerate(selected, start=1):
            item.metadata["digest_rank"] = rank
            if rank <= digest.deep_items:
                item.metadata["summary_depth"] = "deep"
                item.metadata["summary_length_zh"] = "300-500字"
            else:
                item.metadata["summary_depth"] = "brief"
                item.metadata["summary_length_zh"] = "100-180字"

        if log:
            self.console.print(
                f"{self.icons['balance']} Targeted digest selected "
                f"{len(selected)}/{len(items)} items"
            )
            for practice, target in digest.practice_targets.items():
                self.console.print(
                    f"      {self.icons['detail']} practice {practice}: "
                    f"{practice_counts.get(practice, 0)}/{target}"
                )
            for matrix_key, target in digest.matrix_targets.items():
                self.console.print(
                    f"      {self.icons['detail']} {matrix_key}: "
                    f"{matrix_counts.get(matrix_key, 0)}/{target}"
                )
            for profile, target in digest.profile_targets.items():
                self.console.print(
                    f"      {self.icons['detail']} profile {profile}: "
                    f"{profile_counts.get(profile, 0)}/{target}"
                )
            for region, target in digest.region_targets.items():
                self.console.print(
                    f"      {self.icons['detail']} region {region}: "
                    f"{region_counts.get(region, 0)}/{target}"
                )
            self.console.print("")

        return BalancedDigestResult(
            items=selected,
            enabled=True,
            profile_counts=dict(profile_counts),
            region_counts=dict(region_counts),
            matrix_counts=dict(matrix_counts),
            practice_counts=dict(practice_counts),
            group_counts=dict(group_counts),
        )

    def _minimum_candidate_priority(self, item: ContentItem) -> tuple[int, int, float, float]:
        """Prefer the main window, then normal-threshold items, then score."""
        return (
            1 if item.metadata.get("is_fallback") else 0,
            0 if self.passes_profile_filter(item) else 1,
            -self._analysis_score(item),
            -item.published_at.timestamp(),
        )

    def _apply_practice_minimum_digest(
        self,
        items: List[ContentItem],
        *,
        log: bool = True,
    ) -> BalancedDigestResult:
        """Guarantee each external pillar without using low-score items as filler."""
        digest = self.config.digest
        limit = self._external_item_limit()
        candidates = [item for item in items if self._passes_practice_hard_gates(item)]
        minimum_ordered = sorted(candidates, key=self._minimum_candidate_priority)
        quality_ordered = sorted(candidates, key=self._analysis_score, reverse=True)
        selected: List[ContentItem] = []
        selected_ids: set[str] = set()
        practice_counts: Dict[str, int] = defaultdict(int)
        fallback_counts: Dict[str, int] = defaultdict(int)
        source_counts: Dict[str, int] = defaultdict(int)
        today_source_counts: Dict[str, int] = defaultdict(int)
        group_counts: Dict[str, int] = defaultdict(int)
        category_to_group: Dict[str, str] = {}
        for group_key, group in digest.category_groups.items():
            for category in group.categories:
                category_to_group.setdefault(category, group_key)

        def practice(item: ContentItem) -> str:
            analysis = item.processing.analysis if item.processing else None
            value = analysis.practice_category if analysis else None
            return str(value or item.metadata.get("practice_category") or "unclassified")

        def source_key(item: ContentItem) -> str:
            hostname = (urlsplit(str(item.url)).hostname or "unknown").casefold()
            return hostname.removeprefix("www.")

        def can_add(item: ContentItem) -> bool:
            key = source_key(item)
            item_practice = practice(item)
            if (
                digest.max_items_per_source is not None
                and source_counts[key] >= digest.max_items_per_source
            ):
                return False
            if (
                item_practice == "today-use"
                and digest.max_today_use_per_source is not None
                and today_source_counts[key] >= digest.max_today_use_per_source
            ):
                return False
            source_category = item.metadata.get("category")
            group_key = (
                category_to_group.get(source_category)
                if isinstance(source_category, str)
                else None
            )
            if group_key is not None:
                if group_counts[group_key] >= digest.category_groups[group_key].limit:
                    return False
            return True

        def add(item: ContentItem, *, minimum_fill: bool = False) -> None:
            item_practice = practice(item)
            key = source_key(item)
            item.metadata["practice_category"] = item_practice
            item.metadata["model_practice_category"] = item_practice
            if minimum_fill and (
                not self.passes_profile_filter(item)
                or item.metadata.get("is_fallback")
            ):
                item.metadata["minimum_backfill"] = True
                item.metadata["below_threshold_minimum"] = not self.passes_profile_filter(item)
            selected.append(item)
            selected_ids.add(item.id)
            practice_counts[item_practice] += 1
            source_counts[key] += 1
            if item_practice == "today-use":
                today_source_counts[key] += 1
            if item.metadata.get("is_fallback"):
                fallback_counts[item_practice] += 1
            source_category = item.metadata.get("category")
            group_key = (
                category_to_group.get(source_category)
                if isinstance(source_category, str)
                else None
            )
            if group_key is not None:
                group_counts[group_key] += 1

        # First reserve the guaranteed external columns. A below-threshold item
        # can enter only here and only after passing all evidence hard gates.
        for category, minimum in self._external_practice_minimums().items():
            for item in minimum_ordered:
                if len(selected) >= limit or practice_counts[category] >= minimum:
                    break
                if item.id in selected_ids or practice(item) != category or not can_add(item):
                    continue
                add(item, minimum_fill=True)

        # Targets remain quality goals: fill them only with fresh items that
        # clear the normal profile threshold.
        for category, target in digest.practice_targets.items():
            if category == "hands-on" and digest.generated_hands_on:
                continue
            for item in quality_ordered:
                if len(selected) >= limit or practice_counts[category] >= target:
                    break
                if (
                    item.id in selected_ids
                    or practice(item) != category
                    or item.metadata.get("is_fallback")
                    or not self.passes_profile_filter(item)
                    or not can_add(item)
                ):
                    continue
                add(item)

        if digest.quality_fill:
            for item in quality_ordered:
                if len(selected) >= limit:
                    break
                if (
                    item.id in selected_ids
                    or item.metadata.get("is_fallback")
                    or not self.passes_profile_filter(item)
                    or not can_add(item)
                ):
                    continue
                add(item)

        selected.sort(key=self._analysis_score, reverse=True)
        self._annotate_digest_depth(selected)

        shortfalls: Dict[str, str] = {}
        for category, minimum in self._external_practice_minimums().items():
            if practice_counts.get(category, 0) >= minimum:
                continue
            raw_matches = [item for item in items if practice(item) == category]
            gated_matches = [item for item in candidates if practice(item) == category]
            if not raw_matches:
                reason = "model produced no candidate for this category"
            elif not gated_matches:
                reason = "all candidates failed source/evidence/category hard gates"
            else:
                reason = "eligible candidates were blocked by diversity caps or item limit"
            shortfalls[category] = reason

        if log:
            self.console.print(
                f"{self.icons['balance']} Six-column digest selected "
                f"{len(selected)}/{len(items)} external items"
            )
            for category, target in digest.practice_targets.items():
                generated_suffix = " (generated)" if (
                    category == "hands-on" and digest.generated_hands_on
                ) else ""
                self.console.print(
                    f"      {self.icons['detail']} practice {category}: "
                    f"{practice_counts.get(category, 0)}/{target}{generated_suffix}"
                )
            for category, reason in shortfalls.items():
                self.console.print(
                    f"      [yellow]{self.icons['warning']} {category}: {reason}[/yellow]"
                )
            self.console.print("")

        return BalancedDigestResult(
            items=selected,
            enabled=True,
            practice_counts=dict(practice_counts),
            practice_minimum_counts={
                category: min(practice_counts.get(category, 0), minimum)
                for category, minimum in self._external_practice_minimums().items()
            },
            fallback_counts=dict(fallback_counts),
            shortfall_reasons=shortfalls,
            group_counts=dict(group_counts),
        )

    async def _expand_twitter_discussion(self, items: List[ContentItem]) -> None:
        """Second-stage: fetch reply text for important Twitter items and re-analyze.

        Only runs when sources.twitter.fetch_reply_text is True.
        Bounded by max_tweets_to_expand to control cost.
        """
        tw_cfg = self.config.sources.twitter
        if not tw_cfg or not tw_cfg.enabled or not tw_cfg.fetch_reply_text:
            return

        from .models import SourceType

        twitter_items = [
            item for item in items
            if item.source_type == SourceType.TWITTER
        ][:tw_cfg.max_tweets_to_expand]

        if not twitter_items:
            return

        self.console.print(
            f"{self.icons['discussion']} Fetching reply text for "
            f"{len(twitter_items)} Twitter items..."
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            if tw_cfg.mode == "playwright":
                self.console.print(
                    "   [yellow]Reply expansion not yet supported in Playwright mode.[/yellow]"
                )
                return
            scraper = TwitterScraper(tw_cfg, client)
            expanded = []
            for item in twitter_items:
                try:
                    reply_lines = await scraper.fetch_replies_for_item(item)
                    if TwitterScraper.append_discussion_content(item, reply_lines):
                        expanded.append(item)
                        self.console.print(
                            f"   {self.icons['discussion']} {len(reply_lines)} replies "
                            f"added to: {item.title[:60]}"
                        )
                except Exception as exc:
                    self.console.print(
                        f"   [yellow]{self.icons['warning']} Reply fetch failed for "
                        f"{item.id}: {exc}[/yellow]"
                    )

        if not expanded:
            return

        self.console.print(
            f"   Re-analyzing {len(expanded)} Twitter items with reply context...\n"
        )
        ai_client = create_ai_client(self.config.ai)
        analyzer = ContentAnalyzer(
            ai_client,
            self.profiles,
            console=self.console,
            profile_settings=self.config.processing.profile_settings,
        )
        await analyzer.analyze_batch(expanded)

    async def enrich_items(self, items: List[ContentItem]) -> EnrichmentBatchResult:
        """Enrich items with background knowledge (2nd AI pass).

        For each item that passed the score threshold, call AI to generate
        background knowledge based on the item's actual content.

        Args:
            items: Important items to enrich (modified in-place)
        """
        if not items:
            return EnrichmentBatchResult()

        self.console.print(
            f"{self.icons['enrich']} Enriching with background knowledge..."
        )
        ai_client = create_ai_client(self.config.ai)
        enricher = ContentEnricher(
            ai_client,
            self.profiles,
            self.config.ai.languages,
            console=self.console,
        )
        result = await enricher.enrich_batch(items)
        self.console.print(
            f"   Enriched {result.succeeded_count}/{len(items)} items"
        )
        if result.failed_count:
            self.console.print(
                f"   [yellow]Skipped {result.failed_count} items after enrichment "
                f"failed: {', '.join(result.failed_ids)}[/yellow]"
            )
        self.console.print("")
        return result

    async def analyze_items(self, items: List[ContentItem]) -> List[ContentItem]:
        """Analyze content items with AI.

        Args:
            items: Items to analyze

        Returns:
            List[ContentItem]: Analyzed items
        """
        self.console.print(f"{self.icons['ai']} Analyzing content with AI...")

        ai_client = create_ai_client(self.config.ai)
        analyzer = ContentAnalyzer(
            ai_client,
            self.profiles,
            console=self.console,
            profile_settings=self.config.processing.profile_settings,
        )

        return await analyzer.analyze_batch(items)

    async def _generate_summary(
        self,
        items: List[ContentItem],
        date: str,
        total_fetched: int,
        language: str = "en",
    ) -> str:
        """Generate daily summary.

        Args:
            items: Important items to include (already enriched with background/related)
            date: Date string
            total_fetched: Total items fetched
            language: Output language ("en" or "zh")

        Returns:
            str: Markdown summary
        """
        self.console.print(f"{self.icons['summary']} Generating daily summary...")

        summarizer = DailySummarizer(
            profile_names=self.profiles.names,
            profile_order=self.config.digest.profile_order,
            practice_targets=self.config.digest.practice_targets,
        )

        return await summarizer.generate_summary(items, date, total_fetched, language=language)
