# Database pool full

From chapter 4.

All 10 connections have been checked out for 2 minutes.
New requests wait 1 s and then get a 503.

Check: `db_connection_hold_seconds` and
`connection_held_long` warnings: something is holding
connections across a slow call (chapter 4).

Act: a slow partner holding connections recovers when the
partner does; if it doesn't, restart the API process and
find the holder.
