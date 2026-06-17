"""Metadata stored for adapter declarations and registrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .lifecycle_enum import LifecycleEnum


@dataclass(frozen=True, slots=True)
class AdapterMetadata:
  """Describes one registered adapter."""

  adapter: type[Any]
  port: type[Any]
  key: str | None
  lifecycle: LifecycleEnum
  default: bool
  envs: frozenset[str] | None
  order: int

  def is_available_in(self, environment: str) -> bool:
    """Return whether this adapter is active in an environment."""
    return self.envs is None or environment in self.envs

  def environment_label(self) -> str:
    """Return a readable environment label."""
    return ','.join(sorted(self.envs)) if self.envs is not None else '*'
