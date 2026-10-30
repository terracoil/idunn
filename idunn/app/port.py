"""The @Port decorator."""

from __future__ import annotations

from typing import Any, TypeVar, runtime_checkable

from idunn.domain import InvalidPortError

T = TypeVar('T', bound=type[Any])


class Port:
  """Mark a ``typing.Protocol`` as an Idunn port.

  Applied bare (``@Port``). Decoration sets ``__idunn_port__`` and makes the Protocol
  ``runtime_checkable`` so a resolved adapter can be verified against it structurally.
  Nothing is constructed, and no ``Port`` instance ever exists: ``__new__`` hands back the
  decorated Protocol itself.
  """

  __slots__ = ()

  # mypy insists __new__ yield a Port; returning the decorated class *is* the decorator.
  def __new__(cls, target: T) -> T:  # type: ignore[misc]
    """Validate that ``target`` is a Protocol, mark it, and return it in place of an instance."""
    if not getattr(target, '_is_protocol', False):
      message = f'@Port can only be applied to Protocol classes: {target.__qualname__}'
      raise InvalidPortError(message)
    target.__idunn_port__ = True
    return runtime_checkable(target)
