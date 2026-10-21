select
  uri,
  did as author_id,
  text,
  case when created_at_raw ~ '^\d{4}-\d{2}-\d{2}T'
       then created_at_raw::timestamptz end as created_at,
  event_time as seen_at
from {{ source('bluesky', 'raw_posts') }}
where uri not in (select uri from {{ source('bluesky', 'deleted_posts') }})