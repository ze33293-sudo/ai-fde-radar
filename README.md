# AI FDE Radar

每天北京时间 09:15 由 GitHub Actions 在云端启动，从开放互联网收集候选信息，为正在入门的 AI 产品经理/FDE 生成最多 20 条实战情报，发送到飞书并归档到 GitHub Pages。电脑关机不影响运行。

本项目基于 [Horizon](https://github.com/Thysrael/Horizon)（MIT License）改造，增加了双维度配额、跨日去重、分层摘要、运行指标、同日发送保护和安全检查。

## 每期标准

- 抓取窗口：最近 30 小时。
- 原始候选：目标 100–200 条；规则预筛后最多 60 条进入模型评分。
- 常规入围线：两个 Profile 都是 7/10；可靠性、认知增量、行业影响和产品/FDE 启发优先。
- 行动性只加分，不是入选前提；没有可靠可执行动作时不强行生成“今天怎么试”。
- 最终上限：20 条。
- 六栏每天都显示且至少 1 条；5/5/4/3/2/1 是目标而非凑数要求，标题显示实际数/目标数。
- 最近 30 小时优先；栏目不足时定向补搜最近 7 天并标注“近 7 日补充”。
- 原始论文最多 1 条；同一来源最多 3 条，“今天可以用”中同一来源最多 1 条。
- Top 5：300–500 字深度解读；其余：100–180 字精炼摘要。
- 每条明确展示“发生了什么、为什么与你有关、今天怎么试、如何映射到售后工单 Agent/求职、限制与不确定性”。
- 只发布原创转述与原始链接，不复制文章全文。

## 信息源

覆盖官方 RSS、厂商官方 Customer Stories 目录、Google News RSS、GDELT、GitHub Releases、OSSInsight、Hacker News、Reddit、少量研究源以及公开中英文科技媒体索引。检索重点是可立即使用的功能、客服/销售/知识库/数据与办公工作流、真实落地指标、评测与失败复盘、入门教程和国内岗位信号。不抓登录墙、付费墙、微信公众号、知乎、小红书、抖音、X 和私有 Telegram，也不依赖 Apify 或 RSSHub。

处理链路：

```text
抓取 → 30 小时时间过滤 → 原始链接解析 → URL 去重 → 7 天历史去重
→ 六栏候选预筛 → 必需栏目的原始正文免费预检 → 缺栏时定向补搜 7 天
→ 仍缺栏则在调用模型前失败 → 最多 60 条进入 DeepSeek 评分 → 主题去重
→ 5/5/4/3/2/1 栏目选择 → 最终条目正文复核与缺栏修复
→ Top 5/短摘要生成 → 飞书 + GitHub Pages
```

## 部署

1. 在 GitHub 新建公开仓库并推送本项目。
2. 在仓库 `Settings → Secrets and variables → Actions` 添加且只添加：
   - `DEEPSEEK_API_KEY`
   - `HORIZON_WEBHOOK_URL`（飞书自定义机器人 Webhook）
3. 在 `Settings → Pages` 将发布源设为 `Deploy from a branch`，选择 `gh-pages` 与 `/ (root)`。
4. 在 Actions 手动运行一次 `AI FDE Radar Daily`，先选 `preflight_only=true`；该模式不调用 DeepSeek、不发飞书。
5. 来源预检通过后，再以 `dry_run=true` 生成并检查完整日报；最后用默认参数真实推送。

定时表达式是 `15 1 * * *`（UTC），即北京时间约 09:15。GitHub 调度可能延迟，项目不会把 09:30 当作硬截止时间。

### 手动参数

- `dry_run`：生成、测试并上传 Actions Artifact，不发飞书、不发布 Pages、不提交历史状态。
- `force_send`：绕过“同一北京时间日期只成功发送一次”的保护。
- `preflight_only`：只验证六栏候选与原始正文供给；工作流会先移除模型密钥和飞书地址，不调用 DeepSeek、不发飞书、不发布 Pages。

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

只做零模型额度的来源预检：

```bash
uv run horizon --preflight-only --dry-run
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
