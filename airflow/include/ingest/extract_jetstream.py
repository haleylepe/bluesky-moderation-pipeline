import asyncio, json, os, time
import psycopg2
import websockets
from psycopg2.extras import execute_values
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

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


def clean(value):
    # Postgres can't store NUL (\x00) characters in text, so remove them
    return value.replace('\x00', '') if isinstance(value, str) else value


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
    last_seq = load_cursor(conn)
    posts, deletes = [], []
    end = time.time() + RUN_SECONDS

    # Outer loop: if the connection drops, save progress and reconnect until time is up
    while time.time() < end:
        url = JETSTREAM + (f'&cursor={last_seq}' if last_seq else '')
        try:
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
                        posts.append((uri, evt['did'], clean(rec.get('text')), rec.get('langs'),
                                      clean(rec.get('createdAt')), evt['time'], evt['seq'],
                                      json.dumps(evt).replace('\\u0000', '')))
                    elif evt['operation'] == 'delete':
                        deletes.append((uri, evt['seq']))
                    # 'update' events are skipped on purpose; noted in the README

                    if len(posts) + len(deletes) >= BATCH_SIZE:
                        flush(conn, posts, deletes, last_seq)
                        posts, deletes = [], []

        except websockets.exceptions.ConnectionClosed as e:
            print(f'Connection dropped ({e}); saving progress and reconnecting from seq {last_seq}')
            flush(conn, posts, deletes, last_seq)
            posts, deletes = [], []
            await asyncio.sleep(2)

    flush(conn, posts, deletes, last_seq)
    conn.close()


if __name__ == '__main__':
    asyncio.run(run())