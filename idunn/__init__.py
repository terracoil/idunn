"""Idunn: constructor-time dependency inversion for Python, in three decorators.
Everything a user imports lives here: the decorators (:class:`Port`, :class:`Adapter`,
:class:`Invert`), the :class:`Idunn` container, the :class:`LifecycleEnum` handed to
``@Adapter``, the :class:`ReportMap` that discovery returns, and the :class:`IdunnError` family
for your ``except`` clauses. The rest is plumbing and stays out of sight on purpose: what users
never import, nobody has to keep backward compatible.
"""

from .app import Adapter, Idunn, Invert, Port
from .domain import (
  AdapterNotFoundError,
  DiscoveryError,
  IdunnError,
  InjectionCycleError,
  InvalidAdapterError,
  InvalidPortError,
  LifecycleEnum,
  MissingTypeHintError,
  ReportMap,
)

__all__ = [
  'Adapter',
  'AdapterNotFoundError',
  'DiscoveryError',
  'Idunn',
  'IdunnError',
  'InjectionCycleError',
  'InvalidAdapterError',
  'InvalidPortError',
  'Invert',
  'LifecycleEnum',
  'MissingTypeHintError',
  'Port',
  'ReportMap',
]
