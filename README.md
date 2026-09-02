# AI FDE Radar

每天北京时间 09:15 由 GitHub Actions 在云端启动，从开放互联网收集 AI 行业候选信息，使用 DeepSeek 评分和编辑，最多精选 20 条发送到飞书，并归档到 GitHub Pages。电脑关机不影响运行。

本项目基于 [Horizon](https://github.com/Thysrael/Horizon)（MIT License）改造，增加了双维度配额、跨日去重、分层摘要、运行指标、同日发送保护和安全检查。

## 每期标准

- 抓取窗口：最近 30 小时。
- 原始候选：目标 100–200 条；规则预筛后最多 60 条进入模型评分。
- 质量门槛：两个 Profile 都是 7/10，宁缺毋滥。
- 最终上限：20 条。
- 目标矩阵：海外产品/FDE 6、海外技术 6、中国产品/FDE 4、中国技术 4。
- Top 5：300–500 字深度解读；其余：100–180 字精炼摘要。
- 每条明确展示来源、发布时间、分类、地区、事实摘要、分析和行动启示。
- 只发布原创转述与原始链接，不复制文章全文。

## 信息源

首版覆盖官方 RSS、Google News RSS、GDELT、arXiv、GitHub Releases、OSSInsight、Hacker News、Reddit 以及公开中英文科技媒体索引。不抓登录墙、付费墙、微信公众号、知乎、小红书、抖音、X 和私有 Telegram，也不依赖 Apify 或 RSSHub。

处理链路：

```text
抓取 → 30 小时时间过滤 → 原始链接解析 → URL 去重 → 7 天历史去重
→ 规则预筛（最多 60）→ DeepSeek 评分 → 主题去重 → 6/6/4/4 配额选择
→ 最终条目正文抓取 → Top 5/短摘要生成 → 飞书 + GitHub Pages
```

## 部署

1. 在 GitHub 新建公开仓库并推送本项目。
2. 在仓库 `Settings → Secrets and variables → Actions` 添加且只添加：
   - `DEEPSEEK_API_KEY`
   - `HORIZON_WEBHOOK_URL`（飞书自定义机器人 Webhook）
3. 在 `Settings → Pages` 将发布源设为 `Deploy from a branch`，选择 `gh-pages` 与 `/ (root)`。
4. 在 Actions 手动运行一次 `AI FDE Radar Daily`，建议先选 `dry_run=true`。
5. 检查生成物后再以默认参数运行一次真实推送。

定时表达式是 `15 1 * * *`（UTC），即北京时间约 09:15。GitHub 调度可能延迟，项目不会把 09:30 当作硬截止时间。

### 手动参数

- `dry_run`：生成、测试并上传 Actions Artifact，不发飞书、不发布 Pages、不提交历史状态。
- `force_send`：绕过“同一北京时间日期只成功发送一次”的保护。

## 本地运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --extra dev
cp data/config.github.json data/config.json
```

在 `.env` 中配置：

```dotenv
DEEPSEEK_API_KEY=your_key
HORIZON_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_token
```

只生成不推送：

```bash
uv run horizon --hours 30 --dry-run
```

真实运行：

```bash
uv run horizon --hours 30
```

测试：

```bash
uv run pytest
uv run python scripts/verify_no_secrets.py docs data/summaries
```

## 状态与指标

- `data/state/seen_items.json` 保存最近 7 天已入选条目的 URL/标题指纹。
- `data/state/sent/YYYY-MM-DD.json` 是同日发送成功标记。
- Actions 会从 `gh-pages` 恢复状态，所以本地电脑无需保持开机。
- `docs/metrics/YYYY-MM-DD.json` 和 `latest.json` 记录抓取、去重、评分、入选、来源状态和 Token。
- 当前配置按 DeepSeek V4 Flash 的峰时、缓存未命中单价做保守估算；价格基准与核验日期写入指标，费率变化后应同步更新配置。

## 异常与安全

- 单个来源失败会降级继续；全部来源失败则工作流失败，不发送“没有新闻”。
- 有候选但没有内容达到 7 分时，会发送“今日暂无高价值更新”。
- 飞书 HTTP 错误、超时或非零业务码都会令工作流失败，推送阶段会重试一次。
- 飞书 Webhook 路径在日志中脱敏；发布前会扫描构建产物，防止密钥或完整 Webhook 泄露。
- 公开仓库、Pages 与运行指标不应包含任何个人凭据。

## License

[MIT](LICENSE)。上游 Horizon 版权与许可证保留。
