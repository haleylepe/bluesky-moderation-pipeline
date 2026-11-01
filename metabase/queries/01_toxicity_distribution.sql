-- Toxicity score distribution
-- How Detoxify's toxicity scores spread across all scored posts, in 0.05-wide buckets.
-- Suggested chart: bar, x = score_bucket, y = posts.
select
  round(((least(width_bucket(toxicity, 0, 1, 20), 20) - 1) * 0.05)::numeric, 2) as score_bucket,
  count(*) as posts,
  round(100.0 * count(*) / sum(count(*)) over (), 2) as pct_of_posts
from analytics.fct_post_toxicity
group by 1
order by 1;
