"""CLI output separation tests."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from app import cli

runner = CliRunner()


class MockResponse:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code
        self.text = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class MockClient:
    def __init__(
        self,
        *,
        get_responses: list[MockResponse] | None = None,
        post_responses: list[MockResponse] | None = None,
    ) -> None:
        self._get_responses = get_responses or []
        self._post_responses = post_responses or []

    def __enter__(self) -> "MockClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, url: str, params: dict | None = None) -> MockResponse:
        assert self._get_responses, f"Unexpected GET {url}"
        return self._get_responses.pop(0)

    def post(
        self,
        url: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> MockResponse:
        assert self._post_responses, f"Unexpected POST {url}"
        return self._post_responses.pop(0)


class TestCliOutputFiles:
    def test_fanout_json_and_log_file_are_separated(self, tmp_path: Path):
        artifact = tmp_path / "fanout.json"
        log_file = tmp_path / "fanout.log"
        response = MockResponse({
            "target_query": "best CRM for startups",
            "model_used": "gemini-3-flash-preview",
            "total_sub_queries": 1,
            "sub_queries": [{
                "type": "comparative",
                "query": "crm for startups comparison",
                "covered": False,
                "similarity_score": 0.11,
            }],
            "gap_summary": {
                "covered": 0,
                "total": 1,
                "coverage_percent": 0,
                "covered_types": [],
                "missing_types": ["comparative"],
            },
        })

        with patch("app.cli.httpx.Client", return_value=MockClient(post_responses=[response])):
            result = runner.invoke(
                cli.app,
                [
                    "--output", str(artifact),
                    "--log-file", str(log_file),
                    "fanout", "best CRM for startups",
                    "--content", "https://example.com",
                    "--json",
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert artifact.read_text(encoding="utf-8").lstrip().startswith("{")
        assert '"target_query": "best CRM for startups"' in artifact.read_text(encoding="utf-8")
        log_text = log_file.read_text(encoding="utf-8")
        assert "Fetching https://example.com..." in log_text
        assert '"target_query"' not in log_text

    def test_brand_json_and_log_file_are_separated(self, tmp_path: Path):
        artifact = tmp_path / "brand.json"
        log_file = tmp_path / "brand.log"
        response = MockResponse({
            "brand_name": "Notion",
            "query": "best note-taking app",
            "model_used": "gemini-3-flash-preview",
            "platform_analyses": [],
            "aggregate": {
                "overall_sentiment": "positive",
                "platforms_mentioning_brand": 1,
                "total_platforms": 1,
                "avg_brand_position": 1,
                "brand_recommended_on": ["chatgpt"],
                "top_competitors": ["obsidian"],
                "common_strengths": ["collaboration"],
                "common_weaknesses": [],
                "all_keywords_found": ["notes"],
            },
        })

        with patch("app.cli.httpx.Client", return_value=MockClient(post_responses=[response])):
            result = runner.invoke(
                cli.app,
                [
                    "--output", str(artifact),
                    "--log-file", str(log_file),
                    "brand", "Notion", "best note-taking app",
                    "--json",
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert artifact.read_text(encoding="utf-8").lstrip().startswith("{")
        assert '"brand_name": "Notion"' in artifact.read_text(encoding="utf-8")
        log_text = log_file.read_text(encoding="utf-8")
        assert "Analyzing Notion for: best note-taking app" in log_text
        assert "Fetch mode: browser" in log_text
        assert '"brand_name"' not in log_text

    def test_generate_separates_artifact_and_log_output(self, tmp_path: Path):
        artifact = tmp_path / "generate.txt"
        log_file = tmp_path / "generate.log"
        response = MockResponse({
            "id": "lc-123",
            "topic": "best note-taking apps for founders",
            "current_job_id": "job-123",
            "cadence_days": 0,
        })

        def fake_poll(api_url: str, job_id: str, verbose: bool = False) -> None:
            cli.log_console.print("poll log line")
            cli.console.print("final summary line")

        with (
            patch("app.cli.httpx.Client", return_value=MockClient(post_responses=[response])),
            patch("app.cli._poll_job", side_effect=fake_poll),
        ):
            result = runner.invoke(
                cli.app,
                [
                    "--output", str(artifact),
                    "--log-file", str(log_file),
                    "generate", "best note-taking apps for founders",
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        artifact_text = artifact.read_text(encoding="utf-8")
        assert "Lifecycle created: lc-123" in artifact_text
        assert "Topic: best note-taking apps for founders" in artifact_text
        assert "final summary line" in artifact_text
        assert "poll log line" not in artifact_text
        log_text = log_file.read_text(encoding="utf-8")
        assert "poll log line" in log_text
        assert "final summary line" not in log_text
