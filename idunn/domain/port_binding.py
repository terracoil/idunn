"""Structured snapshot of one port's adapter bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapter_metadata import AdapterMetadata


@dataclass(frozen=True, slots=True)
class PortBinding:
  """One port, every adapter registered for it, and the one active in an environment.

  Built by :class:`~idunn.internal.InversionMapper` as the single source of truth
  for introspection (it backs ``Idunn().describe()``). ``selected`` is the adapter an
  unkeyed resolve would return in the snapshot environment, or ``None`` when every
  adapter for the port is keyed.
  """

  port: type[Any]
  selected: AdapterMetadata | None
  adapters: tuple[AdapterMetadata, ...]
