# Evaluation goal

Evaluate technical information when it helps a beginner AI product manager/FDE understand an important product or delivery decision. This is not a raw research leaderboard. The reader is building an enterprise after-sales ticket Agent and needs decision-level understanding of RAG, tools, MCP, agents, evaluations, context, permissions, reliability, latency, cost, and human review. A useful explanation can qualify even when it does not produce an immediate task.

# Weighted scoring

- **Evidence quality — 25%.** Prefer primary papers, official documentation, reproducible code, measured results, real failures, clear methodology, and stated limitations.
- **Personal, project, or job relevance — 20%.** Changes how a capability should be selected, scoped, built, evaluated, governed, or operated for the reader's ticket Agent, FDE work, portfolio, or job readiness.
- **Cognitive gain — 20%.** Clarifies a non-obvious concept, tradeoff, boundary, or failure mode for a beginner.
- **Industry or engineering impact — 15%.** Has consequences for real AI systems, teams, costs, users, or adoption.
- **Beginner/FDE learning value — 10%.** Can be translated into an accurate product explanation without hiding important caveats.
- **Recency and actionability — 10%.** Current and testable work receives a bonus, but lack of a seven-day action is never an automatic penalty.

# Scoring rubric

- **9–10:** Strong primary evidence and broad consequences that materially alter an applied-AI architecture, evaluation, or delivery decision.
- **7–8.9:** Technically credible, beginner-explainable, and tied to a concrete product decision, limitation, or failure mode.
- **6–6.9:** A credible category-matching supplement with limited evidence, impact, or immediate relevance.
- **5–5.9:** Interesting engineering or research with indirect, narrow, or poorly demonstrated product value.
- **3–4.9:** Raw benchmark, minor optimization, or theory with no explained product consequence.
- **0–2.9:** Unsupported claim, hype, off-topic content, inaccessible evidence, or misleading availability.

# Category and evidence hard rules

Choose exactly one category and set `category_requirements_met` accurately:

- `today-use`: only an already publicly available capability backed by official documentation or a Release. Previews, waitlists, and unreleased demos fail.
- `enterprise-case`: require a real business object/user, implementation workflow, and verifiable result or outcome.
- `method-pitfall`: a reusable engineering/product lesson about RAG, evaluation, reliability, security, tool use, rollout, permissions, cost, or human review.
- `beginner-tech`: an accessible concept or technical development that explicitly changes a product choice such as architecture, reliability, latency, cost, privacy, evaluation, or review.
- `industry-trend`: a consequential market or business shift such as infrastructure economics, platform ecosystem strategy, pricing, partnership or acquisition, regulation, or aggregate adoption. Require primary evidence and exclude single features, single customer cases, routine releases, job listings, and unsupported commentary.
- `hands-on`: do not assign external news to this category. The program generates the daily hands-on card separately.

Set `evidence_complete` true only when the supplied original source is accessible enough to verify the central claim. Use `evidence_note` to identify the evidence and largest uncertainty. One item must have only one primary category. The source-suggested category is advisory and may be corrected.

# Actionability

Set `actionable_within_7_days` true and provide `action` only when an honest experiment follows from the evidence. Otherwise set it false and leave `action` empty. Non-actionable work may score 7+ if its evidence, cognitive gain, impact, and decision value justify it.

Explain at most two key concepts and use three to five specific topic tags.
