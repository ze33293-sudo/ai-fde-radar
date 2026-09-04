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
    "å¤§æ¨¡åž‹",
    "äººå·¥æ™ºèƒ½",
    "æ™ºèƒ½ä½“",
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
    "æ•™ç¨‹",
    "æŒ‡å—",
    "å®žæˆ˜",
    "æ‰‹æŠŠæ‰‹",
    "å¤ç›˜",
    "è¸©å‘",
    "æ¡ˆä¾‹",
    "è½åœ°",
    "ä¸Šçº¿",
    "å·¥ä½œæµ",
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
    "å”®åŽ",
    "å®¢æœ",
    "å·¥å•",
    "çŸ¥è¯†åº“",
    "äººå·¥è½¬æŽ¥",
    "äººå·¥å®¡æ ¸",
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
    "èžèµ„",
    "ä¼°å€¼",
    "è‚¡ä»·",
    "è´¢æŠ¥",
    "è¯‰è®¼",
    "ç‰ˆæƒæ¡ˆ",
    "ä¼ é—»",
    "é«˜ç®¡è§‚ç‚¹",
}

_DISTANT_TECH_TITLE_SIGNALS = {
    "cuda",
    "gpu kernel",
    "speculative decoding",
    "model training",
    "training infrastructure",
    "robotics",
    "èŠ¯ç‰‡",
    "ç®—åŠ›é›†ç¾¤",
    "è®­ç»ƒæ¡†æž¶",
    "æœºå™¨äºº",
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
        "å‘å¸ƒ",
        "æŽ¨å‡º",
        "ä¸Šçº¿",
        "å¼€æ”¾ä½¿ç”¨",
        "æ›´æ–°",
        "æ–°åŠŸèƒ½",
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
        "æ¡ˆä¾‹",
        "è½åœ°",
        "éƒ¨ç½²",
        "é‡‡ç”¨çŽ‡",
        "å·¥ä½œæµ",
        "å®¢æœ",
        "å”®åŽ",
        "å·¥å•",
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
        "è¯„æµ‹",
        "è¯„ä¼°",
        "å¤±è´¥",
        "å¯é æ€§",
        "å¯è§‚æµ‹",
        "æƒé™",
        "å®‰å…¨",
        "æˆæœ¬",
        "è¸©å‘",
        "å¤ç›˜",
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
        "å…¥é—¨",
        "ç§‘æ™®",
        "åŽŸç†",
        "æŒ‡å—",
        "æ•™ç¨‹",
        "æž¶æž„",
        "å¯¹æ¯”",
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
        "äº§å“ç»ç†",
        "åº”ç”¨å®žæ–½",
        "å²—ä½",
        "æ‹›è˜",
        "é¢è¯•",
        "ä½œå“é›†",
        "èƒ½åŠ›è¦æ±‚",
        "åŽ¦é—¨",
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
        "å®žæˆ˜",
        "æ•™ç¨‹",
        "æ¨¡æ¿",
        "ç¤ºä¾‹ä»£ç ",
        "å¼€æºé¡¹ç›®",
    },
}

_MEASURABLE_EVIDENCE_PATTERN = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?x\b|"
    r"\b(?:latency|accuracy|resolution rate|handle time|cost|roi|csat)\b|"
    r"(?:å‡†ç¡®çŽ‡|è§£å†³çŽ‡|è½¬äººå·¥çŽ‡|å“åº”æ—¶é—´|å¤„ç†æ—¶é•¿|æˆæœ¬|é‡‡ç”¨çŽ‡|æ»¡æ„åº¦))",
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
     ßo5îÚ$z{-®éÜj×b'·6VÆbæ–6öç5²v&Ææ6Ru×ÒF&vWFVBF–vW7B6VÆV7FVB ¢b'¶ÆVâ‡6VÆV7FVB—Ò÷¶ÆVâ†—FV×2—Ò—FV×2 ¢¢f÷"&7F–6RÂF&vWB–âF–vW7Bç&7F–6U÷F&vWG2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò&7F–6R·&7F–6WÓ¢ ¢b'·&7F–6Uö6÷VçG2ævWB‡&7F–6RÂ—Ò÷·F&vWGÒ ¢¢f÷"ÖG&—…ö¶W’ÂF&vWB–âF–vW7BæÖG&—…÷F&vWG2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò¶ÖG&—…ö¶W—Ó¢ ¢b'¶ÖG&—…ö6÷VçG2ævWB†ÖG&—…ö¶W’Â—Ò÷·F&vWGÒ ¢¢f÷"&öf–ÆRÂF&vWB–âF–vW7Bç&öf–ÆU÷F&vWG2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò&öf–ÆR·&öf–ÆWÓ¢ ¢b'·&öf–ÆUö6÷VçG2ævWB‡&öf–ÆRÂ—Ò÷·F&vWGÒ ¢¢f÷"&Vv–öâÂF&vWB–âF–vW7Bç&Vv–öå÷F&vWG2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò&Vv–öâ·&Vv–öçÓ¢ ¢b'·&Vv–öåö6÷VçG2ævWB‡&Vv–öâÂ—Ò÷·F&vWGÒ ¢¢6VÆbæ6öç6öÆRç&–çB‚"" ¢&WGW&â&Ææ6VDF–vW7E&W7VÇB€¢—FV×3×6VÆV7FVBÀ¢Væ&ÆVCÕG'VRÀ¢&öf–ÆUö6÷VçG3ÖF–7B‡&öf–ÆUö6÷VçG2’À¢&Vv–öåö6÷VçG3ÖF–7B‡&Vv–öåö6÷VçG2’À¢ÖG&—…ö6÷VçG3ÖF–7B†ÖG&—…ö6÷VçG2’À¢&7F–6Uö6÷VçG3ÖF–7B‡&7F–6Uö6÷VçG2’À¢w&÷Wö6÷VçG3ÖF–7B†w&÷Wö6÷VçG2’À¢ ¢FVböÖ–æ–×VÕö6æF–FFU÷&–÷&—G’‡6VÆbÂ—FVÓ¢6öçFVçD—FVÒ’ÓâGWÆU¶–çBÂ–çBÂfÆöBÂfÆöEÓ ¢""%&VfW"F†RÖ–âv–æF÷rÂF†Vâæ÷&ÖÂ×F‡&W6†öÆB—FV×2ÂF†Vâ66÷&Râ"" ¢&WGW&â€¢–b—FVÒæÖWFFFævWB‚&—5öfÆÆ&6²"’VÇ6RÀ¢–b6VÆbç76W5÷&öf–ÆUöf–ÇFW"†—FVÒ’VÇ6RÀ¢×6VÆbåöæÇ—6—5÷66÷&R†—FVÒ’À¢Ö—FVÒçV&Æ—6†VEöBçF–ÖW7F×‚’À¢ ¢FVböÇ•÷&7F–6UöÖ–æ–×VÕöF–vW7B€¢6VÆbÀ¢—FV×3¢Æ—7E´6öçFVçD—FVÕÒÀ¢¢À¢Æös¢&ööÂÒG'VRÀ¢’Óâ&Ææ6VDF–vW7E&W7VÇC ¢""$wV&çFVRV6‚W‡FW&æÂ–ÆÆ"v—F†÷WBW6–ærÆ÷r×66÷&R—FV×22f–ÆÆW"â"" ¢F–vW7BÒ6VÆbæ6öæf–ræF–vW7@¢Æ–Ö—BÒ6VÆbåöW‡FW&æÅö—FVÕöÆ–Ö—B‚¢6æF–FFW2Ò¶—FVÒf÷"—FVÒ–â—FV×2–b6VÆbå÷76W5÷&7F–6Uö†&EövFW2†—FVÒ•Ð¢Ö–æ–×VÕö÷&FW&VBÒ6÷'FVB†6æF–FFW2Â¶W“×6VÆbåöÖ–æ–×VÕö6æF–FFU÷&–÷&—G’¢VÆ—G•ö÷&FW&VBÒ6÷'FVB†6æF–FFW2Â¶W“×6VÆbåöæÇ—6—5÷66÷&RÂ&WfW'6SÕG'VR¢6VÆV7FVC¢Æ—7E´6öçFVçD—FVÕÒÒµÐ¢6VÆV7FVEö–G3¢6WE·7G%ÒÒ6WB‚¢&7F–6Uö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢fÆÆ&6µö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢6÷W&6Uö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢FöF•÷6÷W&6Uö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢w&÷Wö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢6FVv÷'•÷Fõöw&÷W¢F–7E·7G"Â7G%ÒÒ·Ð¢f÷"w&÷Wö¶W’Âw&÷W–âF–vW7Bæ6FVv÷'•öw&÷W2æ—FV×2‚“ ¢f÷"6FVv÷'’–âw&÷Wæ6FVv÷&–W3 ¢6FVv÷'•÷Fõöw&÷Wç6WFFVfVÇB†6FVv÷'’Âw&÷Wö¶W’ ¢FVb&7F–6R†—FVÓ¢6öçFVçD—FVÒ’Óâ7G# ¢æÇ—6—2Ò—FVÒç&ö6W76–ærææÇ—6—2–b—FVÒç&ö6W76–ærVÇ6RæöæP¢fÇVRÒæÇ—6—2ç&7F–6Uö6FVv÷'’–bæÇ—6—2VÇ6RæöæP¢&WGW&â7G"‡fÇVR÷"—FVÒæÖWFFFævWB‚'&7F–6Uö6FVv÷'’"’÷"'Væ6Æ76–f–VB" ¢FVb6÷W&6Uö¶W’†—FVÓ¢6öçFVçD—FVÒ’Óâ7G# ¢†÷7FæÖRÒ‡W&Ç7Æ—B‡7G"†—FVÒçW&Â’’æ†÷7FæÖR÷"'Væ¶æ÷vâ"’æ66VföÆB‚¢&WGW&â†÷7FæÖRç&VÖ÷fW&Vf—‚‚'wwrâ" ¢FVb6åöFB†—FVÓ¢6öçFVçD—FVÒ’Óâ&ööÃ ¢¶W’Ò6÷W&6Uö¶W’†—FVÒ¢—FVÕ÷&7F–6RÒ&7F–6R†—FVÒ¢–b€¢F–vW7BæÖ…ö—FV×5÷W%÷6÷W&6R—2æ÷BæöæP¢æB6÷W&6Uö6÷VçG5¶¶W•ÒãÒF–vW7BæÖ…ö—FV×5÷W%÷6÷W&6P¢“ ¢&WGW&âfÇ6P¢–b€¢—FVÕ÷&7F–6RÓÒ'FöF’×W6R ¢æBF–vW7BæÖ…÷FöF•÷W6U÷W%÷6÷W&6R—2æ÷BæöæP¢æBFöF•÷6÷W&6Uö6÷VçG5¶¶W•ÒãÒF–vW7BæÖ…÷FöF•÷W6U÷W%÷6÷W&6P¢“ ¢&WGW&âfÇ6P¢6÷W&6Uö6FVv÷'’Ò—FVÒæÖWFFFævWB‚&6FVv÷'’"¢w&÷Wö¶W’Ò€¢6FVv÷'•÷Fõöw&÷WævWB‡6÷W&6Uö6FVv÷'’¢–b—6–ç7Fæ6R‡6÷W&6Uö6FVv÷'’Â7G"¢VÇ6RæöæP¢¢–bw&÷Wö¶W’—2æ÷BæöæS ¢–bw&÷Wö6÷VçG5¶w&÷Wö¶W•ÒãÒF–vW7Bæ6FVv÷'•öw&÷W5¶w&÷Wö¶W•ÒæÆ–Ö—C ¢&WGW&âfÇ6P¢&WGW&âG'VP ¢FVbFB†—FVÓ¢6öçFVçD—FVÒÂ¢ÂÖ–æ–×VÕöf–ÆÃ¢&ööÂÒfÇ6R’ÓâæöæS ¢—FVÕ÷&7F–6RÒ&7F–6R†—FVÒ¢¶W’Ò6÷W&6Uö¶W’†—FVÒ¢—FVÒæÖWFFF²'&7F–6Uö6FVv÷'’%ÒÒ—FVÕ÷&7F–6P¢—FVÒæÖWFFF²&ÖöFVÅ÷&7F–6Uö6FVv÷'’%ÒÒ—FVÕ÷&7F–6P¢–bÖ–æ–×VÕöf–ÆÂæB€¢æ÷B6VÆbç76W5÷&öf–ÆUöf–ÇFW"†—FVÒ¢÷"—FVÒæÖWFFFævWB‚&—5öfÆÆ&6²"¢“ ¢—FVÒæÖWFFF²&Ö–æ–×VÕö&6¶f–ÆÂ%ÒÒG'VP¢—FVÒæÖWFFF²&&VÆ÷u÷F‡&W6†öÆEöÖ–æ–×VÒ%ÒÒæ÷B6VÆbç76W5÷&öf–ÆUöf–ÇFW"†—FVÒ¢6VÆV7FVBæVæB†—FVÒ¢6VÆV7FVEö–G2æFB†—FVÒæ–B¢&7F–6Uö6÷VçG5¶—FVÕ÷&7F–6UÒ³Ò¢6÷W&6Uö6÷VçG5¶¶W•Ò³Ò¢–b—FVÕ÷&7F–6RÓÒ'FöF’×W6R# ¢FöF•÷6÷W&6Uö6÷VçG5¶¶W•Ò³Ò¢–b—FVÒæÖWFFFævWB‚&—5öfÆÆ&6²"“ ¢fÆÆ&6µö6÷VçG5¶—FVÕ÷&7F–6UÒ³Ò¢6÷W&6Uö6FVv÷'’Ò—FVÒæÖWFFFævWB‚&6FVv÷'’"¢w&÷Wö¶W’Ò€¢6FVv÷'•÷Fõöw&÷WævWB‡6÷W&6Uö6FVv÷'’¢–b—6–ç7Fæ6R‡6÷W&6Uö6FVv÷'’Â7G"¢VÇ6RæöæP¢¢–bw&÷Wö¶W’—2æ÷BæöæS ¢w&÷Wö6÷VçG5¶w&÷Wö¶W•Ò³Ò ¢2f—'7B&W6W'fRF†RwV&çFVVBW‡FW&æÂ6öÇVÖç2â&VÆ÷r×F‡&W6†öÆB—FVÐ¢26âVçFW"öæÇ’†W&RæBöæÇ’gFW"76–ærÆÂWf–FVæ6R†&BvFW2à¢f÷"6FVv÷'’ÂÖ–æ–×VÒ–â6VÆbåöW‡FW&æÅ÷&7F–6UöÖ–æ–×V×2‚’æ—FV×2‚“ ¢f÷"—FVÒ–âÖ–æ–×VÕö÷&FW&VC ¢–bÆVâ‡6VÆV7FVB’ãÒÆ–Ö—B÷"&7F–6Uö6÷VçG5¶6FVv÷'•ÒãÒÖ–æ–×VÓ ¢'&V°¢–b—FVÒæ–B–â6VÆV7FVEö–G2÷"&7F–6R†—FVÒ’Ò6FVv÷'’÷"æ÷B6åöFB†—FVÒ“ ¢6öçF–çVP¢FB†—FVÒÂÖ–æ–×VÕöf–ÆÃÕG'VR ¢2F&vWG2&VÖ–âVÆ—G’vöÇ3¢f–ÆÂF†VÒöæÇ’v—F‚g&W6‚—FV×2F†@¢26ÆV"F†Ræ÷&ÖÂ&öf–ÆRF‡&W6†öÆBà¢f÷"6FVv÷'’ÂF&vWB–âF–vW7Bç&7F–6U÷F&vWG2æ—FV×2‚“ ¢–b6FVv÷'’ÓÒ&†æG2Ööâ"æBF–vW7BævVæW&FVEö†æG5ööã ¢6öçF–çVP¢f÷"—FVÒ–âVÆ—G•ö÷&FW&VC ¢–bÆVâ‡6VÆV7FVB’ãÒÆ–Ö—B÷"&7F–6Uö6÷VçG5¶6FVv÷'•ÒãÒF&vWC ¢'&V°¢–b€¢—FVÒæ–B–â6VÆV7FVEö–G0¢÷"&7F–6R†—FVÒ’Ò6FVv÷'¢÷"—FVÒæÖWFFFævWB‚&—5öfÆÆ&6²"¢÷"æ÷B6VÆbç76W5÷&öf–ÆUöf–ÇFW"†—FVÒ¢÷"æ÷B6åöFB†—FVÒ¢“ ¢6öçF–çVP¢FB†—FVÒ ¢–bF–vW7BçVÆ—G•öf–ÆÃ ¢f÷"—FVÒ–âVÆ—G•ö÷&FW&VC ¢–bÆVâ‡6VÆV7FVB’ãÒÆ–Ö—C ¢'&V°¢–b€¢—FVÒæ–B–â6VÆV7FVEö–G0¢÷"—FVÒæÖWFFFævWB‚&—5öfÆÆ&6²"¢÷"æ÷B6VÆbç76W5÷&öf–ÆUöf–ÇFW"†—FVÒ¢÷"æ÷B6åöFB†—FVÒ¢“ ¢6öçF–çVP¢FB†—FVÒ ¢6VÆV7FVBç6÷'B†¶W“×6VÆbåöæÇ—6—5÷66÷&RÂ&WfW'6SÕG'VR¢6VÆbåöææ÷FFUöF–vW7EöFWF‚‡6VÆV7FVB ¢6†÷'FfÆÇ3¢F–7E·7G"Â7G%ÒÒ·Ð¢f÷"6FVv÷'’ÂÖ–æ–×VÒ–â6VÆbåöW‡FW&æÅ÷&7F–6UöÖ–æ–×V×2‚’æ—FV×2‚“ ¢–b&7F–6Uö6÷VçG2ævWB†6FVv÷'’Â’ãÒÖ–æ–×VÓ ¢6öçF–çVP¢&uöÖF6†W2Ò¶—FVÒf÷"—FVÒ–â—FV×2–b&7F–6R†—FVÒ’ÓÒ6FVv÷'•Ð¢vFVEöÖF6†W2Ò¶—FVÒf÷"—FVÒ–â6æF–FFW2–b&7F–6R†—FVÒ’ÓÒ6FVv÷'•Ð¢–bæ÷B&uöÖF6†W3 ¢&V6öâÒ&ÖöFVÂ&öGV6VBæò6æF–FFRf÷"F†—26FVv÷'’ ¢VÆ–bæ÷BvFVEöÖF6†W3 ¢&V6öâÒ&ÆÂ6æF–FFW2f–ÆVB6÷W&6RöWf–FVæ6Rö6FVv÷'’†&BvFW2 ¢VÇ6S ¢&V6öâÒ&VÆ–v–&ÆR6æF–FFW2vW&R&Æö6¶VB'’F—fW'6—G’62÷"—FVÒÆ–Ö—B ¢6†÷'FfÆÇ5¶6FVv÷'•ÒÒ&V6öà ¢–bÆös ¢6VÆbæ6öç6öÆRç&–çB€¢b'·6VÆbæ–6öç5²v&Ææ6Ru×Ò6—‚Ö6öÇVÖâF–vW7B6VÆV7FVB ¢b'¶ÆVâ‡6VÆV7FVB—Ò÷¶ÆVâ†—FV×2—ÒW‡FW&æÂ—FV×2 ¢¢f÷"6FVv÷'’ÂF&vWB–âF–vW7Bç&7F–6U÷F&vWG2æ—FV×2‚“ ¢vVæW&FVE÷7Vff—‚Ò"†vVæW&FVB’"–b€¢6FVv÷'’ÓÒ&†æG2Ööâ"æBF–vW7BævVæW&FVEö†æG5ööà¢’VÇ6R" ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò&7F–6R¶6FVv÷'—Ó¢ ¢b'·&7F–6Uö6÷VçG2ævWB†6FVv÷'’Â—Ò÷·F&vWG×¶vVæW&FVE÷7Vff—‡Ò ¢¢f÷"6FVv÷'’Â&V6öâ–â6†÷'FfÆÇ2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·–VÆÆ÷u×·6VÆbæ–6öç5²wv&æ–æru×Ò¶6FVv÷'—Ó¢·&V6öçÕ²÷–VÆÆ÷uÒ ¢¢6VÆbæ6öç6öÆRç&–çB‚"" ¢&WGW&â&Ææ6VDF–vW7E&W7VÇB€¢—FV×3×6VÆV7FVBÀ¢Væ&ÆVCÕG'VRÀ¢&7F–6Uö6÷VçG3ÖF–7B‡&7F–6Uö6÷VçG2’À¢&7F–6UöÖ–æ–×VÕö6÷VçG3×°¢6FVv÷'“¢Ö–â‡&7F–6Uö6÷VçG2ævWB†6FVv÷'’Â’ÂÖ–æ–×VÒ¢f÷"6FVv÷'’ÂÖ–æ–×VÒ–â6VÆbåöW‡FW&æÅ÷&7F–6UöÖ–æ–×V×2‚’æ—FV×2‚¢ÒÀ¢fÆÆ&6µö6÷VçG3ÖF–7B†fÆÆ&6µö6÷VçG2’À¢6†÷'FfÆÅ÷&V6öç3×6†÷'FfÆÇ2À¢w&÷Wö6÷VçG3ÖF–7B†w&÷Wö6÷VçG2’À¢ ¢7–æ2FVböW‡æE÷Gv—GFW%öF—67W76–öâ‡6VÆbÂ—FV×3¢Æ—7E´6öçFVçD—FVÕÒ’ÓâæöæS ¢""%6V6öæB×7FvS¢fWF6‚&WÇ’FW‡Bf÷"–×÷'FçBGv—GFW"—FV×2æB&RÖæÇ—¦Rà ¢öæÇ’'Vç2v†Vâ6÷W&6W2çGv—GFW"æfWF6…÷&WÇ•÷FW‡B—2G'VRà¢&÷VæFVB'’Ö…÷GvVWG5÷FõöW‡æBFò6öçG&öÂ6÷7Bà¢"" ¢Guö6frÒ6VÆbæ6öæf–rç6÷W&6W2çGv—GFW ¢–bæ÷BGuö6fr÷"æ÷BGuö6fræVæ&ÆVB÷"æ÷BGuö6fræfWF6…÷&WÇ•÷FW‡C ¢&WGW&à ¢g&öÒæÖöFVÇ2–×÷'B6÷W&6UG—P ¢Gv—GFW%ö—FV×2Ò°¢—FVÒf÷"—FVÒ–â—FV×0¢–b—FVÒç6÷W&6U÷G—RÓÒ6÷W&6UG—RåEt•EDU ¢Õ³§Guö6fræÖ…÷GvVWG5÷FõöW‡æEÐ ¢–bæ÷BGv—GFW%ö—FV×3 ¢&WGW&à ¢6VÆbæ6öç6öÆRç&–çB€¢b'·6VÆbæ–6öç5²vF—67W76–öâu×ÒfWF6†–ær&WÇ’FW‡Bf÷" ¢b'¶ÆVâ‡Gv—GFW%ö—FV×2—ÒGv—GFW"—FV×2âââ ¢ ¢7–æ2v—F‚‡GG‚ä7–æ46Æ–VçB‡F–ÖV÷WCÓ3ã’26Æ–VçC ¢–bGuö6fræÖöFRÓÒ'Æ—w&–v‡B# ¢6VÆbæ6öç6öÆRç&–çB€¢"·–VÆÆ÷uÕ&WÇ’W‡ç6–öâæ÷B–WB7W÷'FVB–âÆ—w&–v‡BÖöFRå²÷–VÆÆ÷uÒ ¢¢&WGW&à¢67&W"ÒGv—GFW%67&W"‡Guö6frÂ6Æ–VçB¢W‡æFVBÒµÐ¢f÷"—FVÒ–âGv—GFW%ö—FV×3 ¢G'“ ¢&WÇ•öÆ–æW2Òv—B67&W"æfWF6…÷&WÆ–W5öf÷%ö—FVÒ†—FVÒ¢–bGv—GFW%67&W"æVæEöF—67W76–öåö6öçFVçB†—FVÒÂ&WÇ•öÆ–æW2“ ¢W‡æFVBæVæB†—FVÒ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vF—67W76–öâu×Ò¶ÆVâ‡&WÇ•öÆ–æW2—Ò&WÆ–W2 ¢b&FFVBFó¢¶—FVÒçF—FÆU³£c×Ò ¢¢W†6WBW†6WF–öâ2W†3 ¢6VÆbæ6öç6öÆRç&–çB€¢b"·–VÆÆ÷u×·6VÆbæ–6öç5²wv&æ–æru×Ò&WÇ’fWF6‚f–ÆVBf÷" ¢b'¶—FVÒæ–GÓ¢¶W†7Õ²÷–VÆÆ÷uÒ ¢ ¢–bæ÷BW‡æFVC ¢&WGW&à ¢6VÆbæ6öç6öÆRç&–çB€¢b"&RÖæÇ—¦–ær¶ÆVâ†W‡æFVB—ÒGv—GFW"—FV×2v—F‚&WÇ’6öçFW‡BââåÆâ ¢¢•ö6Æ–VçBÒ7&VFUö•ö6Æ–VçB‡6VÆbæ6öæf–ræ’¢æÇ—¦W"Ò6öçFVçDæÇ—¦W"€¢•ö6Æ–VçBÀ¢6VÆbç&öf–ÆW2À¢6öç6öÆS×6VÆbæ6öç6öÆRÀ¢&öf–ÆU÷6WGF–æw3×6VÆbæ6öæf–rç&ö6W76–ærç&öf–ÆU÷6WGF–æw2À¢¢v—BæÇ—¦W"ææÇ—¦Uö&F6‚†W‡æFVB ¢7–æ2FVbVç&–6…ö—FV×2‡6VÆbÂ—FV×3¢Æ—7E´6öçFVçD—FVÕÒ’ÓâVç&–6†ÖVçD&F6…&W7VÇC ¢""$Vç&–6‚—FV×2v—F‚&6¶w&÷VæB¶æ÷vÆVFvRƒ&æB’72’à ¢f÷"V6‚—FVÒF†B76VBF†R66÷&RF‡&W6†öÆBÂ6ÆÂ’FòvVæW&FP¢&6¶w&÷VæB¶æ÷vÆVFvR&6VBöâF†R—FVÒw27GVÂ6öçFVçBà ¢&w3 ¢—FV×3¢–×÷'FçB—FV×2FòVç&–6‚†ÖöF–f–VB–â×Æ6R¢"" ¢–bæ÷B—FV×3 ¢&WGW&âVç&–6†ÖVçD&F6…&W7VÇB‚ ¢6VÆbæ6öç6öÆRç&–çB€¢b'·6VÆbæ–6öç5²vVç&–6‚u×ÒVç&–6†–ærv—F‚&6¶w&÷VæB¶æ÷vÆVFvRâââ ¢¢•ö6Æ–VçBÒ7&VFUö•ö6Æ–VçB‡6VÆbæ6öæf–ræ’¢Vç&–6†W"Ò6öçFVçDVç&–6†W"€¢•ö6Æ–VçBÀ¢6VÆbç&öf–ÆW2À¢6VÆbæ6öæf–ræ’æÆæwVvW2À¢6öç6öÆS×6VÆbæ6öç6öÆRÀ¢¢&W7VÇBÒv—BVç&–6†W"æVç&–6…ö&F6‚†—FV×2¢6VÆbæ6öç6öÆRç&–çB€¢b"Vç&–6†VB·&W7VÇBç7V66VVFVEö6÷VçGÒ÷¶ÆVâ†—FV×2—Ò—FV×2 ¢¢–b&W7VÇBæf–ÆVEö6÷VçC ¢6VÆbæ6öç6öÆRç&–çB€¢b"·–VÆÆ÷uÕ6¶—VB·&W7VÇBæf–ÆVEö6÷VçGÒ—FV×2gFW"Vç&–6†ÖVçB ¢b&f–ÆVC¢²rÂræ¦ö–â‡&W7VÇBæf–ÆVEö–G2—Õ²÷–VÆÆ÷uÒ ¢¢6VÆbæ6öç6öÆRç&–çB‚""¢&WGW&â&W7VÇ@ ¢7–æ2FVbæÇ—¦Uö—FV×2‡6VÆbÂ—FV×3¢Æ—7E´6öçFVçD—FVÕÒ’ÓâÆ—7E´6öçFVçD—FVÕÓ ¢""$æÇ—¦R6öçFVçB—FV×2v—F‚’à ¢&w3 ¢—FV×3¢—FV×2FòæÇ—¦P ¢&WGW&ç3 ¢Æ—7E´6öçFVçD—FVÕÓ¢æÇ—¦VB—FV×0¢"" ¢6VÆbæ6öç6öÆRç&–çB†b'·6VÆbæ–6öç5²v’u×ÒæÇ—¦–ær6öçFVçBv—F‚’âââ" ¢•ö6Æ–VçBÒ7&VFUö•ö6Æ–VçB‡6VÆbæ6öæf–ræ’¢æÇ—¦W"Ò6öçFVçDæÇ—¦W"€¢•ö6Æ–VçBÀ¢6VÆbç&öf–ÆW2À¢6öç6öÆS×6VÆbæ6öç6öÆRÀ¢&öf–ÆU÷6WGF–æw3×6VÆbæ6öæf–rç&ö6W76–ærç&öf–ÆU÷6WGF–æw2À¢ ¢&WGW&âv—BæÇ—¦W"ææÇ—¦Uö&F6‚†—FV×2 ¢7–æ2FVbövVæW&FU÷7VÖÖ'’€¢6VÆbÀ¢—FV×3¢Æ—7E´6öçFVçD—FVÕÒÀ¢FFS¢7G"À¢F÷FÅöfWF6†VC¢–çBÀ¢ÆæwVvS¢7G"Ò&Vâ"À¢’Óâ7G# ¢""$vVæW&FRF–Ç’7VÖÖ'’à ¢&w3 ¢—FV×3¢–×÷'FçB—FV×2Fò–æ6ÇVFR†Ç&VG’Vç&–6†VBv—F‚&6¶w&÷VæB÷&VÆFVB¢FFS¢FFR7G&–æp¢F÷FÅöfWF6†VC¢F÷FÂ—FV×2fWF6†V@¢ÆæwVvS¢÷WGWBÆæwVvR‚&Vâ"÷"'¦‚" ¢&WGW&ç3 ¢7G#¢Ö&¶F÷vâ7VÖÖ'¢"" ¢6VÆbæ6öç6öÆRç&–çB†b'·6VÆbæ–6öç5²w7VÖÖ'’u×ÒvVæW&F–ærF–Ç’7VÖÖ'’âââ" ¢7VÖÖ&—¦W"ÒF–Ç•7VÖÖ&—¦W"€¢&öf–ÆUöæÖW3×6VÆbç&öf–ÆW2ææÖW2À¢&öf–ÆUö÷&FW#×6VÆbæ6öæf–ræF–vW7Bç&öf–ÆUö÷&FW"À¢&7F–6U÷F&vWG3×6VÆbæ6öæf–ræF–vW7Bç&7F–6U÷F&vWG2À¢ ¢&WGW&âv—B7VÖÖ&—¦W"ævVæW&FU÷7VÖÖ'’†—FV×2ÂFFRÂF÷FÅöfWF6†VBÂÆæwVvSÖÆæwVvR