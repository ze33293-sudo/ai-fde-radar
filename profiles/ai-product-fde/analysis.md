# Evaluation goal

Evaluate timely information for a beginner AI product manager/FDE who is building an enterprise after-sales ticket Agent, broadening their industry view, and preparing for applied-AI roles. Reward reliable information that creates a meaningful new mental model, changes a product decision, or reveals how AI is actually being adopted. A near-term action is useful but is not required.

# Weighted scoring

- **Evidence quality — 25%.** Prefer primary documentation, a named workflow, verifiable results, implementation details, or explicit limitations.
- **Personal and product relevance — 20%.** Connects to AI product work, FDE delivery, the ticket Agent, a portfolio, or applied-AI job readiness.
- **Cognitive gain — 20%.** Adds a useful mental model, tradeoff, failure pattern, market signal, or non-obvious constraint.
- **Industry impact — 15%.** Matters to real users, teams, buyers, workflows, or the direction of applied AI.
- **Product/FDE learning value — 10%.** Teaches discovery, scoping, integration, evaluation, human review, permissions, rollout, adoption, or ROI.
- **Recency and actionability — 10%.** Prefer current changes and honest small experiments, but never cap an otherwise valuable item merely because it has no seven-day action.

# Scoring rubric

- **9–10:** Unusually strong primary evidence and impact; materially changes an AI product/FDE decision or understanding.
- **7–8.9:** Reliable, relevant, and meaningfully informative, with a concrete capability, workflow, result, failure, constraint, or market signal.
- **6–6.9:** A credible supplemental item that matches a radar category but has limited novelty, impact, or detail.
- **5–5.9:** Related but generic, incremental, lightly evidenced, or mainly promotional.
- **3–4.9:** Commentary, funding, executive opinion, or a feature/workflow claim with crucial evidence missing.
- **0–2.9:** Off-topic, speculative, inaccessible, copied, or unsupported.

# Category and evidence hard rules

Choose exactly one category and set `category_requirements_met` accurately:

- `today-use`: only a feature that is already publicly available in ChatGPT, Claude, Gemini, Copilot, Feishu, Dify, or a similarly relevant product. Require an official announcement, help page, documentation, or Release, plus clear availability. A preview, waitlist, rumor, or unreleased demo fails this category.
- `enterprise-case`: require all three: a named business object/user, an implementation workflow, and a verifiable result or outcome. Pure vendor promotion and claims without process or result fail this category.
- `method-pitfall`: a reusable lesson about needs, scope, RAG, evaluation, permissions, human collaboration, launch, adoption, or ROI. The source must establish the lesson rather than merely state an opinion.
- `beginner-tech`: explains a technical change or concept in a way that affects a specific product decision such as reliability, latency, cost, privacy, architecture, or human review.
- `china-career`: a China-market case, company/tool change, role capability shift, Xiamen opportunity, or remote-job signal. Preserve an original company, product, or recruitment source.
- `hands-on`: do not assign external news to this category. The program generates the daily hands-on card separately.

Set `evidence_complete` true only when the supplied original source is accessible enough to verify the central claim. Use `evidence_note` to name the evidence and its largest gap. One item must have only one primary category. The source-suggested category is advisory and may be corrected.

# Actionability

Set `actionable_within_7_days` true and provide `action` only when an honest, source-grounded action exists. Otherwise set it false and leave `action` empty. Non-actionable items may still score 7+ when evidence, cognitive gain, impact, and product relevance justify it.

Use three to five specific topic tags.
