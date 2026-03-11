"""Pipeline runner: state machine for article generation."""

import logging
import re
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
    KeywordAnalysis,
    KeywordUsage,
    LinkSuggestions,
    QualityScore,
    ScoreDimension,
    SeoMetadata,
)
from app.article.prompts import (
    analysis_prompt,
    faq_prompt,
    links_prompt,
    outline_prompt,
    quality_llm_prompt,
    section_prompt,
    seo_metadata_prompt,
)
from app.article.scorer import (
    score_faq_coverage,
    score_heading_structure,
    score_keyword_usage,
    score_meta_quality,
    score_word_count,
)
from app.config import settings
from app.errors import StepError
from app.job.models import Job, JobStatus
from app.llm import LlmClient
from app.serp.client import SerpProvider

log = logging.getLogger(__name__)

StepFn = Callable[
    [Job, AsyncSession, LlmClient, SerpProvider],
    Coroutine[Any, Any, None],
]


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
    """Generate article outline from competitive analysis."""
    if job.outline_data:
        return
    analysis = job.get_analysis()
    if not analysis:
        raise StepError("Cannot outline without competitive analysis")

    prompt = outline_prompt(job.topic, job.target_word_count, job.language, analysis)
    outline = await llm.generate_structured(prompt, ArticleOutline)
    job.set_outline(outline)


def _last_sentences(text: str, n: int = 2) -> str:
    """Extract last n sentences from text."""
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    return ". ".join(sentences[-n:]) + "." if sentences else ""


async def generate_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Generate article content section by section.

    Collects all outputs into local variables first, then sets them all on the
    job at the end. This makes the step atomic -- either everything is saved or
    nothing.
    """
    if job.links_data:
        return
    outline = job.get_outline()
    analysis = job.get_analysis()
    serp_data = job.get_serp()
    if not outline or not analysis or not serp_data:
        raise StepError("Cannot generate without outline, analysis, and SERP data")

    quality = job.get_quality()
    revision_instructions = quality.revision_instructions if quality else None

    sections: list[ArticleSection] = []
    previous_ending = ""

    for heading in outline.headings:
        prompt = section_prompt(
            topic=job.topic,
            heading=heading.text,
            heading_level=heading.level.value,
            target_word_count=heading.target_word_count,
            key_points=heading.key_points,
            keywords=heading.keywords_to_include,
            previous_ending=previous_ending,
            language=job.language,
            revision_instructions=revision_instructions,
        )
        content = await llm.generate_text(prompt)
        section = ArticleSection(
            heading=heading.text,
            heading_level=heading.level,
            content=content,
        )
        sections.append(section)
        previous_ending = _last_sentences(content)

    # Generate FAQ
    faq_items: list[FaqItem] = []
    if outline.faq_questions:
        faq_prompt_text = faq_prompt(outline.faq_questions, job.topic, job.language)
        faq_items = await llm.generate_structured(faq_prompt_text, _FaqList)
        faq_items = faq_items.items  # type: ignore[attr-defined]

    article = ArticleContent(sections=sections, faq=faq_items)

    # Generate SEO metadata
    intro_text = sections[0].content if sections else ""
    meta_prompt = seo_metadata_prompt(job.topic, analysis.keywords.primary, intro_text)
    seo_meta = await llm.generate_structured(meta_prompt, SeoMetadata)

    # Compute keyword analysis
    kw_analysis = _compute_keyword_analysis(article, analysis, seo_meta)

    # Generate link suggestions
    headings = [s.heading for s in sections]
    link_prompt = links_prompt(job.topic, headings, analysis, serp_data)
    links = await llm.generate_structured(link_prompt, LinkSuggestions)

    # Set all outputs atomically
    job.set_article(article)
    job.set_seo_metadata(seo_meta)
    job.set_keyword_analysis(kw_analysis)
    job.set_links(links)


class _FaqList(BaseModel):
    items: list[FaqItem] = Field(default_factory=list)


async def score_step(
    job: Job, session: AsyncSession, llm: LlmClient, serp: SerpProvider
) -> None:
    """Score article quality with algorithmic + LLM checks."""
    if job.quality_data:
        return
    article = job.get_article()
    analysis = job.get_analysis()
    seo_meta = job.get_seo_metadata()
    if not article or not analysis or not seo_meta:
        raise StepError("Cannot score without article, analysis, and SEO metadata")

    # Algorithmic dimensions
    dimensions = [
        score_keyword_usage(article, analysis, seo_meta),
        score_heading_structure(article),
        score_word_count(article, job.target_word_count),
        score_meta_quality(seo_meta),
        score_faq_coverage(article),
    ]

    # LLM-based scoring
    try:
        parts = [s.content for s in article.sections]
        parts.extend(f"{f.question} {f.answer}" for f in article.faq)
        full_text = " ".join(parts)
        themes = [t.theme for t in analysis.themes]
        llm_prompt = quality_llm_prompt(full_text, themes)
        llm_dims = await llm.generate_structured(llm_prompt, _LlmScoreList, use_cache=False)
        dimensions.extend(llm_dims.dimensions)
    except Exception as e:
        log.warning("LLM quality scoring failed, using algorithmic only: %s", e)

    overall = sum(d.score for d in dimensions) / len(dimensions) if dimensions else 0.0
    passes = overall >= settings.quality_threshold

    revision_instructions = None
    if not passes:
        failing = [d for d in dimensions if d.score < 0.6]
        if failing:
            revision_instructions = "; ".join(
                f"[{d.name}] {d.feedback}" for d in failing
            )

    quality = QualityScore(
        overall=round(overall, 3),
        dimensions=dimensions,
        passes_threshold=passes,
        revision_instructions=revision_instructions,
    )
    job.set_quality(quality)


class _LlmScoreList(BaseModel):
    dimensions: list[ScoreDimension] = Field(default_factory=list)


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
]

_DATA_CHECKS: list[tuple[JobStatus, str]] = [
    (JobStatus.RESEARCHING, "serp_data"),
    (JobStatus.ANALYZING, "analysis_data"),
    (JobStatus.OUTLINING, "outline_data"),
    (JobStatus.GENERATING, "links_data"),
    (JobStatus.SCORING, "quality_data"),
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

    # Revision loop after initial pipeline completes
    while True:
        quality = job.get_quality()
        if not quality or quality.passes_threshold:
            break
        if job.revision_count >= settings.max_revisions:
            log.info("Max revisions reached for job=%s, accepting current quality", job_id)
            break

        log.info("Quality below threshold, revision %d", job.revision_count + 1)
        job.revision_count += 1
        job.article_data = None
        job.seo_metadata_data = None
        job.keyword_analysis_data = None
        job.links_data = None
        session.add(job)
        await session.commit()

        # Re-run generate and score steps
        gen_index = next(
            i for i, (s, _) in enumerate(STEP_SEQUENCE) if s == JobStatus.GENERATING
        )
        for j in range(gen_index, len(STEP_SEQUENCE)):
            ns, sf = STEP_SEQUENCE[j]
            if ns == JobStatus.SCORING:
                job.quality_data = None
            job.status = ns
            job.current_step = ns.value
            session.add(job)
            await session.commit()
            try:
                await sf(job, session, llm, serp_client)
                session.add(job)
                await session.commit()
            except Exception as e:
                log.exception("Revision step %s failed for job=%s", ns, job_id)
                try:
                    await session.rollback()
                    job.status = JobStatus.FAILED
                    job.error = f"{type(e).__name__}: {e}"
                    session.add(job)
                    await session.commit()
                except Exception:
                    log.exception(
                        "Failed to persist failure state for job=%s",
                        job_id,
                    )
                return

    job.status = JobStatus.COMPLETED
    job.current_step = None
    session.add(job)
    await session.commit()
    log.info("Pipeline completed for job=%s", job_id)
