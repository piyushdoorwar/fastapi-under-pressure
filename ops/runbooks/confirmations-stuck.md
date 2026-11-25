# Confirmation emails stuck

From chapter 12.

The oldest unsent confirmation has been waiting for more
than 5 minutes.

Check: is a worker running (`outbox_oldest_unsent_seconds`
comes from the worker; no data means no worker)? Is the
email provider failing (`confirmation_retry_later` log
lines)? `python tools/outbox.py` lists what is waiting.

Act: start a worker, or wait for the provider. Nothing is
lost while messages wait (chapter 12).
