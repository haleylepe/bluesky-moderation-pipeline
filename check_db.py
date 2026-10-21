import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
EXPECTED = ['deleted_posts', 'ingest_state', 'post_scores', 'raw_posts']

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
with conn.cursor() as cur:
    cur.execute('SELECT version()')
    print('Connected:', cur.fetchone()[0][:30])

    cur.execute('''SELECT table_name FROM information_schema.tables
                   WHERE table_schema = 'public' ORDER BY 1''')
    tables = [r[0] for r in cur.fetchall()]
    assert tables == EXPECTED, f'Tables mismatch: {tables}'
    print('Tables:', tables)

    cur.execute('''INSERT INTO raw_posts (uri, did, text, time_us, raw)
                   VALUES ('test://check', 'did:test', 'hello', 0, '{}')
                   ON CONFLICT (uri) DO NOTHING''')
    cur.execute("SELECT text FROM raw_posts WHERE uri = 'test://check'")
    assert cur.fetchone()[0] == 'hello'
    cur.execute("DELETE FROM raw_posts WHERE uri = 'test://check'")
conn.commit()
conn.close()
print('All checks passed')