# Confirmation dead letters

From chapter 13.

At least one confirmation email was given up on: the
provider refused it, or it failed 10 times.

Check: `python tools/outbox.py --dead` shows each one with
its last error.

Act: fix the cause (often a typo in the address, which
support can correct from the customer's account), then
`python tools/outbox.py --revive <id>` (chapter 13).
