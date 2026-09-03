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
from .models import Config, ContentItem, SourceType, TrafilaturaExtractorConfig
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
                f"{since.strftime('%Y-%m-×ÎøöÚ$z{-®éÜj×–Ö—B—2æ÷BæöæRæBw&÷Wö6÷VçG5¶w&÷Wö¶W•ÒãÒÆ–Ö—C Ð¢6öçF–çVPÐ Ð¢6VÆV7FVBæVæB‚†—FVÒÂw&÷Wö¶W’’Ð¢w&÷Wö6÷VçG5¶w&÷Wö¶W•Ò³ÒÐ Ð¢–bÖ…ö—FV×2—2æ÷BæöæS Ð¢6VÆV7FVBÒ6VÆV7FVE³¦Ö…ö—FV×5ÐÐ Ð¢f–æÅö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çBÐ¢f÷"òÂw&÷Wö¶W’–â6VÆV7FVC Ð¢f–æÅö6÷VçG5¶w&÷Wö¶W•Ò³ÒÐ Ð¢w&÷WöÆ–Ö—G3¢F–7E·7G"Â÷F–öæÅ¶–çEÕÒÒ°Ð¢w&÷Wö¶W“¢w&÷WæÆ–Ö—Bf÷"w&÷Wö¶W’Âw&÷W–âw&÷W2æ—FV×2‚Ð¢ÐÐ¢w&÷WöÆ–Ö—G2ç6WFFVfVÇB†FVfVÇEöw&÷WÂF–vW7BæFVfVÇEöw&÷WöÆ–Ö—BÐ Ð¢–bÆös Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢b'·6VÆbæ–6öç5²v&Ææ6Ru×Ò&Ææ6VBF–vW7B6VÆV7FVB Ð¢b'¶ÆVâ‡6VÆV7FVB—Ò÷¶ÆVâ†—FV×2—Ò—FV×2 Ð¢Ð¢f÷"w&÷Wö¶W’Âw&÷W–âw&÷W2æ—FV×2‚“ Ð¢Æ&VÂÒw&÷WææÖR÷"w&÷Wö¶WÐ¢6VÆbæ6öç6öÆRç&–çB€Ð¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò¶Æ&VÇÓ¢ Ð¢b'¶f–æÅö6÷VçG2ævWB†w&÷Wö¶W’Â—Ò÷¶w&÷WæÆ–Ö—GÒ Ð¢Ð¢–b€Ð¢f–æÅö6÷VçG2ævWB†FVfVÇEöw&÷WÂÐ¢÷"F–vW7BæFVfVÇEöw&÷WöÆ–Ö—B—2æ÷BæöæPÐ¢“ Ð¢Æ–Ö—EöÆ&VÂÒ€Ð¢7G"†F–vW7BæFVfVÇEöw&÷WöÆ–Ö—BÐ¢–bF–vW7BæFVfVÇEöw&÷WöÆ–Ö—B—2æ÷BæöæPÐ¢VÇ6R'VæÆ–Ö—FVB Ð¢Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò¶FVfVÇEöw&÷WÓ¢ Ð¢b'¶f–æÅö6÷VçG2ævWB†FVfVÇEöw&÷WÂ—Ò÷¶Æ–Ö—EöÆ&VÇÒ Ð¢Ð¢6VÆbæ6öç6öÆRç&–çB‚""Ð Ð¢&WGW&â&Ææ6VDF–vW7E&W7VÇB€¢—FV×3Õ¶—FVÒf÷"—FVÒÂò–â6VÆV7FVEÒÀÐ¢Væ&ÆVCÕG'VRÀÐ¢w&÷Wö6÷VçG3ÖF–7B†f–æÅö6÷VçG2’ÀÐ¢w&÷WöÆ–Ö—G3Öw&÷WöÆ–Ö—G2ÀÐ¢GWÆ–6FUö6FVv÷&–W3×6÷'FVB‡6WB†GWÆ–6FUö6FVv÷&–W2’’À¢ ¢FVböÇ•÷F&vWFVEöF–vW7B€¢6VÆbÀ¢—FV×3¢Æ—7E´6öçFVçD—FVÕÒÀ¢¢À¢Æös¢&ööÂÒG'VRÀ¢’Óâ&Ææ6VDF–vW7E&W7VÇC ¢""$f–ÆÂ&7F–6R÷"ÆVv7’F&vWG2ÂF†Vâ&6¶f–ÆÂv—F‚VÆ—G’—FV×2à ¢&7F–6R×–ÆÆ"V÷F2&RF†R7G&öævW7B6öç7G&–çBv†Vâ6öæf–wW&VBà¢WfW'’6æF–FFR†2Ç&VG’76VBF†R&öf–ÆRF‡&W6†öÆBÂ6ò&6¶f–ÆÀ¢6ææ÷B–çG&öGV6RÆ÷r×VÆ—G’f–ÆÆW"â6÷W&6RæB6FVv÷'’62¶VWöæP¢fVæF÷"÷"&r×W"fVVBg&öÒFöÖ–æF–ærF†R&W7VÇBà¢"" ¢F–vW7BÒ6VÆbæ6öæf–ræF–vW7@¢6÷'FVEö—FV×2Ò6÷'FVB€¢—FV×2À¢¶W“ÖÆÖ&F—FVÓ¢€¢—FVÒç&ö6W76–ærææÇ—6—2ç66÷&P¢–b—FVÒç&ö6W76–æp¢æB—FVÒç&ö6W76–ærææÇ—6—0¢æB—FVÒç&ö6W76–ærææÇ—6—2ç66÷&R—2æ÷BæöæP¢VÇ6RÓ¢’À¢&WfW'6SÕG'VRÀ¢¢Æ–Ö—BÒF–vW7BæÖ…ö—FV×2÷"ÆVâ‡6÷'FVEö—FV×2¢6VÆV7FVC¢Æ—7E´6öçFVçD—FVÕÒÒµÐ¢6VÆV7FVEö–G3¢6WE·7G%ÒÒ6WB‚¢ÖG&—…ö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢&öf–ÆUö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢&Vv–öåö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢&7F–6Uö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢6÷W&6Uö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢&öGV7E÷6÷W&6Uö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB¢w&÷Wö6÷VçG3¢F–7E·7G"Â–çEÒÒFVfVÇFF–7B†–çB ¢6FVv÷'•÷Fõöw&÷W¢F–7E·7G"Â7G%ÒÒ·Ð¢f÷"w&÷Wö¶W’Âw&÷W–âF–vW7Bæ6FVv÷'•öw&÷W2æ—FV×2‚“ ¢f÷"6FVv÷'’–âw&÷Wæ6FVv÷&–W3 ¢6FVv÷'•÷Fõöw&÷Wç6WFFVfVÇB†6FVv÷'’Âw&÷Wö¶W’ ¢FVbF–ÖVç6–öç2†—FVÓ¢6öçFVçD—FVÒ’ÓâGWÆU·7G"Â7G"Â7G"Â7G%Ó ¢&Vv–öâÒ7G"†—FVÒæÖWFFFævWB‚'&Vv–öâ"’÷"&vÆö&Â"¢&öf–ÆRÒ€¢—FVÒç&ö6W76–æræ6Æ76–f–6F–öâç&öf–ÆP¢–b—FVÒç&ö6W76–æp¢VÇ6R6VÆbç&öf–ÆW2æFVfVÇE÷&öf–ÆP¢¢æÇ—6—2Ò—FVÒç&ö6W76–ærææÇ—6—2–b—FVÒç&ö6W76–ærVÇ6RæöæP¢&7F–6RÒ€¢æÇ—6—2ç&7F–6Uö6FVv÷'¢–bæÇ—6—2æBæÇ—6—2ç&7F–6Uö6FVv÷'¢VÇ6R7G"†—FVÒæÖWFFFævWB‚'&7F–6Uö6FVv÷'’"’÷"'Væ6Æ76–f–VB"¢¢&WGW&â&Vv–öâÂ&öf–ÆRÂb'·&Vv–öçÒ÷·&öf–ÆWÒ"Â&7F–6P ¢FVb6÷W&6Uö¶W’†—FVÓ¢6öçFVçD—FVÒ’Óâ7G# ¢†÷7FæÖRÒ‡W&Ç7Æ—B‡7G"†—FVÒçW&Â’’æ†÷7FæÖR÷"'Væ¶æ÷vâ"’æ66VföÆB‚¢&WGW&â†÷7FæÖRç&VÖ÷fW&Vf—‚‚'wwrâ" ¢FVbw&÷Wö¶W’†—FVÓ¢6öçFVçD—FVÒ’Óâ÷F–öæÅ·7G%Ó ¢6FVv÷'’Ò—FVÒæÖWFFFævWB‚&6FVv÷'’"¢&WGW&â6FVv÷'•÷Fõöw&÷WævWB†6FVv÷'’’–b—6–ç7Fæ6R†6FVv÷'’Â7G"’VÇ6RæöæP ¢FVb6åöFB†—FVÓ¢6öçFVçD—FVÒ’Óâ&ööÃ ¢òÂòÂòÂ&7F–6RÒF–ÖVç6–öç2†—FVÒ¢¶W’Ò6÷W&6Uö¶W’†—FVÒ¢–b€¢F–vW7BæÖ…ö—FV×5÷W%÷6÷W&6R—2æ÷BæöæP¢æB6÷W&6Uö6÷VçG5¶¶W•ÒãÒF–vW7BæÖ…ö—FV×5÷W%÷6÷W&6P¢“ ¢&WGW&âfÇ6P¢–b€¢&7F–6RÓÒ'FöF’×W6R ¢æBF–vW7BæÖ…÷FöF•÷W6U÷W%÷6÷W&6R—2æ÷BæöæP¢æB&öGV7E÷6÷W&6Uö6÷VçG5¶¶W•ÒãÒF–vW7BæÖ…÷FöF•÷W6U÷W%÷6÷W&6P¢“ ¢&WGW&âfÇ6P¢—FVÕöw&÷WÒw&÷Wö¶W’†—FVÒ¢–b—FVÕöw&÷W—2æ÷BæöæS ¢Æ–Ö—Eöf÷%öw&÷WÒF–vW7Bæ6FVv÷'•öw&÷W5¶—FVÕöw&÷WÒæÆ–Ö—@¢–bw&÷Wö6÷VçG5¶—FVÕöw&÷WÒãÒÆ–Ö—Eöf÷%öw&÷W ¢&WGW&âfÇ6P¢&WGW&âG'VP ¢FVbFB†—FVÓ¢6öçFVçD—FVÒ’ÓâæöæS ¢&Vv–öâÂ&öf–ÆRÂÖG&—…ö¶W’Â&7F–6RÒF–ÖVç6–öç2†—FVÒ¢¶W’Ò6÷W&6Uö¶W’†—FVÒ¢6VÆV7FVBæVæB†—FVÒ¢6VÆV7FVEö–G2æFB†—FVÒæ–B¢ÖG&—…ö6÷VçG5¶ÖG&—…ö¶W•Ò³Ò¢&öf–ÆUö6÷VçG5·&öf–ÆUÒ³Ò¢&Vv–öåö6÷VçG5·&Vv–öåÒ³Ò¢&7F–6Uö6÷VçG5·&7F–6UÒ³Ò¢6÷W&6Uö6÷VçG5¶¶W•Ò³Ò¢–b&7F–6RÓÒ'FöF’×W6R# ¢&öGV7E÷6÷W&6Uö6÷VçG5¶¶W•Ò³Ò¢—FVÕöw&÷WÒw&÷Wö¶W’†—FVÒ¢–b—FVÕöw&÷W—2æ÷BæöæS ¢w&÷Wö6÷VçG5¶—FVÕöw&÷WÒ³Ò¢—FVÒæÖWFFF²'&7F–6Uö6FVv÷'’%ÒÒ&7F–6P ¢–bF–vW7Bç&7F–6U÷F&vWG3 ¢f÷"&7F–6RÂF&vWB–âF–vW7Bç&7F–6U÷F&vWG2æ—FV×2‚“ ¢f÷"—FVÒ–â6÷'FVEö—FV×3 ¢–bÆVâ‡6VÆV7FVB’ãÒÆ–Ö—B÷"&7F–6Uö6÷VçG5·&7F–6UÒãÒF&vWC ¢'&V°¢–b—FVÒæ–B–â6VÆV7FVEö–G2÷"æ÷B6åöFB†—FVÒ“ ¢6öçF–çVP¢–bF–ÖVç6–öç2†—FVÒ•³5ÒÓÒ&7F–6S ¢FB†—FVÒ¢VÆ–bF–vW7BæÖG&—…÷F&vWG3 ¢f÷"—FVÒ–â6÷'FVEö—FV×3 ¢–bÆVâ‡6VÆV7FVB’ãÒÆ–Ö—C ¢'&V°¢òÂòÂÖG&—…ö¶W’ÂòÒF–ÖVç6–öç2†—FVÒ¢F&vWBÒF–vW7BæÖG&—…÷F&vWG2ævWB†ÖG&—…ö¶W’Â¢–bF&vWBæBÖG&—…ö6÷VçG5¶ÖG&—…ö¶W•ÒÂF&vWBæB6åöFB†—FVÒ“ ¢FB†—FVÒ¢VÇ6S ¢2&6·v&BÖ6ö×F–&ÆR–æFWVæFVçBF&vWG2v†VâæòÖG&—‚—27WÆ–VBà¢f÷"—FVÒ–â6÷'FVEö—FV×3 ¢–bÆVâ‡6VÆV7FVB’ãÒÆ–Ö—C ¢'&V°¢&Vv–öâÂ&öf–ÆRÂòÂòÒF–ÖVç6–öç2†—FVÒ¢æVVG5÷&öf–ÆRÒ&öf–ÆUö6÷VçG5·&öf–ÆUÒÂF–vW7Bç&öf–ÆU÷F&vWG2ævWB€¢&öf–ÆRÂ ¢¢æVVG5÷&Vv–öâÒ&Vv–öåö6÷VçG5·&Vv–öåÒÂF–vW7Bç&Vv–öå÷F&vWG2ævWB€¢&Vv–öâÂ ¢¢–b†æVVG5÷&öf–ÆR÷"æVVG5÷&Vv–öâ’æB6åöFB†—FVÒ“ ¢FB†—FVÒ ¢–bF–vW7BçVÆ—G•öf–ÆÂæBÆVâ‡6VÆV7FVB’ÂÆ–Ö—C ¢f÷"—FVÒ–â6÷'FVEö—FV×3 ¢–bÆVâ‡6VÆV7FVB’ãÒÆ–Ö—C ¢'&V°¢–b—FVÒæ–Bæ÷B–â6VÆV7FVEö–G2æB6åöFB†—FVÒ“ ¢FB†—FVÒ ¢f÷"&æ²Â—FVÒ–âVçVÖW&FR‡6VÆV7FVBÂ7F'CÓ“ ¢—FVÒæÖWFFF²&F–vW7E÷&æ²%ÒÒ&æ°¢–b&æ²ÃÒF–vW7BæFVWö—FV×3 ¢—FVÒæÖWFFF²'7VÖÖ'•öFWF‚%ÒÒ&FVW ¢—FVÒæÖWFFF²'7VÖÖ'•öÆVæwF…÷¦‚%ÒÒ#3ÓSZÙr ¢VÇ6S ¢—FVÒæÖWFFF²'7VÖÖ'•öFWF‚%ÒÒ&'&–Vb ¢—FVÒæÖWFFF²'7VÖÖ'•öÆVæwF…÷¦‚%ÒÒ#ÓƒZÙr  ¢–bÆös ¢6VÆbæ6öç6öÆRç&–çB€¢b'·6VÆbæ–6öç5²v&Ææ6Ru×ÒF&vWFVBF–vW7B6VÆV7FVB ¢b'¶ÆVâ‡6VÆV7FVB—Ò÷¶ÆVâ†—FV×2—Ò—FV×2 ¢¢f÷"&7F–6RÂF&vWB–âF–vW7Bç&7F–6U÷F&vWG2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò&7F–6R·&7F–6WÓ¢ ¢b'·&7F–6Uö6÷VçG2ævWB‡&7F–6RÂ—Ò÷·F&vWGÒ ¢¢f÷"ÖG&—…ö¶W’ÂF&vWB–âF–vW7BæÖG&—…÷F&vWG2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò¶ÖG&—…ö¶W—Ó¢ ¢b'¶ÖG&—…ö6÷VçG2ævWB†ÖG&—…ö¶W’Â—Ò÷·F&vWGÒ ¢¢f÷"&öf–ÆRÂF&vWB–âF–vW7Bç&öf–ÆU÷F&vWG2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò&öf–ÆR·&öf–ÆWÓ¢ ¢b'·&öf–ÆUö6÷VçG2ævWB‡&öf–ÆRÂ—Ò÷·F&vWGÒ ¢¢f÷"&Vv–öâÂF&vWB–âF–vW7Bç&Vv–öå÷F&vWG2æ—FV×2‚“ ¢6VÆbæ6öç6öÆRç&–çB€¢b"·6VÆbæ–6öç5²vFWF–Âu×Ò&Vv–öâ·&Vv–öçÓ¢ ¢b'·&Vv–öåö6÷VçG2ævWB‡&Vv–öâÂ—Ò÷·F&vWGÒ ¢¢6VÆbæ6öç6öÆRç&–çB‚"" ¢&WGW&â&Ææ6VDF–vW7E&W7VÇB€¢—FV×3×6VÆV7FVBÀ¢Væ&ÆVCÕG'VRÀ¢&öf–ÆUö6÷VçG3ÖF–7B‡&öf–ÆUö6÷VçG2’À¢&Vv–öåö6÷VçG3ÖF–7B‡&Vv–öåö6÷VçG2’À¢ÖG&—…ö6÷VçG3ÖF–7B†ÖG&—…ö6÷VçG2’À¢&7F–6Uö6÷VçG3ÖF–7B‡&7F–6Uö6÷VçG2’À¢w&÷Wö6÷VçG3ÖF–7B†w&÷Wö6÷VçG2’À¢ Ð¢7–æ2FVböW‡æE÷Gv—GFW%öF—67W76–öâ‡6VÆbÂ—FV×3¢Æ—7E´6öçFVçD—FVÕÒ’ÓâæöæS Ð¢""%6V6öæB×7FvS¢fWF6‚&WÇ’FW‡Bf÷"–×÷'FçBGv—GFW"—FV×2æB&RÖæÇ—¦RàÐ Ð¢öæÇ’'Vç2v†Vâ6÷W&6W2çGv—GFW"æfWF6…÷&WÇ•÷FW‡B—2G'VRàÐ¢&÷VæFVB'’Ö…÷GvVWG5÷FõöW‡æBFò6öçG&öÂ6÷7BàÐ¢"" Ð¢Guö6frÒ6VÆbæ6öæf–rç6÷W&6W2çGv—GFW Ð¢–bæ÷BGuö6fr÷"æ÷BGuö6fræVæ&ÆVB÷"æ÷BGuö6fræfWF6…÷&WÇ•÷FW‡C Ð¢&WGW&àÐ Ð¢g&öÒæÖöFVÇ2–×÷'B6÷W&6UG—PÐ Ð¢Gv—GFW%ö—FV×2Ò°Ð¢—FVÒf÷"—FVÒ–â—FV×0Ð¢–b—FVÒç6÷W&6U÷G—RÓÒ6÷W&6UG—RåEt•EDU Ð¢Õ³§Guö6fræÖ…÷GvVWG5÷FõöW‡æEÐÐ Ð¢–bæ÷BGv—GFW%ö—FV×3 Ð¢&WGW&àÐ Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢b'·6VÆbæ–6öç5²vF—67W76–öâu×ÒfWF6†–ær&WÇ’FW‡Bf÷" Ð¢b'¶ÆVâ‡Gv—GFW%ö—FV×2—ÒGv—GFW"—FV×2âââ Ð¢Ð Ð¢7–æ2v—F‚‡GG‚ä7–æ46Æ–VçB‡F–ÖV÷WCÓ3ã’26Æ–VçC Ð¢–bGuö6fræÖöFRÓÒ'Æ—w&–v‡B# Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢"·–VÆÆ÷uÕ&WÇ’W‡ç6–öâæ÷B–WB7W÷'FVB–âÆ—w&–v‡BÖöFRå²÷–VÆÆ÷uÒ Ð¢Ð¢&WGW&àÐ¢67&W"ÒGv—GFW%67&W"‡Guö6frÂ6Æ–VçBÐ¢W‡æFVBÒµÐÐ¢f÷"—FVÒ–âGv—GFW%ö—FV×3 Ð¢G'“ Ð¢&WÇ•öÆ–æW2Òv—B67&W"æfWF6…÷&WÆ–W5öf÷%ö—FVÒ†—FVÒÐ¢–bGv—GFW%67&W"æVæEöF—67W76–öåö6öçFVçB†—FVÒÂ&WÇ•öÆ–æW2“ Ð¢W‡æFVBæVæB†—FVÒÐ¢6VÆbæ6öç6öÆRç&–çB€Ð¢b"·6VÆbæ–6öç5²vF—67W76–öâu×Ò¶ÆVâ‡&WÇ•öÆ–æW2—Ò&WÆ–W2 Ð¢b&FFVBFó¢¶—FVÒçF—FÆU³£c×Ò Ð¢Ð¢W†6WBW†6WF–öâ2W†3 Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢b"·–VÆÆ÷u×·6VÆbæ–6öç5²wv&æ–æru×Ò&WÇ’fWF6‚f–ÆVBf÷" Ð¢b'¶—FVÒæ–GÓ¢¶W†7Õ²÷–VÆÆ÷uÒ Ð¢Ð Ð¢–bæ÷BW‡æFVC Ð¢&WGW&àÐ Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢b"&RÖæÇ—¦–ær¶ÆVâ†W‡æFVB—ÒGv—GFW"—FV×2v—F‚&WÇ’6öçFW‡BââåÆâ Ð¢Ð¢•ö6Æ–VçBÒ7&VFUö•ö6Æ–VçB‡6VÆbæ6öæf–ræ’Ð¢æÇ—¦W"Ò6öçFVçDæÇ—¦W"†•ö6Æ–VçBÂ6VÆbç&öf–ÆW2Â6öç6öÆS×6VÆbæ6öç6öÆRÐ¢v—BæÇ—¦W"ææÇ—¦Uö&F6‚†W‡æFVBÐ Ð¢7–æ2FVbVç&–6…ö—FV×2‡6VÆbÂ—FV×3¢Æ—7E´6öçFVçD—FVÕÒ’ÓâVç&–6†ÖVçD&F6…&W7VÇC Ð¢""$Vç&–6‚—FV×2v—F‚&6¶w&÷VæB¶æ÷vÆVFvRƒ&æB’72’àÐ Ð¢f÷"V6‚—FVÒF†B76VBF†R66÷&RF‡&W6†öÆBÂ6ÆÂ’FòvVæW&FPÐ¢&6¶w&÷VæB¶æ÷vÆVFvR&6VBöâF†R—FVÒw27GVÂ6öçFVçBàÐ Ð¢&w3 Ð¢—FV×3¢–×÷'FçB—FV×2FòVç&–6‚†ÖöF–f–VB–â×Æ6RÐ¢"" Ð¢–bæ÷B—FV×3 Ð¢&WGW&âVç&–6†ÖVçD&F6…&W7VÇB‚Ð Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢b'·6VÆbæ–6öç5²vVç&–6‚u×ÒVç&–6†–ærv—F‚&6¶w&÷VæB¶æ÷vÆVFvRâââ Ð¢Ð¢•ö6Æ–VçBÒ7&VFUö•ö6Æ–VçB‡6VÆbæ6öæf–ræ’Ð¢Vç&–6†W"Ò6öçFVçDVç&–6†W"€Ð¢•ö6Æ–VçBÀÐ¢6VÆbç&öf–ÆW2ÀÐ¢6VÆbæ6öæf–ræ’æÆæwVvW2ÀÐ¢6öç6öÆS×6VÆbæ6öç6öÆRÀÐ¢Ð¢&W7VÇBÒv—BVç&–6†W"æVç&–6…ö&F6‚†—FV×2Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢b"Vç&–6†VB·&W7VÇBç7V66VVFVEö6÷VçGÒ÷¶ÆVâ†—FV×2—Ò—FV×2 Ð¢Ð¢–b&W7VÇBæf–ÆVEö6÷VçC Ð¢6VÆbæ6öç6öÆRç&–çB€Ð¢b"·–VÆÆ÷uÕ6¶—VB·&W7VÇBæf–ÆVEö6÷VçGÒ—FV×2gFW"Vç&–6†ÖVçB Ð¢b&f–ÆVC¢²rÂræ¦ö–â‡&W7VÇBæf–ÆVEö–G2—Õ²÷–VÆÆ÷uÒ Ð¢Ð¢6VÆbæ6öç6öÆRç&–çB‚""Ð¢&WGW&â&W7VÇ@Ð Ð¢7–æ2FVbæÇ—¦Uö—FV×2‡6VÆbÂ—FV×3¢Æ—7E´6öçFVçD—FVÕÒ’ÓâÆ—7E´6öçFVçD—FVÕÓ Ð¢""$æÇ—¦R6öçFVçB—FV×2v—F‚’àÐ Ð¢&w3 Ð¢—FV×3¢—FV×2FòæÇ—¦PÐ Ð¢&WGW&ç3 Ð¢Æ—7E´6öçFVçD—FVÕÓ¢æÇ—¦VB—FV×0Ð¢"" Ð¢6VÆbæ6öç6öÆRç&–çB†b'·6VÆbæ–6öç5²v’u×ÒæÇ—¦–ær6öçFVçBv—F‚’âââ"Ð Ð¢•ö6Æ–VçBÒ7&VFUö•ö6Æ–VçB‡6VÆbæ6öæf–ræ’Ð¢æÇ—¦W"Ò6öçFVçDæÇ—¦W"†•ö6Æ–VçBÂ6VÆbç&öf–ÆW2Â6öç6öÆS×6VÆbæ6öç6öÆRÐ Ð¢&WGW&âv—BæÇ—¦W"ææÇ—¦Uö&F6‚†—FV×2Ð Ð¢7–æ2FVbövVæW&FU÷7VÖÖ'’€Ð¢6VÆbÀÐ¢—FV×3¢Æ—7E´6öçFVçD—FVÕÒÀÐ¢FFS¢7G"ÀÐ¢F÷FÅöfWF6†VC¢–çBÀÐ¢ÆæwVvS¢7G"Ò&Vâ"ÀÐ¢’Óâ7G# Ð¢""$vVæW&FRF–Ç’7VÖÖ'’àÐ Ð¢&w3 Ð¢—FV×3¢–×÷'FçB—FV×2Fò–æ6ÇVFR†Ç&VG’Vç&–6†VBv—F‚&6¶w&÷VæB÷&VÆFVBÐ¢FFS¢FFR7G&–æpÐ¢F÷FÅöfWF6†VC¢F÷FÂ—FV×2fWF6†V@Ð¢ÆæwVvS¢÷WGWBÆæwVvR‚&Vâ"÷"'¦‚"Ð Ð¢&WGW&ç3 Ð¢7G#¢Ö&¶F÷vâ7VÖÖ'Ð¢"" Ð¢6VÆbæ6öç6öÆRç&–çB†b'·6VÆbæ–6öç5²w7VÖÖ'’u×ÒvVæW&F–ærF–Ç’7VÖÖ'’âââ"Ð Ð¢7VÖÖ&—¦W"ÒF–Ç•7VÖÖ&—¦W"€Ð¢&öf–ÆUöæÖW3×6VÆbç&öf–ÆW2ææÖW2ÀÐ¢&öf–ÆUö÷&FW#×6VÆbæ6öæf–ræF–vW7Bç&öf–ÆUö÷&FW"ÀÐ¢Ð Ð¢&WGW&âv—B7VÖÖ&—¦W"ævVæW&FU÷7VÖÖ'’†—FV×2ÂFFRÂF÷FÅöfWF6†VBÂÆæwVvSÖÆæwVvRÐ 