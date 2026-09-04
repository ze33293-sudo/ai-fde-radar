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
- `max_tweets_to_expand` â€” cap on how many tweets get reply expansion per run, to control Apify credit usage (default: 10)
- `reply_min_likes` â€” only include replies with at least this many likes (default: 0)

The scraper uses the `altimis/scweet` actor by default. You can override it with `actor_id` if needed.

### OpenBB Financial News

OpenBB is useful when you want equity or macro news from providers such as yfinance, Benzinga, FMP, Intrinio, Tiingo, SEC, or Federal Reserve through one SDK.

Install the optional dependency before enabling the source:

```bash
uv sync --extra openbb
```

If your platform struggles to build transitive dependencies, prefer:

```bash
uv pip install --only-binary=:all: openbb openbb-benzin×®<¶‰žËkºwµçpµÍÕµµ…ÉäÍ•Ñ¥½¸ÁÉ¥½É¥Ñä¸1½…‘•ÁÉ½™¥±•Ì¹½Ð(€±¥ÍÑ•¡•É”…É”…ÁÁ•¹‘•…ÕÑ½µ…Ñ¥…±±ä¥¸ÁÉ½™¥±”‘¥Í½Ù•Éä½É‘•È¸U¹­¹½Ý¸½È4(€‘ÕÁ±¥…Ñ”ÁÉ½™¥±”%Ì…É”É•©•Ñ•¸Q¡”•á…µÁ±”ÁÉ¥½É¥Ñ¥é•ÌÑ¡”Ñ¡É•”±¥ÍÑ•4(€ÁÉ½™¥±•Ì¥¸Ñ¡…Ð½É‘•È¸(´ÁÉ…Ñ¥•}Ñ…É•ÑÍ€èEÕ…±¥Ñäµ™¥ÉÍÐÑ…É•Ð½Õ¹ÑÌ™½ÈÑ¡”Í¥à$I…‘…È(€½±Õµ¹Ì¸Q¡•Í”Ñ…É•ÑÌ‘¼¹½Ð…ÕÑ¡½É¥é”±½ÜµÅÕ…±¥Ñä™¥±±•È¸(´ÁÉ…Ñ¥•}µ¥¹¥µÕµÍ€èI•ÅÕ¥É•½Õ¹ÑÌ¸‰•±½ÜµÑ¡É•Í¡½±¥Ñ•´µ…äÍ…Ñ¥Í™ä½¹±ä„(€µ¥¹¥µÕ´…¹µÕÍÐÍÑ¥±°Á…ÍÌ½É¥¥¹…°µÍ½ÕÉ”°™…ÑÕ…°µ•Ù¥‘•¹”°…¹…Ñ•½Éä(€¡…É…Ñ•Ì¸%˜„µ¥¹¥µÕ´É•µ…¥¹ÌÕ¹µ•Ð°‘•±¥Ù•Éä…‰½ÉÑÌ¸(´…¹‘¥‘…Ñ•}ÁÉ…Ñ¥•}É•Í•ÉÙ•Í€èA•Èµ½±Õµ¸µ½‘•°µÍ½É¥¹œÉ•Í•ÉÙ•Ì°¥¹‘•Á•¹‘•¹Ð(€½˜™¥¹…°‘¥ÍÁ±…äÑ…É•ÑÌ¸UÍ”±…É•ÈÙ…±Õ•Ì™½È•Ù¥‘•¹”µ¡•…Ùä½È±½ÜµÙ½±Õµ”(€½±Õµ¹ÌìÕ¹ÕÍ•Í±½ÑÌÉ•ÑÕÉ¸Ñ¼Ñ¡”ÅÕ…±¥Ñäµ™¥ÉÍÐ…¹‘¥‘…Ñ”™¥±°¸]¡•¸Ñ¡”ÍÕ´(€•á••‘ÌÑ¡”…Ù…¥±…‰±”Á…ÍÌ‰Õ‘•Ð°É•Í•ÉÙ•ÌÍ…±”ÁÉ½Á½ÉÑ¥½¹…±±ä¸(´•¹•É…Ñ•‘}¡…¹‘Í}½¹€èI•Í•ÉÙ”•á…Ñ±ä½¹”™¥¹…°Í±½Ð™½È„€Ä×ŠLÌÀµ¥¹ÕÑ”…Ñ¥½¸(€…É•¹•É…Ñ•™É½´Ñ¡”Í•±•Ñ••áÑ•É¹…°¥Ñ•µÌ¸Q¡¥ÌÉ•ÅÕ¥É•Ì‰½Ñ Ñ¡”(€¡…¹‘Ìµ½¹€Ñ…É•Ð…¹µ¥¹¥µÕ´Ñ¼•ÅÕ…°€Å€¸(´…Ñ•½Éå}É½ÕÁÍ€è=ÁÑ¥½¹…°µ…À½˜ÅÕ½Ñ„É½ÕÁÌ¸… É½ÕÀÉ•ÅÕ¥É•Ì„Á½Í¥Ñ¥Ù”4(€±¥µ¥Ñ€…¹„¹½¸µ•µÁÑä…Ñ•½É¥•Í€±¥ÍÐ¸%Ñ•µÌÝ¥Ñ¡¥¸•… É½ÕÀ…É”­•ÁÐ‰ä4(€…¹…±åÍ¥ÌÍ½É”°¡¥¡•ÍÐ™¥ÉÍÐ¸4(´…Ñ•½Éå}É½ÕÁÌ¸¨¹¹…µ•€è=ÁÑ¥½¹…°‘¥ÍÁ±…ä¹…µ”ÕÍ•¥¸ÉÕ¸±½Ì4(´‘•™…Õ±Ñ}É½ÕÁ€èÉ½ÕÀ­•ä™½È¥Ñ•µÌÝ¡½Í”…Ñ•½Éä‘½•Ì¹½Ðµ…Ñ …¹ä4(€½¹™¥ÕÉ•É½ÕÀ¸•™…Õ±Ð¥Ì½Ñ¡•É€¸4(´‘•™…Õ±Ñ}É½ÕÁ}±¥µ¥Ñ€è=ÁÑ¥½¹…°Á½Í¥Ñ¥Ù”±¥µ¥Ð™½ÈÕ¹µ…Ñ¡•¥Ñ•µÌ¸%˜½µ¥ÑÑ•°4(€Õ¹µ…Ñ¡•¥Ñ•µÌ…É”Õ¹±¥µ¥Ñ••á•ÁÐ™½Èµ…á}¥Ñ•µÍ€¸4(4)	…±…¹•‘¥•ÍÐ™¥±Ñ•É¥¹œÉÕ¹Ì…™Ñ•È½¹™¥ÕÉ•ÁÉ½™¥±”™¥±Ñ•É¥¹œ…¹Ñ½Á¥Œ4)‘•‘ÕÁ±¥…Ñ¥½¸°‰ÕÐ‰•™½É”•¹É¥¡µ•¹Ð¸Q¡¥ÌÉ•‘Õ•Ì•¹É¥¡µ•¹Ð…±±ÌÑ¼½¹±äÑ¡”4)¥Ñ•µÌÑ¡…Ð…¸…ÁÁ•…È¥¸Ñ¡”™¥¹…°‘¥•ÍÐ¸4(4)É½ÕÀµ…Ñ¡¥¹œÕÍ•ÌÑ¡”Í½ÕÉ”…Ñ•½ÉäÍÑ½É•¥¸½¹Ñ•¹Ñ%Ñ•´¹µ•Ñ…‘…Ñ„¹…Ñ•½Éå€¸4)±°Í½ÕÉ”ÑåÁ•ÌÍÕÁÁ½ÉÐ„…Ñ•½Éå€™¥•±èÍ½ÕÉ•Ì¹ÉÍÍmt¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹¥Ñ¡Õ‰mt¹…Ñ•½Éå€°Í½ÕÉ•Ì¹¡…­•É¹•ÝÌ¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹É•‘‘¥Ð¹ÍÕ‰É•‘‘¥ÑÍmt¹…Ñ•½Éå€°Í½ÕÉ•Ì¹É•‘‘¥Ð¹ÕÍ•ÉÍmt¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹Ñ•±•É…´¹¡…¹¹•±Ímt¹…Ñ•½Éå€°Í½ÕÉ•Ì¹ÑÝ¥ÑÑ•È¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹½Á•¹‰ˆ¹Ý…Ñ¡±¥ÍÑÍmt¹…Ñ•½Éå€°Í½ÕÉ•Ì¹½ÍÍ¥¹Í¥¡Ð¹…Ñ•½Éå€°4)Í½ÕÉ•Ì¹‘•±Ð¹…Ñ•½Éå€°…¹Í½ÕÉ•Ì¹½½±•}¹•ÝÌ¹…Ñ•½Éå€¸4)M½ÕÉ•ÌÝ¥Ñ¡½ÕÐ„…Ñ•½ÉäÍ•Ð•¹Ñ•ÈÑ¡”‘•™…Õ±ÐÉ½ÕÀ¸4(4)%˜Ñ¡”Í…µ”…Ñ•½Éä…ÁÁ•…ÉÌ¥¸µÕ±Ñ¥Á±”É½ÕÁÌ°!½É¥é½¸±½Ì„Ý…É¹¥¹œ…¹ÕÍ•Ì4)Ñ¡”™¥ÉÍÐÉ½ÕÀ¥¸½¹™¥ÕÉ…Ñ¥½¸½É‘•È¸=µ¥ÑÑ¥¹œ‰½Ñ …Ñ•½Éå}É½ÕÁÍ€…¹4)µ…á}¥Ñ•µÍ€‘¥Í…‰±•Ì‰…±…¹•‘¥•ÍÐ±¥µ¥ÑÌì½¹™¥ÕÉ•ÁÉ½™¥±”Ñ¡É•Í¡½±‘ÌÍÑ¥±°4)…ÁÁ±ä¸4(4(ŒŒ¹Ù¥É½¹µ•¹ÐY…É¥…‰±”MÕ‰ÍÑ¥ÑÕÑ¥½¸4(4)¹äÍÑÉ¥¹œÙ…±Õ”¥¸Ñ¡”…Ñ¥Ù”½¹™¥œ™¥±”ÍÕÁÁ½ÉÑÌ€‘íYI}95õ€Íå¹Ñ…à¸Y…É¥…‰±•Ì…É”•áÁ…¹‘•…ÐÉÕ¹Ñ¥µ”™É½´Ñ¡”•¹Ù¥É½¹µ•¹Ð€¡¥¹±Õ‘¥¹œÙ…±Õ•Ì±½…‘•™É½´€¹•¹Ù€¤¸Q¡¥Ì±•ÑÌå½Ô­••ÀÍ•É•ÑÌ°Ñ•¹…¹ÐµÍÁ•¥™¥Œ•¹‘Á½¥¹ÑÌ°…¹ÁÉ¥Ù…Ñ”UI1Ì½ÕÐ½˜Ñ¡”¡•­•µ¥¸)M=8™¥±”¸4(4)á…µÁ±”è4(4)©Í½¸4)ì4(€€‰…¤ˆèì4(€€€€‰‰…Í•}ÕÉ°ˆè€ˆ‘í!=I%i=9}%}	M}UI1ôˆ4(€ô°4(€€‰Í½ÕÉ•Ìˆèì4(€€€€‰ÉÍÌˆèl4(€€€€€ì4(€€€€€€€€‰¹…µ”ˆè€‰1]8¹¹•Ðˆ°4(€€€€€€€€‰ÕÉ°ˆè€‰¡ÑÑÁÌè¼½±Ý¸¹¹•Ð½¡•…‘±¥¹•Ì½™Õ±±}Ñ•áÐý­•äô‘í1]9}-eôˆ°4(€€€€€€€€‰•¹…‰±•ˆèÑÉÕ”4(€€€€€ô4(€€€t4(€ô°4(€€‰Ý•‰¡½½¬ˆèì4(€€€€‰ÕÉ±}•¹Øˆè€‰!=I%i=9}]	!==-}UI0ˆ°4(€€€€‰¡•…‘•ÉÌˆè€‰ÕÑ¡½É¥é…Ñ¥½¸è	•…É•È€‘í!=I%i=9}]	!==-}Q=-9ôˆ4(€ô4)ô4)€4(4(´€‘í95õ€¥ÌÉ•Á±…•½¹±äÝ¡•¸95€¥Ì„Ù…±¥¥‘•¹Ñ¥™¥•È±¥­”1]9}-e€½È!=I%i=9}%}	M}UI1€¸4(´U¹Í•ÐÙ…É¥…‰±•Ì…É”±•™Ð…Ì€‘í95õ€¥¹ÍÑ•…½˜‰•½µ¥¹œ…¸•µÁÑäÍÑÉ¥¹œ°Í¼½¹™¥ÕÉ…Ñ¥½¸µ¥ÍÑ…­•Ì™…¥°±½Õ‘±ä‘½Ý¹ÍÑÉ•…´¸4(´áÁ…¹Í¥½¸¥ÌÉ•ÕÉÍ¥Ù”Ñ¡É½Õ ‘¥ÑÌ°±¥ÍÑÌ°…¹ÑÕÁ±•Ìì¹½¸µÍÑÉ¥¹œÙ…±Õ•Ì…É”±•™ÐÕ¹¡…¹•¸4(4(ŒŒµ…¥°MÕ‰ÍÉ¥ÁÑ¥½¸4(4)µ…¥°‘•±¥Ù•Éä¥Ì½ÁÑ¥½¹…°…¹‘¥Í…‰±•Õ¹±•ÍÌ•µ…¥°¹•¹…‰±•‘€¥ÌÑÉÕ•€¸!½É¥é½¸ÕÍ•ÌM5Q@Ñ¼Í•¹‘…¥±äÍÕµµ…É¥•Ì…¹%5@Ñ¼¡•¬ÍÕ‰ÍÉ¥‰”½Õ¹ÍÕ‰ÍÉ¥‰”É•ÅÕ•ÍÑÌ¸4(4)©Í½¸4)ì4(€€‰•µ…¥°ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÍµÑÁ}Í•ÉÙ•Èˆè€‰ÍµÑÀ¹ÅÄ¹½´ˆ°4(€€€€‰ÍµÑÁ}Á½ÉÐˆè€ÐØÔ°4(€€€€‰ÍµÑÁ}ÕÍ•É¹…µ”ˆè¹Õ±°°4(€€€€‰¥µ…Á}•¹…‰±•ˆèÑÉÕ”°4(€€€€‰¥µ…Á}Í•ÉÙ•Èˆè€‰¥µ…À¹ÅÄ¹½´ˆ°4(€€€€‰¥µ…Á}Á½ÉÐˆè€ääÌ°4(€€€€‰•µ…¥±}…‘‘É•ÍÌˆè€‰áááÅÄ¹½´ˆ°4(€€€€‰Á…ÍÍÝ½É‘}•¹Øˆè€‰5%1}AMM]=Iˆ°4(€€€€‰Í•¹‘•É}¹…µ”ˆè€‰!½É¥é½¸…¥±äˆ°4(€€€€‰ÍÕ‰ÍÉ¥‰•}­•åÝ½Éˆè€‰MU	MI%	ˆ°4(€€€€‰Õ¹ÍÕ‰ÍÉ¥‰•}­•åÝ½Éˆè€‰U9MU	MI%	ˆ4(€ô4)ô4)€4(4(´•¹…‰±•‘€èQÕÉ¹Ì•µ…¥°ÍÕ‰ÍÉ¥ÁÑ¥½¸¡…¹‘±¥¹œ…¹‘…¥±ä•µ…¥°‘•±¥Ù•Éä½¸½È½™˜¸4(´ÍµÑÁ}Í•ÉÙ•É€€¼ÍµÑÁ}Á½ÉÑ€èM5Q@Í•ÉÙ•ÈÕÍ•Ñ¼Í•¹•µ…¥±Ì¸4(´ÍµÑÁ}ÕÍ•É¹…µ•€è=ÁÑ¥½¹…°M5Q@±½¥¸ÕÍ•É¹…µ”¸%˜½µ¥ÑÑ•°!½É¥é½¸ÕÍ•Ì•µ…¥±}…‘‘É•ÍÍ€¸4(´¥µ…Á}•¹…‰±•‘€èQÕÉ¹Ì%5@ÍÕ‰ÍÉ¥‰”½Õ¹ÍÕ‰ÍÉ¥‰”¡•­Ì½¸½È½™˜¸M•Ð¥ÐÑ¼™…±Í•€™½ÈÍ•¹µ½¹±äM5Q@ÁÉ½Ù¥‘•ÉÌ¸4(´¥µ…Á}Í•ÉÙ•É€€¼¥µ…Á}Á½ÉÑ€è%5@Í•ÉÙ•ÈÕÍ•Ñ¼Í…¸¥¹½µ¥¹œÍÕ‰ÍÉ¥ÁÑ¥½¸É•ÅÕ•ÍÑÌÝ¡•¸¥µ…Á}•¹…‰±•‘€¥ÌÑÉÕ•€¸4(´•µ…¥±}…‘‘É•ÍÍ€èM•¹‘•È…½Õ¹Ð…¹µ…¥±‰½à¡•­•™½ÈÍÕ‰ÍÉ¥ÁÑ¥½¸É•ÅÕ•ÍÑÌ¸4(´Á…ÍÍÝ½É‘}•¹Ù€è¹Ù¥É½¹µ•¹ÐÙ…É¥…‰±”½¹Ñ…¥¹¥¹œÑ¡”•µ…¥°Á…ÍÍÝ½É½È…ÁÀÁ…ÍÍÝ½É¸•™…Õ±ÑÌÑ¼5%1}AMM]=I€¸4(´Í•¹‘•É}¹…µ•€è¥ÍÁ±…ä¹…µ”Í¡½Ý¸¥¸Í•¹Ð•µ…¥±Ì¸4(´ÍÕ‰ÍÉ¥‰•}­•åÝ½É‘€€¼Õ¹ÍÕ‰ÍÉ¥‰•}­•åÝ½É‘€è-•åÝ½É‘Ì!½É¥é½¸±½½­Ì™½È¥¸¥¹½µ¥¹œ•µ…¥°ÍÕ‰©•ÑÌ¸4(4)I•Í•¹M5Q@•á…µÁ±”è4(4)©Í½¸4)ì4(€€‰•µ…¥°ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÍµÑÁ}Í•ÉÙ•Èˆè€‰ÍµÑÀ¹É•Í•¹¹½´ˆ°4(€€€€‰ÍµÑÁ}Á½ÉÐˆè€ÐØÔ°4(€€€€‰ÍµÑÁ}ÕÍ•É¹…µ”ˆè€‰É•Í•¹ˆ°4(€€€€‰Á…ÍÍÝ½É‘}•¹Øˆè€‰IM9}A%}-dˆ°4(€€€€‰¥µ…Á}•¹…‰±•ˆè™…±Í”°4(€€€€‰¥µ…Á}Í•ÉÙ•Èˆè€ˆˆ°4(€€€€‰¥µ…Á}Á½ÉÐˆè€ääÌ°4(€€€€‰•µ…¥±}…‘‘É•ÍÌˆè€‰¹½É•Á±å•á…µÁ±”¹½´ˆ°4(€€€€‰Í•¹‘•É}¹…µ”ˆè€‰!½É¥é½¸…¥±äˆ4(€ô4)ô4)€4(4)M•ÐIM9}A%}-e€¥¸€¹•¹Ù€¸I•¥Á¥•¹ÑÌ…É”±½…‘•™É½´€ñ‘…Ñ„µ‘¥Èø½ÍÕ‰ÍÉ¥‰•ÉÌ¹©Í½¹€€¡‘…Ñ„½ÍÕ‰ÍÉ¥‰•ÉÌ¹©Í½¹€‰ä‘•™…Õ±Ð¤¸4(4(ŒŒ]•‰¡½½¬9½Ñ¥™¥…Ñ¥½¸4(4)]•‰¡½½¬¹½Ñ¥™¥…Ñ¥½¸¥Ì½ÁÑ¥½¹…°…¹‘¥Í…‰±•Õ¹±•ÍÌÝ•‰¡½½¬¹•¹…‰±•‘€¥ÌÑÉÕ•€¸!½É¥é½¸…¸…±°•¥Í¡Ô½1…É¬°¥¹Q…±¬°M±…¬°¥Í½É°½È…¹äÕÍÑ½´Ý•‰¡½½¬•¹‘Á½¥¹ÐÝ¡•¸Ñ¡”Á¥Á•±¥¹”ÍÕ••‘Ì½È™…¥±Ì¸4(4)©Í½¸4)ì4(€€‰Ý•‰¡½½¬ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÕÉ±}•¹Øˆè€‰!=I%i=9}]	!==-}UI0ˆ°4(€€€€‰‘•±¥Ù•Éäˆè€‰ÍÕµµ…Éäˆ°4(€€€€‰½Ù•ÉÙ¥•Ý}Á½Í¥Ñ¥½¸ˆè€‰™¥ÉÍÐˆ°4(€€€€‰Á±…Ñ™½É´ˆè€‰•¹•É¥Œˆ°4(€€€€‰±…å½ÕÐˆè€‰µ…É­‘½Ý¸ˆ°4(€€€€‰™…±±‰…­}±…å½ÕÐˆè€‰µ…É­‘½Ý¸ˆ°4(€€€€‰±…¹Õ…•Ìˆè¹Õ±°°4(€€€€‰É•ÅÕ•ÍÑ}‰½‘äˆèì4(€€€€€€‰Ñ•áÐˆè€ˆíµ•ÍÍ…•}Ñ¥Ñ±•õq¸íÍÕµµ…Éåôˆ4(€€€ô°4(€€€€‰¡•…‘•ÉÌˆè€ˆˆ4(€ô4)ô4)€4(4(´•¹…‰±•‘€èQÕÉ¹ÌÝ•‰¡½½¬‘•±¥Ù•Éä½¸½È½™˜¸Q¡”‘•™…Õ±Ð¥Ì™…±Í•€¸4(´ÕÉ±}•¹Ù€è¹Ù¥É½¹µ•¹ÐÙ…É¥…‰±”Ñ¡…Ð½¹Ñ…¥¹ÌÑ¡”Ý•‰¡½½¬UI0¸½È•á…µÁ±”°Í•Ð!=I%i=9}]	!==-}UI0õ¡ÑÑÁÌè¼¼¸¸¹€¥¸€¹•¹Ù€¸4(´‘•±¥Ù•Éå€è½¹ÑÉ½±Ì¡½Üµ•ÍÍ…•Ì…É”Í•¹Ð¸UÍ”ÍÕµµ…Éå€™½È½¹”™Õ±°µ•ÍÍ…”°½ÈÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€™½È½¹”½Ù•ÉÙ¥•Üµ•ÍÍ…”™½±±½Ý•‰ä½¹”µ•ÍÍ…”Á•ÈÍ•±•Ñ•¥Ñ•´¸4(´½Ù•ÉÙ¥•Ý}Á½Í¥Ñ¥½¹€è½¹ÑÉ½±ÌÝ¡•É”Ñ¡”½Ù•ÉÙ¥•Ü¥ÌÍ•¹Ð¥¸ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€µ½‘”¸UÍ”™¥ÉÍÑ€™½ÈÑ¡”ÑÉ…‘¥Ñ¥½¹…°½É‘•È°½È±…ÍÑ€Ñ¼Í•¹¥Ñ•´‘•Ñ…¥±Ì¥¸É•Ù•ÉÍ”…¹­••ÀÑ¡”½Ù•ÉÙ¥•Ü…ÌÑ¡”¹•Ý•ÍÐ¡…Ðµ•ÍÍ…”¸4(´Á±…Ñ™½Éµ€è=ÁÑ¥½¹…°Ý•‰¡½½¬Á±…Ñ™½É´¡¥¹Ð¸UÍ”•¹•É¥€‰ä‘•™…Õ±Ð°½È™•¥Í¡Õ€€¼±…É­€Ñ¼•¹…‰±”Á±…Ñ™½É´µÍÁ•¥™¥Œ…ÉÉ•¹‘•É¥¹œ¸4(´±…å½ÕÑ€è½¹ÑÉ½±ÌÑ¡”µ•ÍÍ…”±…å½ÕÐ¸UÍ”µ…É­‘½Ý¹€™½ÈÑ•µÁ±…Ñ•5…É­‘½Ý¸‘•±¥Ù•Éä°½È½±±…ÁÍ¥‰±•€Ý¥Ñ Á±…Ñ™½É´è€‰™•¥Í¡Ô‰€€¼€‰±…É¬‰€™½È„Í¥¹±”•¥Í¡Ô…É)M=8€È¸Àµ•ÍÍ…”Ý¥Ñ •… ¥Ñ•´¥¸„½±±…ÁÍ•Á…¹•°¸4(´™…±±‰…­}±…å½ÕÑ€èI•Í•ÉÙ•™…±±‰…¬±…å½ÕÐ™½ÈÕ¹ÍÕÁÁ½ÉÑ•Á±…Ñ™½É´½±…å½ÕÐ½µ‰¥¹…Ñ¥½¹Ì¸Q¡”ÕÉÉ•¹ÐÍ…™”™…±±‰…¬¥Ìµ…É­‘½Ý¹€¸4(´±…¹Õ…•Í€è=ÁÑ¥½¹…°Ý•‰¡½½¬µ½¹±ä±…¹Õ…”™¥±Ñ•È¸UÍ”l‰é ‰u€½Èl‰•¸‰u€Ñ¼Í•¹½¹±äÍ•±•Ñ•±…¹Õ…•ÌìÕÍ”¹Õ±±€½È½µ¥Ð¥ÐÑ¼Í•¹…±°½¹™¥ÕÉ•…¤¹±…¹Õ…•Í€¸4(´É•ÅÕ•ÍÑ}‰½‘å€è=ÁÑ¥½¹…°É•ÅÕ•ÍÐ‰½‘ä¸%˜•µÁÑä°!½É¥é½¸Í•¹‘Ì„Q€É•ÅÕ•ÍÐ¸%˜ÁÉ½Ù¥‘•°!½É¥é½¸Í•¹‘Ì„A=MQ€É•ÅÕ•ÍÐ¸4(´¡•…‘•ÉÍ€è=ÁÑ¥½¹…°ÕÍÑ½´¡•…‘•ÉÌ°½¹”-•äèY…±Õ•€Á…¥ÈÁ•È±¥¹”¸4(4)]¡•¸É•ÅÕ•ÍÑ}‰½‘å€¥Ì„)M=8½‰©•Ð½È…ÉÉ…ä°!½É¥é½¸É•¹‘•ÉÌÁ±…•¡½±‘•ÉÌ…¹Í•É¥…±¥é•Ì¥Ð…Ì)M=8¸]¡•¸¥Ð¥Ì„ÍÑÉ¥¹œ°!½É¥é½¸É•¹‘•ÉÌ¥Ð‘¥É•Ñ±ä…¹‘•Ñ•ÑÌ)M=8¥˜Ñ¡”É•¹‘•É•ÍÑÉ¥¹œ¥ÌÙ…±¥)M=8¸4(4(ŒŒŒ•±¥Ù•Éä5½‘•Ì¹1…å½ÕÑÌ4(4)‘•±¥Ù•Éå€½¹ÑÉ½±Ì¡½Üµ…¹äÝ•‰¡½½¬µ•ÍÍ…•Ì!½É¥é½¸Í•¹‘Ìè4(4(´ÍÕµµ…Éå€èM•¹‘Ì½¹”µ•ÍÍ…”½¹Ñ…¥¹¥¹œÑ¡”™Õ±°‘…¥±äÍÕµµ…Éä¸Q¡¥Ì¥ÌÍ¥µÁ±”°‰ÕÐÍ½µ”¡…ÐÁ±…Ñ™½ÉµÌµ…äÉ•©•Ð±½¹œµ•ÍÍ…•Ì¸4(´ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€èM•¹‘Ì½¹”½Ù•ÉÙ¥•Üµ•ÍÍ…”Á±ÕÌ½¹”µ•ÍÍ…”Á•ÈÍ•±•Ñ•¥Ñ•´¸%¸•… ¥Ñ•´µ•ÍÍ…”°€íÍÕµµ…Éåõ€½¹Ñ…¥¹Ì½¹±äÑ¡…Ð¥Ñ•´Ì5…É­‘½Ý¸‰½‘ä¸Q¡¥Ì¥ÌÕÍ•™Õ°™½ÈÁ±…Ñ™½ÉµÌÑ¡…ÐÉ•©•Ð½ÈÑÉÕ¹…Ñ”±½¹œµ•ÍÍ…•Ì¸4(4)±…å½ÕÑ€½¹ÑÉ½±Ì¡½Ü•… µ•ÍÍ…”¥ÌÉ•¹‘•É•è4(4(´µ…É­‘½Ý¹€èUÍ•Ìå½ÕÈÉ•ÅÕ•ÍÑ}‰½‘å€Ñ•µÁ±…Ñ”™½È•… µ•ÍÍ…”¸Q¡¥Ì¥ÌÑ¡”‘•™…Õ±Ð…¹Ý½É­ÌÝ¥Ñ •¹•É¥ŒÝ•‰¡½½­Ì°¥¹Q…±¬°M±…¬°¥Í½É°•¥Í¡Ô°…¹1…É¬¸4(´½±±…ÁÍ¥‰±•€èÕÉÉ•¹Ñ±äÍÕÁÁ½ÉÑ•™½ÈÁ±…Ñ™½É´è€‰™•¥Í¡Ô‰€½È€‰±…É¬‰€¸!½É¥é½¸¥¹½É•ÌÉ•ÅÕ•ÍÑ}‰½‘å€…¹‰Õ¥±‘Ì½¹”•¥Í¡Ô½1…É¬…É)M=8€È¸Àµ•ÍÍ…”Ý¥Ñ •… ¥Ñ•´¥¸„½±±…ÁÍ•Á…¹•°¸4(4)½ÈÁ±…Ñ™½ÉµÌÝ¥Ñ¡½ÕÐ„Á±…Ñ™½É´µÍÁ•¥™¥Œ±…å½ÕÐ°­••À±…å½ÕÐè€‰µ…É­‘½Ý¸‰€…¹¡½½Í”Ñ¡”µ•ÍÍ…”½Õ¹ÐÝ¥Ñ ‘•±¥Ù•Éå€¸4(4)á…µÁ±”ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€5…É­‘½Ý¸‘•±¥Ù•Éä½¹™¥œè4(4)©Í½¸4)ì4(€€‰Ý•‰¡½½¬ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÕÉ±}•¹Øˆè€‰!=I%i=9}]	!==-}UI0ˆ°4(€€€€‰‘•±¥Ù•Éäˆè€‰ÍÕµµ…Éå}…¹‘}¥Ñ•µÌˆ°4(€€€€‰½Ù•ÉÙ¥•Ý}Á½Í¥Ñ¥½¸ˆè€‰±…ÍÐˆ°4(€€€€‰Á±…Ñ™½É´ˆè€‰•¹•É¥Œˆ°4(€€€€‰±…å½ÕÐˆè€‰µ…É­‘½Ý¸ˆ°4(€€€€‰É•ÅÕ•ÍÑ}‰½‘äˆèì4(€€€€€€‰Ñ•áÐˆè€ˆíµ•ÍÍ…•}Ñ¥Ñ±•õq¹q¸íÍÕµµ…Éäý±¥µ¥ÐôÌÀÀÀ™ÍÁ±¥Ðô´´µôˆ4(€€€ô4(€ô4)ô4)€4(4)]¥Ñ ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€°!½É¥é½¸Í•¹‘Ì½¹”½Ù•ÉÙ¥•ÜÁ±ÕÌ½¹”µ•ÍÍ…”Á•ÈÍ•±•Ñ•¥Ñ•´¸½Ù•ÉÙ¥•Ý}Á½Í¥Ñ¥½¸è€‰±…ÍÐ‰€Í•¹‘Ì¥Ñ•´µ•ÍÍ…•Ì™¥ÉÍÐ…¹­••ÁÌÑ¡”½Ù•ÉÙ¥•Ü…ÌÑ¡”¹•Ý•ÍÐ¡…Ðµ•ÍÍ…”ì½µ¥Ð¥Ð½ÈÍ•Ð€‰™¥ÉÍÐ‰€Ñ¼Í•¹Ñ¡”½Ù•ÉÙ¥•Ü™¥ÉÍÐ¸4(4(ŒŒŒ]•‰¡½½¬Q•µÁ±…Ñ•Ì4(4)Ù…¥±…‰±”Ù…É¥…‰±•Ìè4(4)ðY…É¥…‰±”ð•ÍÉ¥ÁÑ¥½¸ð4)ð´´´´´´´´´µð´´´´´´´´´´´´µð4)ð€í‘…Ñ•õ€ðI•Á½ÉÐ‘…Ñ”°™½È•á…µÁ±”€ÈÀÈØ´ÀÐ´ÈÑ€ð4)ð€í±…¹Õ…•õ€ð1…¹Õ…”½‘”°ÍÕ …Ì•¹€½Èé¡€ð4)ð€í¥µÁ½ÉÑ…¹Ñ}¥Ñ•µÍõ€ð9Õµ‰•È½˜¥Ñ•µÌÍ•±•Ñ•‰äÁÉ½™¥±”™¥±Ñ•É¥¹œð4)ð€í…±±}¥Ñ•µÍõ€ðQ½Ñ…°¹Õµ‰•È½˜™•Ñ¡•¥Ñ•µÌð4)ð€íÉ•ÍÕ±Ñõ€ðÍÕ•ÍÍ€½È™…¥±•‘€ð4)ð€íÑ¥µ•ÍÑ…µÁõ€ðU¹¥àÑ¥µ•ÍÑ…µÀð4)ð€íµ•ÍÍ…•}Ñ¥Ñ±•õ€ð5•ÍÍ…”Ñ¥Ñ±”°ÍÕ …ÌÑ¡”‘…¥±äÑ¥Ñ±”°½Ù•ÉÙ¥•ÜÑ¥Ñ±”°½È¥Ñ•´Ñ¥Ñ±”ð4)ð€íµ•ÍÍ…•}­¥¹‘õ€ð5•ÍÍ…”­¥¹èÍÕµµ…Éå€°½Ù•ÉÙ¥•Ý€°¥Ñ•µ€°™…¥±ÕÉ•€°½Èµ…¹Õ…±€ð4)ð€íÍÕµµ…Éåõ€ð5•ÍÍ…”5…É­‘½Ý¸¸%¸ÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€µ½‘”Ñ¡¥Ì¥ÌÑ¡”½Ù•ÉÙ¥•Ü½È½¹”¥Ñ•´‰½‘ä°‘•Á•¹‘¥¹œ½¸Ñ¡”µ•ÍÍ…”ð4(4)]¡•¸‘•±¥Ù•Éå€¥ÌÍÕµµ…Éå}…¹‘}¥Ñ•µÍ€°¥Ñ•´µ•ÍÍ…•Ì…±Í¼¥¹±Õ‘”è4(4)ðY…É¥…‰±”ð•ÍÉ¥ÁÑ¥½¸ð4)ð´´´´´´´´´µð´´´´´´´´´´´´µð4)ð€í¥Ñ•µ}¥¹‘•áõ€ð€Äµ‰…Í•¥Ñ•´¹Õµ‰•Èð4)ð€í¥Ñ•µ}½Õ¹Ñõ€ðQ½Ñ…°¹Õµ‰•È½˜¥Ñ•´µ•ÍÍ…•Ìð4)ð€íÁÉ½™¥±•}¥Ñ•µ}¥¹‘•áõ€ð€Äµ‰…Í•¥Ñ•´¹Õµ‰•ÈÝ¥Ñ¡¥¸Ñ¡”ÕÉÉ•¹ÐAÉ½™¥±”ð4)ð€íÁÉ½™¥±•}¥Ñ•µ}½Õ¹Ñõ€ð9Õµ‰•È½˜¥Ñ•´µ•ÍÍ…•Ì¥¸Ñ¡”ÕÉÉ•¹ÐAÉ½™¥±”ð4)ð€í¥Ñ•µ}ÁÉ½™¥±•õ€ðÕÉÉ•¹ÐAÉ½™¥±”%ð4)ð€í¥Ñ•µ}ÁÉ½™¥±•}¹…µ•õ€ð1½…±¥é•ÕÉÉ•¹ÐAÉ½™¥±”¹…µ”ð4)ð€í¥Ñ•µ}Ñ¥Ñ±•õ€ðÕÉÉ•¹Ð¥Ñ•´Ñ¥Ñ±”ð4)ð€í¥Ñ•µ}ÕÉ±õ€ðÕÉÉ•¹Ð¥Ñ•´UI0ð4)ð€í¥Ñ•µ}Í½É•õ€ðÕÉÉ•¹Ð¥Ñ•´…¹…±åÍ¥ÌÍ½É”ð4(4)½ÈÝ•‰¡½½¬‘•±¥Ù•Éä°!½É¥é½¸™±…ÑÑ•¹Ì!Q50‘¥Í±½ÍÕÉ”‰±½­ÌÍÕ …Ì€ñ‘•Ñ…¥±ÌøñÍÕµµ…Éäø¸¸¸ð½ÍÕµµ…Éäù€¥¸€íÍÕµµ…Éåõ€¥¹Ñ¼Á±…¥¸5…É­‘½Ý¸±¥¹¬±¥ÍÑÌ¸Q¡¥Ìµ…­•ÌÑ¡”•¹•É…Ñ•ÍÕµµ…Éä•…Í¥•ÈÑ¼É•¹‘•È¥¸¡…ÐÁÉ½‘ÕÑÌ¸M…Ù•5…É­‘½Ý¸™¥±•Ì°¥Ñ!ÕˆA…•Ì°…¹•µ…¥°½¹Ñ•¹Ð…É”Õ¹¡…¹•¸4(4)UÍ”€í­•äý±¥µ¥Ðõ8™ÍÁ±¥Ðõ1%5õ€Ñ¼ÑÉÕ¹…Ñ”±½¹œÙ…±Õ•Ì‰äÍÁ±¥ÑÑ¥¹œ½¸1%5€…¹­••Á¥¹œÍ•µ•¹ÑÌÕ¹Ñ¥°Ñ¡”Ñ½Ñ…°¡…É…Ñ•È½Õ¹ÐÉ•…¡•Ì9€¸4(4)Ñ•áÐ4(íÍÕµµ…Éäý±¥µ¥ÐôÌÀÀÀ™ÍÁ±¥Ðô´´µô4)€4(4(ŒŒŒ¥¹Q…±¬4(4)%¸¥¹Q…±¬°É•…Ñ”„ÕÍÑ½´É½ÕÀÉ½‰½Ð…¹ÕÍ”„ÕÍÑ½´­•åÝ½ÉÍÕ …Ì!½É¥é½¹€¸Q¡”­•åÝ½ÉµÕÍÐ…ÁÁ•…È¥¸Ñ¡”‰½‘ä½¹Ñ•¹Ð¸4(4)©Í½¸4)ì4(€€‰µÍÑåÁ”ˆè€‰µ…É­‘½Ý¸ˆ°4(€€‰µ…É­‘½Ý¸ˆèì4(€€€€‰Ñ¥Ñ±”ˆè€‰!½É¥é½¸€í‘…Ñ•ô…¥±äˆ°4(€€€€‰Ñ•áÐˆè€‰!½É¥é½¸É•ÍÕ±Ðè€íÉ•ÍÕ±Ñõq¹q¹!½É¥é½¸¥µÁ½ÉÑ…¹Ð¥Ñ•µÌè€í¥µÁ½ÉÑ…¹Ñ}¥Ñ•µÍô¼í…±±}¥Ñ•µÍõq¹q¸íÍÕµµ…Éåôˆ4(€ô4)ô4)€4(4(ŒŒŒ•¥Í¡Ô€¼1…É¬4(4)%¸•¥Í¡Ô½È1…É¬°É•…Ñ”„ÕÍÑ½´É½ÕÀÉ½‰½Ð…¹ÕÍ”„ÕÍÑ½´­•åÝ½ÉÍÕ …Ì!½É¥é½¹€¸Q¡”­•åÝ½ÉµÕÍÐ…ÁÁ•…È¥¸Ñ¡”‰½‘ä½¹Ñ•¹Ð¸4(4)UÍ”…É)M=8€È¸À™½È5…É­‘½Ý¸É•¹‘•É¥¹œ¸Q¡”…ÉµÕÍÐ¥¹±Õ‘”€‰Í¡•µ„ˆè€ˆÈ¸À‰€…¹ÁÕÐÉ¥ µÑ•áÐ5…É­‘½Ý¸½µÁ½¹•¹ÑÌÕ¹‘•È…É¹‰½‘ä¹•±•µ•¹ÑÍ€¸4(4)Q¼­••ÀÑ¡”É½ÕÀ¡…Ð½µÁ…ÐÝ¡¥±”ÍÑ¥±°…±±½Ý¥¹œÉ•…‘•ÉÌÑ¼‰É½ÝÍ”Ñ¡”™Õ±°‰É¥•™¥¹œ¥¹Í¥‘”•¥Í¡Ô°ÕÍ”Ñ¡”½±±…ÁÍ¥‰±”±…å½ÕÐè4(4)©Í½¸4)ì4(€€‰Ý•‰¡½½¬ˆèì4(€€€€‰•¹…‰±•ˆèÑÉÕ”°4(€€€€‰ÕÉ±}•¹Øˆè€‰!=I%i=9}]	!==-}UI0ˆ°4(€€€€‰Á±…Ñ™½É´ˆè€‰™•¥Í¡Ôˆ°4(€€€€‰±…å½ÕÐˆè€‰½±±…ÁÍ¥‰±”ˆ°4(€€€€‰™…±±‰…­}±…å½ÕÐˆè€‰µ…É­‘½Ý¸ˆ°4(€€€€‰±…¹Õ…•Ìˆèl‰é ‰t4(€ô4)ô4)€4(4)]¥Ñ Ñ¡¥Ì±…å½ÕÐ°!½É¥é½¸Í•¹‘Ì½¹”¥¹Ñ•É…Ñ¥Ù”…É½¹Ñ…¥¹¥¹œÑ¡”½Ù•ÉÙ¥•Ü…¹½¹”½±±…ÁÍ•Á…¹•°Á•ÈÍ•±•Ñ•¥Ñ•´¸… Á…¹•°…¸‰”•áÁ…¹‘•¥¸•¥Í¡ÔÑ¼É•…Ñ¡”™Õ±°¥Ñ•´‘•Ñ…¥°¸Q¡”É•Õ±…ÈÉ•ÅÕ•ÍÑ}‰½‘å€Ñ•µÁ±…Ñ”¥Ì¥¹½É•™½ÈÑ¡¥ÌÉ•¹‘•É•…É¸4(4)©Í½¸4)ì4(€€‰µÍ}ÑåÁ”ˆè€‰¥¹Ñ•É…Ñ¥Ù”ˆ°4(€€‰…Éˆèì4(€€€€‰Í¡•µ„ˆè€ˆÈ¸Àˆ°4(€€€€‰½¹™¥œˆèì4(€€€€€€‰Ý¥‘•}ÍÉ••¹}µ½‘”ˆèÑÉÕ”4(€€€ô°4(€€€€‰¡•…‘•Èˆèì4(€€€€€€‰Ñ¥Ñ±”ˆèì4(€€€€€€€€‰Ñ…œˆè€‰Á±…¥¹}Ñ•áÐˆ°4(€€€€€€€€‰½¹Ñ•¹Ðˆè€ˆíµ•ÍÍ…•}Ñ¥Ñ±•ôˆ4(€€€€€ô°4(€€€€€€‰Ñ•µÁ±…Ñ”ˆè€‰‰±Õ”ˆ4(€€€ô°4(€€€€‰‰½‘äˆèì4(€€€€€€‰•±•µ•¹ÑÌˆèl4(€€€€€€€ì4(€€€€€€€€€€‰Ñ…œˆè€‰µ…É­‘½Ý¸ˆ°4(€€€€€€€€€€‰½¹Ñ•¹Ðˆè€‰!½É¥é½¸É•ÍÕ±Ðè€íÉ•ÍÕ±Ñõq¹!½É¥é½¸¥µÁ½ÉÑ…¹Ð¥Ñ•µÌè€í¥µÁ½ÉÑ…¹Ñ}¥Ñ•µÍô¼í…±±}¥Ñ•µÍôˆ4(€€€€€€€ô°4(€€€€€€€ì4(€€€€€€€€€€‰Ñ…œˆè€‰¡Èˆ4(€€€€€€€ô°4(€€€€€€€ì4(€€€€€€€€€€‰Ñ…œˆè€‰µ…É­‘½Ý¸ˆ°4(€€€€€€€€€€‰½¹Ñ•¹Ðˆè€ˆíÍÕµµ…Éåôˆ4(€€€€€€€ô4(€€€€€t4(€€€ô4(€ô4)ô4)€4(4(ŒŒŒQ•ÍÑ¥¹œ4(4)UÍ”¡½É¥é½¸µÝ•‰¡½½­€Ñ¼ÁÉ•Ù¥•Ü½ÈÍ•¹„Ñ•ÍÐ¹½Ñ¥™¥…Ñ¥½¸Ý¥Ñ¡½ÕÐÉÕ¹¹¥¹œÑ¡”™Õ±°Á¥Á•±¥¹”è4(4)‰…Í 4)ÕØÉÕ¸¡½É¥é½¸µÝ•‰¡½½¬€´µ‘ÉäµÉÕ¸4)€4(4)ð=ÁÑ¥½¸ð•™…Õ±Ðð•ÍÉ¥ÁÑ¥½¸ð4)ð´´´´´´´µð´´´´´´´´µð´´´´´´´´´´´´µð4)ð€´µ±…¹œ19€ð™¥ÉÍÐ½¹™¥ÕÉ•±…¹Õ…”ð1…¹Õ…”Ñ¼Ñ•ÍÐð4)ð€´µ‘ÉäµÉÕ¹€ð½™˜ðAÉ•Ù¥•ÜÉ•¹‘•É•½¹Ñ•¹ÐÝ¥Ñ¡½ÕÐÍ•¹‘¥¹œð4)ð€´µ‘•±¥Ù•ÉäíÍÕµµ…Éä±ÍÕµµ…Éå}…¹‘}¥Ñ•µÍõ€ðÙ…±Õ”™É½´½¹™¥œð=Ù•ÉÉ¥‘”‘•±¥Ù•Éäµ½‘”™½ÈÑ¡¥ÌÑ•ÍÐð4)ð€µ‘€°€´µ‘…Ñ„µ‘¥ÈAQ!€ð‘…Ñ…€ðA…Ñ Ñ¼Ñ¡”‘…Ñ„‘¥É•Ñ½Éäð4)ð€µ€°€´µ½¹™¥œAQ!€ð€ñ‘…Ñ„µ‘¥Èø½½¹™¥œ¹©Í½¹€ðA…Ñ Ñ¼½¹™¥œ™¥±”ð4)ð€µ±€°€´µ±½œµ±•Ù•°1Y1€ð]I9%9€ð1½¥¹œ±•Ù•°€¡	U½%9<½]I9%9½II=H½I%Q%0¤ð4(4(4(ŒŒMÑ…Ñ¥ŒM¥Ñ”4(4)!½É¥é½¸ÝÉ¥Ñ•Ì•¹•É…Ñ•ÍÕµµ…É¥•ÌÑ¼‘…Ñ„½ÍÕµµ…É¥•Ì½€€¡½È€ñ‘…Ñ„µ‘¥Èø½ÍÕµµ…É¥•Ì½€Ý¡•¸€´µ‘…Ñ„µ‘¥É€¥ÌÍ•Ð¤…¹½Á¥•ÌÁÕ‰±¥Í¡…‰±”5…É­‘½Ý¸¥¹Ñ¼‘½Ì½€™½ÈÑ¡”¥Ñ!ÕˆA…•ÌÍ¥Ñ”¸Q¡”É•Á½Í¥Ñ½Éä¥¹±Õ‘•Ì„É•…‘äµÑ¼µÕÍ”Ý½É­™±½Ü…Ð€¹¥Ñ¡Õˆ½Ý½É­™±½ÝÌ½‘…¥±äµÍÕµµ…Éä¹åµ±€¸4(4)Q¼ÕÍ”¥Ñ!ÕˆA…•Ì°•¹…‰±”A…•Ì™½ÈÑ¡”É•Á½Í¥Ñ½Éä…¹ÉÕ¸Ñ¡”Í¡•‘Õ±•Ý½É­™±½Ü½ÈÑÉ¥•È¥Ðµ…¹Õ…±±ä¸Q¡”•¹•É…Ñ•Í¥Ñ”¥Ì‰Õ¥±Ð™É½´Ñ¡”‘½Ì½€‘¥É•Ñ½Éä¸4(4(ŒŒ5@M•ÉÙ•È4(4)!½É¥é½¸¥¹±Õ‘•Ì…¸5@Í•ÉÙ•È™½È$…ÍÍ¥ÍÑ…¹ÑÌ…¹5@µ½µÁ…Ñ¥‰±”±¥•¹ÑÌ¸4(4)‰…Í 4)ÕØÉÕ¸¡½É¥é½¸µµÀ4)€4(4)Ù…¥±…‰±”Ñ½½±Ì¥¹±Õ‘”¡é}Ù…±¥‘…Ñ•}½¹™¥€°¡é}™•Ñ¡}¥Ñ•µÍ€°¡é}Í½É•}¥Ñ•µÍ€°¡é}™¥±Ñ•É}¥Ñ•µÍ€°¡é}•¹É¥¡}¥Ñ•µÍ€°¡é}•¹•É…Ñ•}ÍÕµµ…Éå€°…¹¡é}ÉÕ¹}Á¥Á•±¥¹•€¸4(4)M•”mÍÉŒ½µÀ½I5¹µ‘t ¸¸½ÍÉŒ½µÀ½I5¹µ¤™½ÈÑ¡”™Õ±°Ñ½½°É•™•É•¹”…¹mÍÉŒ½µÀ½¥¹Ñ•É…Ñ¥½¸¹µ‘t ¸¸½ÍÉŒ½µÀ½¥¹Ñ•É…Ñ¥½¸¹µ¤™½È±¥•¹ÐÍ•ÑÕÀ¸4(