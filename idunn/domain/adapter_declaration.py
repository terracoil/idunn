"""What ``@Adapter`` captured, frozen at decoration time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .lifecycle_enum import LifecycleEnum


@dataclass(frozen=True, slots=True)
class AdapterDeclaration:
  """The options handed to ``@Adapter``, frozen so nobody edits the label after the fact.
  Kept apart from :class:`AdapterMetadata` because it exists before registration does: it is made
  when the decorator is constructed, before it has seen the class it will label, and long before
  anyone knows the registration order.
  """

  port: type[Any]
  key: str | None
  lifecycle: LifecycleEnum
  envs: frozenset[str] | None
