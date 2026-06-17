"""Declaration captured by the @Adapter decorator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .lifecycle_enum import LifecycleEnum


@dataclass(frozen=True, slots=True)
class AdapterDeclaration:
  """Configuration captured by the @Adapter decorator."""

  port: type[Any]
  key: str | None
  lifecycle: LifecycleEnum
  default: bool
  envs: frozenset[str] | None
