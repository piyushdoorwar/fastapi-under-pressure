# Sign-in: tokens from the future

From chapter 15.

A token was refused because it was issued more than 10 s
in the future by this host's clock.

Check: clock offset (NTP status) on the API hosts.

Act: fix the clock. Don't raise the leeway to hide it.
