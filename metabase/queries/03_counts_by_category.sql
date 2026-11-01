-- Counts by Detoxify category
-- Posts scoring 0.5 or higher in each of Detoxify's six categories. A post can count in several.
-- Suggested chart: horizontal bar, x = posts_flagged, y = category.
select
  c.category,
  count(*) filter (where c.score >= 0.5) as posts_flagged,
  round(100.0 * avg((c.score >= 0.5)::int), 2) as pct_of_posts
from analytics.fct_post_toxicity f
cross join lateral (values
  ('toxicity', f.toxicity),
  ('severe_toxicity', f.severe_toxicity),
  ('obscene', f.obscene),
  ('threat', f.threat),
  ('insult', f.insult),
  ('identity_attack', f.identity_attack)
) as c(category, score)
group by 1
order by 2 desc;
