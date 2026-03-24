# Examples

Real CLI artifacts and logs captured from live runs of `autoseo`.

The examples use the CLI's split-output mode:

- `--output <file>` writes the primary artifact
- `--log-file <file>` writes progress, status text, and errors

Some commands naturally produce only an artifact or only a log:

- `export` writes its article artifact to the positional output file argument
- short commands like `status` and `list` usually have empty log files because they do not emit progress text

## Article workflow

Topic: `customer onboarding checklist for B2B SaaS`

Job ID: `b9c6de65-60ce-4a3a-a0d6-2dd314c5f93f`

- `article-workflow/generate.output.txt`: `generate --no-poll` artifact with the created job ID
- `article-workflow/generate.log`: companion log file
- `article-workflow/status.running.txt`: `status` output while the job was still running
- `article-workflow/status.completed.txt`: `status` output after completion
- `article-workflow/watch.output.txt`: final completion artifact from `watch`
- `article-workflow/watch.log`: full progress log from `watch`, including rendered stage output and revision loop
- `article-workflow/result.summary.txt`: `result --summary`
- `article-workflow/result.article.md`: `result` full markdown render
- `article-workflow/result.json`: `result --json`
- `article-workflow/export.article.md`: `export` markdown artifact
- `article-workflow/export.log`: `export` success log

Commands used:

```bash
uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/article-workflow/generate.output.txt \
  --log-file examples/article-workflow/generate.log \
  generate "customer onboarding checklist for B2B SaaS" --words 1400 --no-poll

uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/article-workflow/status.running.txt \
  --log-file examples/article-workflow/status.running.log \
  status b9c6de65-60ce-4a3a-a0d6-2dd314c5f93f

uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/article-workflow/watch.output.txt \
  --log-file examples/article-workflow/watch.log \
  watch b9c6de65-60ce-4a3a-a0d6-2dd314c5f93f

uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/article-workflow/result.summary.txt \
  --log-file examples/article-workflow/result.summary.log \
  result b9c6de65-60ce-4a3a-a0d6-2dd314c5f93f --summary

uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/article-workflow/result.article.md \
  --log-file examples/article-workflow/result.article.log \
  result b9c6de65-60ce-4a3a-a0d6-2dd314c5f93f

uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/article-workflow/result.json \
  --log-file examples/article-workflow/result.json.log \
  result b9c6de65-60ce-4a3a-a0d6-2dd314c5f93f --json

uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --log-file examples/article-workflow/export.log \
  export b9c6de65-60ce-4a3a-a0d6-2dd314c5f93f examples/article-workflow/export.article.md
```

## Job-state examples

- `jobs/list.completed.txt`: `list --status completed --limit 5`
- `jobs/list.failed.txt`: `list --status failed --limit 5`
- `jobs/status.failed.txt`: `status` on a failed job before resume
- `jobs/resume.output.txt`: final completion artifact from a resumed failed job
- `jobs/resume.log`: full progress log from `resume`

Resume target:

- Job ID: `2a1e5aea-bbbe-4b49-83fd-cca33476542d`
- Topic: `best productivity tools for remote teams 2026`

Command used:

```bash
uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/jobs/resume.output.txt \
  --log-file examples/jobs/resume.log \
  resume 2a1e5aea-bbbe-4b49-83fd-cca33476542d
```

## AEO examples

- `aeo/onboarding-article.json`: AEO analysis of the exported onboarding article
- `aeo/onboarding-article.log`: companion log file

Command used:

```bash
uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/aeo/onboarding-article.json \
  --log-file examples/aeo/onboarding-article.log \
  aeo examples/article-workflow/export.article.md --json
```

## Fan-out examples

- `fanout/crm-url-gap.json`: URL-backed fan-out gap analysis for `best CRM for startups`
- `fanout/crm-url-gap.log`: fetch log for the URL-backed example
- `fanout/onboarding-file-gap.json`: file-backed fan-out gap analysis against the exported onboarding article
- `fanout/onboarding-file-gap.log`: companion log file

Commands used:

```bash
uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/fanout/crm-url-gap.json \
  --log-file examples/fanout/crm-url-gap.log \
  fanout "best CRM for startups" --content https://example.com --json

uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/fanout/onboarding-file-gap.json \
  --log-file examples/fanout/onboarding-file-gap.log \
  fanout "customer onboarding checklist for B2B SaaS" \
  --content examples/article-workflow/export.article.md --json
```

## Brand-monitor example

- `brand/notion-api.json`: API-mode brand analysis for Notion on the query `best note-taking app`
- `brand/notion-api.log`: preamble log for the same run

Command used:

```bash
uv run python -m app.cli --api-url http://127.0.0.1:8011 \
  --output examples/brand/notion-api.json \
  --log-file examples/brand/notion-api.log \
  brand Notion "best note-taking app" --mode api --json
```

## Legacy sample

- `sample_output.json`: older sample artifact kept as-is from the original repo state
