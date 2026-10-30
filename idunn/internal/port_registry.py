"""Process-wide record of the Protocols decorated with ``@Port``."""

from typing import Any, ClassVar
from weakref import WeakSet


class PortRegistry:
  """Records ``@Port`` Protocols by identity instead of flagging them with an attribute.

  Python 3.11 counts every attribute in a Protocol's own namespace as a protocol member, so a
  marker written onto the Protocol would make structural adapters fail ``isinstance``. Lookup is
  by exact class: an undecorated subclass of a port (an adapter or another Protocol) is not a
  port. Weak references let throwaway ports, such as ones defined inside tests, be collected.
  """

  _ports: ClassVar[WeakSet[type[Any]]] = WeakSet()

  @classmethod
  def is_port(cls, candidate: object) -> bool:
    """Whether ``candidate`` is the very class that ``@Port`` decorated."""
    return isinstance(candidate, type) and candidate in cls._ports

  @classmethod
  def mark(cls, target: type[Any]) -> None:
    """Record ``target`` as a ``@Port`` without touching its namespace."""
    cls._ports.add(target)
