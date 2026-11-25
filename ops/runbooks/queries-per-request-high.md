# Queries per request high

From chapter 5.

Some route sends more than 25 SQL statements per request
at the 99th percentile.

Check: `db_queries_per_request` by `route`. An N+1 shows
as a count that grows with page size (chapter 5).

Act: load the relationship with `selectinload`, and make
sure the model's relationship is `lazy="raise_on_sql"`.
