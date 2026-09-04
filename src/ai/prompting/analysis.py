"""Prompt construction for profile-driven content analysis."""

from ...models import ContentItem
from ...processing.profiles import LoadedProfile
from .common import EVIDENCE_RULES, UNTRUSTED_INPUT_RULE

ANALYSIS_RULES = f"""You are a content curator evaluating an item under the supplied processing profile.

- {UNTRUSTED_INPUT_RULE}
- Base the analysis only on the supplied item and its metadata.
{EVIDENCE_RULES}
- Apply the profile's evaluation policy consistently."""

PRACTICE_PROFILE_IDS = {"ai-product-fde", "tech-news"}


def _analysis_contract(profile: LoadedProfile) -> str:
    if profile.id not in PRACTICE_PROFILE_IDS:
        return """{
  "score": <number from 0 to 10>,
  "reason": "<concise explanation>",
  "summary": "<one-sentence summary>",
  "tags": ["<tag>", "..."]
}"""
    return """{
  "score": <number from 0 to 10>,
  "reason": "<concise explanation using the configured scoring weights>",
  "summary": "<one-sentence source-grounded summary>",
  "tags": ["<tag>", "..."],
  "practice_category": "<today-use|enterprise-case|method-pitfall|beginner-tech|china-career|hands-on>",
  "actionable_within_7_days": <true or false>,
  "action": "<one concrete 15-30 minute action, or empty when false>",
  "project_relevance": "<specific link to an after-sales ticket Agent, AI PM/FDE portfolio, or job search>",
  "evidence_complete": <true only when the original source is usable and the factual claim is verifiable>,
  "category_requirements_met": <true only when the selected category's hard definition is met>,
  "evidence_note": "<briefly name the primary evidence and any important gap>"
}"""


def analysis_system_prompt(profile: LoadedProfile) -> str:
    return f"""{ANALYSIS_RULES}

# Profile policy

{profile.analysis_prompt}

# Output contract

Return valid JSON only:
{_analysis_contract(profile)}"""


def analysis_user_prompt(
    item: ContentItem,
    content_section: str,
    discussion_section: str,
) -> str:
    verification_target = item.metadata.get("verification_target_practice_category")
    verification_section = ""
    if verification_target:
        verification_section = f"""
Verification target category: {verification_target}
This original source was fetched because that required column still lacks verified
evidence. Use the target category only if its hard definition is genuinely met;
otherwise choose the best evidence-supported category and mark the target's gap
honestly. Never approve an item merely to fill a quota."""
    return f"""Analyze the following content.

Title: {item.title}
Source: {item.source_type.value}
Author: {item.author or "Unknown"}
URL: {item.url}
Published at: {item.published_at.isoformat()}
Region: {item.metadata.get("region", "global")}
Suggested practice category: {item.metadata.get("practice_category") or "none"}
The suggested category is discovery metadata only. Preserve it as context, but choose
exactly one final category from the evidence; do not force a match.
When a first-party China-market source is suggested as china-career, use that category
if the central value is a meaningful domestic product/ecosystem change or a concrete
shift in the skills applied-AI roles need. Do not move it to today-use merely because
the changed tool is available, and do not approve routine version churn.
{verification_section}
{content_section}
{discussion_section}"""
