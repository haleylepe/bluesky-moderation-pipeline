from datetime import datetime, timedelta
from airflow.sdk import dag
from airflow.providers.standard.operators.bash import BashOperator

INCLUDE = '/usr/local/airflow/include'
DBT_DIR = f'{INCLUDE}/dbt/bluesky_dbt'
DBT = '/usr/local/airflow/dbt_venv/bin/dbt'

# Postgres credentials come from the Airflow connection `bluesky_postgres`
# (set as AIRFLOW_CONN_BLUESKY_POSTGRES in airflow/.env, see airflow/.env.example).
# The templates render at run time, so nothing secret lives in this file.
PG = 'conn.bluesky_postgres'
DB_ENV = {
    'DATABASE_URL': (
        f'postgresql://{{{{ {PG}.login }}}}:{{{{ {PG}.password | urlencode }}}}'
        f'@{{{{ {PG}.host }}}}:{{{{ {PG}.port }}}}/{{{{ {PG}.schema }}}}'
    ),
    'DB_HOST': f'{{{{ {PG}.host }}}}',
    'DB_PORT': f'{{{{ {PG}.port }}}}',
    'DB_USER': f'{{{{ {PG}.login }}}}',
    'DB_NAME': f'{{{{ {PG}.schema }}}}',
    'POSTGRES_PASSWORD': f'{{{{ {PG}.password }}}}',
    'RUN_SECONDS': '300',
    'SAMPLE_PCT': '5',
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
        execution_timeout=timedelta(minutes=15),
    )
    # nice keeps the scheduler responsive while Detoxify is using the CPU
    score = BashOperator(
        task_id='score_posts',
        bash_command=f'nice -n 10 python {INCLUDE}/ingest/score_posts.py',
        env=DB_ENV,
        append_env=True,
        execution_timeout=timedelta(minutes=45),
    )
    dbt_run = BashOperator(
        task_id='dbt_run',
        bash_command=f'cd {DBT_DIR} && {DBT} run --profiles-dir .',
        env=DB_ENV,
        append_env=True,
    )
    dbt_test = BashOperator(
        task_id='dbt_test',
        bash_command=f'cd {DBT_DIR} && {DBT} test --profiles-dir .',
        env=DB_ENV,
        append_env=True,
    )
    extract >> score >> dbt_run >> dbt_test


bluesky_pipeline()
