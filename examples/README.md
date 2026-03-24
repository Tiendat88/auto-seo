# Examples

Live CLI artifacts and logs captured from fresh runs of `autoseo`.

These examples use the CLI's split-output mode:

- `--output <file>` writes the primary artifact
- `--log-file <file>` writes progress, status text, and errors

Short commands such as `status` and `list` often have empty log files because they do not emit progress output.

## Clean layout

- `examples/articles/`
  Final markdown article gallery only.
- `examples/article-workflows/`
  One folder per article topic with the full `generate`, `status`, `watch`, `result`, and `export` outputs.
- `examples/article-workflows/manifest.tsv`
  Canonical mapping of `slug`, `job_id`, and topic for the latest rerun set.

## Article gallery

`examples/articles/` contains the final exported markdown for the latest rerun set:

- `articles/customer-onboarding-checklist-for-b2b-saas.md`
- `articles/best-note-taking-apps-for-founders.md`
- `articles/gemini-cli-fallback-verification.md`
- `articles/remote-teamwork-tools.md`
- `articles/best-productivity-tools-for-remote-teams-2026.md`

## Article workflows

Each topic folder under `examples/article-workflows/` contains the same artifact set:

- `generate.output.txt`
- `generate.log`
- `status.running.txt`
- `status.running.log`
- `watch.output.txt`
- `watch.log`
- `status.completed.txt`
- `status.completed.log`
- `result.summary.txt`
- `result.summary.log`
- `result.article.md`
- `result.article.log`
- `result.json`
- `result.json.log`
- `export.article.md`
- `export.log`

Latest workflow set:

- `customer-onboarding-checklist-for-b2b-saas` → job `ab5f8d40-f707-4d34-aa73-f8f04b830b0c`
- `best-note-taking-apps-for-founders` → job `34f1a3f9-a8e2-411a-96e3-a7b378679ee3`
- `gemini-cli-fallback-verification` → job `b3b30ae0-fb6a-4d40-ba5a-f01ab77c9a83`
- `remote-teamwork-tools` → job `348cf194-059b-4265-8157-8a946c4671d9`
- `best-productivity-tools-for-remote-teams-2026` → job `15708637-1219-4e56-8d19-a462f85f3d4e`

Command shape used for each topic:

```bash
uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/article-workflows/<slug>/generate.output.txt \
  --log-file examples/article-workflows/<slug>/generate.log \
  generate "<topic>" --no-poll

uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/article-workflows/<slug>/status.running.txt \
  --log-file examples/article-workflows/<slug>/status.running.log \
  status <job_id>

uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/article-workflows/<slug>/watch.output.txt \
  --log-file examples/article-workflows/<slug>/watch.log \
  watch <job_id>

uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/article-workflows/<slug>/result.summary.txt \
  --log-file examples/article-workflows/<slug>/result.summary.log \
  result <job_id> --summary

uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/article-workflows/<slug>/result.article.md \
  --log-file examples/article-workflows/<slug>/result.article.log \
  result <job_id>

uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/article-workflows/<slug>/result.json \
  --log-file examples/article-workflows/<slug>/result.json.log \
  result <job_id> --json

uv run autoseo --api-url http://127.0.0.1:8015 \
  --log-file examples/article-workflows/<slug>/export.log \
  export <job_id> examples/article-workflows/<slug>/export.article.md
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

## AEO examples

- `aeo/onboarding-article.json`: AEO analysis of the latest exported onboarding article
- `aeo/onboarding-article.log`: companion log file

Command used:

```bash
uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/aeo/onboarding-article.json \
  --log-file examples/aeo/onboarding-article.log \
  aeo examples/article-workflows/customer-onboarding-checklist-for-b2b-saas/export.article.md --json
```

## Fan-out examples

- `fanout/crm-url-gap.json`: URL-backed fan-out gap analysis for `best CRM for startups`
- `fanout/crm-url-gap.log`: fetch log for the URL-backed example
- `fanout/onboarding-file-gap.json`: file-backed fan-out gap analysis against the exported onboarding article
- `fanout/onboarding-file-gap.log`: companion log file

Commands used:

```bash
uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/fanout/crm-url-gap.json \
  --log-file examples/fanout/crm-url-gap.log \
  fanout "best CRM for startups" --content https://example.com --json

uv run autoseo --api-url http://127.0.0.1:8015 \
  --output examples/fanout/onboarding-file-gap.json \
  --log-file examples/fanout/onboarding-file-gap.log \
  fanout "customer onboarding checklist for B2B SaaS" \
  --content examples/article-workflows/customer-onboarding-checklist-for-b2b-saas/export.article.md --json
```

## Brand example

- `brand/notion-api.json`: API-mode brand analysis for Notion on the query `best note-taking app`
- `brand/notion-api.log`: companion log file

## Legacy sample

- `sample_output.json`: older sample artifact kept as-is from the original repo state
