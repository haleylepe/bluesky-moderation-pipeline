from detoxify import Detoxify
import  os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

    
load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')
JETSTREAM = (
    'wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents'
    '?collections=app.bsky.feed.post&kinds=commit'
)
MODEL = 'original'
LABELS = ['toxicity', 'severe_toxicity', 'obscene', 'threat', 'insult', 'identity_attack']
BATCH = 64

def get_unscored_posts(conn):
    with conn.cursor() as cur:
        cur.execute('''
            SELECT r.uri, r.text
            FROM raw_posts r
            LEFT JOIN post_scores s ON s.uri = r.uri
            LEFT JOIN deleted_posts d ON d.uri = r.uri
            WHERE s.uri IS NULL
            AND d.uri IS NULL
            AND r.text IS NOT NULL AND r.text <> ''
            AND 'en' = ANY(r.langs)
            LIMIT 5000
        ''')
        rows = cur.fetchall()
    return rows

def get_text(unformatted_posts):
    texts = []
    for post in unformatted_posts:
        texts.append(post[1])
    return texts


def main():
    conn = psycopg2.connect(DATABASE_URL)
    rows = get_unscored_posts(conn)
    if not rows:
        print('Nothing to score')
        conn.close()
        return

    model = Detoxify(MODEL)

    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        preds = model.predict([text for _, text in chunk])
        values = [
            (uri, *[float(preds[label][j]) for label in LABELS], MODEL)
            for j, (uri, _) in enumerate(chunk)
        ]
        with conn.cursor() as cur:
            execute_values(cur, '''
                INSERT INTO post_scores
                    (uri, toxicity, severe_toxicity, obscene, threat, insult, identity_attack, model_version)
                VALUES %s ON CONFLICT (uri) DO NOTHING''', values)
        conn.commit()

    print(f'Scored {len(rows)} posts')
    conn.close()
    

if __name__ == '__main__':
    main()
