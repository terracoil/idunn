"""Metaclass that turns a class into a process-wide singleton."""

from __future__ import annotations

from threading import Lock
from typing import TypeVar, cast

_T = TypeVar('_T')


class MetaSingleton(type):
  """Metaclass that caches one instance per class for the life of the process.
  A metaclass rather than a module-level instance, so nothing happens (environment lookup
  included) until somebody first calls ``Idunn()``.
  """

  _instances: dict[type, object] = {}
  _lock: Lock = Lock()

  def __call__(cls: type[_T], *args: object, **kwargs: object) -> _T:
    """Return the cached instance, creating it once under a lock.
    Arguments count only on that first call; afterwards they are ignored, not merged.
    ``cls: type[_T]`` is what makes ``Idunn()`` read as ``Idunn`` (not ``object``) to callers
    and the type checker. Double-checked locking keeps first construction race-free without
    paying for the lock on every call after it.
    """
    if cls not in MetaSingleton._instances:
      with MetaSingleton._lock:
        if cls not in MetaSingleton._instances:
          MetaSingleton._instances[cls] = type.__call__(cls, *args, **kwargs)
    return cast(_T, MetaSingleton._instances[cls])
