"""Adapter lifecycle choices."""

from enum import StrEnum, auto


class LifecycleEnum(StrEnum):
  """Supported adapter lifecycles."""

  SINGLETON = auto()
  TRANSIENT = auto()
