# ParcelPath breaker open

From chapter 6.

The circuit breaker for ParcelPath has been open for 5
minutes. Quotes and orders are using the estimate.

Check: ParcelPath's status page; `parcelpath_calls_total`
by outcome.

Act: nothing in the API needs to change; customers see
"Estimated shipping". Tell Ravi if it lasts more than an
hour, because estimated prices are higher than real ones.
