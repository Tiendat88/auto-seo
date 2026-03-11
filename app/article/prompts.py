"""LLM prompt templates for article generation pipeline."""

from app.article.models import (
    CompetitiveAnalysis,
)
from app.serp.models import SerpData


def analysis_prompt(serp: SerpData) -> str:
    results_block = "\n".join(
        f"{r.rank}. [{r.title}]({r.url})\n   {r.snippet}" for r in serp.results
    )
    questions_block = "\n".join(f"- {q.question}" for q in serp.questions) or (
        "None available"
    )

    query_str = serp.query
    return f"""You are an SEO analyst. Analyze these top 10 search results
for the query "{query_str}".

Results:
{results_block}

People Also Ask:
{questions_block}

Extract the following:
1. Primary keyword (the main term competitors target) and 5-10 secondary keywords
2. 3-5 long-tail keyword variations
3. Major themes covered across the top results, with how many results address each theme
4. Subtopics within each theme
5. Content gaps — topics NOT well covered that would add value
6. Estimated average word count of top results (estimate from snippet depth and title complexity)
7. Common heading patterns (what H2-level topics do competitors use?)
8. Search intent classification: informational | transactional | navigational | commercial"""


def outline_prompt(
    topic: str,
    target_word_count: int,
    language: str,
    analysis: CompetitiveAnalysis,
) -> str:
    themes_block = "\n".join(
        f"- {t.theme} (covered by {t.frequency}/10 results): {', '.join(t.subtopics)}"
        for t in analysis.themes
    )
    gaps_block = "\n".join(
        f"- {g.topic}: {g.reason}" for g in analysis.content_gaps
    ) or "None identified"

    return f"""You are an SEO content strategist. Create a detailed article outline for: "{topic}"

Target word count: {target_word_count}
Language: {language}
Search intent: {analysis.search_intent}

Competitive analysis:
- Primary keyword: {analysis.keywords.primary}
- Secondary keywords: {", ".join(analysis.keywords.secondary)}
- Long-tail keywords: {", ".join(analysis.keywords.long_tail)}

Themes competitors cover:
{themes_block}

Content gaps to exploit:
{gaps_block}

Common heading patterns: {", ".join(analysis.common_heading_patterns)}

Requirements:
- One H1 that includes the primary keyword naturally
- 5-8 H2 sections covering the major themes
- H3 subsections where depth is needed
- Allocate target_word_count to each section (must sum to approximately {target_word_count})
- Include key_points for each section (what must be covered)
- Include keywords_to_include for each section
- End with 4-6 FAQ questions drawn from search questions and content gaps
- The outline should be structured to satisfy the search intent: {analysis.search_intent}"""


def section_prompt(
    topic: str,
    heading: str,
    heading_level: str,
    target_word_count: int,
    key_points: list[str],
    keywords: list[str],
    previous_ending: str,
    language: str,
    revision_instructions: str | None = None,
) -> str:
    key_points_block = "\n".join(
        f"- {kp}" for kp in key_points
    ) if key_points else (
        "Use your judgment"
    )
    keywords_block = ", ".join(keywords) if keywords else "None specified"

    transition = ""
    if previous_ending:
        transition = (
            f'\nPrevious section ended with: "{previous_ending}"\n'
            "Continue naturally from this context.\n"
        )

    revision = ""
    if revision_instructions:
        revision = (
            "\nREVISION REQUIRED. Issues from previous draft:\n"
            f"{revision_instructions}\n"
            "Please address these issues in your rewrite.\n"
        )

    return f"""You are an expert content writer creating a section of an article about "{topic}".

Section heading: {heading} ({heading_level})
Target length: ~{target_word_count} words
Language: {language}
{transition}
Key points to cover:
{key_points_block}

Keywords to naturally include: {keywords_block}
{revision}
Guidelines:
- Write naturally and engagingly; avoid keyword stuffing
- Use concrete examples, data points, and actionable advice
- Vary sentence length and structure for readability
- Do NOT use filler phrases like "In today's world", "It's important to note", "In conclusion"
- Do NOT include the heading itself — output only the body text for this section
- Write in {language}
- Aim for exactly ~{target_word_count} words"""


def faq_prompt(questions: list[str], topic: str, language: str) -> str:
    questions_block = "\n".join(f"- {q}" for q in questions)
    return f"""Write concise, helpful answers for these FAQ questions about "{topic}".

Questions:
{questions_block}

Guidelines:
- Each answer should be 2-4 sentences
- Be direct and specific — no filler
- Include relevant keywords naturally
- Write in {language}

Return a JSON object with an "items" key containing an array of objects
with "question" and "answer" fields."""


def seo_metadata_prompt(topic: str, primary_keyword: str, article_intro: str) -> str:
    return f"""Generate SEO metadata for an article about "{topic}".

Primary keyword: {primary_keyword}
Article introduction (first 200 words): {article_intro[:800]}

Generate:
1. title_tag: Under 60 characters, includes primary keyword, compelling for clicks
2. meta_description: Under 155 characters, includes primary keyword, summarizes value proposition
3. primary_keyword: The main keyword this article targets
4. slug: URL-friendly version of the title (lowercase, hyphens, no special chars)"""


def links_prompt(
    topic: str,
    section_headings: list[str],
    analysis: CompetitiveAnalysis,
    serp: SerpData,
) -> str:
    headings_block = "\n".join(f"- {h}" for h in section_headings)
    domains_block = "\n".join(f"- {r.domain}" for r in serp.results[:5])
    themes_str = ", ".join(t.theme for t in analysis.themes)

    return f"""Suggest links for an article about "{topic}".

Article sections:
{headings_block}

Competitor domains:
{domains_block}

Topics from competitive analysis: {themes_str}

Generate:
1. Internal links (3-5): Identify anchor text phrases that could link to
related content on the same website. For each, provide the anchor_text,
suggested_target_topic, and placement_context (a sentence describing where
in the article it fits).

2. External references (2-4): Select authoritative sources that would add
credibility (industry reports, established publications, academic research).
For each, use ONLY URLs from the competitor domains listed above or other
real, well-known authoritative domains. Do NOT invent or guess URLs. Provide
title, url, authority_reason, and which placement_section of the article it
belongs in.

Make internal link suggestions diverse — cover different sections of the
article. Make external references from well-known, authoritative domains."""


def quality_llm_prompt(article_text: str, themes: list[str]) -> str:
    themes_block = ", ".join(themes)
    # Truncate article to avoid token limits
    truncated = article_text[:4000]
    return f"""Rate this article on two quality dimensions (score 0.0 to 1.0 each):

1. content_depth: Does it thoroughly cover the expected themes? Expected themes: {themes_block}
2. readability: Does it read naturally and engagingly? Or does it feel AI-generated/robotic?

Article (truncated):
{truncated}

For each dimension, provide:
- name: the dimension name
- score: 0.0 to 1.0
- feedback: specific, actionable feedback

Return a JSON object with a "dimensions" key containing an array of two objects."""
