"""The registration catalog as one immutable snapshot, indexed by ``(port, key)``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypeAlias

from .adapter_metadata import AdapterMetadata

SlotKey: TypeAlias = tuple[type[Any], str | None]


@dataclass(frozen=True, slots=True)
class Catalog:
  """Every registered port and adapter, frozen together and replaced whole on each registration.
  Readers grab one snapshot and never lock: a registration builds a new catalog beside the old one
  and swaps it in, so nobody ever sees half a batch. Adapters are indexed by ``(port, key)`` slot,
  which turns "which adapter?" into one dict hit plus an environment filter over a slot that
  validation keeps tiny (at most one adapter per environment). Catalogs compare by value but are
  unhashable, like the mappings inside them; for "did anything change?", compare with ``is``.
  """

  ports: frozenset[type[Any]]
  adapters: Mapping[type[Any], AdapterMetadata]  # insertion order is registration order
  slots: Mapping[SlotKey, tuple[AdapterMetadata, ...]]

  @classmethod
  def empty(cls) -> Catalog:
    """Return the catalog of a freshly reset process: no ports, no adapters, no opinions."""
    return cls.freeze(ports=(), adapters={}, slots={})

  @classmethod
  def freeze(
    cls,
    *,
    ports: Iterable[type[Any]],
    adapters: dict[type[Any], AdapterMetadata],
    slots: dict[SlotKey, tuple[AdapterMetadata, ...]],
  ) -> Catalog:
    """Wrap working dicts read-only; the caller hands them over and must not touch them again.
    Wrapping instead of copying keeps a batch at one copy of the catalog, not two.
    """
    return cls(
      ports=frozenset(ports),
      adapters=MappingProxyType(adapters),
      slots=MappingProxyType(slots),
    )

  def find(self, *, port: type[Any], key: str | None, environment: str) -> AdapterMetadata | None:
    """Return the adapter for ``port`` and ``key`` active in ``environment``, or ``None``.
    Validation forbids two adapters of one slot in overlapping environments, so the first match
    is the only match and no tie-breaker is needed.
    """
    return next(
      (
        metadata
        for metadata in self.slots.get((port, key), ())
        if metadata.is_available_in(environment)
      ),
      None,
    )
