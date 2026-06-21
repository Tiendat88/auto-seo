"""Publish service — convert article to HTML and POST to target endpoint."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.job.models import Job
from app.publish.models import PublishJob, PublishJobStatus, PublishMode, PublishTarget

log = logging.getLogger(__name__)

_MAX_RETRIES = 3
_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Article → HTML converter
# ---------------------------------------------------------------------------


def _article_to_html(job: Job) -> str:
    """Convert ArticleContent sections + FAQ to a plain HTML string."""
    content = job.result.get("content") if job.result else None
    if not content:
        # fallback: raw article_data
        content = job.article_data

    if not content:
        return ""

    parts: list[str] = []

    for section in content.get("sections", []):
        level = section.get("heading_level", "h2")
        heading = section.get("heading", "")
        body = section.get("content", "")
        parts.append(f"<{level}>{heading}</{level}>")
        # Wrap each paragraph in <p>
        for para in body.split("\n\n"):
            stripped = para.strip()
            if stripped:
                parts.append(f"<p>{stripped}</p>")

    faqs = content.get("faq", [])
    if faqs:
        parts.append("<h2>FAQ</h2>")
        for item in faqs:
            q = item.get("question", "")
            a = item.get("answer", "")
            parts.append(f"<h3>{q}</h3>")
            parts.append(f"<p>{a}</p>")

    return "\n".join(parts)


def _article_to_markdown(job: Job) -> str:
    content = job.result.get("content") if job.result else None
    if not content:
        content = job.article_data
    if not content:
        return ""
    parts: list[str] = []
    for section in content.get("sections", []):
        level = section.get("heading_level", "h2")
        prefix = "#" if level == "h1" else "##" if level == "h2" else "###"
        parts.append(f"{prefix} {section.get('heading', '')}")
        parts.append(section.get("content", ""))
    faqs = content.get("faq", [])
    if faqs:
        parts.append("## FAQ")
        for item in faqs:
            parts.append(f"**{item.get('question', '')}**\n\n{item.get('answer', '')}")
    return "\n\n".join(parts)


def _build_payload(job: Job, mode: PublishMode) -> dict[str, Any]:
    """Build the JSON payload to send to the custom endpoint."""
    seo = (job.result or {}).get("seo_metadata", {})
    kw = (job.result or {}).get("keyword_analysis", {})
    schema = (job.result or {}).get("schema_markup", {})
    content = (job.result or {}).get("content") or job.article_data or {}
    faq = content.get("faq", [])

    secondary_kws = []
    if kw:
        for k in kw.get("secondary", []):
            secondary_kws.append(k.get("keyword", "") if isinstance(k, dict) else str(k))

    slug = seo.get("slug") or job.topic.lower().replace(" ", "-")[:80]

    return {
        "job_id": job.id,
        "title": seo.get("title_tag") or job.topic,
        "content_html": _article_to_html(job),
        "content_markdown": _article_to_markdown(job),
        "slug": slug,
        "meta": {
            "title_tag": seo.get("title_tag") or job.topic,
            "meta_description": seo.get("meta_description", ""),
            "primary_keyword": kw.get("primary", {}).get("keyword", job.topic) if kw else job.topic,
            "secondary_keywords": secondary_kws,
        },
        "schema_markup": schema or {},
        "faq": [{"question": f.get("question", ""), "answer": f.get("answer", "")} for f in faq],
        "word_count": job.result.get("word_count", 0) if job.result else 0,
        "language": job.language,
        "publish_mode": str(mode),
        "created_at": job.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Core publish logic
# ---------------------------------------------------------------------------


async def _call_endpoint(
    endpoint_url: str, secret_key: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """POST payload to the target endpoint. Returns parsed JSON response."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {secret_key}",
        "X-AutoSEO-Version": "1.0",
        "X-AutoSEO-Job-ID": payload.get("job_id", ""),
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(endpoint_url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


async def publish_article(
    session: AsyncSession,
    publish_job: PublishJob,
    target: PublishTarget,
    job: Job,
) -> PublishJob:
    """Execute publish: build payload, call endpoint, update publish job record."""
    mode = PublishMode(publish_job.mode)
    payload = _build_payload(job, mode)

    publish_job.article_title = payload["title"]
    publish_job.article_slug = payload["slug"]
    publish_job.status = PublishJobStatus.SENT

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = await _call_endpoint(target.endpoint_url, target.secret_key, payload)
            publish_job.status = PublishJobStatus.SUCCESS
            publish_job.published_url = result.get("url")
            publish_job.error_message = None
            log.info("Published job %s → %s", job.id, publish_job.published_url)
            break
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            # 4xx — don't retry
            if 400 <= status_code < 500:
                publish_job.status = PublishJobStatus.FAILED
                publish_job.error_message = f"HTTP {status_code}: {exc.response.text[:500]}"
                log.warning(
                    "Publish failed (no retry) for job %s: %s", job.id, publish_job.error_message
                )
                break
            # 5xx — retry
            publish_job.retry_count = attempt
            if attempt >= _MAX_RETRIES:
                publish_job.status = PublishJobStatus.FAILED
                publish_job.error_message = (
                    f"HTTP {status_code} after {attempt} retries: {exc.response.text[:500]}"
                )
                log.error("Publish failed after %d retries for job %s", attempt, job.id)
        except Exception as exc:  # noqa: BLE001
            publish_job.retry_count = attempt
            if attempt >= _MAX_RETRIES:
                publish_job.status = PublishJobStatus.FAILED
                publish_job.error_message = str(exc)[:500]
                log.error("Publish error after %d retries for job %s: %s", attempt, job.id, exc)

    await session.commit()
    await session.refresh(publish_job)
    return publish_job


async def test_target_connection(endpoint_url: str, secret_key: str) -> dict[str, Any]:
    """Send a ping payload to verify the endpoint is reachable and accepts our secret."""
    ping_payload = {
        "job_id": "autoseo-ping-test",
        "title": "AutoSEO Connection Test",
        "content_html": (
            "<p>This is a connection test from AutoSEO. You can safely delete this.</p>"
        ),
        "content_markdown": "This is a connection test from AutoSEO.",
        "slug": "autoseo-connection-test",
        "meta": {
            "title_tag": "AutoSEO Connection Test",
            "meta_description": "Connection test",
            "primary_keyword": "test",
            "secondary_keywords": [],
        },
        "schema_markup": {},
        "faq": [],
        "word_count": 10,
        "language": "vi",
        "publish_mode": "draft",
        "created_at": "2025-01-01T00:00:00Z",
        "_is_test": True,
    }
    return await _call_endpoint(endpoint_url, secret_key, ping_payload)
