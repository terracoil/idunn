"""One re-entrant lock per key, made on first request and kept for good."""

from __future__ import annotations

from threading import Lock, RLock
from typing import Generic, TypeVar

K = TypeVar('K')  # unbounded, like dict's own keys: mypy will not call type[Any] Hashable


class KeyedLocks(Generic[K]):
  """Hands out the same ``RLock`` for the same key, so unrelated keys never queue on each other.
  The read is a plain ``dict.get``; only a miss takes the guard, and ``setdefault`` under it makes
  sure two threads asking for a new key at once leave with one lock between them, not one each.
  Re-entrant because the holder may come back for its own key on the same thread, and a lock that
  deadlocks against its own owner is a very quiet way to report a bug. Locks are never dropped:
  replace the whole ``KeyedLocks`` to start over.
  """

  def __init__(self) -> None:
    """Start with no locks and one guard for making them."""
    self._locks: dict[K, RLock] = {}
    self._guard: Lock = Lock()

  def for_key(self, key: K) -> RLock:
    """Return ``key``'s lock, creating it if this is the first time anyone asked."""
    lock: RLock | None = self._locks.get(key)
    if lock is None:
      with self._guard:
        lock = self._locks.setdefault(key, RLock())
    return lock
