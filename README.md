# Bluesky Moderation Pipeline

Purpose: Document the end-to-end setup for ingesting Bluesky data, processing moderation scores,
and producing analytics or downstream outputs via the data warehouse and orchestration layers.

This repository is scaffolded to support the following workflow:
- Ingest raw Bluesky data from Jetstream
- Score or classify content for moderation
- Store and transform data in SQL/dbt models
- Orchestrate the workflow with Airflow
