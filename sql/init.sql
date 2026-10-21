CREATE TABLE IF NOT EXISTS raw_posts (
  uri TEXT PRIMARY KEY,
  did TEXT NOT NULL,
  text TEXT,
  langs TEXT[],
  created_at_raw TEXT,
  event_time TIMESTAMPTZ,
  seq BIGINT NOT NULL,
  raw JSONB NOT NULL,
  ingested_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deleted_posts (
  uri TEXT PRIMARY KEY,
  seq BIGINT NOT NULL,
  deleted_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS post_scores (
  uri TEXT PRIMARY KEY,
  toxicity REAL,
  severe_toxicity REAL,
  obscene REAL,
  threat REAL,
  insult REAL,
  identity_attack REAL,
  model_version TEXT,
  scored_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingest_state (
  id INT PRIMARY KEY DEFAULT 1,
  last_seq BIGINT
);