"""Export the aggregates the dashboard needs to dashboard/data/dashboard.json.

The dashboard is a static site (hosted on Vercel), so it never connects to Postgres.
This script reads the analytics schema and the run report, and writes one JSON file
of aggregates and scores. No post text, handles, or raw account IDs are exported:
accounts and posts appear only as short one-way hashes.

Usage, from the project root with the venv active:
    python scripts/run_report.py              # refreshes reports/dag_runs.csv (needs Airflow running)
    python scripts/export_dashboard_data.py   # needs Postgres running (docker compose up -d)

If Postgres is not reachable, the script falls back to reports/daily_toxicity_summary.csv,
and the score distribution and review feed are left empty.
"""
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # optional: lets the CSV fallback run without the venv
    pass

DATABASE_URL = os.getenv('DATABASE_URL')
REPORTS = Path('reports')
OUT = Path('dashboard/data/dashboard.json')
CATEGORIES = ('toxicity', 'severe_toxicity', 'obscene', 'threat', 'insult', 'identity_attack')


def short_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()[:10]


def num(value):
    return None if value in (None, '') else float(value)


def from_db():
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
    cur = conn.cursor()

    cur.execute("""
        select day::text, posts_scored, avg_toxicity, share_toxic, share_insult,
               share_threat, share_identity_attack
        from analytics.daily_toxicity_summary order by day""")
    daily = [dict(zip(('day', 'posts_scored', 'avg_toxicity', 'share_toxic', 'share_insult',
                       'share_threat', 'share_identity_attack'), (r[0], int(r[1]), *map(float, r[2:]))))
             for r in cur.fetchall()]

    cur.execute("""
        select least(width_bucket(toxicity, 0, 1, 20), 20) as bucket, count(*)
        from analytics.fct_post_toxicity group by 1 order by 1""")
    distribution = [{'bucket': round((b - 1) * 0.05, 2), 'posts': int(n)} for b, n in cur.fetchall()]

    cols = ', '.join(CATEGORIES)
    cur.execute(f"""
        select seen_at, uri, author_id, {cols}
        from analytics.fct_post_toxicity order by toxicity desc limit 100""")
    top_posts = []
    for row in cur.fetchall():
        seen_at, uri, author_id, *scores = row
        top_posts.append({
            'seen_at': seen_at.isoformat() if seen_at else None,
            'post': short_hash(uri),
            'account': short_hash(author_id),
            **{c: round(float(s), 3) for c, s in zip(CATEGORIES, scores)},
        })

    flagged = {}
    for c in CATEGORIES:
        cur.execute(f'select count(*) filter (where {c} >= 0.5), count(*) from analytics.fct_post_toxicity')
        n, total = cur.fetchone()
        flagged[c] = {'posts': int(n), 'share': (n / total) if total else 0}

    conn.close()
    return daily, distribution, top_posts, flagged, 'postgres'


def from_csv():
    path = REPORTS / 'daily_toxicity_summary.csv'
    daily = []
    with open(path) as f:
        for r in csv.DictReader(f):
            daily.append({'day': r['day'], 'posts_scored': int(r['posts_scored']),
                          **{k: float(r[k]) for k in ('avg_toxicity', 'share_toxic', 'share_insult',
                                                       'share_threat', 'share_identity_attack')}})
    return daily, None, None, None, 'reports/daily_toxicity_summary.csv'


def runs():
    path = REPORTS / 'dag_runs.csv'
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            # Runs before Nov 1 had one dbt_build task; treat it as both dbt steps
            build = r.get('dbt_build_state')
            out.append({
                'logical_date': r['logical_date_utc'],
                'state': r['state'],
                'duration_s': num(r['duration_s']),
                'tasks': {
                    'extract_jetstream': {'state': r['extract_jetstream_state'], 's': num(r['extract_jetstream_s'])},
                    'score_posts': {'state': r['score_posts_state'], 's': num(r['score_posts_s'])},
                    'dbt_run': {'state': r['dbt_run_state'] or build, 's': num(r['dbt_run_s'] or r.get('dbt_build_s'))},
                    'dbt_test': {'state': r['dbt_test_state'] or build, 's': num(r['dbt_test_s'])},
                },
            })
    return sorted(out, key=lambda r: r['logical_date'])


def main():
    try:
        if not DATABASE_URL:
            raise RuntimeError('DATABASE_URL is not set')
        daily, distribution, top_posts, flagged, source = from_db()
    except Exception as exc:  # fall back to the last run report
        print(f'Postgres not available ({exc}); using reports/ CSVs')
        daily, distribution, top_posts, flagged, source = from_csv()

    total = sum(d['posts_scored'] for d in daily)
    weighted = lambda k: sum(d[k] * d['posts_scored'] for d in daily) / total if total else 0
    data = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': source,
        'threshold': 0.5,
        'summary': {
            'posts_scored': total,
            'first_day': daily[0]['day'] if daily else None,
            'last_day': daily[-1]['day'] if daily else None,
            'days': len(daily),
            'avg_toxicity': weighted('avg_toxicity'),
            'share_toxic': weighted('share_toxic'),
            'share_insult': weighted('share_insult'),
            'share_threat': weighted('share_threat'),
            'share_identity_attack': weighted('share_identity_attack'),
        },
        'daily': daily,
        'flagged_by_category': flagged,
        'distribution': distribution,
        'top_posts': top_posts,
        'runs': runs(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1))
    print(f'Wrote {OUT}: {total:,} posts over {len(daily)} days from {source}, {len(data["runs"])} runs')


if __name__ == '__main__':
    main()
