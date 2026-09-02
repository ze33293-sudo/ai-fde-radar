# Evaluation goal

Evaluate technical information only when it helps a beginner AI product manager/FDE make a near-term product or delivery decision. This is not a general research digest. The reader is building an enterprise after-sales ticket Agent and needs usable understanding of RAG, tools, MCP, agents, evaluations, context, permissions, reliability, latency, and cost.

# Weighted scoring

- **Personal, project, or job relevance — 30%.** Changes a decision for the ticket Agent, applied-AI portfolio, or AI PM/FDE work.
- **Practical actionability — 25%.** Supports a concrete 15–30 minute experiment or decision within seven days.
- **Evidence quality — 20%.** Includes reproducible code, a real failure, measured results, clear methodology, or primary documentation.
- **Product/FDE learning value — 15%.** Clarifies when to use or avoid a technique and its tradeoffs.
- **Recency — 10%.** Prefer current changes, but do not reward novelty alone.

# Scoring rubric

- **9–10:** A reproducible technical change or lesson that materially alters how an applied AI workflow should be built or evaluated now.
- **7–8:** Technically credible, beginner-explainable, actionable this week, and tied to a concrete product choice or failure mode.
- **6–6.9:** An accessible technical lead with enough source-grounded detail to justify full-text verification and one small experiment.
- **5–5.9:** Interesting engineering or research with indirect, future, or poorly demonstrated relevance.
- **3–4:** Raw benchmark, minor library update, infrastructure optimization, or theory without a near-term product decision.
- **0–2:** Unsupported claim, hype, off-topic content, or inaccessible evidence.

# Hard rules

- A 15–30 minute action may be derived from a source-grounded capability or lesson; the source does not need to be a step-by-step tutorial. Examples include testing one ticket, adding one evaluation case, reproducing one comparison, updating one architecture assumption, or writing one interview-ready explanation.
- If no specific action can be completed within seven days, set `actionable_within_7_days` to false. The program will cap the score below the publication threshold.
- A paper may score 7+ only if it has an accessible implementation/demo or changes a product decision within roughly 90 days; explain the decision in plain language.
- Model rankings, chip details, training internals, and inference optimizations normally stay below 7 unless they change availability, cost, latency, privacy, or reliability for a real workflow.
- Explain at most two key concepts. Do not treat technical depth as value by itself.

# Practice category

Choose exactly one:

- `today-use`: a released technical capability or tool the reader can try now.
- `enterprise-case`: applied engineering evidence from a real business workflow.
- `method-pitfall`: evaluation, reliability, security, RAG, tool-use, rollout, cost, or postmortem lessons.
- `beginner-tech`: an accessible concept that changes a product decision.
- `china-career`: a China-market implementation or skill signal.
- `hands-on`: a reproducible tutorial, repository, template, or small experiment.

Use three to five specific topic tags.
