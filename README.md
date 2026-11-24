# Bluesky Moderation Pipeline

An end-to-end data pipeline that samples public Bluesky posts from the Jetstream firehose, scores them with the Detoxify toxicity classifier, and models the results in dbt for a Metabase dashboard. Airflow runs the whole thing every hour. The point is to measure how well an off-the-shelf toxicity model covers the harms a trust and safety team actually handles, and to show where it falls short.

<!-- Optional: add an Airflow graph screenshot as docs/images/airflow-graph.png and embed it here. -->

## Architecture

```mermaid
flowchart LR
    J[Bluesky Jetstream v2<br/>websocket] --> E[extract_jetstream<br/>5% sample, English only]
    E --> R[(Postgres: public<br/>raw_posts, deleted_posts)]
    R --> S[score_posts<br/>Detoxify]
    S --> P[(Postgres: public<br/>post_scores)]
    R --> D[dbt_run<br/>staging and marts]
    P --> D
    D --> A[(Postgres: analytics<br/>stg_posts, fct_post_toxicity,<br/>daily_toxicity_summary)]
    A --> T[dbt_test<br/>45 data tests]
    A --> M[Metabase dashboard]
    AF{{Airflow, hourly}} -.-> E
    AF -.-> S
    AF -.-> D
    AF -.-> T
```

Each hour the `bluesky_pipeline` DAG runs four tasks in order:

1. **extract_jetstream** reads the Jetstream websocket for five minutes, resuming from the last saved cursor. It keeps a deterministic 5% sample of post URIs, stores English posts in `raw_posts`, and records deletions in `deleted_posts`.
2. **score_posts** runs Detoxify on up to 6,000 unscored English posts, newest first, and writes six category scores per post to `post_scores`.
3. **dbt_run** builds the staging view and the two mart tables in the `analytics` schema.
4. **dbt_test** runs the data tests. A failure here marks the run failed, so bad data is visible in Airflow instead of silently reaching the dashboard.

## Why I built it

I come from trust and safety work, where the hard problems are operational: too much content for human review, a limited number of reviewers, and decisions that have to be made quickly and consistently. Classifiers are what make that volume manageable. They decide what gets queued, in what order, and what never reaches a person at all.

That makes the classifier's blind spots an operations problem, not just a modeling one. A model that over-flags casual profanity fills the review queue with noise. A model that misses spam or coordinated harassment written in polite language lets real harm through with no signal at all. Thresholds like 0.5 look neutral but quietly set reviewer workload and user experience.

This project builds the measurement side of that problem on live data: a pipeline that continuously scores a real platform's posts, keeps the data clean and tested, and puts the results in front of a dashboard. It treats the classifier the way a moderation team should, as one signal to be audited, and asks how its scores are distributed, which categories actually fire, how stable flag rates are over time, and what the highest-scoring content looks like.

## Tech stack

| Layer | Tools |
| --- | --- |
| Ingestion | Python, `websockets`, Bluesky Jetstream v2 |
| Storage | PostgreSQL 16 in Docker |
| Scoring | Detoxify 0.5 (`original` model), PyTorch |
| Transformation and testing | dbt (`dbt-postgres` 1.11), `dbt_utils` |
| Orchestration | Apache Airflow 3.3 on Astro Runtime, run locally with the Astro CLI |
| Dashboard | Metabase |

## Running it locally

**Prerequisites:** Docker Desktop, the [Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli), and Git. Python 3.11 or newer is only needed for the optional health check.

1. **Clone the repo.**

   ```bash
   git clone https://github.com/haleylepe/bluesky-moderation-pipeline.git
   cd bluesky-moderation-pipeline
   ```

2. **Create the two env files.** Pick a Postgres password and use the same value in both.

   ```bash
   cp .env.example .env                  # used by docker compose and local scripts
   cp airflow/.env.example airflow/.env  # holds the Airflow connection to Postgres
   ```

   Edit `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env`, and the `password` field in `airflow/.env`. Both files are gitignored.

3. **Start Postgres and Metabase.** On first start, Postgres creates the raw tables from `sql/init.sql`.

   ```bash
   docker compose up -d
   ```

4. **(Optional) Check the database** from your machine:

   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python check_db.py   # prints "All checks passed"
   ```

5. **Start Airflow.** The first build takes several minutes because it installs PyTorch, Detoxify, and dbt.

   ```bash
   cd airflow
   astro dev start
   ```

   Airflow's containers reach Postgres through `host.docker.internal:5433`, the port published by docker compose.

6. **Run the pipeline.** Open http://localhost:8080, unpause `bluesky_pipeline`, and click **Trigger**. A run takes about 20 minutes, most of it scoring. From then on it runs every hour while your machine is awake.

7. **Set up Metabase** at http://localhost:3000 by following [metabase/README.md](metabase/README.md). It walks through connecting to Postgres and building the dashboard from the saved queries in [metabase/queries/](metabase/queries/).

To see how runs are going, `python scripts/run_report.py` prints a summary of recent DAG runs and row counts and writes CSVs to `reports/`.

## Dashboard

A static dashboard in [dashboard/](dashboard/) presents the results with Bluesky's colors and Inter type: an overview of flag rates by category, a review feed of the highest-scoring posts (scores only, hashed IDs), and pipeline health from the Airflow run history. It reads one file, `dashboard/data/dashboard.json`, so it can be hosted on Vercel without any connection to the database.

To refresh it, with Postgres (and, for run history, Airflow) running:

```bash
python scripts/run_report.py              # refreshes reports/dag_runs.csv
python scripts/export_dashboard_data.py   # writes dashboard/data/dashboard.json
```

Then commit the JSON and redeploy. Without Postgres, the export falls back to the last run report, and the score distribution and review feed stay empty until the next full export.

## Data model

The raw layer is written by the Python tasks. dbt builds everything downstream of it in the `analytics` schema.

| Layer | Model | Type | What it holds |
| --- | --- | --- | --- |
| Raw (`public`) | `raw_posts` | table | Every sampled English post as received, including the full event JSON |
| Raw (`public`) | `deleted_posts` | table | Delete events for sampled posts |
| Raw (`public`) | `post_scores` | table | Six Detoxify scores per post, keyed on post URI |
| Staging | `stg_posts` | view | Posts with clean column names and parsed timestamps, minus anything the author deleted |
| Mart | `fct_post_toxicity` | table | One row per scored, non-deleted post with all six scores and an `is_toxic` flag (toxicity of 0.5 or higher) |
| Mart | `daily_toxicity_summary` | table | Per day: posts scored, average toxicity, and the share of posts over 0.5 for toxicity, insult, threat, and identity attack |

Staging is where raw data gets cleaned and deletions are honored. It is a view, so it always reflects the latest raw data. Marts are what the dashboard reads: rebuilt as tables each run, shaped around the questions being asked, and fast to query.

**Tests.** `dbt_test` runs 45 data tests across sources, staging, and marts: post IDs are unique and not null at every layer, timestamps are not null, every Detoxify score and daily share falls between 0 and 1, and every post in the fact table exists in staging. A relationship test that every score belongs to an ingested post is set to warn rather than fail.

## How the pipeline handles real-world data

- **Deterministic sampling.** A post is kept if a hash of its URI falls in the bottom 5%. The same post always gets the same answer, so a later delete event for a sampled post is captured too.
- **Resumable and idempotent.** Each run saves the last Jetstream sequence number and resumes from it. Posts are keyed on their `at://` URI and inserted with `ON CONFLICT DO NOTHING`, so replays never create duplicates. Posts, deletions, and the cursor commit in one transaction, so the cursor can never get ahead of the saved data.
- **Deletions are honored downstream.** Deleted posts stay in the raw layer for reprocessing but are excluded from every analytics model.
- **Scoring is bounded.** Each run scores at most 6,000 posts, newest first, so recent days fill in before the older backlog. Scoring is capped at four CPU threads and runs at low priority so it doesn't starve the local Airflow scheduler.

## Findings

Results below come from the pipeline's own outputs (`reports/daily_toxicity_summary.csv` and `reports/dag_runs.csv`, written by `scripts/run_report.py`).

![Share of scored posts flagged each day](docs/images/daily-flag-rate.png)

**Dataset.** 574,207 English posts scored between October 21 and October 31, 2026. October 21 (255,048 posts) was captured from the full firehose while the extract was being built; every day after that comes from the deterministic 5% sample, at roughly 8,000 to 93,000 scored posts per day depending on how long the laptop running Airflow stayed awake. Because daily counts reflect collection, not Bluesky's posting volume, the comparisons below use shares, not raw counts.

**1. Score distribution.** The average toxicity score across all posts is 0.10, while 9.2% of posts cross the 0.5 threshold. A low mean alongside a meaningful flagged share means the distribution is heavily skewed: most posts sit near zero, and a long tail of high scores carries the flags. In review-queue terms, the 0.5 cutoff would route about 1 in 11 English posts to a human, which is far more than any real moderation team could review at Bluesky's scale.

**2. Flagged volume over time.** The flagged share is remarkably stable, ranging only from 8.4% (October 30) to 9.7% (October 25) across eleven days, and the full-firehose day (9.2%) matches the sampled days. That stability is a good sign for the sampling method, since the 5% hash sample reproduces the full-stream rate. It also suggests the classifier is measuring a steady background level of rough language rather than reacting to specific events.

**3. Categories.** Categories fall off sharply after the general toxicity score: 2.4% of posts are flagged for insult, 0.3% for identity attack, and 0.13% for threat. Even if every insult flag also counted as toxic, at most about a quarter of toxicity flags would be insults, which fits the early observation that profanity, not targeted abuse, drives most of the general score. The categories that map most directly to policy (threats, identity-based attacks) are the rarest, so a team relying on the general toxicity score would be sorting through mostly profanity to find them.

**4. Top-scoring posts.** Reading the highest-scoring posts (see the early observations below) shows the same pattern as the category counts: casual profanity scores as high as targeted abuse, and jokes, game talk, and genuine threats can land at similar scores. The model sees only the text of a single post, so it cannot tell a friend joking from a stranger harassing someone, which means a reviewer would dismiss many of the top-ranked posts on sight.

**What this means for moderation operations.** Detoxify is useful as a first-pass ranking signal: sorting a queue by its threat and identity-attack scores would surface a small, high-priority slice. Used as a single 0.5 gate on the general toxicity score, it would flood reviewers with profanity while staying blind to spam, scams, and polite coordinated harassment. In practice it would need per-category thresholds, conversation and account context, and separate detectors for non-hostile harms before it could carry real enforcement decisions.

### Pipeline reliability

The run report covers 100 hourly DAG runs from October 25 to November 1. 45 succeeded end to end. Every failure was operational, not a data-quality problem: 33 runs failed at `extract_jetstream` and 22 at `score_posts`, mostly when the laptop slept mid-run and a task hit its timeout or lost its websocket. `dbt_test` never failed on a run that reached it, so every row that reached the dashboard passed all data tests. Because the extract resumes from a saved cursor and inserts are idempotent, failed runs caught up on the next success without duplicates. Moving Airflow and Postgres to an always-on host would be the single biggest reliability fix.

### Early observations

From a manual read of high-scoring posts:

- **Profanity inflates scores.** Casual swearing with no target scores as highly toxic, even when nothing abusive is happening.
- **Context is lost.** Phrases that could be jokes, game talk, or genuine threats receive similar scores, since the model sees only the text of a single post.
- **Some harms are invisible to toxicity scoring.** Spam and solicitation written in neutral, promotional language score near zero. A toxicity model measures hostile language, so these harms need separate, purpose-built detection.

## Limitations

- **Sampled, not complete.** The extract keeps 5% of posts, and only while the machine running Airflow is awake.
- **English only.** Detoxify's `original` model is trained on English text, so only English posts are stored.
- **Toxicity is one signal.** Scores reflect hostile language, not every kind of policy violation.
- **Edits are skipped.** Post updates are not ingested.
- **Scoring can lag ingestion.** When the backlog grows, the newest posts are scored first and older ones wait.

## Privacy and handling

These are posts from real people, so the project follows a few rules:

- Authors are stored by their permanent account ID (DID), never by handle.
- Dashboard questions show scores and aggregates, not post text.
- Deletions are honored downstream; deleted posts are excluded from analysis tables.
- Post text stays in the local database and is never committed to this repository.

## Repository layout

```
├── docker-compose.yml          # Postgres and Metabase
├── sql/init.sql                # Raw table definitions, run on first database start
├── check_db.py                 # Health check: connection, tables, read/write
├── scripts/run_report.py       # Summary of DAG runs and row counts
├── metabase/
│   ├── README.md               # Connecting Metabase and building the dashboard
│   └── queries/                # SQL for the four dashboard questions
├── dashboard/                  # Static dashboard for Vercel (index.html, app.js, data/dashboard.json)
├── scripts/export_dashboard_data.py  # Writes the dashboard's JSON from the analytics schema
└── airflow/                    # Astro project
    ├── Dockerfile              # Astro Runtime plus a separate dbt virtualenv
    ├── requirements.txt        # Python packages for the Airflow image
    ├── dags/bluesky_pipeline.py
    └── include/
        ├── ingest/
        │   ├── extract_jetstream.py
        │   ├── score_posts.py
        │   └── explore_detoxify.py   # Scratch exploration of Detoxify
        └── dbt/bluesky_dbt/          # dbt project: staging, marts, tests
```

## Next steps

- **To do: account-level view.** Switch the extract to sample by author DID instead of post URI (so every post from a sampled account is kept), add a `fct_author_toxicity` dbt table with one row per account (posts scored, flagged posts, flag rate, max score, first and last seen, keyed on `author_id` as text), and add a Users tab to the dashboard that shows hashed account IDs only.
- Compare Detoxify scores with Bluesky's own moderation labels.
- Hand-label a sample of high-scoring posts to estimate precision at the 0.5 threshold.
- Add source freshness checks to the DAG so a stalled extract fails loudly.
