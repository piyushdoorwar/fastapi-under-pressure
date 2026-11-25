# Memory high

From chapter 7.

The API process has used more than 700 MB for 15 minutes.
The container limit is 1 GB.

Check: whether it is growing steadily (a leak) or jumped
(one large request). Run `tools/memory_probe.py` against a
copy if it is growing (chapter 7).

Act: a rolling restart buys time (chapter 14); it does not
fix a leak. Look first at caches without a size limit.
