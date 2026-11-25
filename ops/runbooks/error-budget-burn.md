# Error budget burning

From chapter 1.

More than 1.44 % of requests have been failing with a 5xx
for the last hour, and still are.

Check: which routes (`http_request_duration_seconds_count`
by `route` and `status`). Then the alerts below: a full
pool, an open breaker or high memory usually explain a
burn.

Act: if a deploy went out in the last hour, roll back
first and investigate after. Otherwise follow the runbook
of the more specific alert that is firing.
