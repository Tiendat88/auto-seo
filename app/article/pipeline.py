"""Pipeline runner: state machine for article generation."""

import asyncio
import logging
import re
import statistics
import time
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.article.models import (
    ArticleContent,
    ArticleOutline,
    ArticleSection,
    CompetitiveAnalysis,
    CompetitorTheme,
    ContentGap,
    FaqItem,
    HeadingLevel,
    KeywordAnalysis,
    KeywordCluster,
    KeywordDistribution,
    KeywordUsage,
    LinkSuggestions,
    QualityScore,
    ReviewResult,
    ScoreDimension,
    SectionKeywordDensity,
    SeoMetadata,
    SeoMetaOptions,
)
from app.article.prompts import (
    _structured_article_text,
    accuracy_consistency_score_prompt,
    analysis_prompt,
    depth_differentiation_score_prompt,
    edit_prompt,
    format_brief,
    generate_article_prompt,
    links_prompt,
    meta_options_prompt,
    outline_prompt,
    readability_actionability_score_prompt,
    review_prompt,
    seo_metadata_prompt,
)
from app.article.scorer import (
    score_differentiation,
    score_heading_structure,
    score_humanity,
    score_keyword_distribution,
    score_keyword_usage,
    score_readability,
    score_word_count,
)
from app.article.scrubber import scrub_article
from app.config import settings
from app.errors import StepError
from app.job.models import Job, JobStatus
from app.llm import LlmClient, get_llm_council
from app.serp.client import SerpProvider

log = logging.getLogger(__name__)

StepFn = Callable[
    [Job, AsyncSession, LlmClient, SerpProvider],
    Coroutine[Any, Any, None],
]


# --- Internal Models ---


class _ScorePair(BaseModel):
    dimensions: list[ScoreDimension] = Field(..., min_length=2, max_length=2)


# --- Pipeline Steps ---


async def research_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Fetch SERP data and optionally scrape top result pages via Firecrawl."""
    if job.serp_data:
        return
    data = await serp.search(job.topic)

    if settings.firecrawl_api_key:
        from app.serp.fetcher import fetch_page_content

        fetch_events: list[tuple[str, str, str]] = []

        async def _fetch_one(result):
            try:
                content, wc = await fetch_page_content(result.url)
                result.content = content
                result.word_count = wc
                fetch_events.append(
                    ("researching", "fetch", f"Fetched {result.domain}: {wc} words")
                )
            except Exception as e:
                log.warning("Failed to fetch %s: %s", result.url, e)

        await asyncio.gather(
            *[_fetch_one(r) for r in data.results[:settings.content_fetch_top_n]]
        )
        for step, event, detail in fetch_events:
            job.append_event(step, event, detail)

    job.set_serp(data)


async def planning_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Multi-provider analysis + single-provider outline in one pipeline state."""
    if job.outline_data:
        return

    serp_data = job.get_serp()
    if not serp_data:
        raise StepError("Cannot plan without SERP data")

    # --- Phase 1: Multi-provider analysis with tools ---
    if not job.analysis_data:
        job.current_step = "planning:analysis"
        session.add(job)
        await session.commit()

        prompt = analysis_prompt(serp_data)
        council = get_llm_council()

        tasks = []
        for provider in council:
            if settings.firecrawl_api_key:
                from functools import partial

                from app.article.tools import RESEARCH_TOOLS, handle_tool_call

                allowed_domains = {r.domain for r in serp_data.results}
                handler = partial(handle_tool_call, allowed_domains=allowed_domains)
                tasks.append(provider.generate_with_tools(
                    prompt, RESEARCH_TOOLS, handler, CompetitiveAnalysis,
                ))
            else:
                tasks.append(
                    provider.generate_structured(prompt, CompetitiveAnalysis)
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for provider in council:
            usage = provider.drain_usage()
            for u in usage:
                u.step = "planning"
            job.append_usage(usage)
            for entry in provider.drain_call_log():
                job.append_event("planning", entry["event"], entry["detail"])

        analyses: list[CompetitiveAnalysis] = []
        for i, r in enumerate(results):
            if isinstance(r, CompetitiveAnalysis):
                name = council[i]._backend
                job.append_event(
                    "planning", "result",
                    f"{name}: primary='{r.keywords.primary}', "
                    f"{len(r.themes)} themes, {len(r.content_gaps)} gaps",
                )
                analyses.append(r)
            elif isinstance(r, Exception):
                log.warning("Analysis call failed: %s", r)

        if not analyses:
            raise StepError("All analysis calls failed")

        analysis = (
            _merge_competitive_analyses(analyses)
            if len(analyses) > 1
            else analyses[0]
        )
        if len(analyses) > 1:
            job.append_event(
                "planning", "merge",
                f"Merged {len(analyses)} analyses from {len(council)} providers",
            )
        job.set_analysis(analysis)
        session.add(job)
        await session.commit()
    else:
        analysis = job.get_analysis()

    # --- Phase 2: Single-provider outline from merged analysis ---
    job.current_step = "planning:outline"
    session.add(job)
    await session.commit()

    from app.article.prompts import extract_competitor_headings

    competitor_headings = extract_competitor_headings(serp_data)
    brand_voice = job.get_brand_voice()
    prompt = outline_prompt(
        job.topic, job.target_word_count, job.language, analysis,
        brand_voice=brand_voice,
        competitor_headings=competitor_headings,
    )
    outline = await llm.generate_structured(prompt, ArticleOutline)
    job.set_outline(outline)


async def generate_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Generate full article in a single call, then metadata + links in parallel."""
    if job.links_data:
        return
    outline = job.get_outline()
    analysis = job.get_analysis()
    serp_data = job.get_serp()
    if not outline or not analysis or not serp_data:
        raise StepError("Cannot generate without outline, analysis, and SERP data")

    quality = job.get_quality()
    revision_instructions = quality.revision_instructions if quality else None
    brand_voice = job.get_brand_voice()

    # 1. Single-call article generation (includes FAQ)
    job.current_step = "generating:article"
    session.add(job)
    await session.commit()

    max_tok = max(4096, int(job.target_word_count * 1.5))
    prompt = generate_article_prompt(
        outline, job.language, revision_instructions,
        brand_voice=brand_voice, target_word_count=job.target_word_count,
        content_gaps=analysis.content_gaps,
    )
    article_md = await llm.generate_text(prompt, max_tok)

    # 2. Parse markdown → sections + FAQ, then scrub
    sections, faq_items = _parse_article_markdown(article_md, outline)
    article, scrub_stats = scrub_article(ArticleContent(sections=sections, faq=faq_items))
    job.append_event("generating", "result",
        f"Article: {article.total_word_count} words, {len(faq_items)} FAQ items")
    job.append_event("generating", "scrub",
        f"Scrubbed: {scrub_stats.filler_removed} fillers removed, "
        f"{scrub_stats.paragraphs_split} para splits | "
        f"Found: {scrub_stats.ai_words_found} AI words, "
        f"{scrub_stats.em_dashes_found} em-dashes")

    # 3. Parallel: metadata + links + meta options
    job.current_step = "generating:metadata"
    session.add(job)
    await session.commit()
    brief = outline.brief
    meta_task = llm.generate_structured(
        seo_metadata_prompt(
            job.topic,
            analysis.keywords.primary,
            article.sections[0].content if article.sections else "",
            brief=brief,
            section_headings=[s.heading for s in article.sections],
        ),
        SeoMetadata,
    )
    competitor_pages = [
        (r.title, r.url) for r in serp_data.results if r.content
    ]
    links_task = llm.generate_structured(
        links_prompt(
            job.topic,
            [s.heading for s in article.sections],
            analysis,
            serp_data,
            brief=brief,
            section_summaries=_section_summaries(article.sections),
            competitor_pages=competitor_pages,
        ),
        LinkSuggestions,
    )
    meta_opts_task = llm.generate_structured(
        meta_options_prompt(
            job.topic,
            analysis.keywords.primary,
            article.sections[0].content if article.sections else "",
            [s.heading for s in article.sections],
            brief=brief,
        ),
        SeoMetaOptions,
    )

    results = await asyncio.gather(
        meta_task, links_task, meta_opts_task, return_exceptions=True
    )
    seo_meta = results[0]
    links = results[1]
    meta_opts = results[2] if not isinstance(results[2], Exception) else None
    if isinstance(results[2], Exception):
        log.warning("Meta options generation failed: %s", results[2])
    if isinstance(seo_meta, Exception):
        raise seo_meta
    if isinstance(links, Exception):
        raise links

    # 4. Keyword analysis (algorithmic)
    kw_analysis = _compute_keyword_analysis(article, analysis, seo_meta)

    # Atomic write
    job.set_article(article)
    job.set_seo_metadata(seo_meta)
    job.set_keyword_analysis(kw_analysis)
    job.set_links(links)
    if meta_opts:
        job.set_meta_options(meta_opts)


async def score_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Score article quality with algorithmic guardrails + parallel LLM scoring."""
    if job.quality_data:
        return
    article = job.get_article()
    analysis = job.get_analysis()
    seo_meta = job.get_seo_metadata()
    outline = job.get_outline()
    kw_analysis = job.get_keyword_analysis()
    if not article or not analysis or not seo_meta or not outline:
        raise StepError("Cannot score without article, analysis, SEO metadata, and outline")

    # Algorithmic dimensions (free, deterministic)
    job.current_step = "scoring:algorithmic"
    session.add(job)
    await session.commit()

    serp_data = job.get_serp()
    algo_dims = [
        score_keyword_usage(article, analysis, seo_meta),
        score_heading_structure(article),
        score_word_count(article, job.target_word_count),
        score_readability(article),
        score_humanity(article),
        score_differentiation(article, outline.brief, serp_data),
    ]
    if kw_analysis:
        algo_dims.append(score_keyword_distribution(kw_analysis))

    # LLM dimensions — all configured providers in parallel
    job.current_step = "scoring:llm"
    session.add(job)
    await session.commit()
    brief = outline.brief
    structured_text = _structured_article_text(article, 20000)
    brief_text = format_brief(brief) if brief else ""

    score_prompts = [
        depth_differentiation_score_prompt(structured_text, brief_text),
        accuracy_consistency_score_prompt(structured_text, brief_text),
        readability_actionability_score_prompt(structured_text, brief_text),
    ]

    council = get_llm_council()
    tasks = []
    for provider in council:
        tasks.extend(
            provider.generate_structured(p, _ScorePair, use_cache=False)
            for p in score_prompts
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Drain usage and call logs from all council members
    n_prompts = len(score_prompts)
    for provider in council:
        usage = provider.drain_usage()
        for u in usage:
            u.step = "scoring"
        job.append_usage(usage)
        for entry in provider.drain_call_log():
            job.append_event("scoring", entry["event"], entry["detail"])

    # Collect all successful dimensions, log per-provider results
    all_dims: list[ScoreDimension] = []
    for i, r in enumerate(results):
        if isinstance(r, _ScorePair):
            provider_name = council[i // n_prompts]._backend
            dims = ", ".join(f"{d.name}={d.score:.2f}" for d in r.dimensions)
            job.append_event("scoring", "result", f"{provider_name}: {dims}")
            all_dims.extend(r.dimensions)
        elif isinstance(r, Exception):
            log.warning("Scoring call failed: %s", r)

    # Merge: average scores for dimensions with the same name
    llm_dims = _merge_score_dimensions(all_dims)
    job.append_event(
        "scoring", "merge",
        f"Merged {len(all_dims)} dimensions from {len(council)} providers",
    )

    succeeded = sum(1 for r in results if isinstance(r, _ScorePair))
    if succeeded < 2:
        raise StepError(f"Only {succeeded} scoring calls succeeded, need at least 2")

    dimensions = algo_dims + llm_dims
    total_weight = sum(DIMENSION_WEIGHTS.get(d.name, 1.0) for d in dimensions)
    weighted_sum = sum(
        d.score * DIMENSION_WEIGHTS.get(d.name, 1.0) for d in dimensions
    )
    overall = weighted_sum / total_weight
    passes = overall >= settings.quality_threshold

    quality = QualityScore(
        overall=round(overall, 3),
        dimensions=dimensions,
        passes_threshold=passes,
    )
    job.set_quality(quality)


async def review_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Holistic AI review with optional multi-provider consensus."""
    if job.review_data:
        return
    article = job.get_article()
    outline = job.get_outline()
    if not article or not outline:
        raise StepError("Cannot review without article and outline")

    brief = outline.brief
    structured_text = _structured_article_text(article, 20000)
    headings = [h.text for h in outline.headings]
    prompt = review_prompt(structured_text, headings, brief, job.target_word_count)

    # All configured providers review in parallel
    council = get_llm_council()
    tasks = [
        provider.generate_structured(prompt, ReviewResult, use_cache=False)
        for provider in council
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Drain usage and call logs from all council members
    for provider in council:
        usage = provider.drain_usage()
        for u in usage:
            u.step = "reviewing"
        job.append_usage(usage)
        for entry in provider.drain_call_log():
            job.append_event("reviewing", entry["event"], entry["detail"])

    # Log per-provider results
    reviews: list[ReviewResult] = []
    for i, r in enumerate(results):
        if isinstance(r, ReviewResult):
            provider_name = council[i]._backend
            n_issues = len(r.issues)
            critical = sum(
                1 for x in r.issues if x.severity in ("critical", "major")
            )
            job.append_event(
                "reviewing", "result",
                f"{provider_name}: {'PASS' if r.passed else 'FAIL'} "
                f"({n_issues} issues, {critical} critical/major)",
            )
            reviews.append(r)
        elif isinstance(r, Exception):
            log.warning("Review call failed: %s", r)

    if not reviews:
        raise StepError("All review calls failed")

    review = _merge_reviews(reviews) if len(reviews) > 1 else reviews[0]
    job.append_event(
        "reviewing", "merge",
        f"Merged {len(reviews)} reviews, passed={review.passed}",
    )

    # Build revision instructions from merged issues
    if not review.passed:
        actionable = [i for i in review.issues if i.severity in ("critical", "major")]
        if actionable:
            review.revision_instructions = "; ".join(
                f"[{i.category}] {i.description} -> {i.suggestion}" for i in actionable
            )

    job.set_review(review)


async def edit_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Edit article in place using score + review feedback."""
    article = job.get_article()
    outline = job.get_outline()
    quality = job.get_quality()
    review = job.get_review()
    brand_voice = job.get_brand_voice()
    if not article or not outline or not quality:
        raise StepError("Cannot edit without article, outline, and quality data")

    structured_text = _structured_article_text(article, 20000)
    brief = outline.brief
    prompt = edit_prompt(
        structured_text, brief, quality.dimensions, review,
        brand_voice=brand_voice, target_word_count=job.target_word_count,
        actual_word_count=article.total_word_count,
    )

    max_tok = max(4096, int(job.target_word_count * 1.5))
    edited_md = await llm.generate_text(prompt, max_tok)

    sections, faq_items = _parse_article_markdown(edited_md, outline)
    # Prefer parsed FAQ, fall back to existing if edit didn't include FAQ, then scrub
    edited, scrub_stats = scrub_article(ArticleContent(
        sections=sections,
        faq=faq_items if faq_items else article.faq,
    ))

    # Re-compute keyword analysis
    analysis = job.get_analysis()
    seo_meta = job.get_seo_metadata()
    if analysis and seo_meta:
        kw_analysis = _compute_keyword_analysis(edited, analysis, seo_meta)
        job.set_keyword_analysis(kw_analysis)

    job.set_article(edited)
    job.revision_count += 1


# --- Markdown Parser ---


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def _parse_article_markdown(
    markdown: str, outline: ArticleOutline
) -> tuple[list[ArticleSection], list[FaqItem]]:
    """Parse LLM markdown output into ArticleSections and FaqItems."""
    # Split into (level_str, heading_text, body) chunks
    chunks: list[tuple[str, str, str]] = []
    matches = list(_HEADING_RE.finditer(markdown))

    if not matches:
        # Fallback: no headings found — treat entire text as single H2 section
        return (
            [ArticleSection(
                heading="Article", heading_level=HeadingLevel.H2,
                content=markdown.strip(),
            )],
            [],
        )

    for i, m in enumerate(matches):
        level_str = m.group(1)  # "#", "##", or "###"
        heading_text = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        chunks.append((level_str, heading_text, body))

    # Separate FAQ section from article sections
    faq_items: list[FaqItem] = []
    article_chunks: list[tuple[str, str, str]] = []
    in_faq = False

    for level_str, heading_text, body in chunks:
        heading_lower = heading_text.lower()
        if not in_faq and ("faq" in heading_lower or "frequently asked" in heading_lower):
            in_faq = True
            continue  # Skip the FAQ heading itself

        if in_faq:
            # Each sub-heading in FAQ section is a question
            if body:
                faq_items.append(FaqItem(question=heading_text, answer=body))
        else:
            article_chunks.append((level_str, heading_text, body))

    # Build outline heading lookup for fuzzy matching
    outline_map: dict[str, HeadingLevel] = {}
    for h in outline.headings:
        outline_map[h.text.lower()] = h.level

    # Convert article chunks to ArticleSections
    sections: list[ArticleSection] = []
    for level_str, heading_text, body in article_chunks:
        if not body:
            continue
        heading_level = _match_heading_level(level_str, heading_text, outline_map)
        sections.append(ArticleSection(
            heading=heading_text,
            heading_level=heading_level,
            content=body,
        ))

    if not sections:
        # Fallback: all chunks were FAQ or empty
        sections = [ArticleSection(
            heading="Article", heading_level=HeadingLevel.H2, content=markdown.strip()
        )]

    return sections, faq_items


def _match_heading_level(
    level_str: str, heading_text: str, outline_map: dict[str, HeadingLevel]
) -> HeadingLevel:
    """Match a parsed heading to the outline, with fuzzy fallback."""
    text_lower = heading_text.lower()

    # Exact match
    if text_lower in outline_map:
        return outline_map[text_lower]

    # Fuzzy: check if outline heading is substring of parsed or vice versa
    for outline_text, level in outline_map.items():
        if outline_text in text_lower or text_lower in outline_text:
            return level

    # Infer from # count
    hash_count = len(level_str)
    if hash_count == 1:
        return HeadingLevel.H1
    if hash_count == 3:
        return HeadingLevel.H3
    return HeadingLevel.H2


# --- Helpers ---


def _section_summaries(sections: list[ArticleSection]) -> list[tuple[str, str]]:
    """Extract (heading, first_sentences) pairs for prompt context."""
    result = []
    for s in sections:
        sentences = s.content.split(".")
        summary = ". ".join(sentences[:2]).strip()
        if summary and not summary.endswith("."):
            summary += "."
        result.append((s.heading, summary))
    return result


def _merge_competitive_analyses(
    analyses: list[CompetitiveAnalysis],
) -> CompetitiveAnalysis:
    """Merge multiple competitive analyses by consensus."""
    from collections import Counter

    # Primary keyword: majority vote
    primaries = Counter(a.keywords.primary.lower() for a in analyses)
    primary = primaries.most_common(1)[0][0]
    for a in analyses:
        if a.keywords.primary.lower() == primary:
            primary = a.keywords.primary
            break

    # Secondary: union, dedup, frequency-rank (preserve first-seen casing)
    sec_counter: Counter[str] = Counter()
    sec_original: dict[str, str] = {}
    lt_original: dict[str, str] = {}
    for a in analyses:
        for kw in a.keywords.secondary:
            key = kw.lower()
            sec_counter[key] += 1
            if key not in sec_original:
                sec_original[key] = kw
        for kw in a.keywords.long_tail:
            key = kw.lower()
            if key not in lt_original:
                lt_original[key] = kw
    secondary = [sec_original[kw] for kw, _ in sec_counter.most_common()]
    long_tail = sorted(lt_original.values(), key=lambda x: x.lower())

    # Themes: exact match (case-insensitive), average frequency, union subtopics
    theme_groups: dict[str, list[CompetitorTheme]] = {}
    for a in analyses:
        for t in a.themes:
            key = t.theme.lower()
            theme_groups.setdefault(key, []).append(t)
    themes = []
    for key, group in theme_groups.items():
        avg_freq = round(sum(t.frequency for t in group) / len(group))
        all_subs = list(dict.fromkeys(s for t in group for s in t.subtopics))
        themes.append(CompetitorTheme(
            theme=group[0].theme, frequency=max(avg_freq, 1), subtopics=all_subs,
        ))
    themes.sort(key=lambda t: t.frequency, reverse=True)

    # Content gaps: union, dedup by topic
    seen_gaps: set[str] = set()
    gaps: list[ContentGap] = []
    for a in analyses:
        for g in a.content_gaps:
            key = g.topic.lower()
            if key not in seen_gaps:
                seen_gaps.add(key)
                gaps.append(g)

    avg_wc = round(sum(a.avg_word_count for a in analyses) / len(analyses))

    pattern_counter: Counter[str] = Counter()
    for a in analyses:
        for p in a.common_heading_patterns:
            pattern_counter[p.lower()] += 1
    patterns = [p for p, _ in pattern_counter.most_common()]

    intents = Counter(a.search_intent for a in analyses)
    intent = intents.most_common(1)[0][0]

    return CompetitiveAnalysis(
        keywords=KeywordCluster(
            primary=primary, secondary=secondary, long_tail=long_tail,
        ),
        themes=themes,
        content_gaps=gaps,
        avg_word_count=avg_wc,
        common_heading_patterns=patterns,
        search_intent=intent,
    )


def _merge_score_dimensions(dims: list[ScoreDimension]) -> list[ScoreDimension]:
    """Average scores for dimensions with the same name, group feedback by scorer."""
    groups: dict[str, list[ScoreDimension]] = defaultdict(list)
    for d in dims:
        groups[d.name].append(d)
    merged = []
    for name, group in groups.items():
        avg = sum(d.score for d in group) / len(group)
        if len(group) == 1:
            feedback = group[0].feedback
        else:
            parts = [
                f"Scorer {i + 1}: {d.feedback}"
                for i, d in enumerate(group) if d.feedback
            ]
            feedback = " | ".join(parts)
        merged.append(ScoreDimension(name=name, score=round(avg, 3), feedback=feedback))
    return merged


def _merge_reviews(reviews: list[ReviewResult]) -> ReviewResult:
    """Merge multiple ReviewResults by consensus, grouped by reviewer."""
    all_issues = []
    all_strengths: list[str] = []
    summaries: list[str] = []
    for i, r in enumerate(reviews):
        label = f"Reviewer {i + 1}"
        summaries.append(f"{label}: {r.summary}")
        for issue in r.issues:
            issue.description = f"[{label}] {issue.description}"
            all_issues.append(issue)
        all_strengths.extend(r.strengths)

    unique_strengths = list(dict.fromkeys(all_strengths))
    has_serious = any(i.severity in ("critical", "major") for i in all_issues)
    passed = not has_serious

    return ReviewResult(
        passed=passed,
        summary=" | ".join(summaries),
        issues=all_issues,
        strengths=unique_strengths,
    )


def _compute_keyword_analysis(
    article: ArticleContent,
    analysis: CompetitiveAnalysis,
    seo_meta: SeoMetadata,
) -> KeywordAnalysis:
    """Compute keyword usage statistics algorithmically."""
    parts = [s.content for s in article.sections]
    parts.extend(f"{f.question} {f.answer}" for f in article.faq)
    full_text = " ".join(parts)
    word_count = len(full_text.split())

    def usage(keyword: str) -> KeywordUsage:
        kw = keyword.lower()
        text = full_text.lower()
        count = len(re.findall(r"\b" + re.escape(kw) + r"\b", text))
        density = round(count / word_count * 100, 2) if word_count else 0
        locations: list[str] = []
        if kw in seo_meta.title_tag.lower():
            locations.append("title")
        if kw in seo_meta.meta_description.lower():
            locations.append("meta_description")
        if article.sections and kw in article.sections[0].content.lower():
            locations.append("intro")
        for s in article.sections:
            if kw in s.heading.lower():
                locations.append(f"heading:{s.heading}")
        return KeywordUsage(keyword=keyword, count=count, density=density, locations=locations)

    primary = usage(analysis.keywords.primary)
    secondary = [usage(kw) for kw in analysis.keywords.secondary]

    # Section-level keyword distribution
    primary_kw = analysis.keywords.primary.lower()
    section_densities = []
    densities_list: list[float] = []
    for s in article.sections:
        section_text = s.content.lower()
        section_wc = s.word_count
        kw_count = len(re.findall(r"\b" + re.escape(primary_kw) + r"\b", section_text))
        density = round(kw_count / section_wc * 100, 2) if section_wc else 0.0
        densities_list.append(density)
        section_densities.append(SectionKeywordDensity(
            section_heading=s.heading,
            keyword=analysis.keywords.primary,
            count=kw_count,
            density=density,
            word_count=section_wc,
        ))

    # Distribution score: 1.0 = perfectly even, lower = clustered
    if primary.count == 0:
        dist_score = 0.0
    elif len(densities_list) < 2:
        dist_score = 1.0
    elif any(d > 0 for d in densities_list):
        mean_d = statistics.mean(densities_list)
        stdev_d = statistics.stdev(densities_list)
        normalized = stdev_d / mean_d if mean_d > 0 else 0
        dist_score = round(max(0.0, min(1.0, 1.0 - normalized)), 2)
    else:
        dist_score = 0.0

    distribution = KeywordDistribution(
        primary_by_section=section_densities,
        distribution_score=dist_score,
    )

    return KeywordAnalysis(
        primary=primary, secondary=secondary, keyword_distribution=distribution
    )


# --- Scoring Weights ---

DIMENSION_WEIGHTS: dict[str, float] = {
    "word_count_target": 2.0,
}


# --- Step Registry ---

STEP_SEQUENCE: list[tuple[JobStatus, StepFn]] = [
    (JobStatus.RESEARCHING, research_step),
    (JobStatus.PLANNING, planning_step),
    (JobStatus.GENERATING, generate_step),
    (JobStatus.SCORING, score_step),
    (JobStatus.REVIEWING, review_step),
]

_DATA_CHECKS: list[tuple[JobStatus, str]] = [
    (JobStatus.RESEARCHING, "serp_data"),
    (JobStatus.PLANNING, "outline_data"),
    (JobStatus.GENERATING, "links_data"),
    (JobStatus.SCORING, "quality_data"),
    (JobStatus.REVIEWING, "review_data"),
]


def _determine_resume_index(job: Job) -> int:
    """Find the first step whose output is missing."""
    for i, (_, attr) in enumerate(_DATA_CHECKS):
        if getattr(job, attr) is None:
            return i
    return len(_DATA_CHECKS)


async def run_pipeline(
    job_id: str,
    session: AsyncSession,
    llm: LlmClient,
    serp_client: SerpProvider,
) -> None:
    """Execute the article generation pipeline for a job."""
    job = await session.get(Job, job_id)
    if not job:
        log.error("Job %s not found", job_id)
        return

    start_index = _determine_resume_index(job)
    log.info("Starting pipeline for job=%s from step=%d", job_id, start_index)

    for i in range(start_index, len(STEP_SEQUENCE)):
        next_status, step_fn = STEP_SEQUENCE[i]
        job.status = next_status
        job.current_step = next_status.value
        session.add(job)
        await session.commit()

        try:
            job.append_event(next_status.value, "step_start", f"Starting {next_status.value}")
            step_start = time.monotonic()
            await step_fn(job, session, llm, serp_client)
            elapsed = time.monotonic() - step_start
            job.append_event(next_status.value, "timing", f"{elapsed:.1f}s")
            # Drain token usage and call logs from LLM client
            usage = llm.drain_usage()
            for u in usage:
                u.step = next_status.value
            job.append_usage(usage)
            for entry in llm.drain_call_log():
                job.append_event(next_status.value, entry["event"], entry["detail"])
            session.add(job)
            await session.commit()
        except Exception as e:
            log.exception("Pipeline step %s failed for job=%s", next_status, job_id)
            try:
                await session.rollback()
                job.status = JobStatus.FAILED
                job.error = f"{type(e).__name__}: {e}"
                session.add(job)
                await session.commit()
            except Exception:
                log.exception(
                    "Failed to persist failure state for job=%s", job_id
                )
            return

    # Edit loop: edit → re-score → re-review
    while True:
        quality = job.get_quality()
        review = job.get_review()
        quality_ok = quality.passes_threshold if quality else True
        review_ok = review.passed if review else True

        if quality_ok and review_ok:
            break
        if job.revision_count >= settings.max_revisions:
            log.info("Max edits reached for job=%s, accepting current quality", job_id)
            break

        log.info(
            "Edit %d: quality_pass=%s review_pass=%s",
            job.revision_count + 1, quality_ok, review_ok,
        )

        # EDITING
        job.status = JobStatus.EDITING
        job.current_step = "editing"
        session.add(job)
        await session.commit()

        try:
            await edit_step(job, session, llm, serp_client)
            usage = llm.drain_usage()
            for u in usage:
                u.step = "editing"
            job.append_usage(usage)
            for entry in llm.drain_call_log():
                job.append_event("editing", entry["event"], entry["detail"])
            session.add(job)
            await session.commit()
        except Exception as e:
            log.exception("Edit step failed for job=%s", job_id)
            try:
                await session.rollback()
                job.status = JobStatus.FAILED
                job.error = f"{type(e).__name__}: {e}"
                session.add(job)
                await session.commit()
            except Exception:
                log.exception("Failed to persist failure state for job=%s", job_id)
            return

        # RE-SCORE
        job.quality_data = None
        job.status = JobStatus.SCORING
        job.current_step = "scoring"
        session.add(job)
        await session.commit()

        try:
            await score_step(job, session, llm, serp_client)
            usage = llm.drain_usage()
            for u in usage:
                u.step = "scoring"
            job.append_usage(usage)
            for entry in llm.drain_call_log():
                job.append_event("scoring", entry["event"], entry["detail"])
            session.add(job)
            await session.commit()
        except Exception as e:
            log.exception("Re-score step failed for job=%s", job_id)
            try:
                await session.rollback()
                job.status = JobStatus.FAILED
                job.error = f"{type(e).__name__}: {e}"
                session.add(job)
                await session.commit()
            except Exception:
                log.exception("Failed to persist failure state for job=%s", job_id)
            return

        # RE-REVIEW
        job.review_data = None
        job.status = JobStatus.REVIEWING
        job.current_step = "reviewing"
        session.add(job)
        await session.commit()

        try:
            await review_step(job, session, llm, serp_client)
            usage = llm.drain_usage()
            for u in usage:
                u.step = "reviewing"
            job.append_usage(usage)
            for entry in llm.drain_call_log():
                job.append_event("reviewing", entry["event"], entry["detail"])
            session.add(job)
            await session.commit()
        except Exception as e:
            log.exception("Re-review step failed for job=%s", job_id)
            try:
                await session.rollback()
                job.status = JobStatus.FAILED
                job.error = f"{type(e).__name__}: {e}"
                session.add(job)
                await session.commit()
            except Exception:
                log.exception("Failed to persist failure state for job=%s", job_id)
            return

    job.status = JobStatus.COMPLETED
    job.current_step = None
    # Schema markup preview event
    result = job.build_result()
    if result and result.schema_markup:
        schemas = [k for k, v in result.schema_markup.items() if v]
        snippets = len(result.snippet_opportunities)
        job.append_event("completed", "schema",
            f"JSON-LD: {', '.join(schemas)}. {snippets} snippet opportunities")
    if not settings.persist_events:
        job.events_data = None
    session.add(job)
    await session.commit()
    log.info("Pipeline completed for job=%s", job_id)
