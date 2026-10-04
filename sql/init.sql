-- Purpose: Initialize the database schema for the moderation pipeline.
-- This file should create raw tables, staging tables, and any foundational indexes
-- or constraints required by the downstream transformations.


CREATE TABLE IF NOT EXISTS raw_post (
    uri TEXT PRIMARY KEY,
    did TEXT NOT NULL,
    text TEXT,
    lang TEXT[],
    created_at_raw TEXT,
    time_us BIGINT NOT NULL,
    raw JSONB NOT NULL,
    raw JSONB NOT NULL,
    ingested_at TIMESTAMPZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deleted_posts (
  uri TEXT PRIMARY KEY,
  time_us BIGINT NOT NULL,
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
  last_time_us BIGINT
);