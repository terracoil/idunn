"""The ``@Port`` decorator: turns a Protocol into a contract Idunn will vouch for."""

from __future__ import annotations

from typing import Any, TypeVar, runtime_checkable

from idunn.domain import InvalidPortError
from idunn.internal import PortRegistry

T = TypeVar('T', bound=type[Any])


class Port:
  """Mark a ``typing.Protocol`` as an Idunn port.
  Applied bare (``@Port``). The Protocol is recorded in :class:`~idunn.internal.PortRegistry`
  rather than in its own namespace, because Python 3.11 would count a marker attribute as a
  protocol member and structural adapters would quietly stop matching. It is also made
  ``runtime_checkable`` so every resolved adapter can be checked against it. Only the decorated
  class is a port; subclasses have to earn their own badge. No ``Port`` instance ever exists:
  ``__new__`` hands back the Protocol, which is the whole trick.
  """

  __slots__ = ()

  # mypy insists __new__ yield a Port; returning the decorated class *is* the decorator.
  def __new__(cls, target: T) -> T:  # type: ignore[misc]
    """Check that ``target`` is a Protocol, record it, and return it in place of an instance."""
    # typing.is_protocol is 3.13+; the private flag is the only check available on 3.11.
    if not getattr(target, '_is_protocol', False):
      message = f'@Port can only be applied to Protocol classes: {target.__qualname__}'
      raise InvalidPortError(message)
    PortRegistry.mark(target)
    return runtime_checkable(target)
