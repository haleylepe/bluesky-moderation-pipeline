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

def get_unscored_posts(conn):
    with conn.cursor() as cur:
        cur.execute('''
            SELECT r.uri, r.text
            FROM raw_posts r
            LEFT JOIN post_scores s ON s.uri = r.uri
            WHERE s.uri IS NULL
              AND 'en' = ANY(r.langs)
            LIMIT 10
        ''')
        rows = cur.fetchall()
    return rows

def get_text(unformatted_posts):
    texts = []
    for post in unformatted_posts:
        texts.append(post[1])
    return texts

    
conn = psycopg2.connect(DATABASE_URL)
model = Detoxify('original')
texts = get_text(get_unscored_posts(conn))
results = model.predict(texts) 

for text, score in zip(texts, results['toxicity']):
    print(f'{score:.3f}  {text[:80]}')
conn.close()
    

    
