"""Internal layer: discovery, the inversion engine, and decorator-support helpers.

These power the :class:`~idunn.app.Idunn` facade — the catalog (``InversionMapper``),
the construction engine (``InversionResolver``), bounded autodiscovery (``AutoDiscovery``),
and the ``DecoratorSupport`` helpers. The classes reached across the package boundary are
re-exported here (e.g. for ``idunn.app``); the stateless ``InversionValidator`` is used
only via sibling imports within ``idunn.internal`` and is **not** re-exported. None of
these are part of Idunn's public API — ``idunn/__init__`` deliberately does not expose them.
"""

from .auto_discovery import AutoDiscovery
from .decorator_support import DecoratorSupport
from .inversion_mapper import InversionMapper
from .inversion_resolver import InversionResolver

__all__ = [
  'AutoDiscovery',
  'DecoratorSupport',
  'InversionMapper',
  'InversionResolver',
]
