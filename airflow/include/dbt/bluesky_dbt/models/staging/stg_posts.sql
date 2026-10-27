select
  r.uri,
  r.did as author_id,
  r.text,
  case when r.created_at_raw ~ '^\d{4}-\d{2}-\d{2}T'
       then r.created_at_raw::timestamptz end as created_at,
  r.event_time as seen_at
from {{ source('bluesky', 'raw_posts') }} r
where not exists (
  select 1
  from {{ source('bluesky', 'deleted_posts') }} d
  where d.uri = r.uri
)