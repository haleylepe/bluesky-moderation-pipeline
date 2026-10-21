import asyncio, json, os, time
import psycopg2
import websockets
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv('DATABASE_URL')
JETSTREAM = (
    'wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents'
    '?collections=app.bsky.feed.post&kinds=commit'
)
RUN_SECONDS = int(os.getenv('RUN_SECONDS', '300'))
BATCH_SIZE = 500


def load_cursor(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT last_seq FROM ingest_state WHERE id = 1')
        row = cur.fetchone()
    return row[0] if row else None


def flush(conn, posts, deletes, last_seq):
    with conn.cursor() as cur:
        if posts:
            execute_values(cur, '''
                INSERT INTO raw_posts (uri, did, text, langs, created_at_raw, event_time, seq, raw)
                VALUES %s ON CONFLICT (uri) DO NOTHING''', posts)
        if deletes:
            execute_values(cur, '''
                INSERT INTO deleted_posts (uri, seq)
                VALUES %s ON CONFLICT (uri) DO NOTHING''', deletes)
        if last_seq:
            cur.execute('''
                INSERT INTO ingest_state (id, last_seq) VALUES (1, %s)
                ON CONFLICT (id) DO UPDATE SET last_seq = EXCLUDED.last_seq''',
                (last_seq,))
    conn.commit()


async def run():
    conn = psycopg2.connect(DB_URL)
    cursor = load_cursor(conn)
    url = JETSTREAM + (f'&cursor={cursor}' if cursor else '')
    posts, deletes, last_seq = [], [], cursor
    end = time.time() + RUN_SECONDS

    async with websockets.connect(url, subprotocols=['xrpc.v1.json'], max_size=2**22) as ws:
        while time.time() < end:
            frame = json.loads(await ws.recv())
            if frame.get('$type') != 'message':
                print('Non-event frame:', frame)  # errors arrive this way
                continue
            evt = frame['payload']
            if not evt.get('$type', '').endswith('#commit'):
                continue

            uri = f"at://{evt['did']}/{evt['collection']}/{evt['rkey']}"
            last_seq = evt['seq']

            if evt['operation'] == 'create':
                rec = evt.get('record', {})
                posts.append((uri, evt['did'], rec.get('text'), rec.get('langs'),
                              rec.get('createdAt'), evt['time'], evt['seq'], json.dumps(evt)))
            elif evt['operation'] == 'delete':
                deletes.append((uri, evt['seq']))
            # 'update' events are skipped on purpose; note that in your README

            if len(posts) + len(deletes) >= BATCH_SIZE:
                flush(conn, posts, deletes, last_seq)
                posts, deletes = [], []

    flush(conn, posts, deletes, last_seq)
    conn.close()


if __name__ == '__main__':
    asyncio.run(run())