"""Report on bluesky_pipeline runs and the data they produced.

Pulls run and task history from the Airflow REST API (Airflow 3 / Astro Runtime 3.x)
and row counts from Postgres, prints a summary, and writes two CSVs to reports/.

Usage, from the project root with the venv active and `astro dev start` running:
    python scripts/run_report.py
"""
import csv
import os
from datetime import datetime
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

AIRFLOW_URL = os.getenv('AIRFLOW_URL', 'http://localhost:8080')
AIRFLOW_USER = os.getenv('AIRFLOW_USER', 'admin')
AIRFLOW_PASSWORD = os.getenv('AIRFLOW_PASSWORD', 'admin')
DAG_ID = 'bluesky_pipeline'
DATABASE_URL = os.getenv('DATABASE_URL')
OUT_DIR = Path('reports')


def airflow_token():
    r = requests.post(f'{AIRFLOW_URL}/auth/token',
                      json={'username': AIRFLOW_USER, 'password': AIRFLOW_PASSWORD}, timeout=10)
    r.raise_for_status()
    return r.json()['access_token']


def get(session, path, **params):
    r = session.get(f'{AIRFLOW_URL}/api/v2{path}', params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def duration_s(start, end):
    if not start or not end:
        return None
    fmt = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00'))
    return round((fmt(end) - fmt(start)).total_seconds(), 1)


def fetch_runs(session):
    runs = get(session, f'/dags/{DAG_ID}/dagRuns', limit=200, order_by='-run_after')['dag_runs']
    rows = []
    for run in runs:
        tasks = get(session, f'/dags/{DAG_ID}/dagRuns/{run["dag_run_id"]}/taskInstances')['task_instances']
        by_task = {t['task_id']: t for t in tasks}
        row = {
            'run_id': run['dag_run_id'],
            'logical_date_utc': run.get('logical_date') or run.get('run_after'),
            'state': run['state'],
            'run_type': run['run_type'],
            'duration_s': duration_s(run.get('start_date'), run.get('end_date')),
        }
        for task_id in ('extract_jetstream', 'score_posts', 'dbt_build'):
            t = by_task.get(task_id, {})
            row[f'{task_id}_state'] = t.get('state')
            row[f'{task_id}_s'] = duration_s(t.get('start_date'), t.get('end_date'))
            row[f'{task_id}_tries'] = t.get('try_number')
        rows.append(row)
    return rows


def fetch_data_stats():
    conn = psycopg2.connect(DATABASE_URL)
    stats = {}
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
        for table in ('raw_posts', 'deleted_posts', 'post_scores'):
            cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = %s", (table,))
            stats[table] = max(cur.fetchone()[0], 0)
        stats['unscored_posts'] = max(stats['raw_posts'] - stats['post_scores'], 0)
        cur.execute("SELECT min(event_time), max(event_time) FROM raw_posts")
        stats['first_post_utc'], stats['last_post_utc'] = cur.fetchone()
        cur.execute("""
            SELECT EXISTS (SELECT 1 FROM information_schema.tables
                           WHERE table_schema = 'analytics' AND table_name = 'daily_toxicity_summary')""")
        if cur.fetchone()[0]:
            cur.execute('SELECT * FROM analytics.daily_toxicity_summary ORDER BY 1')
            cols = [d[0] for d in cur.description]
            stats['daily_summary'] = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return stats


def write_csv(path, rows):
    if not rows:
        return
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    OUT_DIR.mkdir(exist_ok=True)

    session = requests.Session()
    session.headers['Authorization'] = f'Bearer {airflow_token()}'
    runs = fetch_runs(session)
    write_csv(OUT_DIR / 'dag_runs.csv', runs)

    ok = [r for r in runs if r['state'] == 'success']
    failed = [r for r in runs if r['state'] == 'failed']
    print(f'\n{DAG_ID}: {len(runs)} runs, {len(ok)} succeeded, {len(failed)} failed')
    if ok:
        avg = lambda key: round(sum(r[key] for r in ok if r[key]) / len(ok), 1)
        print(f"  avg run {avg('duration_s')}s  "
              f"(extract {avg('extract_jetstream_s')}s, score {avg('score_posts_s')}s, dbt {avg('dbt_build_s')}s)")
    for r in failed:
        bad = [t for t in ('extract_jetstream', 'score_posts', 'dbt_build') if r[f'{t}_state'] == 'failed']
        print(f"  FAILED {r['logical_date_utc']}: {', '.join(bad) or 'unknown task'}")

    stats = fetch_data_stats()
    print('\nPostgres:')
    for k in ('raw_posts', 'deleted_posts', 'post_scores', 'unscored_posts'):
        print(f'  {k:16} {stats[k]:>10,}')
    print(f"  posts span      {stats['first_post_utc']}  to  {stats['last_post_utc']}")
    if 'daily_summary' in stats:
        write_csv(OUT_DIR / 'daily_toxicity_summary.csv', stats['daily_summary'])
        print(f"\nanalytics.daily_toxicity_summary ({len(stats['daily_summary'])} days):")
        for row in stats['daily_summary']:
            print('  ' + '  '.join(f'{k}={v}' for k, v in row.items()))

    print(f'\nWrote {OUT_DIR}/dag_runs.csv' + (' and daily_toxicity_summary.csv' if 'daily_summary' in stats else ''))


if __name__ == '__main__':
    main()