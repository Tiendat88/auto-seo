import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.article.models import (
    ArticleContent,
    ArticleOutline,
    ArticleSection,
    CompetitiveAnalysis,
    CompetitorTheme,
    ContentGap,
    ExternalReference,
    FaqItem,
    HeadingLevel,
    InternalLink,
    KeywordAnalysis,
    KeywordCluster,
    KeywordUsage,
    LinkSuggestions,
    OutlineHeading,
    SeoMetadata,
)
from app.db import Base
from app.job.models import Job
from app.serp.models import SerpData

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session(async_engine) -> AsyncSession:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture
def sample_serp_data() -> SerpData:
    raw = json.loads((FIXTURES_DIR / "serp_results.json").read_text())
    return SerpData.model_validate(raw)


@pytest.fixture
def sample_analysis() -> CompetitiveAnalysis:
    return CompetitiveAnalysis(
        keywords=KeywordCluster(
            primary="productivity tools",
            secondary=["remote team tools", "collaboration software", "project management"],
            long_tail=["best productivity tools for remote teams 2025"],
        ),
        themes=[
            CompetitorTheme(
                theme="Project Management",
                frequency=8,
                subtopics=["task tracking", "Gantt charts", "Kanban boards"],
            ),
            CompetitorTheme(
                theme="Communication Tools",
                frequency=7,
                subtopics=["video conferencing", "instant messaging", "async communication"],
            ),
            CompetitorTheme(
                theme="Time Management",
                frequency=5,
                subtopics=["time tracking", "pomodoro", "scheduling"],
            ),
        ],
        content_gaps=[
            ContentGap(topic="AI-powered productivity", reason="Emerging trend not well covered"),
        ],
        avg_word_count=2000,
        common_heading_patterns=["Best Tools", "Features", "Pricing", "How to Choose"],
        search_intent="informational",
    )


@pytest.fixture
def sample_outline() -> ArticleOutline:
    return ArticleOutline(
        h1="Best Productivity Tools for Remote Teams in 2025",
        headings=[
            OutlineHeading(
                level=HeadingLevel.H1,
                text="Best Productivity Tools for Remote Teams in 2025",
                target_word_count=150,
                key_points=["Introduction to the challenge of remote work"],
                keywords_to_include=["productivity tools", "remote teams"],
            ),
            OutlineHeading(
                level=HeadingLevel.H2,
                text="Project Management Tools",
                target_word_count=300,
                key_points=["Task tracking", "Popular options"],
                keywords_to_include=["project management", "task tracking"],
            ),
            OutlineHeading(
                level=HeadingLevel.H2,
                text="Communication and Collaboration",
                target_word_count=300,
                key_points=["Video conferencing", "Async communication"],
                keywords_to_include=["collaboration software", "communication"],
            ),
            OutlineHeading(
                level=HeadingLevel.H2,
                text="Time Management Solutions",
                target_word_count=250,
                key_points=["Time tracking", "Scheduling"],
                keywords_to_include=["time management", "scheduling"],
            ),
            OutlineHeading(
                level=HeadingLevel.H2,
                text="How to Choose the Right Tools",
                target_word_count=200,
                key_points=["Evaluation criteria", "Budget considerations"],
                keywords_to_include=["choose", "evaluation"],
            ),
        ],
        estimated_total_words=1200,
        faq_questions=[
            "What are the best productivity tools for remote teams?",
            "How much do productivity tools cost?",
            "What features should I look for?",
            "Are free productivity tools good enough?",
        ],
    )


@pytest.fixture
def sample_article() -> ArticleContent:
    return ArticleContent(
        sections=[
            ArticleSection(
                heading="Best Productivity Tools for Remote Teams in 2025",
                heading_level=HeadingLevel.H1,
                content=(
                    "Remote work has transformed how teams operate. Choosing "
                    "the right productivity tools can make the difference "
                    "between a team that thrives and one that struggles. "
                ) * 5,
            ),
            ArticleSection(
                heading="Project Management Tools",
                heading_level=HeadingLevel.H2,
                content=(
                    "Project management tools like Asana, Monday.com, and "
                    "Trello help remote teams track tasks and deadlines. These "
                    "productivity tools offer Kanban boards, Gantt charts, and "
                    "automated workflows. "
                ) * 8,
            ),
            ArticleSection(
                heading="Communication and Collaboration",
                heading_level=HeadingLevel.H2,
                content=(
                    "Effective communication is the backbone of remote team "
                    "productivity. Tools like Slack, Microsoft Teams, and Zoom "
                    "provide real-time messaging, video conferencing, and file "
                    "sharing. "
                ) * 8,
            ),
            ArticleSection(
                heading="Time Management Solutions",
                heading_level=HeadingLevel.H2,
                content=(
                    "Time tracking tools help remote teams understand where "
                    "their hours go. Solutions like Toggl, Clockify, and "
                    "RescueTime offer detailed insights into productivity "
                    "patterns. "
                ) * 6,
            ),
            ArticleSection(
                heading="How to Choose the Right Tools",
                heading_level=HeadingLevel.H2,
                content=(
                    "When selecting productivity tools for your remote team, "
                    "consider integration capabilities, pricing, ease of use, "
                    "and scalability. The best tools grow with your team. "
                ) * 5,
            ),
        ],
        faq=[
            FaqItem(
                question="What are the best productivity tools for remote teams?",
                answer=(
                    "The best productivity tools include Asana for project "
                    "management, Slack for communication, and Toggl for time "
                    "tracking."
                ),
            ),
            FaqItem(
                question="How much do productivity tools cost?",
                answer=(
                    "Most productivity tools offer free tiers for small teams. "
                    "Premium plans typically range from $5 to $25 per user per "
                    "month."
                ),
            ),
            FaqItem(
                question="What features should I look for?",
                answer=(
                    "Key features include task management, real-time "
                    "collaboration, integrations with other tools, and mobile "
                    "access."
                ),
            ),
            FaqItem(
                question="Are free productivity tools good enough?",
                answer=(
                    "Free tiers work well for small teams under 10 people. "
                    "Larger teams typically need premium features like advanced "
                    "reporting and admin controls."
                ),
            ),
        ],
    )


@pytest.fixture
def sample_seo_metadata() -> SeoMetadata:
    return SeoMetadata(
        title_tag="Best Productivity Tools for Remote Teams (2025)",
        meta_description=(
            "Discover the top productivity tools that help remote teams "
            "collaborate effectively. Expert-tested picks for project "
            "management, communication, and more."
        ),
        primary_keyword="productivity tools",
        slug="best-productivity-tools-remote-teams",
    )


@pytest.fixture
def sample_keyword_analysis() -> KeywordAnalysis:
    return KeywordAnalysis(
        primary=KeywordUsage(
            keyword="productivity tools",
            count=15,
            density=1.8,
            locations=[
                "title",
                "meta_description",
                "intro",
                "heading:Project Management Tools",
            ],
        ),
        secondary=[
            KeywordUsage(
                keyword="remote teams",
                count=8,
                density=0.9,
                locations=["title", "intro"],
            ),
        ],
    )


@pytest.fixture
def sample_links() -> LinkSuggestions:
    return LinkSuggestions(
        internal=[
            InternalLink(
                anchor_text="project management best practices",
                suggested_target_topic="Project Management Guide",
                placement_context="In the project management section",
            ),
            InternalLink(
                anchor_text="remote team communication tips",
                suggested_target_topic="Remote Communication Guide",
                placement_context="In the communication section",
            ),
            InternalLink(
                anchor_text="time tracking for freelancers",
                suggested_target_topic="Freelancer Productivity Guide",
                placement_context="In the time management section",
            ),
        ],
        external=[
            ExternalReference(
                title="State of Remote Work 2025 - Buffer",
                url="https://buffer.com/state-of-remote-work",
                authority_reason="Annual industry survey with large sample size",
                placement_section="Introduction",
            ),
            ExternalReference(
                title="Gartner Magic Quadrant for Project Management",
                url="https://www.gartner.com/reviews/market/project-management",
                authority_reason="Industry-standard analyst evaluation",
                placement_section="Project Management Tools",
            ),
        ],
    )


@pytest.fixture
async def sample_job(session: AsyncSession) -> Job:
    job = Job(
        topic="best productivity tools for remote teams",
        target_word_count=1500,
        language="en",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job
