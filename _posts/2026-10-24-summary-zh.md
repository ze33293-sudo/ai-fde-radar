---
layout: default
title: "AI FDE Radar: 2026-10-24 (ZH)"
date: 2026-10-24
lang: zh
---

> 从 620 条内容中筛选出 5 条重要资讯。

---

**今天可以用 1/5**
1. [Dify 1.18.0：Agent 可选择工作流分支，应用包可移植](#item-today-use-1) ⭐️ 7.9/10

**企业落地案例 1/5**
1. [Bayer 的 22 个专家 Agent：把“解释结果”做成产品](#item-enterprise-case-1) ⭐️ 8.6/10

**产品方法与踩坑 1/4**
1. [【近 7 日补充】Anthropic 谈 Agent 评测：看环境终态，分清 pass@k 与 pass^k](#item-method-pitfall-1) ⭐️ 8.7/10

**小白技术翻译 1/3**
1. [Kimi K3.1 Pro 上线：定价、加速档与开源承诺](#item-beginner-tech-1) ⭐️ 6.4/10

**行业趋势与商业信号 0/2**
本期暂无可靠更新

**今天动手做 1/1**
1. [今天动手做｜把一个方法变成坏案例检查项](#item-hands-on-1)

---

## 今天可以用 1/5

<a id="item-today-use-1"></a>
### [Dify 1.18.0：Agent 可选择工作流分支，应用包可移植](https://github.com/langgenius/dify/releases/tag/1.18.0) ⭐️ 7.9/10

据 GitHub 发布页（2026-10-23），Dify 1.18.0 让 Agent 决定工作流走哪条分支：用户可设置 Output Routes（输出路由）和每条路由的选择条件，并通过只读输出查看最终选中的路由。该版本还加入 .ifpkg 应用包、嵌套工作流运行追踪，以及需要用户主动开启的 Agent Knowledge Base Beta。升级时，API、workers、Agent Backend 和 Agent 运行时镜像必须同步升级；源码部署需要 Python 3.13；difyctl 需要重新登录；同时要保留原有的 PASSWORD\_PEPPER。

**来源**: github · laipz8200 · 10月23日 06:33

**栏目**: 今天可以用 · **地区**: 中国 · **解读模式**: deep · **状态**: 今日新内容

**「为什么与你有关」** 分析：这直接对应售后工单 Agent 的“直接解决或转专家”分流。FDE（现场交付工程师）可以用 .ifpkg 迁移应用，并借助嵌套追踪排查子流程失败；但路由条件、兜底路径和人工接管必须明确设计，否则一旦模型选错，就没有人工介入的保障。

**「今天怎么试」** 用 20 分钟画一张工单路由表：写 3 条条件（退款、技术故障、投诉）和 1 条人工兜底；再检查每张工单是否只有唯一去向。输出一页表；若出现无归属或重复归属，就不合格。这是设计演练，不需要安装 Dify。

**「映射到售后工单 Agent / 求职」** 你可以把这张路由表和“选中路由可观察”写进作品集，作为工单分流的证据；面试时可讲你如何用明确条件与兜底降低误路由，并保留追踪记录。

**「限制与不确定性」** Agent Knowledge Base 仍为 Beta，需要独立的服务和数据库，KnowledgeFS 默认 API 镜像目前仅支持 amd64；嵌套用量与步骤统计在暂停或停止后仍可能只是近似值。发布页未给出生产环境的解决率收益。

**标签**: `#Dify 1.18`, `#agent routing`, `#workflow observability`, `#portable apps`, `#ticket triage`

---

## 企业落地案例 1/5

<a id="item-enterprise-case-1"></a>
### [Bayer 的 22 个专家 Agent：把“解释结果”做成产品](https://aws.amazon.com/blogs/machine-learning/how-bayer-crop-science-built-an-agentic-decision-engine-on-amazon-bedrock-agentcore-with-aws-unified-operations/) ⭐️ 8.6/10

AWS 第一方案例称，Bayer Crop Science 在 Amazon Bedrock AgentCore 上构建 ADE，为其管理机器学习工作流的 CDE 提供自然语言多智能体入口。主管 Agent 分类问题后路由给专家 Agent；生产环境有 22 个专家 Agent，各自限定工具和数据源。案例称首阶段约 80% 用户问题无需工程师介入即可解决，故障诊断从 1 小时以上降到 10 分钟内。AgentCore 提供会话隔离，Gateway 把后端 API 暴露为 MCP 工具（一种工具调用接口），认证授权不写进 Agent 代码。

**来源**: rss · AWS Machine Learning - Enterprise Workflows · 10月23日 16:21

**栏目**: 企业落地案例 · **地区**: global · **解读模式**: deep · **状态**: 今日新内容

**「为什么与你有关」** 分析：瓶颈从“跑工作流”转向“解释工作流”。售后工单 Agent 的价值也在按问题路由到查状态、诊断、知识库等受限工具，而非一个聊天框。机会是减少一线升级工程师；风险是“解决”口径不清。产品决策：先做主管 + 专家 Agent，别让一个 Agent 挂全部工具。

**「今天怎么试」** 今天用 15–30 分钟画一张“身份跳转表”：用户 SSO → 主管 Agent → 工具 API，每一跳写明签发方、受众、权限范围、凭证有效期和负责人。通过标准：每一跳都有值，且没有把上一跳的令牌直接复用。

**「映射到售后工单 Agent / 求职」** 落到作品集：画出售后工单 Agent 的路由图，标出 3 个专家 Agent（查工单、故障诊断、知识库）及各自工具白名单；面试用“为什么不用一个大 Agent”回答身份与工具边界问题。

**「限制与不确定性」** 限制：AWS 第一方案例，数据为厂商自述；仅首阶段，所给内容未说明“80% 解决”的样本量与判定口径，22 个 Agent 的规模也未必适合小团队。

**标签**: `#agentic AI`, `#Amazon Bedrock AgentCore`, `#enterprise agent deployment`, `#tool scoping`, `#agent identity`

---

## 产品方法与踩坑 1/4

<a id="item-method-pitfall-1"></a>
### [【近 7 日补充】Anthropic 谈 Agent 评测：看环境终态，分清 pass@k 与 pass^k](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) ⭐️ 8.7/10

Anthropic 于 2026-01-09 发布工程指南，讲多轮 AI Agent 的自动化评测：定义任务、试验、评分器、对话轨迹、环境终态、评测框架与套件；建议同一任务多次运行，评分可看轨迹或终态，并用 pass@k/pass^k 处理非确定性。文中举例 Opus 4.5 在 τ2-bench 订票任务发现政策漏洞，按原评测算失败，但对用户更优。

**来源**: google\_news · Anthropic · 1月9日 08:00

**栏目**: 产品方法与踩坑 · **地区**: global · **解读模式**: deep · **状态**: 近 7 日补充

**「为什么与你有关」** 分析：两个概念直接影响产品选择。对话轨迹是 Agent 的回复和工具调用记录；环境终态是工单系统里是否真的退款、改状态或升级。只看“回复说已解决”会漏掉假成功。pass@k 指 k 次里至少成功一次；pass^k 指 k 次都成功。前者适合草稿建议，后者适合自动退款、自动关单等高风险动作。

**「今天怎么试」** 今天用 20 分钟：若已有可调用 Agent，取 5 张历史工单，写明期望终态（如 CRM 状态=已退款/已升级），每张跑 2 次；输出 5×2 表，分别记录“回复声称解决”和“终态达成”，并草算 pass@2 与 pass^2。终态未达成即判失败。

**「映射到售后工单 Agent / 求职」** 为作品集做一个“售后工单评测集 v0”：10 个任务，每个含终态断言、轨迹检查和是否允许自动执行的阈值；面试时用它说明你如何区分演示效果与生产可靠性。

**「限制与不确定性」** 该指南基于内部与客户实践，证据以经验和示例为主，未给统一基线、样本量与统计细节；τ2-bench 个例不能证明普遍效果。迁移到售后需自建终态检查和人工校准。

**标签**: `#agent-evals`, `#pass@k-pass^k`, `#tool-use`, `#reliability`, `#transcripts`

---

## 小白技术翻译 1/3

<a id="item-beginner-tech-1"></a>
### [Kimi K3.1 Pro 上线：定价、加速档与开源承诺](https://simonwillison.net/2026/Oct/23/kimi-k31-pro/) ⭐️ 6.4/10

2026 年 10 月 23 日，Kimi K3.1 Pro 上线 Kimi API。据 Simon Willison 记录：模型暂未开放权重（参数可下载自部署），Moonshot 承诺 2026 年 11 月 4 日前放出完整权重。另提供“Highspeed”版本，速度快 2–3 倍、价格翻倍，但输入 token 缓存命中部分同价（缓存命中指重复的前缀上下文被复用，计费更低）。美元定价为输入每百万 token 2 美元、输出 10 美元，与 GPT-6.1 Sol 相同，是 Claude Opus 5.5 的一半。Moonshot 自测显示其与 Opus 5.5、GPT-6 Astra 大致持平；第三方 Artificial Analysis 给 55 分，高于 Claude Fable 5.1、GPT-6 Astra、Gemini 4 Argon（均 53），仅次于 Opus 5.5（58）。作者称这是首个即将开源的模型在对抗前沿模型时拿到如此高分。

**来源**: rss · Simon Willison · 10月23日 19:40

**栏目**: 小白技术翻译 · **地区**: global · **解读模式**: deep · **状态**: 今日新内容

**「为什么与你有关」** （以下为分析）对做售后工单 Agent 的你，重点不在榜单名次，而在“同一模型可以有多个能力—成本—延迟档位”：花 2 倍价格换 2–3 倍速度，缓存命中输入同价。工单场景中，分类、字段抽取是高频短请求，吃缓存与低延迟；多轮故障排查吃推理深度。这两类需求本就不该共用一档。开源权重承诺（有明确时间点但未兑现）则关系到未来自托管与数据合规的选择空间。

**「今天怎么试」** 用你已有权限的任意“OpenAI 兼容接口”，对同一个 prompt 分别用 low、medium、max 三档推理投入各跑一次，保存输出、耗时与花费；输入选一条真实工单文本，让它抽取固定字段。判定标准：升到 max 后抽取是否真的更准；若没有明显提升，说明这档对你的任务不值这个价。产出：一张三行对比小表。

**「映射到售后工单 Agent / 求职」** 在作品集里加一页“模型选型与成本”：按任务（工单分类、字段抽取、多轮诊断）列出所用档位、单价、延迟与准确率，并写明缓存命中率假设。面试可这样答：我先用 low、medium、max 三档对照，决定工单抽取走便宜档、复杂诊断走贵档。

**「限制与不确定性」** 定价与基准都是 Moonshot 自测与第三方索引的转述，非官方模型文档；作者的实操仅是一次 SVG 生成的主观对比，未做系统评测；开源权重目前只是承诺、尚未交付。单一综合分不能代表它在你工单任务上的表现，需自行验证。

**标签**: `#model-pricing`, `#open-weight-models`, `#model-selection`, `#cost-latency-tradeoff`, `#benchmarks`

---

## 行业趋势与商业信号 0/2

> 本期暂无可靠更新

## 今天动手做 1/1

<a id="item-hands-on-1"></a>
### [今天动手做｜把一个方法变成坏案例检查项](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

基于本期《Demystifying evals for AI agents - Anthropic》生成，不要求额外寻找教程。

**来源**: AI FDE Radar · 基于本期资讯生成 · 10月24日 05:56

**栏目**: 今天动手做 · **地区**: global · **解读模式**: action · **状态**: 今日生成

**「时间」** 15–30 分钟

**「输入」** 本期方法或踩坑资讯、5 条脱敏工单样例或自拟边界样例

**「步骤」** \1. 提炼一个失败条件；2. 写成可判断的评估规则；3. 检查 5 条样例；4. 记录误判及需要人工复核的位置。

**「完成标准」** 新增 1 条评估规则、至少 1 个坏案例，并说明通过标准。

**「映射到售后工单 Agent」** 把产出保存到项目的评估集、PRD 决策记录或作品集证据中。

<details><summary>参考链接</summary>
<ul>
<li><a href="https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents">Demystifying evals for AI agents - Anthropic</a></li>

</ul>
</details>

**标签**: `#ticket-agent`, `#hands-on`

---