"""What one ``@Invert(...)`` was told, frozen at decoration time."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar


@dataclass(frozen=True, slots=True)
class InvertDeclaration:
  """The explicit map and keys handed to ``@Invert``, the counterpart of ``AdapterDeclaration``.
  It travels on the wrapper as ``__idunn_invert__``, which serves two readers: the resolver, so an
  adapter constructor's own keys and map are honoured when it is built as a dependency, and a
  second ``@Invert``, which finds it there and refuses to stack. It says nothing about the
  function's shape, because one ``Invert(...)`` may decorate an ``__init__`` and a plain function
  alike.
  """

  ATTRIBUTE: ClassVar[str] = '__idunn_invert__'

  ports: Mapping[str, type[Any]] = field(default_factory=lambda: MappingProxyType({}))
  keys: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

  @classmethod
  def frozen(
    cls,
    *,
    ports: Mapping[str, type[Any]],
    keys: Mapping[str, str],
  ) -> InvertDeclaration:
    """Copy the caller's mappings behind read-only proxies; later edits to them change nothing."""
    return cls(ports=MappingProxyType(dict(ports)), keys=MappingProxyType(dict(keys)))

  @property
  def names(self) -> frozenset[str]:
    """Every parameter the declaration mentions, mapped or keyed."""
    return frozenset(self.ports).union(self.keys)

  def attach(self, function: Callable[..., Any]) -> None:
    """Stamp this declaration on ``function`` for the resolver and the stacked-``@Invert`` check."""
    setattr(function, self.ATTRIBUTE, self)

  @classmethod
  def of(cls, function: object) -> InvertDeclaration | None:
    """Return the declaration stamped on ``function``, or ``None`` when it was never inverted.
    ``functools.wraps`` copies ``__dict__``, so a declaration survives other decorators on top.
    """
    found: object = getattr(function, cls.ATTRIBUTE, None)
    return found if isinstance(found, cls) else None
