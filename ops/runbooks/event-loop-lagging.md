# Event loop lagging

From chapter 2.

The event loop has been late by more than 250 ms in the
last 5 minutes. Every request in the process waits while
it is.

Check: `event_loop_blocked` warnings in the logs; run
`py-spy dump --pid <pid>` while it happens (chapter 3).

Act: find the blocking call and move it off the loop
(`await`, a thread, or a different library).
