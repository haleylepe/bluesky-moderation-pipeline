-- Top-scoring posts
-- The 50 posts with the highest toxicity score, with all six category scores.
-- Post text is left out on purpose: the project's privacy rule is that the dashboard
-- shows scores and aggregates, not what individuals wrote. For a private review view,
-- join analytics.stg_posts on uri and select its text column.
-- Suggested visualization: table.
select
  f.seen_at,
  f.uri,
  round(f.toxicity::numeric, 3) as toxicity,
  round(f.severe_toxicity::numeric, 3) as severe_toxicity,
  round(f.obscene::numeric, 3) as obscene,
  round(f.threat::numeric, 3) as threat,
  round(f.insult::numeric, 3) as insult,
  round(f.identity_attack::numeric, 3) as identity_attack
from analytics.fct_post_toxicity f
order by f.toxicity desc
limit 50;
