class SeoAgentError(Exception):
    """Base exception for all application errors."""


class JobNotFoundError(SeoAgentError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id} not found")
        self.job_id = job_id


class StepError(SeoAgentError):
    """A pipeline step failed due to missing precondition."""


class LlmError(SeoAgentError):
    """LLM API call failed after retries."""


class SerpError(SeoAgentError):
    """SERP API call failed."""
