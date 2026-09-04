"""Core data models for Horizon."""

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Annotated, Literal, Optional, List, Dict, Any, NamedTuple, Union
from pydantic import BaseModel, ConfigDict, HttpUrl, Field, field_validator, model_validator


class SourceType(str, Enum):
    """Supported information source types."""

    GITHUB = "github"
    HACKERNEWS = "hackernews"
    RSS = "rss"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    TWITTER = "twitter"
    OPENBB = "openbb"
    OSSINSIGHT = "ossinsight"
    GDELT = "gdelt"
    GOOGLE_NEWS = "google_news"
    HF_PAPERS = "hf_papers"
    CUSTOMER_STORIES = "customer_stories"


class SourceDefinition(NamedTuple):
    """How a top-level source is represented in SourcesConfig."""

    config_field: str
    config_is_list: bool = False
    item_fields: tuple[str, ...] = ()


SOURCE_REGISTRY = {
    SourceType.GITHUB.value: SourceDefinition("github", config_is_list=True),
    SourceType.HACKERNEWS.value: SourceDefinition("hackernews"),
    SourceType.RSS.value: SourceDefinition("rss", config_is_list=True),
    SourceType.REDDIT.value: SourceDefinition("reddit", item_fields=("subreddits", "users")),
    SourceType.TELEGRAM.value: SourceDefinition("telegram", item_fields=("channels",)),
    SourceType.TWITTER.value: SourceDefinition("twitter", item_fields=("users",)),
    SourceType.OPENBB.value: SourceDefinition("openbb", item_fields=("watchlists",)),
    SourceType.OSSINSIGHT.value: SourceDefinition("ossinsight"),
    SourceType.GDELT.value: SourceDefinition("gdelt"),
    SourceType.GOOGLE_NEWS.value: SourceDefinition("google_news"),
    SourceType.HF_PAPERS.value: SourceDefinition("hf_papers"),
    SourceType.CUSTOMER_STORIES.value: SourceDefinition(
        "customer_stories", config_is_list=True
    ),
}

ProfileRoute = Optional[Union[str, List[str]]]
SourceRegion = Literal["global", "china"]
PracticeCategory = Literal[
    "today-use",
    "enterprise-case",
    "method-pitfall",
    "beginner-tech",
    "industry-trend",
    "hands-on",
]


class ClassificationResult(BaseModel):
    """Resolved processing profile for a content item."""

    profile: str
    method: Literal["source_override", "ai_match"]
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    reason: Optional[str] = None


class ContentAnalysis(BaseModel):
    """Profile-driven first-pass analysis."""

    score: Optional[float] = Field(default=None, ge=0, le=10, allow_inf_nan=False)
    reason: str
    summary: str
    tags: List[str] = Field(default_factory=list)
    practice_category: Optional[PracticeCategory] = None
    actionable_within_7_days: Optional[bool] = None
    action: Optional[str] = None
    project_relevance: Optional[str] = None
    evidence_complete: Optional[bool] = None
    category_requirements_met: Optional[bool] = None
    evidence_note: Optional[str] = None


class ArtifactSource(BaseModel):
    """External source used while producing an artifact."""

    id: str
    title: str
    url: str


class ContentBlock(BaseModel):
    """A renderable section produced by an enrichment profile."""

    id: str
    type: Literal["section"] = "section"
    title: str
    content: str
    source_refs: List[str] = Field(default_factory=list)
    primary: bool = False


class ContentArtifact(BaseModel):
    """Localized, profile-defined enriched content."""

    language: str
    title: str
    blocks: List[ContentBlock] = Field(default_factory=list)
    sources: List[ArtifactSource] = Field(default_factory=list)


class ProcessingResult(BaseModel):
    """All AI processing state for a content item."""

    classification: ClassificationResult
    analysis: Optional[ContentAnalysis] = None
    artifacts: Dict[str, ContentArtifact] = Field(default_factory=dict)


class ContentItem(BaseModel):
    """Unified content item model from any source."""

    model_config = ConfigDict(extra="forbid")

    id: str  # Format: {source}:{subtype}:{native_id}
    source_type: SourceType
    title: str
    url: HttpUrl
    content: Optional[str] = None
    author: Optional[str] = None
    published_at: datetime
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    profile: ProfileRoute = None
    processing: Optional[ProcessingResult] = None


class AIProvider(str, Enum):
    """Supported AI providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    AZURE = "azure"
    ALI = "ali"
    GEMINI = "gemini"
    DOUBAO = "doubao"
    MINIMAX = "minimax"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"


# Provider-specific defaults used by setup and provider-chain expansion.
AI_PROVIDER_DEFAULTS = {
    AIProvider.ANTHROPIC: {
        "model": "claude-3-5-sonnet-20241022",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": None,
    },
    AIProvider.OPENAI: {
        "model": "gpt-4",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
    },
    AIProvider.AZURE: {
        "model": "gpt-4",
        "api_key_env": "AZURE_OPENAI_API_KEY",
        "base_url": None,
        "azure_endpoint_env": "AZURE_OPENAI_ENDPOINT",
        "api_version": "2024-10-21",
    },
    AIProvider.ALI: {
        "model": "qwen-plus",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    AIProvider.GEMINI: {
        "model": "gemini-1.5-flash",
        "api_key_env": "GOOGLE_API_KEY",
        "base_url": None,
    },
    AIProvider.DOUBAO: {
        "model": "doubao-pro-32k",
        "api_key_env": "DOUBAO_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    },
    AIProvider.MINIMAX: {
        "model": "MiniMax-M3",
        "api_key_env": "MINIMAX_API_KEY",
        "base_url": "https://api.minimax.io/v1",
    },
    AIProvider.DEEPSEEK: {
        "model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
    },
    AIProvider.OLLAMA: {
        "model": "llama3.1",
        "api_key_env": "",
        "base_url": "http://localhost:11434/v1",
    },
}


class AIConfig(BaseModel):
    """AI client configuration."""

    provider: AIProvider
    provider_chain: Optional[str] = None
    model: str
    base_url: Optional[str] = None
    api_key_env: str
    temperature: float = 0.3
    max_tokens: int = 4096
    throttle_sec: float = 0.0
    analysis_concurrency: int = 1
    enrichment_concurrency: int = 1
    languages: List[str] = Field(default_factory=lambda: ["en"])
    # Azure OpenAI specific; required when provider == AZURE
    azure_endpoint_env: Optional[str] = None
    api_version: Optional[str] = None

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, languages: List[str]) -> List[str]:
        """Allow conventional language tags while excluding path syntax."""
        language_tag = re.compile(r"^[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{1,8})*$")
        invalid = [language for language in languages if not language_tag.fullmatch(language)]
        if invalid:
            raise ValueError(f"invalid language code: {invalid[0]!r}")
        return languages


class GitHubSourceConfig(BaseModel):
    """GitHub source configuration."""

    type: str  # "user_events", "repo_releases", etc.
    username: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    enabled: bool = True
    category: Optional[str] = None
    profile: ProfileRoute = None
    region: SourceRegion = "global"
    source_tier: int = Field(default=1, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None


class HackerNewsConfig(BaseModel):
    """Hacker News configuration."""

    enabled: bool = True
    fetch_top_stories: int = 30
    min_score: int = 100
    category: Optional[str] = None
    profile: ProfileRoute = None
    region: SourceRegion = "global"
    source_tier: int = Field(default=3, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None


class ExtractorType(str, Enum):
    TRAFILATURA = "trafilatura"


class TrafilaturaExtractorConfig(BaseModel):
    type: Literal[ExtractorType.TRAFILATURA] = ExtractorType.TRAFILATURA
    favor_precision: bool = False
    favor_recall: bool = False


ExtractorConfig = Annotated[
    Union[TrafilaturaExtractorConfig],
    Field(discriminator="type"),
]


class RSSSourceConfig(BaseModel):
    """RSS feed source configuration."""

    name: str
    url: HttpUrl
    enabled: bool = True
    category: Optional[str] = None
    content_extractor: Optional[str] = None
    profile: ProfileRoute = None
    region: SourceRegion = "global"
    source_tier: int = Field(default=2, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None
    include_keywords: List[str] = Field(default_factory=list)
    include_title_keywords: List[str] = Field(default_factory=list)
    exclude_keywords: List[str] = Field(default_factory=list)

    @field_validator(
        "include_keywords", "include_title_keywords", "exclude_keywords"
    )
    @classmethod
    def validate_rss_keywords(cls, value: List[str]) -> List[str]:
        normalized = [keyword.strip() for keyword in value]
        if any(not keyword for keyword in normalized):
            raise ValueError("RSS keyword filters must not contain empty strings")
        return normalized


class CustomerStoriesSourceConfig(BaseModel):
    """First-party customer-story listing page configuration."""

    name: str
    url: HttpUrl
    enabled: bool = True
    story_path_prefix: str = "/customers/"
    max_results: int = Field(default=30, gt=0, le=100)
    category: Optional[str] = "official-enterprise-customer-case"
    profile: ProfileRoute = "ai-product-fde"
    region: SourceRegion = "global"
    source_tier: int = Field(default=1, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = "enterprise-case"

    @field_validator("story_path_prefix")
    @classmethod
    def validate_story_path_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/") or not normalized.endswith("/"):
            raise ValueError(
                "customer_stories.story_path_prefix must start and end with '/'"
            )
        return normalized


class RedditSubredditConfig(BaseModel):
    """Configuration for monitoring a specific subreddit."""

    subreddit: str
    enabled: bool = True
    sort: str = "hot"  # hot, new, top, rising
    time_filter: str = (
        "day"  # hour, day, week, month, year, all (only for top/controversial)
    )
    fetch_limit: int = 25
    min_score: int = 10
    category: Optional[str] = None
    profile: ProfileRoute = None
    region: SourceRegion = "global"
    source_tier: int = Field(default=3, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None


class RedditUserConfig(BaseModel):
    """Configuration for monitoring a specific Reddit user."""

    username: str  # without u/ prefix
    enabled: bool = True
    sort: str = "new"
    fetch_limit: int = 10
    category: Optional[str] = None
    profile: ProfileRoute = None
    region: SourceRegion = "global"
    source_tier: int = Field(default=3, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None


class RedditConfig(BaseModel):
    """Reddit source configuration."""

    enabled: bool = True
    subreddits: List[RedditSubredditConfig] = Field(default_factory=list)
    users: List[RedditUserConfig] = Field(default_factory=list)
    fetch_comments: int = 5  # top comments per post, 0 to disable


class TelegramChannelConfig(BaseModel):
    """Configuration for monitoring a specific Telegram channel."""

    channel: str  # channel username, e.g. "zaihuapd"
    enabled: bool = True
    fetch_limit: int = 20
    category: Optional[str] = None
    profile: ProfileRoute = None


class TelegramConfig(BaseModel):
    """Telegram source configuration."""

    enabled: bool = True
    channels: List[TelegramChannelConfig] = Field(default_factory=list)


class TwitterConfig(BaseModel):
    """Twitter source configuration.

    Two modes are supported:
    - "apify": Use Apify scweet actor (requires APIFY_TOKEN, more reliable)
    - "playwright": Use Playwright + browser cookies (free, no token needed)
    """

    enabled: bool = True
    mode: str = "apify"  # "apify" or "playwright"
    users: List[str] = Field(default_factory=list)
    fetch_limit: int = 10
    category: Optional[str] = None
    profile: ProfileRoute = None
    fetch_reply_text: bool = False
    max_replies_per_tweet: int = 3
    max_tweets_to_expand: int = 10
    reply_min_likes: int = 0
    # Apify settings (used when mode == "apify")
    apify_token_env: str = "APIFY_TOKEN"
    actor_id: str = "altimis~scweet"
    # Playwright settings (used when mode == "playwright")
    cookie_dir: str = "data"
    cookie_file_pattern: str = "x_cookies_*.json"


class OpenBBWatchlist(BaseModel):
    """A named watchlist of tickers fetched from one OpenBB provider.

    Each watchlist produces one news.company() call per run, so group
    symbols by provider rather than creating one watchlist per symbol.
    """

    name: str
    symbols: List[str] = Field(default_factory=list)
    enabled: bool = True
    provider: str = "yfinance"
    fetch_limit: int = 20
    category: Optional[str] = None
    profile: ProfileRoute = None


class OpenBBConfig(BaseModel):
    """OpenBB Platform source configuration.

    Uses the installed `openbb` SDK to fetch news and filings for a set of
    tickers. The SDK is an optional dependency; if it is not installed the
    scraper will no-op with a console warning rather than crash the run.

    Provider credentials (FMP, Benzinga, Polygon, Intrinio, Tiingo, etc.)
    are resolved by openbb from environment variables / its own user
    settings file, so Horizon does not need to pass them explicitly.
    """

    enabled: bool = True
    watchlists: List[OpenBBWatchlist] = Field(default_factory=list)
    fetch_filings: bool = False
    filings_provider: str = "sec"


class OSSInsightConfig(BaseModel):
    """OSS Insight trending repos source configuration.

    Pulls top star-gain repositories from the OSS Insight public API and
    emits them as ContentItems. Optional `keywords` filter limits results
    to repos whose description, repo name, or collection names contain at
    least one of the listed substrings (case-insensitive). Leave
    `keywords` empty to ingest everything trending in the configured
    languages.
    """

    enabled: bool = False
    period: str = "past_24_hours"  # past_24_hours, past_28_days
    languages: List[str] = Field(
        default_factory=lambda: ["All", "Python", "TypeScript"]
    )
    keywords: List[str] = Field(default_factory=list)
    min_stars: int = 5
    max_items: int = 30
    category: Optional[str] = None
    profile: ProfileRoute = None
    region: SourceRegion = "global"
    source_tier: int = Field(default=2, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None


class GDELTConfig(BaseModel):
    """GDELT 2.0 DOC API source configuration.

    Queries the key-less GDELT DOC API
    (https://api.gdeltproject.org/api/v2/doc/doc) for recent news articles
    matching a search query and emits them as ContentItems. No API key is
    required. The DOC API caps results at 250 records per request, so keep
    `max_records` modest.
    """

    enabled: bool = False
    query: str = "artificial intelligence"
    mode: str = "ArtList"
    max_records: int = 75  # GDELT DOC API caps at 250; keep modest
    timespan: Optional[str] = None  # e.g. "24h"; overrides since-derived window
    language: Optional[str] = None  # sourcelang filter, e.g. "english"; None = no filter
    country: Optional[str] = None  # sourcecountry filter; None = no filter
    category: Optional[str] = None  # Horizon category label for downstream grouping
    profile: ProfileRoute = None
    region: SourceRegion = "global"
    source_tier: int = Field(default=2, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None


class GoogleNewsConfig(BaseModel):
    """Google News RSS search source configuration.

    Builds Google News RSS search URLs
    (https://news.google.com/rss/search) for a query and parses the
    resulting feed via feedparser. No API key is required.
    """

    enabled: bool = False
    query: str = "artificial intelligence"
    language: str = "en"  # hl
    country: str = "US"  # gl
    ceid: Optional[str] = None  # when None scraper derives it as "{country}:{language}"
    max_results: int = 100  # cap ~100
    category: Optional[str] = None
    profile: ProfileRoute = None
    region: SourceRegion = "global"
    source_tier: int = Field(default=2, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None


class HuggingFacePapersConfig(BaseModel):
    """Hugging Face Daily Papers public API configuration."""

    enabled: bool = False
    max_results: int = Field(default=50, gt=0, le=100)
    sort: Literal["publishedAt", "trending"] = "publishedAt"
    category: Optional[str] = "daily-papers"
    profile: ProfileRoute = "tech-news"
    region: SourceRegion = "global"
    source_tier: int = Field(default=1, ge=1, le=3)
    practice_category: Optional[PracticeCategory] = None


class SourcesConfig(BaseModel):
    """All sources configuration."""

    github: List[GitHubSourceConfig] = Field(default_factory=list)
    hackernews: HackerNewsConfig = Field(default_factory=HackerNewsConfig)
    rss: List[RSSSourceConfig] = Field(default_factory=list)
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    twitter: Optional[TwitterConfig] = None
    openbb: Optional[OpenBBConfig] = None
    ossinsight: OSSInsightConfig = Field(default_factory=OSSInsightConfig)
    gdelt: Optional[GDELTConfig] = None
    google_news: Optional[Union[GoogleNewsConfig, List[GoogleNewsConfig]]] = None
    hf_papers: HuggingFacePapersConfig = Field(
        default_factory=HuggingFacePapersConfig
    )
    customer_stories: List[CustomerStoriesSourceConfig] = Field(
        default_factory=list
    )

    def google_news_queries(self) -> List[GoogleNewsConfig]:
        """Return Google News configuration in normalized list form.

        Both the historical single-object shape and the multi-query array shape
        remain valid configuration inputs.
        """
        if self.google_news is None:
            return []
        if isinstance(self.google_news, list):
            return self.google_news
        return [self.google_news]


class WebhookConfig(BaseModel):
    """Webhook notification configuration."""

    url_env: Optional[str] = (
        None  # Environment variable name containing the webhook URL
    )
    request_body: Optional[Union[str, dict, list]] = (
        None  # POST body: real JSON object or string with #{key} placeholders; if empty, will use GET
    )
    headers: Optional[str] = None  # Custom headers, "Key: Value" per line
    delivery: str = "summary"  # summary, or summary_and_items
    overview_position: str = "first"  # For summary_and_items: first, or last
    platform: str = "generic"  # generic, feishu, lark, dingtalk, slack, discord
    layout: str = "markdown"  # markdown, or collapsible
    fallback_layout: str = (
        "markdown"  # Layout to use when the requested layout is unsupported
    )
    languages: Optional[List[str]] = (
        None  # Optional language filter for webhook delivery; defaults to all AI languages
    )
    enabled: bool = False

    @field_validator("delivery")
    @classmethod
    def validate_delivery(cls, v: str) -> str:
        allowed = {"summary", "summary_and_items"}
        if v not in allowed:
            raise ValueError(f"webhook.delivery must be one of {allowed}, got '{v}'")
        return v

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        allowed = {"generic", "feishu", "lark", "dingtalk", "slack", "discord"}
        if v not in allowed:
            raise ValueError(f"webhook.platform must be one of {allowed}, got '{v}'")
        return v

    @field_validator("layout")
    @classmethod
    def validate_layout(cls, v: str) -> str:
        allowed = {"markdown", "collapsible"}
        if v not in allowed:
            raise ValueError(f"webhook.layout must be one of {allowed}, got '{v}'")
        return v

    @field_validator("fallback_layout")
    @classmethod
    def validate_fallback_layout(cls, v: str) -> str:
        allowed = {"markdown", "collapsible"}
        if v not in allowed:
            raise ValueError(
                f"webhook.fallback_layout must be one of {allowed}, got '{v}'"
            )
        return v

    @field_validator("overview_position")
    @classmethod
    def validate_overview_position(cls, v: str) -> str:
        allowed = {"first", "last"}
        if v not in allowed:
            raise ValueError(
                f"webhook.overview_position must be one of {allowed}, got '{v}'"
            )
        return v


class EmailConfig(BaseModel):
    """Email configuration for updates/subscriptions."""

    imap_server: str
    imap_port: int = 993
    imap_enabled: bool = True
    smtp_server: str
    smtp_port: int = 465
    smtp_username: Optional[str] = None
    email_address: str
    password_env: str = "EMAIL_PASSWORD"
    sender_name: str = "Horizon Daily"
    subscribe_keyword: str = "SUBSCRIBE"
    unsubscribe_keyword: str = "UNSUBSCRIBE"
    enabled: bool = False


class CategoryGroupConfig(BaseModel):
    """A quota group containing one or more source categories."""

    name: Optional[str] = None
    limit: int = Field(gt=0)
    categories: List[str] = Field(min_length=1)


class ProfileSettingsConfig(BaseModel):
    """User preferences applied to a processing profile at runtime."""

    model_config = ConfigDict(extra="forbid")

    threshold: Optional[float] = Field(default=None, ge=0, le=10)
    topic_dedup: bool = True
    require_actionable_within_7_days: bool = True


class ProcessingConfig(BaseModel):
    """Profile discovery and fallback settings."""

    model_config = ConfigDict(extra="forbid")

    profiles_dir: str = "profiles"
    default_profile: str = "tech-news"
    profile_settings: Dict[str, ProfileSettingsConfig] = Field(default_factory=dict)


class DisplayConfig(BaseModel):
    """Controls terminal output presentation."""

    model_config = ConfigDict(extra="forbid")

    icon_style: Literal["emoji", "nerd", "ascii"] = "emoji"


class CollectionConfig(BaseModel):
    """Controls which source items are fetched."""

    model_config = ConfigDict(extra="forbid")

    time_window_hours: int = Field(default=24, gt=0)
    fallback_window_hours: Optional[int] = Field(default=None, gt=0)
    candidate_limit: int = Field(default=60, gt=0)
    fallback_candidate_limit: int = Field(default=10, ge=0)
    history_days: int = Field(default=7, ge=0, le=365)
    history_path: str = "data/state/seen_items.json"
    sent_marker_dir: str = "data/state/sent"
    fetch_fulltext: bool = False


class DigestConfig(BaseModel):
    """Controls grouping and limits in the final digest."""

    model_config = ConfigDict(extra="forbid")

    max_items: Optional[int] = Field(default=None, gt=0)
    category_groups: Dict[str, CategoryGroupConfig] = Field(default_factory=dict)
    default_group: str = "other"
    default_group_limit: Optional[int] = Field(default=None, gt=0)
    profile_order: List[str] = Field(default_factory=list)
    profile_targets: Dict[str, int] = Field(default_factory=dict)
    region_targets: Dict[SourceRegion, int] = Field(default_factory=dict)
    matrix_targets: Dict[str, int] = Field(default_factory=dict)
    practice_targets: Dict[PracticeCategory, int] = Field(default_factory=dict)
    practice_minimums: Dict[PracticeCategory, int] = Field(default_factory=dict)
    candidate_practice_reserves: Dict[PracticeCategory, int] = Field(
        default_factory=dict
    )
    preflight_practice_reserves: Dict[PracticeCategory, int] = Field(
        default_factory=dict
    )
    generated_hands_on: bool = False
    quality_fill: bool = True
    deep_items: int = Field(default=5, ge=0)
    brief_items: int = Field(default=15, ge=0)
    fulltext_reserve: int = Field(default=5, ge=0)
    max_items_per_source: Optional[int] = Field(default=None, gt=0)
    max_today_use_per_source: Optional[int] = Field(default=1, gt=0)

    @field_validator("profile_order")
    @classmethod
    def validate_profile_order(cls, value: List[str]) -> List[str]:
        if any(not profile_id.strip() for profile_id in value):
            raise ValueError("digest.profile_order entries must be non-empty strings")
        if len(value) != len(set(value)):
            raise ValueError("digest.profile_order entries must be unique")
        return value

    @field_validator(
        "profile_targets",
        "matrix_targets",
        "practice_targets",
        "practice_minimums",
        "candidate_practice_reserves",
        "preflight_practice_reserves",
    )
    @classmethod
    def validate_positive_targets(cls, value: Dict[str, int]) -> Dict[str, int]:
        if any(not key.strip() for key in value):
            raise ValueError("digest target keys must be non-empty strings")
        if any(target < 0 for target in value.values()):
            raise ValueError("digest targets must be zero or positive")
        return value

    @field_validator("matrix_targets")
    @classmethod
    def validate_matrix_targets(cls, value: Dict[str, int]) -> Dict[str, int]:
        for key in value:
            region, separator, profile = key.partition("/")
            if separator != "/" or region not in {"global", "china"} or not profile:
                raise ValueError(
                    "digest.matrix_targets keys must use '<global|china>/<profile>'"
                )
        return value

    @model_validator(mode="after")
    def validate_practice_minimums(self):
        for category, minimum in self.practice_minimums.items():
            target = self.practice_targets.get(category)
            if target is not None and minimum > target:
                raise ValueError(
                    f"digest.practice_minimums.{category} cannot exceed its target"
                )
        if self.max_items is not None and sum(self.practice_minimums.values()) > self.max_items:
            raise ValueError("digest.practice_minimums cannot exceed digest.max_items")
        if self.generated_hands_on:
            if self.practice_targets.get("hands-on") != 1:
                raise ValueError(
                    "digest.generated_hands_on requires practice_targets.hands-on = 1"
                )
            if self.practice_minimums.get("hands-on") != 1:
                raise ValueError(
                    "digest.generated_hands_on requires practice_minimums.hands-on = 1"
                )
            if self.candidate_practice_reserves.get("hands-on", 0) > 0:
                raise ValueError(
                    "digest.generated_hands_on cannot reserve model candidates for hands-on"
                )
        if self.preflight_practice_reserves:
            missing_preflight = [
                category
                for category, minimum in self.practice_minimums.items()
                if category != "hands-on"
                and minimum > 0
                and self.preflight_practice_reserves.get(category, 0) <= 0
            ]
            if missing_preflight:
                raise ValueError(
                    "digest.preflight_practice_reserves must cover every required "
                    "external practice category: "
                    + ", ".join(sorted(missing_preflight))
                )
            if self.preflight_practice_reserves.get("hands-on", 0) > 0:
                raise ValueError(
                    "digest.preflight_practice_reserves cannot include generated hands-on"
                )
        return self


class MetricsConfig(BaseModel):
    """Controls public, secret-free run metric artifacts."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    output_dir: str = "docs/metrics"
    input_cost_per_million_usd: Optional[float] = Field(default=None, ge=0)
    output_cost_per_million_usd: Optional[float] = Field(default=None, ge=0)
    pricing_note: Optional[str] = None


class Config(BaseModel):
    """Main configuration model."""

    model_config = ConfigDict(extra="forbid")

    ai: AIConfig
    sources: SourcesConfig
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    digest: DigestConfig = Field(default_factory=DigestConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    extractors: Dict[str, ExtractorConfig] = Field(default_factory=dict)
    email: Optional[EmailConfig] = None
    webhook: Optional[WebhookConfig] = None
