"""The ``@Adapter`` decorator: a label for a class, never a factory."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar

from idunn.domain import AdapterDeclaration, InvalidAdapterError, InvalidPortError, LifecycleEnum
from idunn.internal import DecoratorSupport, PortRegistry
from idunn.util import QualifiedName

T = TypeVar('T', bound=type[Any])


class Adapter:
  """Declare a concrete class as an adapter for a port.
  Applied with arguments: ``@Adapter(SomePort, key=..., lifecycle=..., envs=...)``. Constructing
  the decorator validates the port and freezes an :class:`~idunn.domain.AdapterDeclaration`;
  applying it stamps that declaration onto the class and builds nothing. Checking early means a
  wrong port fails at import, next to the culprit, rather than at first resolve, next to nobody.

  Without ``key`` the adapter is *unkeyed* and answers plain ``@Invert()`` injection. At most one
  unkeyed adapter per port may be active in any environment, so that answer is never a guess.
  With ``key`` it is opt-in: only ``@Invert(keys={...})`` reaches it, so it never competes with
  the plain implementation. ``lifecycle`` takes a :class:`~idunn.LifecycleEnum` or its lowercase
  value, such as ``'singleton'``.
  """

  __slots__ = ('_declaration',)

  def __call__(self, cls: T) -> T:
    """Stamp the declaration onto ``cls`` and hand the class back otherwise untouched.
    Two stamps, two readers. Discovery looks for ``__idunn_adapter__`` in the class's *own*
    ``__dict__``, so an undecorated subclass does not inherit a badge it never wore; the mapper
    reads the declaration through ordinary attribute lookup. A second ``@Adapter`` on the same
    class is refused: the inner declaration would be silently overwritten by the outer one, so one
    of the two lines was always a lie. A subclass may still wear its own badge.
    """
    if not isinstance(cls, type):
      message = f'@Adapter can only be applied to classes: {QualifiedName.of(cls)}'
      raise InvalidAdapterError(message)
    if '__idunn_adapter_declaration__' in vars(cls):
      message = (
        f'@Adapter is applied more than once to {QualifiedName.of(cls)}; one class gets one '
        'declaration. Subclass it to declare another.'
      )
      raise InvalidAdapterError(message)
    cls.__idunn_adapter__ = True
    cls.__idunn_adapter_declaration__ = self._declaration
    return cls

  def __init__(
    self,
    port: type[Any],
    *,
    key: str | None = None,
    lifecycle: LifecycleEnum | str = LifecycleEnum.TRANSIENT,
    envs: Iterable[str] | str | None = None,
  ) -> None:
    """Validate ``port`` now and freeze the normalized declaration this decorator will apply."""
    if not PortRegistry.is_port(port):
      message = f'Adapter port is not marked with @Port: {QualifiedName.of(port)}'
      raise InvalidPortError(message)
    self._declaration: AdapterDeclaration = AdapterDeclaration(
      port=port,
      key=key,
      lifecycle=LifecycleEnum(lifecycle),
      envs=DecoratorSupport.normalize_envs(envs),
    )
