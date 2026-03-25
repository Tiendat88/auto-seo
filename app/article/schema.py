"""JSON-LD schema markup generation and featured snippet detection."""

import re
from typing import Any, Literal

from pydantic import BaseModel

from app.article.models import (
    ArticleContent,
    ArticleOutline,
    CompetitiveAnalysis,
    SeoMetadata,
)


class SchemaMarkup(BaseModel):
    """JSON-LD schema markup for Article and FAQPage."""

    article_schema: dict[str, Any]
    faq_schema: dict[str, Any] | None = None


class SnippetOpportunity(BaseModel):
    """A detected featured snippet optimization opportunity."""

    type: Literal["list", "table", "definition", "qa"]
    section_heading: str
    description: str
    current_format_ok: bool
    suggestion: str | None = None


def generate_schema_markup(
    article: ArticleContent,
    seo_meta: SeoMetadata,
    outline: ArticleOutline,
) -> SchemaMarkup:
    """Generate Article and FAQPage JSON-LD from article data."""
    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": seo_meta.title_tag,
        "description": seo_meta.meta_description,
        "articleSection": [s.heading for s in article.sections],
        "wordCount": article.total_word_count,
        "keywords": seo_meta.primary_keyword,
    }

    faq_schema = None
    if article.faq:
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f.question,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": f.answer,
                    },
                }
                for f in article.faq
            ],
        }

    return SchemaMarkup(article_schema=article_schema, faq_schema=faq_schema)


# --- Featured Snippet Detection ---

_NUMBERED_PATTERN = re.compile(r"(?:^|\n)\s*\d+[.)]\s", re.MULTILINE)
_ORDINAL_PATTERN = re.compile(
    r"\b(?:first|second|third|fourth|fifth|step\s+\d)\b", re.IGNORECASE
)
_LIST_MARKDOWN = re.compile(r"(?:^|\n)\s*[-*]\s", re.MULTILINE)
_TABLE_MARKDOWN = re.compile(r"\|.*\|.*\|", re.MULTILINE)
_COMPARISON_PATTERN = re.compile(
    r"\b(?:vs\.?|versus|compared\s+to|comparison|better\s+than|worse\s+than)\b",
    re.IGNORECASE,
)
_DEFINITION_HEADING = re.compile(r"^what\s+(?:is|are)\b", re.IGNORECASE)


def detect_snippet_opportunities(
    article: ArticleContent,
    analysis: CompetitiveAnalysis,
) -> list[SnippetOpportunity]:
    """Detect featured snippet opportunities in article content."""
    opportunities: list[SnippetOpportunity] = []

    for section in article.sections:
        content = section.content
        heading = section.heading

        # List snippet: numbered items or ordinals without markdown list formatting
        has_numbered = bool(_NUMBERED_PATTERN.search(content))
        has_ordinals = bool(_ORDINAL_PATTERN.search(content))
        has_list_md = bool(_LIST_MARKDOWN.search(content))

        if (has_numbered or has_ordinals) and not has_list_md:
            opportunities.append(SnippetOpportunity(
                type="list",
                section_heading=heading,
                description="Section contains sequential items without list formatting",
                current_format_ok=False,
                suggestion="Convert numbered items to a markdown list for snippet eligibility",
            ))
        elif has_list_md:
            opportunities.append(SnippetOpportunity(
                type="list",
                section_heading=heading,
                description="Section uses list formatting",
                current_format_ok=True,
            ))

        # Table snippet: comparison language without table formatting
        has_comparison = bool(_COMPARISON_PATTERN.search(content))
        has_table_md = bool(_TABLE_MARKDOWN.search(content))

        if has_comparison and not has_table_md:
            opportunities.append(SnippetOpportunity(
                type="table",
                section_heading=heading,
                description="Section discusses comparisons without table format",
                current_format_ok=False,
                suggestion="Add a comparison table to target featured snippet",
            ))

        # Definition snippet: heading starts with "What is/are"
        if _DEFINITION_HEADING.match(heading):
            first_para = content.split("\n\n")[0] if content else ""
            word_count = len(first_para.split())
            format_ok = 30 <= word_count <= 60
            opp = SnippetOpportunity(
                type="definition",
                section_heading=heading,
                description=f"Definition heading with {word_count}-word opening paragraph",
                current_format_ok=format_ok,
            )
            if not format_ok:
                opp.suggestion = "Adjust opening paragraph to 30-60 words for definition snippet"
            opportunities.append(opp)

    # Q&A snippets from FAQ
    for faq in article.faq:
        opportunities.append(SnippetOpportunity(
            type="qa",
            section_heading="FAQ",
            description=f"FAQ: {faq.question[:60]}",
            current_format_ok=True,
        ))

    return opportunities
