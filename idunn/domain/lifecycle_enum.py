"""Adapter lifecycles."""

from enum import StrEnum, auto


class LifecycleEnum(StrEnum):
  """How long a resolved adapter lives: built once (``SINGLETON``) or per resolve (``TRANSIENT``).
  A ``StrEnum`` with lowercase values, so ``@Adapter(lifecycle='singleton')`` works too.
  """

  SINGLETON = auto()
  TRANSIENT = auto()
