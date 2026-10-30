"""The @Port decorator."""

from __future__ import annotations

from typing import Any, TypeVar, runtime_checkable

from idunn.domain import InvalidPortError
from idunn.internal import PortRegistry

T = TypeVar('T', bound=type[Any])


class Port:
  """Mark a ``typing.Protocol`` as an Idunn port.

  Applied bare (``@Port``). Decoration records the Protocol in the
  :class:`~idunn.internal.PortRegistry` (never in the Protocol's own namespace) and makes it
  ``runtime_checkable`` so a resolved adapter can be verified against it structurally. Only the
  decorated class itself is a port; its subclasses are not.
  Nothing is constructed, and no ``Port`` instance ever exists: ``__new__`` hands back the
  decorated Protocol itself.
  """

  __slots__ = ()

  # mypy insists __new__ yield a Port; returning the decorated class *is* the decorator.
  def __new__(cls, target: T) -> T:  # type: ignore[misc]
    """Validate that ``target`` is a Protocol, mark it, and return it in place of an instance."""
    # typing.is_protocol is 3.13+; the private flag is the only check available on 3.11.
    if not getattr(target, '_is_protocol', False):
      message = f'@Port can only be applied to Protocol classes: {target.__qualname__}'
      raise InvalidPortError(message)
    PortRegistry.mark(target)
    return runtime_checkable(target)
