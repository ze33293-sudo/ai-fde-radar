---
layout: default
title: Configuration Guide
---

# Configuration Guide

Horizon is configured through a `.env` file for secrets, a JSON file for runtime settings, and processing profiles for analysis and enrichment prompts. The JSON file defaults to `data/config.json`; profiles default to `profiles/`.

## Configuration Paths

`horizon`, `horizon-wizard`, and `horizon-webhook` all resolve configuration and state paths the same way:

| Option | Effect |
| --- | --- |
| `-d`, `--data-dir PATH` | Changes the state directory used for summaries, subscribers, and the default `<data-dir>/config.json` path. |
| `-c`, `--config PATH` | Uses an explicit config file without changing the state directory. |

```bash
uv run horizon --data-dir /srv/horizon
uv run horizon --config /etc/horizon/config.json
uv run horizon --data-dir /srv/horizon --config /etc/horizon/config.json
```

When both options are present, configuration is loaded from `--config`, while summaries and subscribers remain under `--data-dir`. Because this logic is identical across all three CLIs, passing the same `-d`/`-c` flags to each one keeps them pointed at the same files â€” for example, generating a config with `horizon-wizard --data-dir /srv/horizon`, then running `horizon --data-dir /srv/horizon` and testing with `horizon-webhook --data-dir /srv/horizon`.

Without either flag, all three default to `data/config.json`. To bootstrap a custom location without the wizard, initialize it manually:

```bash
mkdir -p /etc/horizon
cp data/config.example.json /etc/horizon/config.json
```

## Interactive Wizard

`horizon-wizard` asks about your interests and generates `data/config.json` from matched presets and, optionally, AI recommendations:

```bash
uv run horizon-wizard
```

| Option | Default | Description |
|--------|---------|-------------|
| `-d`, `--data-dir PATH` | `data` | Path to the data directory |
| `-c`, `--config PATH` | `<data-dir>/config.json` | Path to config file |
| `-l`, `--log-level LEVEL` | `WARNING` | Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |

## Terminal Icons

The `display.icon_style` setting controls icons printed to the terminal:

```json
{
  "display": {
    "icon_style": "nerd"
  }
}
```

Supported styles:

| Value | Description |
| --- | --- |
| `emoji` | Color emoji icons. This is the default when `display` is omitted. |
| `nerd` | Monochrome Nerd Font icons. Requires a Nerd Font in the terminal. |
| `ascii` | ASCII-only markers for terminals without Unicode icon support. |

This setting affects terminal output only. Icons embedded in generated Markdown
and webhook message content are unchanged.

## Processing Profiles

The `processing` section controls profile discovery and the fallback used when
automatic matching cannot select a profile:

```json
{
  "processing": {
    "profiles_dir": "profiles",
    "default_profile": "tech-news",
    "profile_settings": {
      "tech-news": {
        "threshold": 7.0,
        "topic_dedup": true,
        "require_actionable_within_7_days": false
      },
      "tech-blog": {
        "threshold": 4.0,
        "topic_dedup": false
      }
    }
  }
}
```

- `profiles_dir`: Directory containing one subdirectory per processing profile.
- `default_profile`: ID of a profile present in `profiles_dir`.
- `profile_settings`: User preferences keyed by profile ID. `threshold` accepts
  `0` through `10` or `null` for no score filter; `topic_dedup` defaults to
  `true`; `require_actionable_within_7_days` controls whether an analysis without
  a seven-day action is score-capped and defaults to `true` for backward
  compatibility. Unknown profile IDs are rejected when Horizon starts.

Each profile owns its matching, analysis, and enrichment behavior. Runtime
filtering preferences stay in the main JSON configuration. See [Processing
Profiles](profiles.md) for the file layout, complete schema, source routing
rules, and block tool permissions.

## AI Providers

Configure which AI model analyzes and enriches your content.

`api_key_env` is always an environment variable name, not the API key value.
Store secrets in `.env` or your shell environment, then point `api_key_env` at
that variable:

```bash
OPENAI_API_KEY=sk-your-key
GOOGLE_API_KEY=your-gemini-key
```

When Horizon starts, environment variables have priority because
the active config file does not store the secret. For local VS Code runs, create
`.env` in the repository root and launch Horizon from that same root directory.

Common API key variable names:

| Provider | `api_key_env` value |
| --- | --- |
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` |
| Gemini | `GOOGLE_API_KEY` |
| MiniMax | `MINIMAX_API_KEY` |
| Aliyun DashScope | `DASHSCOPE_API_KEY` |
| Doubao | `DOUBAO_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |

**Anthropic Claude**:

```json
{
  "ai": {
    "provider": "anthropic",
    "model": "claude-sonnet-4.5-20250929",
    "api_key_env": "ANTHROPIC_API_KEY",
    "throttle_sec": 0
  }
}
```

**OpenAI**:

```json
{
  "ai": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key_env": "OPENAI_API_KEY",
    "throttle_sec": 0
  }
}
```

**Gemini**:

```json
{
  "ai": {
    "provider": "gemini",
    "model": "gemini-2.0-flash",
    "api_key_env": "GOOGLE_API_KEY",
    "throttle_sec": 0
  }
}
```

**Azure OpenAI**:

```json
{
  "ai": {
    "provider": "azure",
    "model": "gpt-4o-production",
    "api_key_env": "AZURE_OPENAI_API_KEY",
    "azure_endpoint_env": "AZURE_OPENAI_ENDPOINT",
    "api_version": "2024-10-21",
    "throttle_sec": 0
  }
}
```

Set `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT` in your `.env`. The `model` field should be your Azure deployment name, not just the base model family name.

**MiniMax**:

The built-in provider defaults to `MiniMax-M3` and the global
OpenAI-compatible endpoint:

```json
{
  "ai": {
    "provider": "minimax",
    "model": "MiniMax-M3",
    "api_key_env": "MINIMAX_API_KEY",
    "base_url": "https://api.minimax.io/v1",
    "throttle_sec": 0
  }
}
```

Available models: `MiniMax-M3`, `MiniMax-M2.7`, `MiniMax-M2.7-highspeed`.

Use the endpoint for your account region and preferred compatible API:

| Region | OpenAI-compatible base URL | Anthropic-compatible base URL |
| --- | --- | --- |
| Global | `https://api.minimax.io/v1` | `https://api.minimax.io/anthropic` |
| China | `https://api.minimaxi.com/v1` | `https://api.minimaxi.com/anthropic` |

For the Anthropic-compatible API, keep `provider` set to `minimax` and pass
the base URL directly without adding `/v1`. Horizon selects its Anthropic
client for this endpoint, and the SDK appends `/v1/messages` when sending a
request:

```json
{
  "ai": {
    "provider": "minimax",
    "model": "MiniMax-M3",
    "api_key_env": "MINIMAX_API_KEY",
    "base_url": "https://api.minimax.io/anthropic",
    "throttle_sec": 0
  }
}
```

**Aliyun DashScope** (OpenAI-compatible):

```json
{
  "ai": {
    "provider": "ali",
    "model": "qwen-plus",
    "api_key_env": "DASHSCOPE_API_KEY",
    "throttle_sec": 0
  }
}
```

Use the [DashScope compatible-mode](https://help.aliyun.com/zh/dashscope/developer-reference/use-dashscope-by-calling-openai-api) endpoint. Set `DASHSCOPE_API_KEY` in your `.env`. Optional: set `base_url` to override the default `https://dashscope.aliyuncs.com/compatible-mode/v1`.

**Ollama**:

```json
{
  "ai": {
    "provider": "ollama",
    "model": "llama3.1",
    "api_key_env": "",
    "base_url": "http://192.168.1.10:11434",
    "throttle_sec": 0
  }
}
```

Omit `base_url` to use the default `http://localhost:11434/v1`.
For remote Ollama servers, set `ai.base_url` in the active config file or set
`HORIZON_OLLAMA_BASE_URL` in `.env`. `OLLAMA_BASE_URL` and `OLLAMA_HOST` are
also recognized. If the value omits `/v1`, Horizon appends it automatically
for Ollama's OpenAI-compatible endpoint.

### AI throttling

If your model has a strict per-minute request cap, you can slow the scorer down in the active config file:

```json
{
  "ai": {
    "throttle_sec": 4.5
  }
}
```

- `throttle_sec`: Pause between scored items in seconds. Default is `0`.
- `4.5` is a reasonable starting point for free-tier models capped around 15 requests per minute.
- Set it back to `0` if you have enough throughput headroom and want maximum speed.

### AI Concurrency

By default, AI scoring and enrichment run one item at a time. If your API endpoint supports concurrent requests, you can increase throughput:

```json
{
  "ai": {
    "analysis_concurrency": 4,
    "enrichment_concurrency": 2
  }
}
```

- `analysis_concurrency`: Number of items scored in parallel. Default is `1`.
- `enrichment_concurrency`: Number of high-scoring items enriched in parallel. Default is `1`.
- Both values are clamped to a minimum of `1`.
- Preserve the existing retry behavior per item.
- Result ordering is preserved regardless of concurrency.
- If you also use `throttle_sec`, each concurrent task sleeps independently after finishing an item.

**Custom Base URL** (for proxies):

```json
{
  "ai": {
    "provider": "anthropic",
    "base_url": "https://your-proxy.com/v1",
    ...
  }
}
```

For OpenAI-compatible gateways, Horizon sends `temperature` by default. If a newer reasoning-style model rejects that parameter with an error such as `temperature is deprecated for this model`, Horizon retries once without it and remembers that capability for later requests.

## Information Sources

All sources are configured under the top-level `sources` key in `config.json`.
Source entries also accept `profile`. An explicit profile ID uses that profile
without an AI matching call. If `profile` is missing or set to `"auto"`, Horizon
matches the item against the loaded profiles. An unknown explicit ID is an
error. For nested sources, set the field on the item-producing entry, such as an
RSS feed, Reddit subreddit or user, or OpenBB watchlist.

### GitHub

```json
{
  "sources": {
    "github": [
      {
        "type": "user_events",
        "username": "gvanrossum",
        "enabled": true,
        "category": "oss",
        "profile": "tech-news"
      },
      {
        "type": "repo_releases",
        "owner": "python",
        "repo": "cpython",
        "enabled": true,
        "category": "oss"
      }
    ]
  }
}
```

### Hacker News

```json
{
  "sources": {
    "hackernews": {
      "enabled": true,
      "fetch_top_stories": 30,
      "min_score": 100,
      "category": "tech"
    }
  }
}
```

### RSS Feeds

```json
{
  "sources": {
    "rss": [
      {
        "name": "Blog Name",
        "url": "https://example.com/feed.xml",
        "enabled": true,
        "category": "ai-ml",
        "profile": "auto",
        "include_title_keywords": ["customer support", "knowledge base"],
        "include_keywords": ["evaluation", "resolution rate"],
        "exclude_keywords": ["sponsored"]
      }
    ]
  }
}
```

Large official feeds can be narrowed before model scoring. `include_title_keywords`
requires at least one phrase in the entry title, while `include_keywords` searches
the title, feed body, and tags. `exclude_keywords` rejects an entry when any phrase
appears. Matching is case-insensitive. When multiple include fields are configured,
each configured field must match.

### Official customer-story indexes

```json
{
  "sources": {
    "customer_stories": [
      {
        "name": "Claude Customer Stories",
        "url": "https://claude.com/customers",
        "story_path_prefix": "/customers/",
        "max_results": 30,
        "profile": "ai-product-fde",
        "source_tier": 1,
        "practice_category": "enterprise-case"
      }
    ]
  }
}
```

This source reads canonical story links and real publication dates directly from
a first-party customer-story index. The story page is still opened and checked
before scoring, so a listing card alone cannot satisfy an enterprise-case minimum.

### Reddit

Reddit scraping is free and does not require API keys. Subreddit posts and comments prefer `old.reddit.com`; JSON and RSS endpoints are used as fallbacks when needed.

```json
{
  "sources": {
    "reddit": {
      "enabled": true,
      "fetch_comments": 5,
      "subreddits": [
        {
          "subreddit": "MachineLearning",
          "sort": "hot",
          "fetch_limit": 25,
          "min_score": 10,
          "category": "ai-ml"
        }
      ],
      "users": [
        {
          "username": "spez",
          "sort": "new",
          "fetch_limit": 10,
          "category": "social"
        }
      ]
    }
  }
}
```

### Telegram

Telegram scraping uses the public web preview at `https://t.me/s/<channel>`, so no API key is required. Only public channels are supported.

```json
{
  "sources": {
    "telegram": {
      "enabled": true,
      "channels": [
        {
          "channel": "zaihuapd",
          "enabled": true,
          "fetch_limit": 20,
          "category": "ai-news"
        }
      ]
    }
  }
}
```

- `enabled` â€” enable or disable Telegram fetching globally
- `channels` â€” list of public Telegram channels to monitor
- `channel` â€” Telegram channel username only, without `@` or the full `https://t.me/` URL
- `fetch_limit` â€” maximum number of recent messages to inspect per channel per run (default: `20`)
- `category` â€” optional tag for balanced digest grouping (e.g., `"ai-news"`, `"finance"`)

### Twitter

Requires an [Apify](https://apify.com) account. Set `APIFY_TOKEN` in your `.env` file. The free tier includes $5/month of credit, enough for roughly 20,000 tweets.

```json
{
  "sources": {
    "twitter": {
      "enabled": true,
      "users": ["karpathy", "ylecun"],
      "fetch_limit": 10,
      "category": "social",
      "fetch_reply_text": false,
      "max_replies_per_tweet": 3,
      "max_tweets_to_expand": 10,
      "reply_min_likes": 5
    }
  }
}
```

- `users` â€” Twitter screen names to monitor, without the `@` prefix
- `fetch_limit` â€” maximum tweets to fetch per run (across all users combined; minimum 100 due to actor constraint)
- `category` â€” optional tag for balanced digest grouping (applies to all tweets from this source)
- `fetch_reply_text` â€” when `true`, fetch actual reply bodies for important tweets and append them under `--- Top Comments ---` so the AI can factor in community discussion. Disabled by default.
- `max_replies_per_tweet` â€” maximum reply lines to append per tweet (default: 3)
- `max_tweets_to_expand` â€” cap on how many tweets get reply expansion per run, to control Apify credit usage (defaultÛ]:¶‰ËkºwµçI”°™…ÑÕ…°µ•Ù¥‘•¹”°…¹…Ñ•½Éä(€¡…É…Ñ•Ì¸%˜„µ¥¹¥µÕ´É•µ…¥¹ÌÕ¹µ•Ğ°‘•±¥Ù•Éä…‰½ÉÑÌ¸(´…¹‘¥‘…Ñ•}ÁÉ…Ñ¥•}É•Í•ÉÙ•Í€èA•Èµ½±Õµ¸µ½‘•°µÍ½É¥¹œÉ•Í•ÉÙ•Ì°¥¹‘•Á•¹‘•¹Ğ(€½˜™¥¹…°‘¥ÍÁ±…äÑ…É•ÑÌ¸UÍ”±…É•ÈÙ…±Õ•Ì™½È•Ù¥‘•¹”µ¡•…Ùä½È±½ÜµÙ½±Õµ”(€½±Õµ¹ÌìÕ¹ÕÍ•Í±½ÑÌÉ•ÑÕÉ¸Ñ¼Ñ¡”ÅÕ…±¥Ñäµ™¥ÉÍĞ…¹‘¥‘…Ñ”™¥±°¸]¡•¸Ñ¡”ÍÕ´(€•á••‘ÌÑ¡”…Ù…¥±…‰±”Á…ÍÌ‰Õ‘•Ğ°É•Í•ÉÙ•ÌÍ…±”ÁÉ½Á½ÉÑ¥½¹…±±ä¸(´ÁÉ•™±¥¡Ñ}ÁÉ…Ñ¥•}É•Í•ÉÙ•Í€è5…á¥µÕ´½É¥¥¹…°Á…•Ì½Á•¹•Á•È½±Õµ¸‰•™½É”(€Ñ¡”™¥ÉÍĞµ½‘•°É•ÅÕ•ÍĞ¸%¹…•ÍÍ¥‰±”Á…•Ì…É”É•µ½Ù•™½È™É•”¸%˜Ñ¡”µ…¥¸(€…¹Ñ…É•Ñ•™…±±‰…¬İ¥¹‘½İÌÍÑ¥±°…¹¹½ĞÍÕÁÁ±ä•Ù•ÉäÉ•ÅÕ¥É•½±Õµ¸°Ñ¡”(€ÉÕ¸•á¥ÑÌ‰•™½É”…±±¥¹œÑ¡”$ÁÉ½Ù¥‘•È¸™¥ÉÍĞµÁ…ÉÑäÑ¥•È´ÄIML•¹ÑÉäµ…äÕÍ”(€¥ÑÌ½µÁ±•Ñ”½¹Ñ•¹Ğé•¹½‘•‘€…ÉÑ¥±”İ¡•¸Ñ¡”±¥¹­•Á…”‰±½­Ì…ÕÑ½µ…Ñ¥½¸ì(€…¸½™™¥¥…°¥Ñ!ÕˆI•±•…Í”µ…ä±¥­•İ¥Í”ÕÍ”Ñ¡”É•±•…Í”‰½‘äÉ•ÑÕÉ¹•‰äÑ¡”(€¥Ñ!ÕˆA$¸(´•¹•É…Ñ•‘}¡…¹‘Í}½¹€èI•Í•ÉÙ”•á…Ñ±ä½¹”™¥¹…°Í±½Ğ™½È„€Ä×ŠLÌÀµ¥¹ÕÑ”…Ñ¥½¸(€…É•¹•É…Ñ•™É½´Ñ¡”Í•±•Ñ••áÑ•É¹…°¥Ñ•µÌ¸Q¡¥ÌÉ•ÅÕ¥É•Ì‰½Ñ Ñ¡”(€¡…¹‘Ìµ½¹€Ñ…É•Ğ…¹µ¥¹¥µÕ´Ñ¼•ÅÕ…°€Å€¸(´…Ñ•½Éå}É½ÕÁÍ€è=ÁÑ¥½¹…°µ…À½˜ÅÕ½Ñ„É½ÕÁÌ¸… É½ÕÀÉ•ÅÕ¥É•Ì„Á½Í¥Ñ¥Ù”4(€±¥µ¥Ñ€…¹„¹½¸µ•µÁÑä…Ñ•½É¥•Í€±¥ÍĞ¸%Ñ•µÌİ¥Ñ¡¥¸•… É½ÕÀ…É”­•ÁĞ‰ä4(€…¹…±åÍ¥ÌÍ½É”°¡¥¡•ÍĞ™¥ÉÍĞ¸4(´…Ñ•½Éå}É½ÕÁÌ¸¨¹¹…µ•€è=ÁÑ¥½¹…°‘¥ÍÁ±…ä¹…µ”ÕÍ•¥¸ÉÕ¸±½Ì4(´‘•™…Õ±Ñ}É½ÕÁ€èÉ½ÕÀ­•ä™½È¥Ñ•µÌİ¡½Í”…Ñ•½Éä‘½•Ì¹½Ğµ…Ñ …¹ä4(€½¹™¥ÕÉ•É½ÕÀ¸•™…Õ±Ğ¥Ì½Ñ¡•É€¸4(´‘•™…Õ±Ñ}É½ÕÁ}±¥µ¥Ñ€è=ÁÑ¥½¹…°Á½Í¥Ñ¥Ù”±¥µ¥Ğ™½ÈÕ¹µ…Ñ¡•¥Ñ•µÌ¸%˜½µ¥ÑÑ•°4(€Õ¹µ…Ñ¡•¥Ñ•µÌ…É”Õ¹±¥µ¥Ñ••á•ÁĞ™½Èµ…á}¥Ñ•µÍ€¸4(4)	…±…¹•‘¥•ÍĞ™¥±Ñ•É¥¹œÉÕ¹Ì…™Ñ•È½¹™¥ÕÉ•ÁÉ½™¥±”™¥±Ñ•É¥¹œ…¹Ñ½Á¥Œ4)‘•‘ÕÁ±¥…Ñ¥½¸°‰ÕĞ‰•™½É”•¹É¥¡µ•¹Ğ¸Q¡¥ÌÉ•‘Õ•Ì•¹É¥¡µ•¹Ğ…±±ÌÑ¼½¹±äÑ¡”4)¥Ñ•µÌÑ¡…Ğ…¸…ÁÁ•…È¥¸Ñ¡”™¥¹…°‘¥•ÍĞ¸4(4)É½ÕÀµ…Ñ¡¥¹œÕÍ•ÌÑ¡”Í½ÕÉ”…Ñ•½ÉäÍÑ½É•¥¸½¹Ñ•¹Ñ%Ñ•´¹µ•Ñ…‘…Ñ„¹…Ñ•½Éå€¸4)±°Í½ÕÉ”ÑåÁ•ÌÍÕÁÁ½ÉĞ„…Ñ•½Éå€™¥•±èÍ½ÕÉ•Ì¹ÉÍÍmt¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹¥Ñ¡Õ‰mt¹…Ñ•½Éå€°Í½ÕÉ•Ì¹¡…­•É¹•İÌ¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹É•‘‘¥Ğ¹ÍÕ‰É•‘‘¥ÑÍmt¹…Ñ•½Éå€°Í½ÕÉ•Ì¹É•‘‘¥Ğ¹ÕÍ•ÉÍmt¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹Ñ•±•É…´¹¡…¹¹•±Ímt¹…Ñ•½Éå€°Í½ÕÉ•Ì¹Ñİ¥ÑÑ•È¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹½Á•¹‰ˆ¹İ…Ñ¡±¥ÍÑÍmt¹…Ñ•½Éå€°Í½ÕÉ•Ì¹½ÍÍ¥¹Í¥¡Ğ¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹‘•±Ğ¹…Ñ•½Éå€°…¹Í½ÕÉ•Ì¹½½±•}¹•İÌ¹…Ñ•½Éå€¸4)M½ÕÉ•Ìİ¥Ñ¡½ÕĞ„…Ñ•½ÉäÍ•Ğ•¹Ñ•ÈÑ¡”‘•™…Õ±ĞÉ½ÕÀ¸4(4)%˜Ñ¡”Í…µ”…Ñ•½Éä…ÁÁ•…ÉÌ¥¸µÕ±Ñ¥Á±”É½ÕÁÌ°!½É¥é½¸±½Ì„İ…É¹¥¹œ…¹ÕÍ•Ì4)Ñ¡”™¥ÉÍĞÉ½ÕÀ¥¸½¹™¥ÕÉ…Ñ¥½¸½É‘•È¸=µ¥ÑÑ¥¹œ‰½Ñ …Ñ•½Éå}É½ÕÁÍ€…¹4)µ…á}¥Ñ•µÍ€‘¥Í…‰±•Ì‰…±…¹•‘¥•ÍĞ±¥µ¥ÑÌì½¹™¥ÕÉ•ÁÉ½™¥±”Ñ¡É•Í¡½±‘ÌÍÑ¥±°4)…ÁÁ±ä¸4(4(ŒŒ¹Ù¥É½¹µ•¹ĞY…É¥…‰±”MÕ‰ÍÑ¥ÑÕÑ¥½¸4(4)¹äÍÑÉ¥¹œÙ…±Õ”¥¸Ñ¡”…Ñ¥Ù”½¹™¥œ™¥±”ÍÕÁÁ½ÉÑÌ€‘íYI}95õ€Íå¹Ñ…à¸Y…É¥…‰±•Ì…É”•áÁ…¹‘•…ĞÉÕ¹Ñ¥µ”™É½´Ñ¡”•¹Ù¥É½¹µ•¹Ğ€¡¥¹±Õ‘¥¹œÙ…±Õ•Ì±½…‘•™É½´€¹•¹Ù€¤¸Q¡¥Ì±•ÑÌå½Ô­••ÀÍ•É•ÑÌ°Ñ•¹…¹ĞµÍÁ•¥™¥Œ•¹‘Á½¥¹ÑÌ°…¹ÁÉ¥Ù…Ñ”UI1Ì½ÕĞ½˜Ñ¡”¡•­•µ¥¸)M=8™¥±”¸4(4)á…µÁ±”è4(4)©Í½¸4)ì4(€€‰…¤ˆèì4(€€€€‰‰…Í•}ÕÉ°ˆè€ˆ‘í!=I%i=9}%}	M}UI1ôˆ4(€ô°4(€€‰Í½ÕÉ•Ìˆèì4(€€€€‰ÉÍÌˆèl4(€€€€€ì4(€€€€€€€€‰¹…µ”ˆè€‰1]8¹¹•Ğˆ°4(€€€€€€€€‰ÕÉ°ˆè€‰¡ÑÑÁÌè¼½±İ¸¹¹•Ğ½¡•…‘±¥¹•Ì½™Õ±±}Ñ•áĞı­•äô‘í1]9}-eôˆ°4(€€€€€€€€‰•¹…‰±•ˆèÑÉÕ”4(€€€€€ô4(€€€t4(€ô°4(€€‰İ•‰¡½½¬ˆèì4(€€€€‰ÕÉ±}•¹Øˆè€‰!=I%i=9}]	!==-}UI0ˆ°4(€€€€‰¡•…‘•ÉÌˆè€‰ÕÑ¡½É¥é…Ñ¥½¸è	•…É•È€‘í!=I%i=9}]	!==-}Q=-9ôˆ4(€ô4)ô4)€4(4(´€‘í95õ€¥ÌÉ•Á±…•½¹±äİ¡•¸95€¥Ì„Ù…±¥¥‘•¹Ñ¥™¥•È±¥­”1]9}-e€½È!=I%i=9}%}	M}UI1€¸4(´U¹Í•ĞÙ…É¥…‰±•Ì…É”±•™Ğ…Ì€‘í95õ€¥¹ÍÑ•…½˜‰•½µ¥¹œ…¸•µÁÑäÍÑÉ¥¹œ°Í¼½¹™¥ÕÉ…Ñ¥½¸µ¥ÍÑ…­•Ì™…¥°±½Õ‘±ä‘½İ¹ÍÑÉ•…´¸4(´áÁ…¹Í¥½¸¥ÌÉ•ÕÉÍ¥Ù”Ñ¡É½Õ ‘¥ÑÌ°±¥ÍÑÌ°…¹ÑÕÁ±•Ìì¹½¸µÍÑÉ¥¹œÙ…±Õ•Ì…É”±•™ĞÕ¹¡…¹•¸4(4(ŒŒµ…¥°MÕ‰ÍÉ¥ÁÑ¥½¸4(4)µ…¥°‘•±¥Ù•Éä¥Ì½ÁÑ¥½¹…°…¹‘¥Í…‰±•Õ¹±•ÍÌ•µ…¥°¹•¹…‰±•‘€¥ÌÑÉÕ•€¸!½É¥é½¸ÕÍ•ÌM5Q@Ñ¼Í•¹‘…¥±äÍÕµµ…É¥•Ì…¹%5@Ñ¼¡•¬ÍÕ‰ÍÉ¥‰”½Õ¹ÍÕ‰ÍÉ¥‰”É•ÅÕ•ÍÑÌ¸4(4)©Í½¸4)ì4(€€‰•µ…¥°ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÍµÑÁ}Í•ÉÙ•Èˆè€‰ÍµÑÀ¹ÅÄ¹½´ˆ°4(€€€€‰ÍµÑÁ}Á½ÉĞˆè€ĞØÔ°4(€€€€‰ÍµÑÁ}ÕÍ•É¹…µ”ˆè¹Õ±°°4(€€€€‰¥µ…Á}•¹…‰±•ˆèÑÉÕ”°4(€€€€‰¥µ…Á}Í•ÉÙ•Èˆè€‰¥µ…À¹ÅÄ¹½´ˆ°4(€€€€‰¥µ…Á}Á½ÉĞˆè€ääÌ°4(€€€€‰•µ…¥±}…‘‘É•ÍÌˆè€‰áááÅÄ¹½´ˆ°4(€€€€‰Á…ÍÍİ½É‘}•¹Øˆè€‰5%1}AMM]=Iˆ°4(€€€€‰Í•¹‘•É}¹…µ”ˆè€‰!½É¥é½¸…¥±äˆ°4(€€€€‰ÍÕ‰ÍÉ¥‰•}­•åİ½Éˆè€‰MU	MI%	ˆ°4(€€€€‰Õ¹ÍÕ‰ÍÉ¥‰•}­•åİ½Éˆè€‰U9MU	MI%	ˆ4(€ô4)ô4)€4(4(´•¹…‰±•‘€èQÕÉ¹Ì•µ…¥°ÍÕ‰ÍÉ¥ÁÑ¥½¸¡…¹‘±¥¹œ…¹‘…¥±ä•µ…¥°‘•±¥Ù•Éä½¸½È½™˜¸4(´ÍµÑÁ}Í•ÉÙ•É€€¼ÍµÑÁ}Á½ÉÑ€èM5Q@Í•ÉÙ•ÈÕÍ•Ñ¼Í•¹•µ…¥±Ì¸4(´ÍµÑÁ}ÕÍ•É¹…µ•€è=ÁÑ¥½¹…°M5Q@±½¥¸ÕÍ•É¹…µ”¸%˜½µ¥ÑÑ•°!½É¥é½¸ÕÍ•Ì•µ…¥±}…‘‘É•ÍÍ€¸4(´¥µ…Á}•¹…‰±•‘€èQÕÉ¹Ì%5@ÍÕ‰ÍÉ¥‰”½Õ¹ÍÕ‰ÍÉ¥‰”¡•­Ì½¸½È½™˜¸M•Ğ¥ĞÑ¼™…±Í•€™½ÈÍ•¹µ½¹±äM5Q@ÁÉ½Ù¥‘•ÉÌ¸4(´¥µ…Á}Í•ÉÙ•É€€¼¥µ…Á}Á½ÉÑ€è%5@Í•ÉÙ•ÈÕÍ•Ñ¼Í…¸¥¹½µ¥¹œÍÕ‰ÍÉ¥ÁÑ¥½¸É•ÅÕ•ÍÑÌİ¡•¸¥µ…Á}•¹…‰±•‘€¥ÌÑÉÕ•€¸4(´•µ…¥±}…‘‘É•ÍÍ€èM•¹‘•È…½Õ¹Ğ…¹µ…¥±‰½à¡•­•™½ÈÍÕ‰ÍÉ¥ÁÑ¥½¸É•ÅÕ•ÍÑÌ¸4(´Á…ÍÍİ½É‘}•¹Ù€è¹Ù¥É½¹µ•¹ĞÙ…É¥…‰±”½¹Ñ…¥¹¥¹œÑ¡”•µ…¥°Á…ÍÍİ½É½È…ÁÀÁ…ÍÍİ½É¸•™…Õ±ÑÌÑ¼5%1}AMM]=I€¸4(´Í•¹‘•É}¹…µ•€è¥ÍÁ±…ä¹…µ”Í¡½İ¸¥¸Í•¹Ğ•µ…¥±Ì¸4(´ÍÕ‰ÍÉ¥‰•}­•åİ½É‘€€¼Õ¹ÍÕ‰ÍÉ¥‰•}­•åİ½É‘€è-•åİ½É‘Ì!½É¥é½¸±½½­Ì™½È¥¸¥¹½µ¥¹œ•µ…¥°ÍÕ‰©•ÑÌ¸4(4)I•Í•¹M5Q@•á…µÁ±”è4(4)©Í½¸4)ì4(€€‰•µ…¥°ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÍµÑÁ}Í•ÉÙ•Èˆè€‰ÍµÑÀ¹É•Í•¹¹½´ˆ°4(€€€€‰ÍµÑÁ}Á½ÉĞˆè€ĞØÔ°4(€€€€‰ÍµÑÁ}ÕÍ•É¹…µ”ˆè€‰É•Í•¹ˆ°4(€€€€‰Á…ÍÍİ½É‘}•¹Øˆè€‰IM9}A%}-dˆ°4(€€€€‰¥µ…Á}•¹…‰±•ˆè™…±Í”°4(€€€€‰¥µ…Á}Í•ÉÙ•Èˆè€ˆˆ°4(€€€€‰¥µ…Á}Á½ÉĞˆè€ääÌ°4(€€€€‰•µ…¥±}…‘‘É•ÍÌˆè€‰¹½É•Á±å•á…µÁ±”¹½´ˆ°4(€€€€‰Í•¹‘•É}¹…µ”ˆè€‰!½É¥é½¸…¥±äˆ4(€ô4)ô4)€4(4)M•ĞIM9}A%}-e€¥¸€¹•¹Ù€¸I•¥Á¥•¹ÑÌ…É”±½…‘•™É½´€ñ‘…Ñ„µ‘¥Èø½ÍÕ‰ÍÉ¥‰•ÉÌ¹©Í½¹€€¡‘…Ñ„½ÍÕ‰ÍÉ¥‰•ÉÌ¹©Í½¹€‰ä‘•™…Õ±Ğ¤¸4(4(ŒŒ]•‰¡½½¬9½Ñ¥™¥…Ñ¥½¸4(4)]•‰¡½½¬¹½Ñ¥™¥…Ñ¥½¸¥Ì½ÁÑ¥½¹…°…¹‘¥Í…‰±•Õ¹±•ÍÌİ•‰¡½½¬¹•¹…‰±•‘€¥ÌÑÉÕ•€¸!½É¥é½¸…¸…±°•¥Í¡Ô½1…É¬°¥¹Q…±¬°M±…¬°¥Í½É°½È…¹äÕÍÑ½´İ•‰¡½½¬•¹‘Á½¥¹Ğİ¡•¸Ñ¡”Á¥Á•±¥¹”ÍÕ••‘Ì½È™…¥±Ì¸4(4)©Í½¸4)ì4(€€‰İ•‰¡½½¬ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÕÉ±}•¹Øˆè€‰!=I%i=9}]	!==-}UI0ˆ°4(€€€€‰‘•±¥Ù•Éäˆè€‰ÍÕµµ…Éäˆ°4(€€€€‰½Ù•ÉÙ¥•İ}Á½Í¥Ñ¥½¸ˆè€‰™¥ÉÍĞˆ°4(€€€€‰Á±…Ñ™½É´ˆè€‰•¹•É¥Œˆ°4(€€€€‰±…å½ÕĞˆè€‰µ…É­‘½İ¸ˆ°4(€€€€‰™…±±‰…­}±…å½ÕĞˆè€‰µ…É­‘½İ¸ˆ°4(€€€€‰±…¹Õ…•Ìˆè¹Õ±°°4(€€€€‰É•ÅÕ•ÍÑ}‰½‘äˆèì4(€€€€€€‰Ñ•áĞˆè€ˆíµ•ÍÍ…•}Ñ¥Ñ±•õq¸íÍÕµµ…Éåôˆ4(€€€ô°4(€€€€‰¡•…‘•ÉÌˆè€ˆˆ4(€ô4)ô4)€4(4(´•¹…‰±•‘€èQÕÉ¹Ìİ•‰¡½½¬‘•±¥Ù•Éä½¸½È½™˜¸Q¡”‘•™…Õ±Ğ¥Ì™…±Í•€¸4(´ÕÉ±}•¹Ù€è¹Ù¥É½¹µ•¹ĞÙ…É¥…‰±”Ñ¡…Ğ½¹Ñ…¥¹ÌÑ¡”İ•‰¡½½¬UI0¸½È•á…µÁ±”°Í•Ğ!=I%i=9}]	!==-}UI0õ¡ÑÑÁÌè¼¼¸¸¹€¥¸€¹•¹Ù€¸4(´‘•±¥Ù•Éå€è½¹ÑÉ½±Ì¡½Üµ•ÍÍ…•Ì…É”Í•¹Ğ¸UÍ”ÍÕµµ…Éå€™½È½¹”™Õ±°µ•ÍÍ…”°½ÈÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€™½È½¹”½Ù•ÉÙ¥•Üµ•ÍÍ…”™½±±½İ•‰ä½¹”µ•ÍÍ…”Á•ÈÍ•±•Ñ•¥Ñ•´¸4(´½Ù•ÉÙ¥•İ}Á½Í¥Ñ¥½¹€è½¹ÑÉ½±Ìİ¡•É”Ñ¡”½Ù•ÉÙ¥•Ü¥ÌÍ•¹Ğ¥¸ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€µ½‘”¸UÍ”™¥ÉÍÑ€™½ÈÑ¡”ÑÉ…‘¥Ñ¥½¹…°½É‘•È°½È±…ÍÑ€Ñ¼Í•¹¥Ñ•´‘•Ñ…¥±Ì¥¸É•Ù•ÉÍ”…¹­••ÀÑ¡”½Ù•ÉÙ¥•Ü…ÌÑ¡”¹•İ•ÍĞ¡…Ğµ•ÍÍ…”¸4(´Á±…Ñ™½Éµ€è=ÁÑ¥½¹…°İ•‰¡½½¬Á±…Ñ™½É´¡¥¹Ğ¸UÍ”•¹•É¥€‰ä‘•™…Õ±Ğ°½È™•¥Í¡Õ€€¼±…É­€Ñ¼•¹…‰±”Á±…Ñ™½É´µÍÁ•¥™¥Œ…ÉÉ•¹‘•É¥¹œ¸4(´±…å½ÕÑ€è½¹ÑÉ½±ÌÑ¡”µ•ÍÍ…”±…å½ÕĞ¸UÍ”µ…É­‘½İ¹€™½ÈÑ•µÁ±…Ñ•5…É­‘½İ¸‘•±¥Ù•Éä°½È½±±…ÁÍ¥‰±•€İ¥Ñ Á±…Ñ™½É´è€‰™•¥Í¡Ô‰€€¼€‰±…É¬‰€™½È„Í¥¹±”•¥Í¡Ô…É)M=8€È¸Àµ•ÍÍ…”İ¥Ñ •… ¥Ñ•´¥¸„½±±…ÁÍ•Á…¹•°¸4(´™…±±‰…­}±…å½ÕÑ€èI•Í•ÉÙ•™…±±‰…¬±…å½ÕĞ™½ÈÕ¹ÍÕÁÁ½ÉÑ•Á±…Ñ™½É´½±…å½ÕĞ½µ‰¥¹…Ñ¥½¹Ì¸Q¡”ÕÉÉ•¹ĞÍ…™”™…±±‰…¬¥Ìµ…É­‘½İ¹€¸4(´±…¹Õ…•Í€è=ÁÑ¥½¹…°İ•‰¡½½¬µ½¹±ä±…¹Õ…”™¥±Ñ•È¸UÍ”l‰é ‰u€½Èl‰•¸‰u€Ñ¼Í•¹½¹±äÍ•±•Ñ•±…¹Õ…•ÌìÕÍ”¹Õ±±€½È½µ¥Ğ¥ĞÑ¼Í•¹…±°½¹™¥ÕÉ•…¤¹±…¹Õ…•Í€¸4(´É•ÅÕ•ÍÑ}‰½‘å€è=ÁÑ¥½¹…°É•ÅÕ•ÍĞ‰½‘ä¸%˜•µÁÑä°!½É¥é½¸Í•¹‘Ì„Q€É•ÅÕ•ÍĞ¸%˜ÁÉ½Ù¥‘•°!½É¥é½¸Í•¹‘Ì„A=MQ€É•ÅÕ•ÍĞ¸4(´¡•…‘•ÉÍ€è=ÁÑ¥½¹…°ÕÍÑ½´¡•…‘•ÉÌ°½¹”-•äèY…±Õ•€Á…¥ÈÁ•È±¥¹”¸4(4)]¡•¸É•ÅÕ•ÍÑ}‰½‘å€¥Ì„)M=8½‰©•Ğ½È…ÉÉ…ä°!½É¥é½¸É•¹‘•ÉÌÁ±…•¡½±‘•ÉÌ…¹Í•É¥…±¥é•Ì¥Ğ…Ì)M=8¸]¡•¸¥Ğ¥Ì„ÍÑÉ¥¹œ°!½É¥é½¸É•¹‘•ÉÌ¥Ğ‘¥É•Ñ±ä…¹‘•Ñ•ÑÌ)M=8¥˜Ñ¡”É•¹‘•É•ÍÑÉ¥¹œ¥ÌÙ…±¥)M=8¸4(4(ŒŒŒ•±¥Ù•Éä5½‘•Ì¹1…å½ÕÑÌ4(4)‘•±¥Ù•Éå€½¹ÑÉ½±Ì¡½Üµ…¹äİ•‰¡½½¬µ•ÍÍ…•Ì!½É¥é½¸Í•¹‘Ìè4(4(´ÍÕµµ…Éå€èM•¹‘Ì½¹”µ•ÍÍ…”½¹Ñ…¥¹¥¹œÑ¡”™Õ±°‘…¥±äÍÕµµ…Éä¸Q¡¥Ì¥ÌÍ¥µÁ±”°‰ÕĞÍ½µ”¡…ĞÁ±…Ñ™½ÉµÌµ…äÉ•©•Ğ±½¹œµ•ÍÍ…•Ì¸4(´ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€èM•¹‘Ì½¹”½Ù•ÉÙ¥•Üµ•ÍÍ…”Á±ÕÌ½¹”µ•ÍÍ…”Á•ÈÍ•±•Ñ•¥Ñ•´¸%¸•… ¥Ñ•´µ•ÍÍ…”°€íÍÕµµ…Éåõ€½¹Ñ…¥¹Ì½¹±äÑ¡…Ğ¥Ñ•´Ì5…É­‘½İ¸‰½‘ä¸Q¡¥Ì¥ÌÕÍ•™Õ°™½ÈÁ±…Ñ™½ÉµÌÑ¡…ĞÉ•©•Ğ½ÈÑÉÕ¹…Ñ”±½¹œµ•ÍÍ…•Ì¸4(4)±…å½ÕÑ€½¹ÑÉ½±Ì¡½Ü•… µ•ÍÍ…”¥ÌÉ•¹‘•É•è4(4(´µ…É­‘½İ¹€èUÍ•Ìå½ÕÈÉ•ÅÕ•ÍÑ}‰½‘å€Ñ•µÁ±…Ñ”™½È•… µ•ÍÍ…”¸Q¡¥Ì¥ÌÑ¡”‘•™…Õ±Ğ…¹İ½É­Ìİ¥Ñ •¹•É¥Œİ•‰¡½½­Ì°¥¹Q…±¬°M±…¬°¥Í½É°•¥Í¡Ô°…¹1…É¬¸4(´½±±…ÁÍ¥‰±•€èÕÉÉ•¹Ñ±äÍÕÁÁ½ÉÑ•™½ÈÁ±…Ñ™½É´è€‰™•¥Í¡Ô‰€½È€‰±…É¬‰€¸!½É¥é½¸¥¹½É•ÌÉ•ÅÕ•ÍÑ}‰½‘å€…¹‰Õ¥±‘Ì½¹”•¥Í¡Ô½1…É¬…É)M=8€È¸Àµ•ÍÍ…”İ¥Ñ •… ¥Ñ•´¥¸„½±±…ÁÍ•Á…¹•°¸4(4)½ÈÁ±…Ñ™½ÉµÌİ¥Ñ¡½ÕĞ„Á±…Ñ™½É´µÍÁ•¥™¥Œ±…å½ÕĞ°­••À±…å½ÕĞè€‰µ…É­‘½İ¸‰€…¹¡½½Í”Ñ¡”µ•ÍÍ…”½Õ¹Ğİ¥Ñ ‘•±¥Ù•Éå€¸4(4)á…µÁ±”ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€5…É­‘½İ¸‘•±¥Ù•Éä½¹™¥œè4(4)©Í½¸4)ì4(€€‰İ•‰¡½½¬ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÕÉ±}•¹Øˆè€‰!=I%i=9}]	!==-}UI0ˆ°4(€€€€‰‘•±¥Ù•Éäˆè€‰ÍÕµµ…Éå}…¹‘}¥Ñ•µÌˆ°4(€€€€‰½Ù•ÉÙ¥•İ}Á½Í¥Ñ¥½¸ˆè€‰±…ÍĞˆ°4(€€€€‰Á±…Ñ™½É´ˆè€‰•¹•É¥Œˆ°4(€€€€‰±…å½ÕĞˆè€‰µ…É­‘½İ¸ˆ°4(€€€€‰É•ÅÕ•ÍÑ}‰½‘äˆèì4(€€€€€€‰Ñ•áĞˆè€ˆíµ•ÍÍ…•}Ñ¥Ñ±•õq¹q¸íÍÕµµ…Éäı±¥µ¥ĞôÌÀÀÀ™ÍÁ±¥Ğô´´µôˆ4(€€€ô4(€ô4)ô4)€4(4)]¥Ñ ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€°!½É¥é½¸Í•¹‘Ì½¹”½Ù•ÉÙ¥•ÜÁ±ÕÌ½¹”µ•ÍÍ…”Á•ÈÍ•±•Ñ•¥Ñ•´¸½Ù•ÉÙ¥•İ}Á½Í¥Ñ¥½¸è€‰±…ÍĞ‰€Í•¹‘Ì¥Ñ•´µ•ÍÍ…•Ì™¥ÉÍĞ…¹­••ÁÌÑ¡”½Ù•ÉÙ¥•Ü…ÌÑ¡”¹•İ•ÍĞ¡…Ğµ•ÍÍ…”ì½µ¥Ğ¥Ğ½ÈÍ•Ğ€‰™¥ÉÍĞ‰€Ñ¼Í•¹Ñ¡”½Ù•ÉÙ¥•Ü™¥ÉÍĞ¸4(4(ŒŒŒ]•‰¡½½¬Q•µÁ±…Ñ•Ì4(4)Ù…¥±…‰±”Ù…É¥…‰±•Ìè4(4)ğY…É¥…‰±”ğ•ÍÉ¥ÁÑ¥½¸ğ4)ğ´´´´´´´´´µğ´´´´´´´´´´´´µğ4)ğ€í‘…Ñ•õ€ğI•Á½ÉĞ‘…Ñ”°™½È•á…µÁ±”€ÈÀÈØ´ÀĞ´ÈÑ€ğ4)ğ€í±…¹Õ…•õ€ğ1…¹Õ…”½‘”°ÍÕ …Ì•¹€½Èé¡€ğ4)ğ€í¥µÁ½ÉÑ…¹Ñ}¥Ñ•µÍõ€ğ9Õµ‰•È½˜¥Ñ•µÌÍ•±•Ñ•‰äÁÉ½™¥±”™¥±Ñ•É¥¹œğ4)ğ€í…±±}¥Ñ•µÍõ€ğQ½Ñ…°¹Õµ‰•È½˜™•Ñ¡•¥Ñ•µÌğ4)ğ€íÉ•ÍÕ±Ñõ€ğÍÕ•ÍÍ€½È™…¥±•‘€ğ4)ğ€íÑ¥µ•ÍÑ…µÁõ€ğU¹¥àÑ¥µ•ÍÑ…µÀğ4)ğ€íµ•ÍÍ…•}Ñ¥Ñ±•õ€ğ5•ÍÍ…”Ñ¥Ñ±”°ÍÕ …ÌÑ¡”‘…¥±äÑ¥Ñ±”°½Ù•ÉÙ¥•ÜÑ¥Ñ±”°½È¥Ñ•´Ñ¥Ñ±”ğ4)ğ€íµ•ÍÍ…•}­¥¹‘õ€ğ5•ÍÍ…”­¥¹èÍÕµµ…Éå€°½Ù•ÉÙ¥•İ€°¥Ñ•µ€°™…¥±ÕÉ•€°½Èµ…¹Õ…±€ğ4)ğ€íÍÕµµ…Éåõ€ğ5•ÍÍ…”5…É­‘½İ¸¸%¸ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€µ½‘”Ñ¡¥Ì¥ÌÑ¡”½Ù•ÉÙ¥•Ü½È½¹”¥Ñ•´‰½‘ä°‘•Á•¹‘¥¹œ½¸Ñ¡”µ•ÍÍ…”ğ4(4)]¡•¸‘•±¥Ù•Éå€¥ÌÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€°¥Ñ•´µ•ÍÍ…•Ì…±Í¼¥¹±Õ‘”è4(4)ğY…É¥…‰±”ğ•ÍÉ¥ÁÑ¥½¸ğ4)ğ´´´´´´´´´µğ´´´´´´´´´´´´µğ4)ğ€í¥Ñ•µ}¥¹‘•áõ€ğ€Äµ‰…Í•¥Ñ•´¹Õµ‰•Èğ4)ğ€í¥Ñ•µ}½Õ¹Ñõ€ğQ½Ñ…°¹Õµ‰•È½˜¥Ñ•´µ•ÍÍ…•Ìğ4)ğ€íÁÉ½™¥±•}¥Ñ•µ}¥¹‘•áõ€ğ€Äµ‰…Í•¥Ñ•´¹Õµ‰•Èİ¥Ñ¡¥¸Ñ¡”ÕÉÉ•¹ĞAÉ½™¥±”ğ4)ğ€íÁÉ½™¥±•}¥Ñ•µ}½Õ¹Ñõ€ğ9Õµ‰•È½˜¥Ñ•´µ•ÍÍ…•Ì¥¸Ñ¡”ÕÉÉ•¹ĞAÉ½™¥±”ğ4)ğ€í¥Ñ•µ}ÁÉ½™¥±•õ€ğÕÉÉ•¹ĞAÉ½™¥±”%ğ4)ğ€í¥Ñ•µ}ÁÉ½™¥±•}¹…µ•õ€ğ1½…±¥é•ÕÉÉ•¹ĞAÉ½™¥±”¹…µ”ğ4)ğ€í¥Ñ•µ}Ñ¥Ñ±•õ€ğÕÉÉ•¹Ğ¥Ñ•´Ñ¥Ñ±”ğ4)ğ€í¥Ñ•µ}ÕÉ±õ€ğÕÉÉ•¹Ğ¥Ñ•´UI0ğ4)ğ€í¥Ñ•µ}Í½É•õ€ğÕÉÉ•¹Ğ¥Ñ•´…¹…±åÍ¥ÌÍ½É”ğ4(4)½Èİ•‰¡½½¬‘•±¥Ù•Éä°!½É¥é½¸™±…ÑÑ•¹Ì!Q50‘¥Í±½ÍÕÉ”‰±½­ÌÍÕ …Ì€ñ‘•Ñ…¥±ÌøñÍÕµµ…Éäø¸¸¸ğ½ÍÕµµ…Éäù€¥¸€íÍÕµµ…Éåõ€¥¹Ñ¼Á±…¥¸5…É­‘½İ¸±¥¹¬±¥ÍÑÌ¸Q¡¥Ìµ…­•ÌÑ¡”•¹•É…Ñ•ÍÕµµ…Éä•…Í¥•ÈÑ¼É•¹‘•È¥¸¡…ĞÁÉ½‘ÕÑÌ¸M…Ù•5…É­‘½İ¸™¥±•Ì°¥Ñ!ÕˆA…•Ì°…¹•µ…¥°½¹Ñ•¹Ğ…É”Õ¹¡…¹•¸4(4)UÍ”€í­•äı±¥µ¥Ğõ8™ÍÁ±¥Ğõ1%5õ€Ñ¼ÑÉÕ¹…Ñ”±½¹œÙ…±Õ•Ì‰äÍÁ±¥ÑÑ¥¹œ½¸1%5€…¹­••Á¥¹œÍ•µ•¹ÑÌÕ¹Ñ¥°Ñ¡”Ñ½Ñ…°¡…É…Ñ•È½Õ¹ĞÉ•…¡•Ì9€¸4(4)Ñ•áĞ4(íÍÕµµ…Éäı±¥µ¥ĞôÌÀÀÀ™ÍÁ±¥Ğô´´µô4)€4(4(ŒŒŒ¥¹Q…±¬4(4)%¸¥¹Q…±¬°É•…Ñ”„ÕÍÑ½´É½ÕÀÉ½‰½Ğ…¹ÕÍ”„ÕÍÑ½´­•åİ½ÉÍÕ …Ì!½É¥é½¹€¸Q¡”­•åİ½ÉµÕÍĞ…ÁÁ•…È¥¸Ñ¡”‰½‘ä½¹Ñ•¹Ğ¸4(4)©Í½¸4)ì4(€€‰µÍÑåÁ”ˆè€‰µ…É­‘½İ¸ˆ°4(€€‰µ…É­‘½İ¸ˆèì4(€€€€‰Ñ¥Ñ±”ˆè€‰!½É¥é½¸€í‘…Ñ•ô…¥±äˆ°4(€€€€‰Ñ•áĞˆè€‰!½É¥é½¸É•ÍÕ±Ğè€íÉ•ÍÕ±Ñõq¹q¹!½É¥é½¸¥µÁ½ÉÑ…¹Ğ¥Ñ•µÌè€í¥µÁ½ÉÑ…¹Ñ}¥Ñ•µÍô¼í…±±}¥Ñ•µÍõq¹q¸íÍÕµµ…Éåôˆ4(€ô4)ô4)€4(4(ŒŒŒ•¥Í¡Ô€¼1…É¬4(4)%¸•¥Í¡Ô½È1…É¬°É•…Ñ”„ÕÍÑ½´É½ÕÀÉ½‰½Ğ…¹ÕÍ”„ÕÍÑ½´­•åİ½ÉÍÕ …Ì!½É¥é½¹€¸Q¡”­•åİ½ÉµÕÍĞ…ÁÁ•…È¥¸Ñ¡”‰½‘ä½¹Ñ•¹Ğ¸4(4)UÍ”…É)M=8€È¸À™½È5…É­‘½İ¸É•¹‘•É¥¹œ¸Q¡”…ÉµÕÍĞ¥¹±Õ‘”€‰Í¡•µ„ˆè€ˆÈ¸À‰€…¹ÁÕĞÉ¥ µÑ•áĞ5…É­‘½İ¸½µÁ½¹•¹ÑÌÕ¹‘•È…É¹‰½‘ä¹•±•µ•¹ÑÍ€¸4(4)Q¼­••ÀÑ¡”É½ÕÀ¡…Ğ½µÁ…Ğİ¡¥±”ÍÑ¥±°…±±½İ¥¹œÉ•…‘•ÉÌÑ¼‰É½İÍ”Ñ¡”™Õ±°‰É¥•™¥¹œ¥¹Í¥‘”•¥Í¡Ô°ÕÍ”Ñ¡”½±±…ÁÍ¥‰±”±…å½ÕĞè4(4)©Í½¸4)ì4(€€‰İ•‰¡½½¬ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÕÉ±}•¹Øˆè€‰!=I%i=9}]	!==-}UI0ˆ°4(€€€€‰Á±…Ñ™½É´ˆè€‰™•¥Í¡Ôˆ°4(€€€€‰±…å½ÕĞˆè€‰½±±…ÁÍ¥‰±”ˆ°4(€€€€‰™…±±‰…­}±…å½ÕĞˆè€‰µ…É­‘½İ¸ˆ°4(€€€€‰±…¹Õ…•Ìˆèl‰é ‰t4(€ô4)ô4)€4(4)]¥Ñ Ñ¡¥Ì±…å½ÕĞ°!½É¥é½¸Í•¹‘Ì½¹”¥¹Ñ•É…Ñ¥Ù”…É½¹Ñ…¥¹¥¹œÑ¡”½Ù•ÉÙ¥•Ü…¹½¹”½±±…ÁÍ•Á…¹•°Á•ÈÍ•±•Ñ•¥Ñ•´¸… Á…¹•°…¸‰”•áÁ…¹‘•¥¸•¥Í¡ÔÑ¼É•…Ñ¡”™Õ±°¥Ñ•´‘•Ñ…¥°¸Q¡”É•Õ±…ÈÉ•ÅÕ•ÍÑ}‰½‘å€Ñ•µÁ±…Ñ”¥Ì¥¹½É•™½ÈÑ¡¥ÌÉ•¹‘•É•…É¸4(4)©Í½¸4)ì4(€€‰µÍ}ÑåÁ”ˆè€‰¥¹Ñ•É…Ñ¥Ù”ˆ°4(€€‰…Éˆèì4(€€€€‰Í¡•µ„ˆè€ˆÈ¸Àˆ°4(€€€€‰½¹™¥œˆèì4(€€€€€€‰İ¥‘•}ÍÉ••¹}µ½‘”ˆèÑÉÕ”4(€€€ô°4(€€€€‰¡•…‘•Èˆèì4(€€€€€€‰Ñ¥Ñ±”ˆèì4(€€€€€€€€‰Ñ…œˆè€‰Á±…¥¹}Ñ•áĞˆ°4(€€€€€€€€‰½¹Ñ•¹Ğˆè€ˆíµ•ÍÍ…•}Ñ¥Ñ±•ôˆ4(€€€€€ô°4(€€€€€€‰Ñ•µÁ±…Ñ”ˆè€‰‰±Õ”ˆ4(€€€ô°4(€€€€‰‰½‘äˆèì4(€€€€€€‰•±•µ•¹ÑÌˆèl4(€€€€€€€ì4(€€€€€€€€€€‰Ñ…œˆè€‰µ…É­‘½İ¸ˆ°4(€€€€€€€€€€‰½¹Ñ•¹Ğˆè€‰!½É¥é½¸É•ÍÕ±Ğè€íÉ•ÍÕ±Ñõq¹!½É¥é½¸¥µÁ½ÉÑ…¹Ğ¥Ñ•µÌè€í¥µÁ½ÉÑ…¹Ñ}¥Ñ•µÍô¼í…±±}¥Ñ•µÍôˆ4(€€€€€€€ô°4(€€€€€€€ì4(€€€€€€€€€€‰Ñ…œˆè€‰¡Èˆ4(€€€€€€€ô°4(€€€€€€€ì4(€€€€€€€€€€‰Ñ…œˆè€‰µ…É­‘½İ¸ˆ°4(€€€€€€€€€€‰½¹Ñ•¹Ğˆè€ˆíÍÕµµ…Éåôˆ4(€€€€€€€ô4(€€€€€t4(€€€ô4(€ô4)ô4)€4(4(ŒŒŒQ•ÍÑ¥¹œ4(4)UÍ”¡½É¥é½¸µİ•‰¡½½­€Ñ¼ÁÉ•Ù¥•Ü½ÈÍ•¹„Ñ•ÍĞ¹½Ñ¥™¥…Ñ¥½¸İ¥Ñ¡½ÕĞÉÕ¹¹¥¹œÑ¡”™Õ±°Á¥Á•±¥¹”è4(4)‰…Í 4)ÕØÉÕ¸¡½É¥é½¸µİ•‰¡½½¬€´µ‘ÉäµÉÕ¸4)€4(4)ğ=ÁÑ¥½¸ğ•™…Õ±Ğğ•ÍÉ¥ÁÑ¥½¸ğ4)ğ´´´´´´´µğ´´´´´´´´µğ´´´´´´´´´´´´µğ4)ğ€´µ±…¹œ19€ğ™¥ÉÍĞ½¹™¥ÕÉ•±…¹Õ…”ğ1…¹Õ…”Ñ¼Ñ•ÍĞğ4)ğ€´µ‘ÉäµÉÕ¹€ğ½™˜ğAÉ•Ù¥•ÜÉ•¹‘•É•½¹Ñ•¹Ğİ¥Ñ¡½ÕĞÍ•¹‘¥¹œğ4)ğ€´µ‘•±¥Ù•ÉäíÍÕµµ…Éä±ÍÕµµ…Éå}…¹‘}¥Ñ•µÍõ€ğÙ…±Õ”™É½´½¹™¥œğ=Ù•ÉÉ¥‘”‘•±¥Ù•Éäµ½‘”™½ÈÑ¡¥ÌÑ•ÍĞğ4)ğ€µ‘€°€´µ‘…Ñ„µ‘¥ÈAQ!€ğ‘…Ñ…€ğA…Ñ Ñ¼Ñ¡”‘…Ñ„‘¥É•Ñ½Éäğ4)ğ€µ€°€´µ½¹™¥œAQ!€ğ€ñ‘…Ñ„µ‘¥Èø½½¹™¥œ¹©Í½¹€ğA…Ñ Ñ¼½¹™¥œ™¥±”ğ4)ğ€µ±€°€´µ±½œµ±•Ù•°1Y1€ğ]I9%9€ğ1½¥¹œ±•Ù•°€¡	U½%9<½]I9%9½II=H½I%Q%0¤ğ4(4(4(ŒŒMÑ…Ñ¥ŒM¥Ñ”4(4)!½É¥é½¸İÉ¥Ñ•Ì•¹•É…Ñ•ÍÕµµ…É¥•ÌÑ¼‘…Ñ„½ÍÕµµ…É¥•Ì½€€¡½È€ñ‘…Ñ„µ‘¥Èø½ÍÕµµ…É¥•Ì½€İ¡•¸€´µ‘…Ñ„µ‘¥É€¥ÌÍ•Ğ¤…¹½Á¥•ÌÁÕ‰±¥Í¡…‰±”5…É­‘½İ¸¥¹Ñ¼‘½Ì½€™½ÈÑ¡”¥Ñ!ÕˆA…•ÌÍ¥Ñ”¸Q¡”É•Á½Í¥Ñ½Éä¥¹±Õ‘•Ì„É•…‘äµÑ¼µÕÍ”İ½É­™±½Ü…Ğ€¹¥Ñ¡Õˆ½İ½É­™±½İÌ½‘…¥±äµÍÕµµ…Éä¹åµ±€¸4(4)Q¼ÕÍ”¥Ñ!ÕˆA…•Ì°•¹…‰±”A…•Ì™½ÈÑ¡”É•Á½Í¥Ñ½Éä…¹ÉÕ¸Ñ¡”Í¡•‘Õ±•İ½É­™±½Ü½ÈÑÉ¥•È¥Ğµ…¹Õ…±±ä¸Q¡”•¹•É…Ñ•Í¥Ñ”¥Ì‰Õ¥±Ğ™É½´Ñ¡”‘½Ì½€‘¥É•Ñ½Éä¸4(4(ŒŒ5@M•ÉÙ•È4(4)!½É¥é½¸¥¹±Õ‘•Ì…¸5@Í•ÉÙ•È™½È$…ÍÍ¥ÍÑ…¹ÑÌ…¹5@µ½µÁ…Ñ¥‰±”±¥•¹ÑÌ¸4(4)‰…Í 4)ÕØÉÕ¸¡½É¥é½¸µµÀ4)€4(4)Ù…¥±…‰±”Ñ½½±Ì¥¹±Õ‘”¡é}Ù…±¥‘…Ñ•}½¹™¥€°¡é}™•Ñ¡}¥Ñ•µÍ€°¡é}Í½É•}¥Ñ•µÍ€°¡é}™¥±Ñ•É}¥Ñ•µÍ€°¡é}•¹É¥¡}¥Ñ•µÍ€°¡é}•¹•É…Ñ•}ÍÕµµ…Éå€°…¹¡é}ÉÕ¹}Á¥Á•±¥¹•€¸4(4)M•”mÍÉŒ½µÀ½I5¹µ‘t ¸¸½ÍÉŒ½µÀ½I5¹µ¤™½ÈÑ¡”™Õ±°Ñ½½°É•™•É•¹”…¹mÍÉŒ½µÀ½¥¹Ñ•É…Ñ¥½¸¹µ‘t ¸¸½ÍÉŒ½µÀ½¥¹Ñ•É…Ñ¥½¸¹µ¤™½È±¥•¹ĞÍ•ÑÕÀ¸4