select
  p.uri,
  p.author_id,
  p.seen_at,
  s.toxicity,
  s.severe_toxicity,
  s.obscene,
  s.threat,
  s.insult,
  s.identity_attack,
  s.toxicity >= 0.5 as is_toxic,
  s.model_version
from {{ ref('stg_posts') }} p
join {{ source('bluesky', 'post_scores') }} s using (uri)