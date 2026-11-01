# Metabase

Metabase runs from the project's `docker-compose.yml` at http://localhost:3000. Its own settings,
questions, and dashboards live in an H2 file on the `metabase-data` Docker volume, so they survive
`docker compose down` and image updates. `docker compose down -v` deletes them.

## Connect it to the pipeline database

1. Start the stack with `docker compose up -d` and open http://localhost:3000. The first start takes about a minute.
2. Create the admin account.
3. When asked to add data, choose **PostgreSQL** and enter:
   - Display name: `Bluesky`
   - Host: `postgres` (the compose service name, not `localhost`)
   - Port: `5432` (the port inside the Docker network, not the published 5433)
   - Database name: `bluesky`
   - Username: `haley`
   - Password: the `POSTGRES_PASSWORD` value from your `.env`
4. Under the connection's advanced options, set **Schemas** to "Only these" and enter `analytics`,
   so Metabase shows the dbt models and not the raw tables.

## Build the dashboard

For each file in `queries/`, choose **New > SQL query**, pick the Bluesky database, paste the file,
run it, set the visualization named in the file's header comment, and save it. Then create a
dashboard and add the four saved questions.

| File | Question | Visualization |
| --- | --- | --- |
| `01_toxicity_distribution.sql` | How are toxicity scores distributed? | Bar |
| `02_flagged_volume_over_time.sql` | How many posts cross the threshold each day? | Combo (bars and line) |
| `03_counts_by_category.sql` | Which Detoxify categories fire most? | Horizontal bar |
| `04_top_scoring_posts.sql` | Which posts score highest? | Table |
