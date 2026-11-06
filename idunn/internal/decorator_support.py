"""Annotation, environment and key helpers for the decorators, the planner and the resolver."""

from collections.abc import Iterable
from typing import Any, get_args

from idunn.util import Environment

from .port_registry import PortRegistry


class DecoratorSupport:
  """Helpers shared by the decorators and the constructor planner.
  One copy of the annotation rule means ``@Invert`` functions and adapter constructors cannot drift
  apart on what counts as an optional port.
  """

  @staticmethod
  def normalize_envs(envs: Iterable[str] | str | None) -> frozenset[str] | None:
    """Normalize ``envs`` to a frozenset of names, or ``None`` for "everywhere".
    Done at decoration, so the names already compare equal to what ``Environment.current``
    produces. An empty collection yields an empty set: an adapter that is active nowhere, which
    is legal if not especially useful.
    """
    if envs is None:
      return None
    raw_vals: Iterable[str] = (envs,) if isinstance(envs, str) else envs
    return frozenset(Environment.normalize(item) for item in raw_vals)

  @staticmethod
  def plain_key(key: str) -> str:
    """Return ``key`` as a plain ``str``, so a ``StrEnum`` member is kept and printed as its value.
    ``str.__str__`` rather than ``str()``: a ``(str, Enum)`` member's ``__str__`` answers
    ``'Grade.GOLD'``, which would quietly stop it matching the ``'gold'`` it equals. Every key, from
    ``@Adapter``, ``@Invert`` or ``Harness.override``, goes through here after its type check, and
    so does ``@Invert(bootstrap=...)``'s root, which discovery would otherwise spell the same way.
    """
    return str.__str__(key)

  @staticmethod
  def port_from_annotation(annotation: Any) -> tuple[type[Any] | None, bool]:
    """Resolve a constructor annotation to ``(port, optional)``.
    A bare ``@Port`` annotation yields ``(port, False)``; ``Port | None`` yields ``(port, True)``,
    the ``| None`` being the signal that a missing adapter is survivable. Anything else yields
    ``(None, False)``.
    """
    args: tuple[Any, ...] = get_args(annotation)
    non_none: tuple[Any, ...] = tuple(arg for arg in args if arg is not type(None))
    result: tuple[type[Any] | None, bool]
    if PortRegistry.is_port(annotation):
      result = (annotation, False)
    elif type(None) in args and len(non_none) == 1 and PortRegistry.is_port(non_none[0]):
      result = (non_none[0], True)
    else:
      result = (None, False)
    return result
