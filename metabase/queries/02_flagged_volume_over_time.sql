-- Flagged-post volume over time
-- Posts at or above the 0.5 toxicity threshold per day (UTC), with the share of all scored posts.
-- Daily counts reflect how many posts were scored for that day, not Bluesky's posting volume:
-- early days were captured from the full firehose, later ones from a 5% sample, and scoring
-- works through a backlog newest first. Compare pct_flagged across days, not raw counts.
-- Suggested chart: combo, bars = flagged_posts, line = pct_flagged.
select
  seen_at::date as day,
  count(*) filter (where is_toxic) as flagged_posts,
  count(*) as posts_scored,
  round(100.0 * avg(is_toxic::int), 2) as pct_flagged
from analytics.fct_post_toxicity
group by 1
order by 1;
