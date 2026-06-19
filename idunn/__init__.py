"""Idunn: tiny constructor-time dependency inversion for Python.

The entire public surface lives here: the three decorators (:func:`Port`,
:func:`Adapter`, :func:`Invert`), the :class:`Idunn` container, the
:class:`LifecycleEnum` you hand to ``@Adapter``, and the :class:`IdunnError`
exception hierarchy you catch. Everything else is internal plumbing.
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
]
