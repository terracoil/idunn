"""Metaclass that turns a class into a process-wide singleton."""

from __future__ import annotations

from threading import Lock
from typing import TypeVar, cast

_T = TypeVar('_T')


class MetaSingleton(type):
  """Metaclass whose instances are cached one-per-class for the process."""

  _instances: dict[type, object] = {}
  _lock: Lock = Lock()

  def __call__(cls: type[_T], *args: object, **kwargs: object) -> _T:
    """Return the cached instance, creating it once under a lock.

    ``cls: type[_T]`` is what makes ``Idunn()`` resolve to ``Idunn`` (not
    ``object``) for callers and the type checker. Double-checked locking keeps
    first-construction race-free without paying for the lock on every call.
    """
    if cls not in MetaSingleton._instances:
      with MetaSingleton._lock:
        if cls not in MetaSingleton._instances:
          MetaSingleton._instances[cls] = type.__call__(cls, *args, **kwargs)
    return cast(_T, MetaSingleton._instances[cls])
