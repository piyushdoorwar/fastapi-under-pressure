# Quotes slow

From chapter 1.

The 99th percentile of `POST /checkout/quote` has been
over 1.5 s for 10 minutes. The storefront gives up at 2 s.

Check: ParcelPath latency and `parcelpath_calls_total` by
outcome (chapter 6); `event_loop_lag_seconds` (chapter 3);
`db_pool_connections_in_use` (chapter 4).

Act: quotes should never take much more than the 1 s
ParcelPath budget. If they do, something is blocking the
event loop or waiting for a connection.
