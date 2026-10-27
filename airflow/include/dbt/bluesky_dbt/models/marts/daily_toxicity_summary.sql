select
  seen_at::date as day,
  count(*) as posts_scored,
  avg(toxicity) as avg_toxicity,
  avg(case when is_toxic then 1.0 else 0 end) as share_toxic,
  avg(case when insult >= 0.5 then 1.0 else 0 end) as share_insult,
  avg(case when threat >= 0.5 then 1.0 else 0 end) as share_threat,
  avg(case when identity_attack >= 0.5 then 1.0 else 0 end) as share_identity_attack
from {{ ref('fct_post_toxicity') }}
group by 1