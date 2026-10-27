from datetime import datetime, timedelta
from airflow.sdk import dag
from airflow.providers.standard.operators.bash import BashOperator

INCLUDE = '/usr/local/airflow/include'
DBT_DIR = f'{INCLUDE}/dbt/bluesky_dbt'
DBT = '/usr/local/airflow/dbt_venv/bin/dbt'

DB_ENV = {
    'DATABASE_URL': 'postgresql://haley:localdev@host.docker.internal:5433/bluesky',
    'DB_HOST': 'host.docker.internal',
    'RUN_SECONDS': '300',
}

@dag(
    schedule='@hourly',
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args={'retries': 2, 'retry_delay': timedelta(minutes=5)},
    tags=['bluesky'],
)
def bluesky_pipeline():
    extract = BashOperator(
        task_id='extract_jetstream',
        bash_command=f'python {INCLUDE}/ingest/extract_jetstream.py',
        env=DB_ENV,
        append_env=True,
    )
    score = BashOperator(
        task_id='score_posts',
        bash_command=f'python {INCLUDE}/ingest/score_posts.py',
        env=DB_ENV,
        append_env=True,
    )
    transform = BashOperator(
        task_id='dbt_build',
        bash_command=f'cd {DBT_DIR} && {DBT} build --profiles-dir .',
        env=DB_ENV,
        append_env=True,
    )
    extract >> score >> transform
    


bluesky_pipeline()