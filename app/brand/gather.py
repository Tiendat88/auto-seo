"""Shared async task gathering with partial failure tolerance."""

import asyncio
import logging
from typing import TypeVar

from app.errors import LlmError

log = logging.getLogger(__name__)

T = TypeVar("T")


async def gather_partial(
    tasks: dict[str, asyncio.Task[T]], label: str,
) -> list[T]:
    """Await tasks, collect successes, raise if all fail."""
    results: list[T] = []
    errors: list[str] = []

    done = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for name, result in zip(tasks.keys(), done, strict=True):
        if isinstance(result, BaseException):
            log.warning("%s fetch from %s failed: %s", label, name, result)
            errors.append(f"{name}: {result}")
        else:
            results.append(result)

    if not results:
        raise LlmError(f"All {label} fetches failed: {'; '.join(errors)}")
    if errors:
        log.warning("Some %s fetches failed: %s", label, "; ".join(errors))
    return results
