"""Hashable ``(port, key)`` used in the mapper's selection-cache key."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RegistrationKey:
  """The ``(port, key)`` half of a selection-cache key; the environment is the other half."""

  port: type[Any]
  key: str | None = None
