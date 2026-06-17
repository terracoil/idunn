"""Hashable key used by the inversion table."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RegistrationKey:
  """Identifies one adapter binding for one port and optional key."""

  port: type[Any]
  key: str | None = None
