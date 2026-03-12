"""Pipeline runner: state machine for article generation."""

import asyncio
import logging
import re
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
    FaqItem,
    HeadingLevel,
    KeywordAnalysis,
    KeywordUsage,
    LinkSuggestions,
    QualityScore,
    ReviewResult,
    ScoreDimension,
    SeoMetadata,
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
    outline_prompt,
    readability_actionability_score_prompt,
    review_prompt,
    seo_metadata_prompt,
)
from app.article.scorer import (
    score_heading_structure,
    score_keyword_usage,
    score_word_count,
)
from app.config import settings
from app.errors import StepError
from app.job.models import Job, JobStatus
from app.llm import LlmClient, get_secondary_llm
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
    """Fetch SERP data for the topic."""
    if job.serp_data:
        return
    data = await serp.search(job.topic)
    job.set_serp(data)


async def analyze_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Extract competitive analysis from SERP data."""
    if job.analysis_data:
        return
    serp_data = job.get_serp()
    if not serp_data:
        raise StepError("Cannot analyze without SERP data")

    prompt = analysis_prompt(serp_data)
    analysis = await llm.generate_structured(prompt, CompetitiveAnalysis)
    job.set_analysis(analysis)


async def outline_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Generate article outline with editorial brief from competitive analysis."""
    if job.outline_data:
        return
    analysis = job.get_analysis()
    if not analysis:
        raise StepError("Cannot outline without competitive analysis")

    prompt = outline_prompt(job.topic, job.target_word_count, job.language, analysis)
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

    # 1. Single-call article generation (includes FAQ)
    max_tok = max(4096, int(job.target_word_count * 2))
    prompt = generate_article_prompt(outline, job.language, revision_instructions)
    article_md = await llm.generate_text(prompt, max_tok)

    # 2. Parse markdown → sections + FAQ
    sections, faq_items = _parse_article_markdown(article_md, outline)
    article = ArticleContent(sections=sections, faq=faq_items)

    # 3. Parallel: metadata + links
    brief = outline.brief
    meta_task = llm.generate_structured(
        seo_metadata_prompt(
            job.topic,
            analysis.keywords.primary,
            sections[0].content if sections else "",
            brief=brief,
            section_headings=[s.heading for s in sections],
        ),
        SeoMetadata,
    )
    links_task = llm.generate_structured(
        links_prompt(
            job.topic,
            [s.heading for s in sections],
            analysis,
            serp_data,
            brief=brief,
            section_summaries=_section_summaries(sections),
        ),
        LinkSuggestions,
    )

    seo_meta, links = await asyncio.gather(meta_task, links_task)

    # 4. Keyword analysis (algorithmic)
    kw_analysis = _compute_keyword_analysis(article, analysis, seo_meta)

    # Atomic write
    job.set_article(article)
    job.set_seo_metadata(seo_meta)
    job.set_keyword_analysis(kw_analysis)
    job.set_links(links)


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
    if not article or not analysis or not seo_meta or not outline:
        raise StepError("Cannot score without article, analysis, SEO metadata, and outline")

    # Algorithmic dimensions (free, deterministic)
    algo_dims = [
        score_keyword_usage(article, analysis, seo_meta),
        score_heading_structure(article),
        score_word_count(article, job.target_word_count),
    ]

    # LLM dimensions — multi-provider if Gemini configured
    brief = outline.brief
    structured_text = _structured_article_text(article, 20000)
    brief_text = format_brief(brief) if brief else ""

    score_prompts = [
        depth_differentiation_score_prompt(structured_text, brief_text),
        accuracy_consistency_score_prompt(structured_text, brief_text),
        readability_actionability_score_prompt(structured_text, brief_text),
    ]

    # Primary (Claude): 3 calls
    tasks = [
        llm.generate_structured(p, _ScorePair, use_cache=False)
        for p in score_prompts
    ]

    # Secondary (Gemini): 3 more calls if configured
    secondary = get_secondary_llm()
    if secondary:
        tasks.extend(
            secondary.generate_structured(p, _ScorePair, use_cache=False)
            for p in score_prompts
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect all successful dimensions
    all_dims: list[ScoreDimension] = []
    for r in results:
        if isinstance(r, _ScorePair):
            all_dims.extend(r.dimensions)
        elif isinstance(r, Exception):
            log.warning("Scoring call failed: %s", r)

    # Merge: average scores for dimensions with the same name
    llm_dims = _merge_score_dimensions(all_dims)

    succeeded = sum(1 for r in results if isinstance(r, _ScorePair))
    if succeeded < 2:
        raise StepError(f"Only {succeeded} scoring calls succeeded, need at least 2")

    dimensions = algo_dims + llm_dims
    overall = sum(d.score for d in dimensions) / len(dimensions)
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

    # Primary review (Claude)
    tasks: list = [llm.generate_structured(prompt, ReviewResult, use_cache=False)]

    # Secondary review (Gemini) if configured
    secondary = get_secondary_llm()
    if secondary:
        tasks.append(secondary.generate_structured(prompt, ReviewResult, use_cache=False))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    reviews = [r for r in results if isinstance(r, ReviewResult)]
    for r in results:
        if isinstance(r, Exception):
            log.warning("Review call failed: %s", r)

    if not reviews:
        raise StepError("All review calls failed")

    review = _merge_reviews(reviews) if len(reviews) > 1 else reviews[0]

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
    if not article or not outline or not quality:
        raise StepError("Cannot edit without article, outline, and quality data")

    structured_text = _structured_article_text(article, 20000)
    brief = outline.brief
    prompt = edit_prompt(structured_text, brief, quality.dimensions, review)

    max_tok = max(4096, int(job.target_word_count * 2))
    edited_md = await llm.generate_text(prompt, max_tok)

    sections, faq_items = _parse_article_markdown(edited_md, outline)
    # Prefer parsed FAQ, fall back to existing if edit didn't include FAQ
    edited = ArticleContent(
        sections=sections,
        faq=faq_items if faq_items else article.faq,
    )

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


def _merge_score_dimensions(dims: list[ScoreDimension]) -> list[ScoreDimension]:
    """Average scores for dimensions with the same name."""
    groups: dict[str, list[ScoreDimension]] = defaultdict(list)
    for d in dims:
        groups[d.name].append(d)
    merged = []
    for name, group in groups.items():
        avg = sum(d.score for d in group) / len(group)
        worst = min(group, key=lambda d: d.score)
        merged.append(ScoreDimension(name=name, score=round(avg, 3), feedback=worst.feedback))
    return merged


def _merge_reviews(reviews: list[ReviewResult]) -> ReviewResult:
    """Merge multiple ReviewResults by consensus."""
    all_issues = []
    all_strengths: list[str] = []
    for r in reviews:
        all_issues.extend(r.issues)
        all_strengths.extend(r.strengths)

    unique_strengths = list(dict.fromkeys(all_strengths))
    has_serious = any(i.severity in ("critical", "major") for i in all_issues)
    passed = not has_serious

    summaries = [r.summary for r in reviews]
    summary = " | ".join(summaries)

    return ReviewResult(
        passed=passed,
        summary=summary,
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
    return KeywordAnalysis(primary=primary, secondary=secondary)


# --- Step Registry ---

STEP_SEQUENCE: list[tuple[JobStatus, StepFn]] = [
    (JobStatus.RESEARCHING, research_step),
    (JobStatus.ANALYZING, analyze_step),
    (JobStatus.OUTLINING, outline_step),
    (JobStatus.GENERATING, generate_step),
    (JobStatus.SCORING, score_step),
    (JobStatus.REVIEWING, review_step),
]

_DATA_CHECKS: list[tuple[JobStatus, str]] = [
    (JobStatus.RESEARCHING, "serp_data"),
    (JobStatus.ANALYZING, "analysis_data"),
    (JobStatus.OUTLINING, "outline_data"),
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
            await step_fn(job, session, llm, serp_client)
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
    session.add(job)
    await session.commit()
    log.info("Pipeline completed for job=%s", job_id)
