"""Internal layer: the catalog, the construction engine, discovery and decorator helpers.
These power the :class:`~idunn.app.Idunn` facade: ``InversionMapper`` (keeper of the catalog),
``InversionResolver`` (construction), ``AutoDiscovery``, the ``BootstrapGate`` behind
``bootstrap()``, ``DecoratorSupport`` and the ``PortRegistry`` of ``@Port`` Protocols. Only classes
used across the package boundary are re-exported; ``InversionValidator``, ``BootstrapFlight`` and
``ReportMerger`` are reached by sibling imports and stay home.
None of this is public API, which is exactly what lets it change without a deprecation notice.
"""

from .auto_discovery import AutoDiscovery
from .bootstrap_gate import BootstrapGate
from .decorator_support import DecoratorSupport
from .inversion_mapper import InversionMapper
from .inversion_resolver import InversionResolver
from .port_registry import PortRegistry

__all__ = [
  'AutoDiscovery',
  'BootstrapGate',
  'DecoratorSupport',
  'InversionMapper',
  'InversionResolver',
  'PortRegistry',
]
