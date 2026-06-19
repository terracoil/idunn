"""Test seams for driving the internal inversion engine.

Resolution and manual registration are no longer on the public ``Idunn`` facade, so
engine-level tests drive :class:`Wiring` (a standalone mapper+resolver), and ``@Invert``
integration tests use :class:`Container` to install adapters into the process singleton.
"""

from __future__ import annotations

from typing import Any

from idunn import Idunn
from idunn.internal import InversionMapper, InversionResolver
from idunn.util import Environment


class Wiring:
  """A standalone engine (own mapper + resolver) mirroring the facade's register/resolve."""

  def __init__(self, environment: str | None = None) -> None:
    """Resolve the environment like the facade does (arg → IDUNN_ENV → local)."""
    self.environment: str = Environment.current(environment).name
    self.mapper: InversionMapper = InversionMapper()
    self.resolver: InversionResolver = InversionResolver(self.mapper)

  def register_adapter(self, adapter: type[Any]) -> bool:
    """Register a ``@Adapter`` class into this engine's catalog."""
    return self.mapper.register_adapter(adapter)

  def register_port(self, port: type[Any]) -> bool:
    """Register a ``@Port`` Protocol into this engine's catalog."""
    return self.mapper.register_port(port)

  def resolve(self, port: type[Any], *, key: str | None = None) -> Any:
    """Resolve a port into an adapter instance for this engine's environment."""
    return self.resolver.resolve(port=port, key=key, environment=self.environment)

  @property
  def ports(self) -> frozenset[type[Any]]:
    """Ports registered in this engine's catalog."""
    return self.mapper.ports


class Container:
  """Installs adapters into the process-wide ``Idunn()`` singleton that ``@Invert`` reads."""

  @staticmethod
  def install(*adapters: type[Any]) -> None:
    """Register each adapter into the singleton's catalog."""
    mapper = Idunn()._mapper
    for adapter in adapters:
      mapper.register_adapter(adapter)
