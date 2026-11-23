"""A small in-memory cache with a size limit and a
time limit. The oldest-used entry goes first when the
cache is full, and no entry lives longer than ttl_s.
"""

import time
from collections import OrderedDict
from collections.abc import Callable


class TTLCache[V]:
    def __init__(
        self,
        max_entries: int,
        ttl_s: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self.clock = clock
        self.data: OrderedDict[str, tuple[float, V]] = (
            OrderedDict()
        )

    def get(self, key: str) -> V | None:
        item = self.data.get(key)
        if item is None:
            return None
        expires, value = item
        if self.clock() >= expires:
            del self.data[key]
            return None
        self.data.move_to_end(key)  # recently used
        return value

    def put(self, key: str, value: V) -> None:
        self.data[key] = (self.clock() + self.ttl_s, value)
        self.data.move_to_end(key)
        while len(self.data) > self.max_entries:
            self.data.popitem(last=False)  # oldest

    def __len__(self) -> int:
        return len(self.data)

    def clear(self) -> None:
        self.data.clear()
