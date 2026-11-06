"""Metadata recorded for each registered adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .lifecycle_enum import LifecycleEnum


@dataclass(frozen=True, slots=True)
class AdapterMetadata:
  """One registered adapter: its declaration plus the class it labels.
  There is no arrival order on purpose. Validation never lets two adapters compete for one slot
  in one environment, and the catalog's insertion order already remembers who came first.
  """

  adapter: type[Any]
  port: type[Any]
  key: str | None
  lifecycle: LifecycleEnum
  envs: frozenset[str] | None

  def environment_label(self) -> str:
    """Return the environments as ``ci,test`` for ``describe()``, or ``*`` for everywhere."""
    return ','.join(sorted(self.envs)) if self.envs is not None else '*'

  def is_available_in(self, environment: str) -> bool:
    """Return whether this adapter is active in ``environment``; ``envs=None`` means always."""
    return self.envs is None or environment in self.envs
