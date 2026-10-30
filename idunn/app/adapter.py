"""The @Adapter decorator."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar

from idunn.domain import AdapterDeclaration, InvalidAdapterError, InvalidPortError, LifecycleEnum
from idunn.internal import DecoratorSupport

T = TypeVar('T', bound=type[Any])


class Adapter:
  """Declare a concrete class as an adapter for a port.

  Applied with arguments (``@Adapter(SomePort, key=..., lifecycle=..., envs=...)``).
  Constructing the decorator validates the port and freezes an
  :class:`~idunn.domain.AdapterDeclaration`; applying it stamps that declaration onto the
  class. Nothing is constructed.

  Without ``key`` the adapter is *unkeyed*: it answers plain ``@Invert`` injection
  — exactly one unkeyed adapter may be active per port in any environment.

  With ``key`` the adapter is *opt-in*: it answers only ``@Invert(keys={...})`` and
  is ignored by unkeyed resolution, so it never competes with the plain
  implementation.
  """

  __slots__ = ('_declaration',)

  def __call__(self, cls: T) -> T:
    """Stamp the frozen declaration onto ``cls`` and return the class unchanged otherwise."""
    if not isinstance(cls, type):
      message = f'@Adapter can only be applied to classes: {cls!r}'
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
    """Validate ``port`` and capture the normalized declaration this decorator will apply."""
    if not getattr(port, '__idunn_port__', False):
      message = f'Adapter port is not marked with @Port: {port.__qualname__}'
      raise InvalidPortError(message)
    self._declaration: AdapterDeclaration = AdapterDeclaration(
      port=port,
      key=key,
      lifecycle=LifecycleEnum(lifecycle),
      envs=DecoratorSupport.normalize_envs(envs),
    )
