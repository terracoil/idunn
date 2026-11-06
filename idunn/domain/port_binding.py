"""A snapshot of one port and its adapters, for introspection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapter_metadata import AdapterMetadata


@dataclass(frozen=True, slots=True)
class PortBinding:
  """One port, every adapter registered for it, and the one an unkeyed resolve would pick.
  Built by :class:`~idunn.internal.InversionMapper` from the same selection the resolver uses, so
  the ``selected`` line of ``Idunn().describe()`` is exactly what an unkeyed ``@Invert()``
  parameter receives. ``selected`` is ``None`` when no unkeyed adapter is active in the snapshot
  environment, which includes the port having no adapters at all.
  """

  port: type[Any]
  selected: AdapterMetadata | None
  adapters: tuple[AdapterMetadata, ...]
